"""Watch whole runs in the Workbench, with fake agents: `make demo`.

Real runs on the live stack — the real workflow on the normal WSL worker, the real Workbench, the
real live terminals — whose agents are fake CLIs that take a few watchable seconds a turn and call
no model, each answer and each lifecycle control pressed as the Workbench's own button in a headless
browser. One run goes the whole way: the engineer plans, the architect sends the plan back once and
passes it, the plan is approved, the engineer builds, the architect verifies, and the change is
merged. One is stopped while its engineer works, and one while it waits for approval; each ends
stopped with its worktree and branch as they were. One is force-terminated when its Stop cannot
finish, because its merge is held in a git hook. Then everything it made is removed, its runs and
the reads of their changes deleted from Temporal too: the Workbench lists every run Temporal retains.

It proves the workflow code the live WSL worker loaded, and `make up` leaves a running worker as it
is: after a change to the workflow, restart the workers onto it (`make down`, then `make up`) before
a pass counts for that change.

It is isolated by its own policy, never by a mode of the production code: a target queue of its
own, polled only by this tool's activity worker, which carries the fakes and registers no workflow,
so no real run can reach a fake agent and the demo's runs cannot reach a real one; a throwaway
repository; and a Workbench of its own on a spare port, whose URL it prints to watch. It needs the
stack up (`make up`) and, for the button presses, Windows' headless Edge.

    uv run --locked python tools/demo.py
"""
import asyncio
import concurrent.futures
import json
import os
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

from temporalio.api.common.v1 import WorkflowExecution  # noqa: E402
from temporalio.api.enums.v1 import TaskQueueType  # noqa: E402
from temporalio.api.workflowservice.v1 import DeleteWorkflowExecutionRequest  # noqa: E402
from temporalio.service import RPCError, RPCStatusCode  # noqa: E402

from app.agents import terminal, trust  # noqa: E402
from app.application import client as runs  # noqa: E402
from app.foundation import paths  # noqa: E402
from app.foundation import policy as P  # noqa: E402
from app.orchestration import workflow as WF  # noqa: E402

