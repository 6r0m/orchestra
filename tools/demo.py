"""Watch a whole run in the Workbench, with fake agents: `make demo`.

A real run on the live stack — the real workflow on the normal WSL worker, the real Workbench,
the real live terminals — whose agents are fake CLIs that take a few watchable seconds a turn and
call no model. The engineer plans, the architect sends the plan back once and passes it, the plan
is approved by pressing the Workbench's own button in a headless browser, the engineer builds, the
architect verifies, and the change is merged by pressing Merge. Then everything it made is removed.

It is isolated by its own policy, never by a mode of the production code: a target queue of its
own, polled only by this tool's activity worker, which carries the fakes and registers no workflow,
so no real run can reach a fake agent and the demo run cannot reach a real one; a throwaway
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

from temporalio.api.enums.v1 import TaskQueueType  # noqa: E402

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


class Demo:
    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="orch-demo-")
        self.repo = os.path.join(self.tmp, "demo-repository")
        self.bin = os.path.join(self.tmp, "bin")
        self.state = os.path.join(self.tmp, "state")
        self.processes = []
        self.run_id = None

    def setup(self):
        worktrees = os.path.join(self.tmp, "worktrees")
        for folder in (self.repo, self.bin, self.state, os.path.join(self.tmp, "no-hooks"),
                       os.path.join(worktrees, "demo")):
            os.makedirs(folder)
        git(self.repo, "init", "-q", "-b", "develop")
        for key, value in (("user.name", "demo"), ("user.email", "demo@localhost"), ("commit.gpgsign", "false"),
                           ("core.hooksPath", os.path.join(self.tmp, "no-hooks"))):
            git(self.repo, "config", key, value)
        os.makedirs(os.path.join(self.repo, "todo", "done"))
        for name, body in (("README.md", "A throwaway repository for the Workbench demo.\n"),
                           (os.path.join("todo", "done", ".keep"), "")):
            with open(os.path.join(self.repo, name), "w") as fh:
                fh.write(body)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")
        for name in ("claude", "codex"):
            path = os.path.join(self.bin, name)
            with open(path, "w") as fh:
                fh.write(FAKE)
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

    def api(self, path, body=None):
        request = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.port, path), method="POST" if body is not None else "GET",
            data=json.dumps(body).encode() if body is not None else None,
            headers={"X-Workbench-Token": terminal.token(), "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())

    def view(self):
        return self.api("/api/runs/%s" % self.run_id)["view"]

    def until(self, reached, seconds, what):
        """The run's view once `reached` holds of it, read once a second; a run that failed or
        ended instead fails the demo at once, with the run's own lines."""
        def probe():
            view = self.view()
            if reached(view):
                return view
            if view["state"] in ("failed", "closed"):
                lines = self.api("/api/runs/%s" % self.run_id)["lines"]
                raise SystemExit("demo failed: waiting for %s, the run is %s: %s\n  %s" % (
                    what, view["state"], view["failure"] or view["status"], "\n  ".join(lines[-12:])))
            return None
        return wait(probe, seconds, what)

    def press(self, label, action):
        """Press the run's button labelled `label` in headless Edge on Windows, as the operator would."""
        script = subprocess.run(["wslpath", "-w", os.path.join(HERE, "demo_press.ps1")],
                                capture_output=True, text=True, check=True).stdout.strip()
        pressed = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
                                  "http://127.0.0.1:%d/" % self.port, self.run_id, label, action],
                                 capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=300)
        print("  " + (pressed.stdout + pressed.stderr).strip().replace("\n", "\n  "), flush=True)
        return pressed.returncode == 0

    async def ready(self):
        client = await runs.connect()
        workflows = await runs.polled(client, WF.TASK_QUEUE, TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW)
        check(workflows, "the normal WSL worker runs the workflows (`make up` starts it)")
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
        self.run_id = self.api("/api/runs", {"task": TASK, "repo": "demo"})["run_id"]
        check(bool(self.run_id), "the Workbench started run %s" % self.run_id)
        view = self.until(lambda view: view["state"] == "waiting", 300, "the plan's approval")
        timeline = self.api("/api/runs/%s" % self.run_id)["timeline"]
        verdicts = [entry.get("verdict") for entry in timeline if entry.get("verdict")]
        check(verdicts == ["PATCH", "PASS"], "the architect sent the plan back once, then passed it: %s" % verdicts)
        check(view["stop"]["reason"] == "approval" and "approve" in view["actions"],
              "the run waits for approval, and says so")

        step("the plan approved by pressing the Workbench's own button")
        check(self.press("Approve", "approve"), "the page sent the answer, and the workflow took it")
        view = self.until(lambda view: view["state"] == "waiting" and view["stop"]["reason"] == "final", 300,
                          "the final gate")
        check(True, "the engineer built and the architect verified")

        step("the change merged by pressing Merge")
        check(self.press("Merge", "merge"), "the page sent the answer, with its confirmation")
        view = self.until(lambda view: view["state"] == "closed", 300, "the merge")
        check(view["status"] == "MERGED", "the run ended merged")
        check("greeting.txt" in git(self.repo, "ls-tree", "--name-only", "develop"),
              "the base branch holds the change")

    def cleanup(self):
        if self.run_id:
            try:
                if self.view()["state"] != "closed":
                    asyncio.run(self._terminate())
            except Exception:                        # noqa: BLE001 - the Workbench may be gone already
                pass
            shutil.rmtree(os.path.join(paths.RUNTIME_ROOT, self.run_id), ignore_errors=True)
        for process in reversed(self.processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        trust.forget(self.repo, ["claude", "codex"])
        shutil.rmtree(self.tmp, ignore_errors=True)
        print("\n  removed: the demo's worker, Workbench, repository and trust records", flush=True)

    async def _terminate(self):
        client = await runs.connect()
        await client.get_workflow_handle(self.run_id).terminate("the demo ended before its run did")


async def activity_worker():
    """The demo's worker: this policy's own queue, the real activities, no workflows."""
    from temporalio.worker import Worker
    from app.application import activities
    policy = P.load()
    client = await runs.connect()
    terminal.serve(policy["targets"]["wsl"]["terminal_port"], policy["workbench_port"])
    await Worker(client, task_queue=P.queue(policy, "wsl"), activities=activities.Activities().all(),
                 activity_executor=concurrent.futures.ThreadPoolExecutor(max_workers=8)).run()


def main():
    if sys.argv[1:] == ["--worker"]:
        asyncio.run(activity_worker())
        return 0
    demo = Demo()
    try:
        demo.run()
        print("\nDEMO PASSED: run %s, watched in the Workbench and answered from its buttons" % demo.run_id)
        return 0
    finally:
        demo.cleanup()


if __name__ == "__main__":
    sys.exit(main())
