"""Watch whole runs in the Workbench, with fake agents: `make demo`.

Real runs on the real workflow, the real Workbench and the real live terminals, whose agents are fake
CLIs that take a few watchable seconds a turn and call no model; every answer and every control is
pressed as the Workbench's own button in a headless browser. It is a stack of its own beside the live
one: its own Workbench, and its own worker — the real worker, started and stopped from that Workbench
through the stack's one owner — on queues of its own, sharing only the live Temporal.

One run goes the whole way: the engineer plans, the architect sends the plan back once and passes it,
the plan is approved, the engineer builds, the architect verifies, and the change is merged. One is
stopped while its engineer works, and one while it waits for approval — sent back first with a note
typed into the page, which reaches the engineer's next plan; each ends stopped with its worktree and
branch as they were. One is force-terminated when its Stop cannot finish, because its
merge is held in a git hook — and once let go, with its worker still running, that merge still lands:
termination cannot stop what a host is already doing. Then the worker goes down while an engineer
works: its stage's settings go with it, the run says it is blocked by it, the run's own button starts
it again, and the failed stage is continued. A restart of the worker while a run waits leaves the run
waiting, and that run is discarded. What the run stopped at its approval kept is removed. The demo's
worker is stopped from its Workbench, and everything it made is removed, its runs, the reads of their
changes and the removal from Temporal too: the Workbench lists every run Temporal retains.

It is isolated by its own policy, never by a mode of the production code: a workflow queue and target
queue of its own, polled only by its own worker, which carries the fakes, so no real run can reach a
fake agent and the demo's runs cannot reach a real one; a throwaway repository; and a Workbench of its
own on a spare port, whose URL it prints to watch. It proves the workflow code this checkout holds.
It needs Temporal up (`make up`) and, for the button presses, Windows' headless Edge.

    uv run --locked python tools/demo.py
"""
import asyncio
import glob
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
TESTS = os.path.join(PKG, "tests")
sys.path[:0] = [PKG]
# The suite's own helpers, behind everything else so none of their names can stand in for another.
sys.path.append(TESTS)

from app.agents import terminal, trust  # noqa: E402
from app.application import client as runs  # noqa: E402
from app.application import stack  # noqa: E402
from app.foundation import paths  # noqa: E402
from app.foundation import policy as P  # noqa: E402
from app.observability import telemetry  # noqa: E402
import temporal_cleanup  # noqa: E402

# Each run's task says what it shows, and gives its plan a file of its own: a plan is named by its
# run's task and start minute, and two runs' plans must not meet on the base branch.
TASKS = {"merged": "Add a greeting to the repository, with the test that proves it",
         "working": "Stop me at work: add a greeting to the repository",
         "waiting": "Stop me at my approval: add a greeting to the repository",
         "stuck": "Hold my merge, then terminate me: add a greeting to the repository",
         "down": "Lose my worker at work: add a greeting to the repository",
         "discarded": "Restart my worker, then discard me: add a greeting to the repository"}

# The demo's agents, speaking the turn contract the runner expects through `fake_cli`, as the
# acceptance's do — and taking a few seconds a turn so that a person can watch them work.
FAKE = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, re, sys, time
    sys.path.insert(0, "{{TESTS}}")
    import fake_cli

    argv = sys.argv[1:]
    prompt = argv[-1]
    brain = "codex" if "codex" in os.path.basename(sys.argv[0]) else "claude"
    complete = fake_cli.completer(brain, argv, prompt)
    state = os.environ["DEMO_STATE"]

    def say(*lines):
        for line in lines:
            fake_cli.draw(line)
            time.sleep(1.5)

    # A turn the demo holds at work, so that a Stop reaches an agent mid-turn.
    while os.path.exists(os.path.join(state, "hold-turn")):
        say("still working...")

    if brain == "codex":
        if "Independently assess" in prompt:
            counted = os.path.join(state, "assessments")
            rounds = (int(open(counted).read()) if os.path.exists(counted) else 0) + 1
            open(counted, "w").write(str(rounds))
            say("reading the plan and the repository...", "checking the plan against the task...")
            verdict = ("PATCH", "Required finding - the plan does not name the test that proves it. "
                                "Smallest safe fix: name the test.") if rounds == 1 else (
                       "PASS", "Direction: add greeting.txt and its test.\\nBlast radius: one new file.")
        else:
            say("reading the change...", "comparing it with the approved plan...")
            verdict = ("PASS", "The change is the approved plan.")
        message = json.dumps({"verdict": verdict[0], "feedback": verdict[1]})
    else:
        todo = re.search(r"write the reviewable todo to exactly: (\\S+)", prompt)
        if "Implement the approved todo" in prompt:
            say("implementing the approved plan...", "running the test...")
            open("greeting.txt", "w").write("hello\\n")
        elif todo:
            say("reading the repository...", "writing the plan...")
            os.makedirs(os.path.dirname(todo.group(1)), exist_ok=True)
            open(todo.group(1), "w").write("**Status:** DRAFT\\n# Add a greeting\\n")
            open(os.path.join(state, "todo"), "w").write(todo.group(1))
        else:
            say("reading the architect's finding...", "naming the test in the plan...")
            open(open(os.path.join(state, "todo")).read(), "a").write("Test: greeting.txt says hello.\\n")
        message = "done"
    complete(message)
    time.sleep(0.2)