TASK = "Add a greeting to the repository, with the test that proves it"

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
        # The deployment's own policy, with a host of the demo's own: its queue is polled by no
        # worker but this tool's, and its ports are free now.
        policy = json.load(open(P.POLICY_FILE, encoding="utf-8"))
        for role in policy["roles"].values():
            role["prompt"] = os.path.join(PKG, role["prompt"])
        host = "demo%s" % os.urandom(3).hex()
        policy["heartbeat_seconds"], policy["timeout_seconds"] = 10, 900
        policy["targets"] = {"wsl": {"host": host, "worktree_root": worktrees,
                                     "terminal_port": free_port()},
                             "windows": {"host": host, "worktree_root": "C:\\Worktrees", "terminal_port": free_port()}}
        policy["workbench_port"] = free_port()
        self.policy = os.path.join(self.tmp, "policy.json")
        with open(self.policy, "w", encoding="utf-8") as fh:
            json.dump(policy, fh)
        self.port = policy["workbench_port"]
        self.queue = P.queue(P.load(self.policy), "wsl")
        # The repositories the demo's Workbench offers: only its own, by name, with its worktrees' folder.
        self.descriptors = os.path.join(self.tmp, "repos.json")
        with open(self.descriptors, "w", encoding="utf-8") as fh:
            json.dump({"demo": {"path": self.repo, "target": "wsl", "worktree_root": os.path.join(worktrees, "demo")}},
                      fh)

    def env(self):
        return dict(os.environ, PATH=self.bin + os.pathsep + os.environ["PATH"], ORCH_POLICY=self.policy,
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

    def start(self):
        run_id = self.api("/api/runs", {"task": TASK, "repo": "demo"})["run_id"]
        self.runs.append(run_id)
        check(bool(run_id), "the Workbench started run %s" % run_id)
        return run_id

    def view(self, run_id):
        return self.api("/api/runs/%s" % run_id)["view"]

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

    def press(self, run_id, label, said):
        """Press the run's button labelled `label` in headless Edge on Windows, as the operator would;
        whether the page then said `said`."""
        script = subprocess.run(["wslpath", "-w", os.path.join(HERE, "demo_press.ps1")],
                                capture_output=True, text=True, check=True).stdout.strip()
        pressed = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
                                  "http://127.0.0.1:%d/" % self.port, run_id, label, said],
                                 capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=300)
        print("  " + (pressed.stdout + pressed.stderr).strip().replace("\n", "\n  "), flush=True)
        return pressed.returncode == 0

    def kept(self, run_id, worktree):
        """Whether the run's worktree and its branch are still there."""
        listed = git(self.repo, "worktree", "list", "--porcelain").splitlines()
        branch = subprocess.run(["git", "-C", self.repo, "rev-parse", "--verify", "--quiet", "refs/heads/" + run_id],
                                capture_output=True).returncode == 0
        return "worktree %s" % worktree in listed and branch

    def agents(self):
        """How many of the demo's fake agents are running."""
        return len(subprocess.run(["pgrep", "-f", self.bin + os.sep], capture_output=True, text=True).stdout.split())

    async def ready(self):
        client = await runs.connect()
        workflows = await runs.polled(client, WF.TASK_QUEUE, TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW)
        check(workflows, "the normal WSL worker runs the workflows, with the code it loaded (`make up` starts it; "
                         "after a workflow change, `make down` first)")
        deadline = time.monotonic() + 90
        while not await runs.polled(client, self.queue, TaskQueueType.TASK_QUEUE_TYPE_ACTIVITY):
            if time.monotonic() > deadline:
                check(False, "the demo's worker polls %s" % self.queue)
            await asyncio.sleep(1)
        check(True, "the demo's worker, and only it, polls %s" % self.queue)

    def run(self):
        step("a demo stack beside the live one: its own worker, queue and Workbench")
        self.setup()
        self.spawn(os.path.join(HERE, "demo.py"), "--worker")
        self.spawn("-m", "app.interfaces.workbench.server")
        asyncio.run(self.ready())
        wait(lambda: self.api("/api/health").get("temporal") == "up", 60, "the demo Workbench answering")
        print("  watch it: http://127.0.0.1:%d/" % self.port, flush=True)

        step("a run started from the Workbench, its agents working in live terminals")
        merged = self.start()
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
        working = self.start()
        self.until(working, lambda view: view["state"] == "running" and view["stage"] == "plan", 120,
                   "the engineer at work")
        check(self.press(working, "Stop run", "stopping"), "the page sent the Stop, with its confirmation")
        view = self.until(working, closed, 120, "the Stop")
        self.hold("hold-turn", False)
        check((view["status"], view["execution"]) == ("STOPPED", "CANCELED"),
              "the run ended stopped, and Temporal says cancelled: %s, %s" % (view["status"], view["execution"]))
        check(wait(lambda: self.agents() == 0, 30, "its agent ending"), "its agent ended with it")
        check(self.kept(working, view["worktree"]), "its worktree and branch are as they were")

        step("a run stopped while it waits for the operator")
        waiting = self.start()
        self.until(waiting, lambda view: view["state"] == "waiting", 300, "the plan's approval")
        check(self.press(waiting, "Stop run", "stopping"), "the page sent the Stop")
        view = self.until(waiting, closed, 120, "the Stop")
        check(view["status"] == "STOPPED", "the run ended stopped")
        check(self.kept(waiting, view["worktree"]), "its worktree and branch are as they were")

        step("a run whose Stop cannot finish, force terminated")
        self.hold("hold-merge")
        stuck = self.start()
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
        view = self.until(stuck, closed, 60, "the termination")
        check(view["execution"] == "TERMINATED", "Temporal ended the run at once")
        check(self.kept(stuck, view["worktree"]), "its worktree and branch are left, as the confirmation says")

        step("the runs deleted from Temporal, so the Workbench no longer lists them")

        def listed():
            shown = {run["run_id"] for run in self.api("/api/runs")["runs"]}
            return [run_id for run_id in self.runs if run_id in shown]
        check(listed() == self.runs, "the Workbench lists the demo's %d finished runs" % len(self.runs))
        removed, kept = asyncio.run(self.forget())
        check(set(self.runs) <= set(removed), "Temporal held them and %d read(s) of their changes, and deleted them"
              % (len(removed) - len(self.runs)))
        check(not kept, "Temporal holds none of them now%s" % (": %s" % ", ".join(kept) if kept else ""))
        check(wait(lambda: not listed(), 30, "the Workbench dropping them"), "the Workbench no longer lists them")

    def made(self):
        """The listing's query for every execution the demo made in Temporal: its runs, and each read of
        a run's change the page started, which `client.review_diff` names after the run."""
        return " OR ".join("WorkflowId = '%s' OR WorkflowId STARTS_WITH 'diff-%s-'" % (run_id, run_id)
                           for run_id in self.runs)

    async def forget(self):
        """Delete every execution the demo made from Temporal — an open run is terminated by its
        deletion, which Temporal completes on its own time — and wait up to a minute for it to finish.
        Returns the ids deleted, and those Temporal still holds, by themselves or in its listing."""
        client = await runs.connect()
        found = {execution.id: execution.run_id async for execution in client.list_workflows(self.made())}
        for run_id in self.runs:
            try:
                # Each run by its own id as well: one that only just started may not be listed yet.
                found.setdefault(run_id, (await client.get_workflow_handle(run_id).describe()).run_id)
            except RPCError as error:
                if error.status != RPCStatusCode.NOT_FOUND:
                    raise
        for workflow_id, execution in found.items():
            try:
                await client.workflow_service.delete_workflow_execution(DeleteWorkflowExecutionRequest(
                    namespace=client.namespace,
                    workflow_execution=WorkflowExecution(workflow_id=workflow_id, run_id=execution)))
            except RPCError as error:
                if error.status != RPCStatusCode.NOT_FOUND:
                    raise
        deadline = time.monotonic() + 60
        while True:
            kept = await self._held(client, found)
            if not kept or time.monotonic() > deadline:
                self.forgotten = not kept
                return sorted(found), kept
            await asyncio.sleep(1)

    async def _held(self, client, ids):
        listed = {execution.id async for execution in client.list_workflows(self.made())}
        described = set()
        for workflow_id in ids:
            try:
                await client.get_workflow_handle(workflow_id).describe()
                described.add(workflow_id)
            except RPCError as error:
                if error.status != RPCStatusCode.NOT_FOUND:
                    raise
        return sorted(listed | described)

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
        # The worker goes before anything it holds: a held merge's git, and a turn still running, which
        # writes into its run's folder.
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


async def activity_worker():
    """The demo's worker: this policy's own queue, the real activities, no workflows."""
    from temporalio.worker import Worker
    from app.application import activities
    policy = P.load()
    client = await runs.connect()
    terminal.serve(policy["targets"]["wsl"]["terminal_port"], policy["workbench_port"])
    await Worker(client, task_queue=P.queue(policy, "wsl"), activities=activities.Activities().all(),
                 activity_executor=concurrent.futures.ThreadPoolExecutor(max_workers=8)).run()


def interrupted(*_):
    # The first Ctrl-C ends the demo; a second — pressed again, or passed on by `uv run`, whose child
    # gets a process group's SIGINT twice (measured) — must not cut its cleanup short.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    raise KeyboardInterrupt


def main():
    if sys.argv[1:] == ["--worker"]:
        asyncio.run(activity_worker())
        return 0
    signal.signal(signal.SIGINT, interrupted)
    demo = Demo()
    try:
        demo.run()
    finally:
        left = demo.cleanup()
    if left:
        raise SystemExit("demo failed: it left behind %s" % "; ".join(left))
    print("\nDEMO PASSED: runs %s — watched in the Workbench, answered, stopped and force-terminated from its "
          "buttons, and removed" % ", ".join(demo.runs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