""").replace("{{TESTS}}", TESTS)

# The demo repository's one hook: the commit a merge makes waits here while the demo holds it, so a
# Stop meets a git side effect it must not cut off.
HOLD_MERGE = textwrap.dedent("""\
    #!/bin/sh
    while [ -e "$DEMO_STATE/hold-merge" ]; do sleep 1; done
""")


def step(text):
    print("\n== %s" % text, flush=True)


def check(condition, text):
    print("  %s %s" % ("PASS" if condition else "FAIL", text), flush=True)
    if not condition:
        raise SystemExit("demo failed: %s" % text)


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def git(path, *args):
    return subprocess.run(["git", "-C", path] + list(args), capture_output=True, text=True, check=True).stdout


def wait(predicate, seconds, what):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            found = predicate()
        except OSError:
            # Not listening yet, or not answering this once: look again.
            found = None
        if found:
            return found
        time.sleep(1)
    raise SystemExit("demo failed: %s did not happen within %ds" % (what, seconds))


def alive(pid):
    return telemetry._alive(pid)


def closed(view):
    return view["state"] == "closed"


class Demo:
    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="orch-demo-")
        self.repo = os.path.join(self.tmp, "demo-repository")
        self.bin = os.path.join(self.tmp, "bin")
        self.state = os.path.join(self.tmp, "state")
        self.hooks = os.path.join(self.tmp, "hooks")
        self.processes = []
        self.runs = []
        self.forgotten = False
        self.policy = None
        self.said = ""

    def setup(self):
        worktrees = os.path.join(self.tmp, "worktrees")
        for folder in (self.repo, self.bin, self.state, self.hooks, os.path.join(worktrees, "demo")):
            os.makedirs(folder)
        git(self.repo, "init", "-q", "-b", "develop")
        for key, value in (("user.name", "demo"), ("user.email", "demo@localhost"), ("commit.gpgsign", "false"),
                           ("core.hooksPath", self.hooks)):
            git(self.repo, "config", key, value)
        os.makedirs(os.path.join(self.repo, "todo", "done"))
        for name, body in (("README.md", "A throwaway repository for the Workbench demo.\n"),
                           (os.path.join("todo", "done", ".keep"), "")):
            with open(os.path.join(self.repo, name), "w") as fh:
                fh.write(body)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")
        for path, body in ((os.path.join(self.bin, "claude"), FAKE), (os.path.join(self.bin, "codex"), FAKE),
                           (os.path.join(self.hooks, "pre-commit"), HOLD_MERGE)):
            with open(path, "w") as fh:
                fh.write(body)
            os.chmod(path, 0o755)
        # The deployment's own policy, with a host and a workflow queue of the demo's own: its queues are
        # polled by no worker but the demo's, and its ports are free now.
        policy = json.load(open(P.POLICY_FILE, encoding="utf-8"))
        for role in policy["roles"].values():
            role["prompt"] = os.path.join(PKG, role["prompt"])
        host = "demo%s" % os.urandom(3).hex()
        policy["heartbeat_seconds"], policy["timeout_seconds"] = 10, 900
        policy["workflow_queue"] = "orchestration:%s" % host
        policy["targets"] = {"wsl": {"host": host, "worktree_root": worktrees,
                                     "terminal_port": free_port()},
                             "windows": {"host": host, "worktree_root": "C:\\Worktrees", "terminal_port": free_port()}}
        policy["workbench_port"] = free_port()
        path = os.path.join(self.tmp, "policy.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(policy, fh)
        self.policy_path, self.policy = path, P.load(path)
        self.port = policy["workbench_port"]
        # The repositories the demo's Workbench offers: only its own, by name, with its worktrees' folder.
        self.descriptors = os.path.join(self.tmp, "repos.json")
        with open(self.descriptors, "w", encoding="utf-8") as fh:
            json.dump({"demo": {"path": self.repo, "target": "wsl", "worktree_root": os.path.join(worktrees, "demo")}},
                      fh)

    def env(self):
        # The Workbench's environment is the one the worker it starts inherits: the fakes first on its PATH.
        return dict(os.environ, PATH=self.bin + os.pathsep + os.environ["PATH"], ORCH_POLICY=self.policy_path,
                    ORCH_REPOS=self.descriptors, DEMO_STATE=self.state, LANGFUSE_TRACING_ENVIRONMENT="fixture")

    def spawn(self, *argv):
        log = open(os.path.join(self.tmp, "%s.log" % len(self.processes)), "a")
        process = subprocess.Popen([sys.executable] + list(argv), cwd=PKG, env=self.env(), stdout=log,
                                   stderr=log, start_new_session=True)
        self.processes.append(process)
        return process

    def hold(self, what, held=True):
        """Hold, or let go of, what the fakes and the hook wait on: `hold-turn` or `hold-merge`."""
        path = os.path.join(self.state, what)
        if held:
            open(path, "w").close()
        elif os.path.exists(path):
            os.remove(path)

    def api(self, path, body=None):
        request = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.port, path), method="POST" if body is not None else "GET",
            data=json.dumps(body).encode() if body is not None else None,
            headers={"X-Workbench-Token": terminal.token(), "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())

    def start(self, kind):
        """A run started as the operator starts one: its task typed into the page's form, Start pressed."""
        pressed = self.press("start", TASKS[kind], "started ")
        started = re.search(r"started ([\w-]+)", self.said)
        if started:
            self.runs.append(started.group(1))
        check(pressed and started, "the task typed into the Workbench's form, and Start pressed")
        run_id = started.group(1)
        # Where the run's own status says it runs: a run on the live workflow queue would run there.
        queue = wait(lambda: self.api("/api/runs/%s" % run_id).get("workflow_queue"), 60, "the run's status")
        check(queue == P.workflow_queue(self.policy),
              "the Workbench started run %s, on the demo's own workflow queue, %s" % (run_id, queue))
        return run_id

    def view(self, run_id):
        return self.api("/api/runs/%s" % run_id)["view"]

    def worker(self):
        """The demo's worker as its Workbench reads it: its state and its pid."""
        part = next(part for part in self.api("/api/health")["components"] if part["name"] == "wsl")
        return part["state"], part["pid"]

    def until(self, run_id, reached, seconds, what):
        """The run's view once `reached` holds of it, read once a second; a run that failed or
        ended instead fails the demo at once, with the run's own lines."""
        def probe():
            view = self.view(run_id)
            if reached(view):
                return view
            if view["state"] in ("failed", "closed"):
                lines = self.api("/api/runs/%s" % run_id)["lines"]
                raise SystemExit("demo failed: waiting for %s, the run is %s: %s\n  %s" % (
                    what, view["state"], view["failure"] or view["status"], "\n  ".join(lines[-12:])))
            return None
        return wait(probe, seconds, what)

    def press(self, run_id, label, said, note=""):
        """Press the button labelled `label` in headless Edge on Windows, as the operator would — the run's,
        or the stack panel's for run `stack`, with `note` typed as the answer's words; whether the page's
        word on it then begins with `said`."""
        script = subprocess.run(["wslpath", "-w", os.path.join(HERE, "demo_press.ps1")],
                                capture_output=True, text=True, check=True).stdout.strip()
        pressed = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
                                  "http://127.0.0.1:%d/" % self.port, run_id, label, said] + ([note] if note else []),
                                 capture_output=True, stdin=subprocess.DEVNULL, timeout=420,
                                 # What the page said passes through the Windows console's own code page.
                                 encoding="utf-8", errors="replace")
        self.said = (pressed.stdout + pressed.stderr).strip()
        print("  " + self.said.replace("\n", "\n  "), flush=True)
        return pressed.returncode == 0

    def asked(self, *words):
        """Whether the page asked, at the last press, a question holding every one of `words`."""
        return any(all(word in line for word in words)
                   for line in self.said.splitlines() if line.startswith("it asked: "))

    def kept(self, run_id, worktree):
        """Whether the run's worktree and its branch are still there."""
        listed = git(self.repo, "worktree", "list", "--porcelain").splitlines()
        branch = subprocess.run(["git", "-C", self.repo, "rev-parse", "--verify", "--quiet", "refs/heads/" + run_id],
                                capture_output=True).returncode == 0
        return "worktree %s" % worktree in listed and branch

    def removal(self, run_id):
        """The removal of what `run_id` kept, as Temporal lists it by its own id; None when it holds none."""
        async def read():
            return await runs.execution(await runs.connect(), "remove-%s" % run_id)
        return asyncio.run(read())

    def agents(self):
        """How many of the demo's fake agents are running."""
        return len(subprocess.run(["pgrep", "-f", self.bin + os.sep], capture_output=True, text=True).stdout.split())

    def settings_of(self, pid):
        """A traced Claude stage's settings in worker `pid` — the trace store's key in them — named as
        `harness_settings` names them in the worker's temporary folder. The demo places one: this
        machine traces a stage only when Langfuse is configured, and the suite proves the real one."""
        folder = tempfile.mkdtemp(prefix="%s%d-" % (telemetry.SETTINGS_DIR_PREFIX, pid), dir="/tmp")
        with open(os.path.join(folder, telemetry.SETTINGS_FILE), "w") as fh:
            json.dump({"stands for": "a traced stage's settings, with the trace store's key"}, fh)
        return folder

    def run(self):
        step("a demo stack beside the live one: its own Workbench, and its own worker started from it")
        self.setup()
        self.spawn("-m", "app.interfaces.workbench.server")
        wait(lambda: self.api("/api/health").get("temporal") == "up", 60,
             "the demo Workbench answering, with Temporal up (`make up`)")
        print("  watch it: http://127.0.0.1:%d/" % self.port, flush=True)
        check(self.worker()[0] == "down", "its worker is down before it is started")
        check(self.press("stack", "Start WSL worker", "done: start WSL worker"),
              "Start pressed in the stack panel; the owner started the worker and it polls")
        state, pid = self.worker()
        check(state == "up" and alive(pid), "the Workbench reads the worker up, pid %s" % pid)
        scope = "/orchestra-%s.scope" % stack.worker_name(self.policy, "wsl")
        with open("/proc/%d/cgroup" % pid) as fh:
            check(scope in fh.read(), "in a systemd scope of its own, %s, which no restart of a Workbench takes"
                  % scope[1:])

        step("a run started from the Workbench, its agents working in live terminals")
        merged = self.start("merged")
        view = self.until(merged, lambda view: view["state"] == "waiting", 300, "the plan's approval")
        timeline = self.api("/api/runs/%s" % merged)["timeline"]
        verdicts = [entry.get("verdict") for entry in timeline if entry.get("verdict")]
        check(verdicts == ["PATCH", "PASS"], "the architect sent the plan back once, then passed it: %s" % verdicts)
        check(view["stop"]["reason"] == "approval" and "approve" in view["actions"],
              "the run waits for approval, and says so")

        step("the plan approved by pressing the Workbench's own button")
        check(self.press(merged, "Approve", "answered: approve"), "the page sent the answer, and the workflow took it")
        self.until(merged, lambda view: view["state"] == "waiting" and view["stop"]["reason"] == "final", 300,
                   "the final gate")
        check(True, "the engineer built and the architect verified")

        step("the change merged by pressing Merge")
        check(self.press(merged, "Merge", "answered: merge"), "the page sent the answer, with its confirmation")
        view = self.until(merged, closed, 300, "the merge")
        check(view["status"] == "MERGED", "the run ended merged")
        check("greeting.txt" in git(self.repo, "ls-tree", "--name-only", "develop"),
              "the base branch holds the change")

        step("a run stopped while its engineer works")
        self.hold("hold-turn")
        working = self.start("working")
        self.until(working, lambda view: view["state"] == "running" and view["stage"] == "plan", 120,
                   "the engineer at work")
        check(self.press(working, "terminal:engineer", "still working"),
              "the page's own terminal shows the engineer at work, live from its host")
        check(self.press(working, "Stop run", "stopping") and self.asked("Stop this run?", "stay as they are"),
              "the page asked first, then sent the Stop")
        view = self.until(working, closed, 120, "the Stop")
        self.hold("hold-turn", False)
        check((view["status"], view["execution"]) == ("STOPPED", "CANCELED"),
              "the run ended stopped, and Temporal says cancelled: %s, %s" % (view["status"], view["execution"]))
        check(wait(lambda: self.agents() == 0, 30, "its agent ending"), "its agent ended with it")
        check(self.kept(working, view["worktree"]), "its worktree and branch are as they were")

        step("a run sent back with the operator's words, then stopped while it waits for the operator")
        waiting = self.start("waiting")
        first = self.until(waiting, lambda view: view["state"] == "waiting", 300, "the plan's approval")["stop"]
        # The page sends only words the operator wrote: a revise with none reaches the workflow with none.
        check(self.press(waiting, "Revise", "not accepted") and "needs the feedback" in self.said,
              "Revise pressed with no note: the workflow refused it, needing your words")
        note = "Name the file greeting.txt, and say which test proves it."
        check(self.press(waiting, "Revise", "answered: revise", note), "Revise pressed, with a note typed beside it")
        self.until(waiting, lambda view: view["state"] == "waiting" and view["stop"]["id"] != first["id"], 300,
                   "the plan again, and its approval")
        with open(os.path.join(paths.RUNTIME_ROOT, waiting, "logs", "plan-e2-1.prompt"), encoding="utf-8") as fh:
            check(note in fh.read(), "the note reached the engineer's next plan, word for word")
        check(self.press(waiting, "Stop run", "stopping"), "the page sent the Stop")
        waited = self.until(waiting, closed, 120, "the Stop")
        check(waited["status"] == "STOPPED", "the run ended stopped")
        check(self.kept(waiting, waited["worktree"]), "its worktree and branch are as they were")

        step("a run whose Stop cannot finish, force terminated")
        self.hold("hold-merge")
        stuck = self.start("stuck")
        self.until(stuck, lambda view: view["state"] == "waiting", 300, "the plan's approval")
        check(self.press(stuck, "Approve", "answered: approve"), "approved")
        self.until(stuck, lambda view: view["state"] == "waiting" and view["stop"]["reason"] == "final", 300,
                   "the final gate")
        check(self.press(stuck, "Merge", "answered: merge"), "merge pressed; its commit is held in the hook")
        check(self.press(stuck, "Stop run", "stopping"), "the page sent the Stop")
        self.until(stuck, lambda view: view["state"] == "stopping", 60, "the Stop heard")
        time.sleep(5)
        view = self.view(stuck)
        check((view["state"], view["stage"]) == ("stopping", "merge"),
              "the Stop waits for the merge, which it never cuts off: %s, %s" % (view["state"], view["stage"]))
        check(self.press(stuck, "Force terminate", "terminated"), "the page sent the force terminate, confirmed")
        check(self.asked("Force terminate", "a merge", "may still change the repository"),
              "and its question said a merge already running goes on and may still change the repository")
        view = self.until(stuck, closed, 60, "the termination")
        check(view["execution"] == "TERMINATED", "Temporal closed the run at once")
        check(self.kept(stuck, view["worktree"]), "its worktree and branch are there, the merge still held")

        step("the held merge let go, with the worker still running: termination did not stop it")
        before = git(self.repo, "rev-parse", "develop").strip()
        plan = os.path.splitext(os.path.basename(self.api("/api/runs/%s" % stuck)["state"]["plan"]))[0]
        self.hold("hold-merge", False)
        wait(lambda: git(self.repo, "rev-parse", "develop").strip() != before, 60, "the held merge going on")
        subject = git(self.repo, "log", "-1", "--format=%s", "develop").strip()
        check(subject == "Merge %s" % plan,
              "the merge landed on the base branch after its run had closed, as the confirmation warns: %r" % subject)
        check(wait(lambda: not self.kept(stuck, view["worktree"]), 30, "the merge's own cleanup"),
              "and its own cleanup took the run's worktree and branch")

        step("the worker goes down while an engineer works, and takes its stage's settings with it")
        self.hold("hold-turn")
        down = self.start("down")
        self.until(down, lambda view: view["state"] == "running" and view["stage"] == "plan", 120,
                   "the engineer at work")
        _, pid = self.worker()
        settings = self.settings_of(pid)
        check(os.path.isdir(settings), "worker %d holds a stage's settings: %s" % (pid, settings))
        check(self.press("stack", "Stop WSL worker", "done: stop WSL worker"), "Stop pressed in the stack panel, confirmed")
        check(self.asked("Stopping the WSL worker ends any agent at work on it"),
              "and its question said what the stop interrupts")
        check(not alive(pid), "the worker is gone")
        check(not os.path.exists(settings) and not glob.glob("/tmp/%s%d-*" % (telemetry.SETTINGS_DIR_PREFIX, pid)),
              "and its stages' settings, the trace store's key in them, went with its stop, not at its next start")
        check(wait(lambda: self.agents() == 0, 30, "its agent ending"), "its engineer's agent ended with it")
        self.hold("hold-turn", False)
        time.sleep(3)
        check(self.worker()[0] == "down", "it stays down: the Workbench reads it down")
        view = self.view(down)
        check(view["blocked_by"] == ["wsl"], "the run says it is blocked by the WSL worker: %s" % view["blocked_by"])

        step("the worker started again from the blocked run's own button, and the run carried on")
        check(self.press(down, "Start the WSL worker", "done: start WSL worker"), "the run's own button started it")
        check(self.worker()[0] == "up", "the Workbench reads it up")
        view = self.until(down, lambda view: view["state"] == "failed", 120, "the lost stage stopping for the operator")
        check(True, "its stage ended with the worker, and waits for the operator: %s"
              % (view["failure"] or "").splitlines()[0])
        check(self.press(down, "Continue", "answered: continue"), "Continue pressed: the stage runs once more")
        self.until(down, lambda view: view["state"] == "waiting" and view["stop"]["reason"] == "approval", 300,
                   "the plan's approval")
        check(self.press(down, "Stop run", "stopping"), "and the run stopped at its approval")
        self.until(down, closed, 120, "the Stop")

        step("a worker restarted while a run waits: the run still waits, and is discarded")
        discarded = self.start("discarded")
        self.until(discarded, lambda view: view["state"] == "waiting", 300, "the plan's approval")
        _, before = self.worker()
        check(self.press("stack", "Restart WSL worker", "done: restart WSL worker"), "Restart pressed, confirmed")
        state, pid = self.worker()
        check(state == "up" and pid != before and not alive(before), "a new worker, pid %s, polls" % pid)
        view = self.until(discarded, lambda view: view["state"] == "waiting", 60, "the run read again")
        check(view["stop"]["reason"] == "approval", "the run still waits at its approval")
        check(self.press(discarded, "Approve", "answered: approve"), "approved")
        view = self.until(discarded, lambda view: view["state"] == "waiting" and view["stop"]["reason"] == "final",
                          300, "the final gate")
        check(self.press(discarded, "Discard", "answered: discard"), "Discard pressed, confirmed")
        check(self.asked("Discard deletes the worktree and its branch"), "and its question said what it deletes")
        view = self.until(discarded, closed, 120, "the discard")
        check(view["status"] == "DISCARDED" and not self.kept(discarded, view["worktree"]),
              "the run ended discarded, its worktree and branch gone")

        step("what a stopped run kept, removed from the Workbench")
        check(self.kept(waiting, waited["worktree"]), "the run stopped at its approval still keeps its work")
        check(self.press(waiting, "Remove worktree and branch", "removed"), "Remove pressed on it, confirmed")
        check(self.asked("Remove deletes run %s's worktree and its branch" % waiting),
              "and its question named the run whose work it deletes")
        check(not self.kept(waiting, waited["worktree"]), "its worktree and branch are gone, by its host's git")
        removal = self.removal(waiting) or {}
        check((removal.get("execution"), removal.get("task_queue")) == ("COMPLETED", P.workflow_queue(self.policy)),
              "through a workflow of its own, remove-%s, on the demo's own workflow queue" % waiting)

        step("the demo's worker stopped from its Workbench")
        _, pid = self.worker()
        check(self.press("stack", "Stop WSL worker", "done: stop WSL worker"), "Stop pressed, confirmed")
        check(not alive(pid) and self.worker()[0] == "down", "the worker is gone, and the Workbench says so")

        step("the runs deleted from Temporal, so the Workbench no longer lists them")

        def listed():
            shown = {run["run_id"] for run in self.api("/api/runs")["runs"]}
            return [run_id for run_id in self.runs if run_id in shown]
        check(listed() == self.runs, "the Workbench lists the demo's %d finished runs" % len(self.runs))
        removed, kept = asyncio.run(self.forget())
        check(set(self.runs) <= set(removed), "Temporal held them and %d read(s) and removal(s) of their work, "
              "and deleted them" % (len(removed) - len(self.runs)))
        check(not kept, "Temporal holds none of them now%s" % (": %s" % ", ".join(kept) if kept else ""))
        check(self.removal(waiting) is None, "nor the removal of what the stopped run kept, read by its own id")
        check(wait(lambda: not listed(), 30, "the Workbench dropping them"), "the Workbench no longer lists them")

    async def forget(self):
        """Delete the demo's runs, the reads of their changes and the removals of their work, from Temporal."""
        removed, kept = await temporal_cleanup.delete_runs(await runs.connect(), self.runs)
        self.forgotten = not kept
        return removed, kept

    def cleanup(self):
        """Remove whatever the demo made that is still there; returns what could not be removed."""
        # It is bounded, and nothing may cut it short.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        left = []
        if self.runs and not self.forgotten:
            try:
                left += ["%s in Temporal" % workflow_id for workflow_id in asyncio.run(self.forget())[1]]
            except Exception as error:              # noqa: BLE001 - reported as left behind
                left.append("runs %s in Temporal (%s)" % (", ".join(self.runs), error))
        # Its worker, through the owner that started it, before anything the worker holds: a held merge's
        # git, and a turn still running, which writes into its run's folder.
        if self.policy is not None:
            try:
                [stopped] = stack.stop(self.policy)
                if not stopped["ok"]:
                    left.append("its worker (%s)" % stopped["said"])
            except Exception as error:              # noqa: BLE001 - reported as left behind
                left.append("its worker (%s)" % error)
            name = os.path.join(paths.RUNTIME_ROOT, stack.worker_name(self.policy, "wsl"))
            for suffix in (".pid", ".log"):
                if os.path.exists(name + suffix):
                    os.remove(name + suffix)
        for process in reversed(self.processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        for run_id in self.runs:
            shutil.rmtree(os.path.join(paths.RUNTIME_ROOT, run_id), ignore_errors=True)
        trust.forget(self.repo, ["claude", "codex"])
        shutil.rmtree(self.tmp, ignore_errors=True)
        if left:
            print("\n  LEFT BEHIND: %s" % "; ".join(left), flush=True)
        else:
            print("\n  removed: the demo's %sworker, Workbench, repository and trust records"
                  % ("runs from Temporal, its " if self.runs else ""), flush=True)
        return left


def interrupted(*_):
    # The first Ctrl-C ends the demo; a second — pressed again, or passed on by `uv run`, whose child
    # gets a process group's SIGINT twice (measured) — must not cut its cleanup short.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    raise KeyboardInterrupt


def main():
    signal.signal(signal.SIGINT, interrupted)
    demo = Demo()
    try:
        demo.run()
    finally:
        left = demo.cleanup()
    if left:
        raise SystemExit("demo failed: it left behind %s" % "; ".join(left))
    print("\nDEMO PASSED: runs %s — watched in the Workbench, answered, stopped, force-terminated, blocked by a "
          "worker brought back, discarded and their kept work removed, all from its buttons, and removed"
          % ", ".join(demo.runs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
