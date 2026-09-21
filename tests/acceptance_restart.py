"""Acceptance on the live Temporal stack: restarts, a killed worker, run ids, and the approved merge.

Proves a restart while a run waits, a worker killed mid-role, a run id refused while open
and after it closed, a rejected answer writing no event on a real server, and a merge and
a discard through real workers and real git.

It never touches a real repository or agent. A throwaway repository, fake `claude` and
`codex` executables, and a dedicated `accept` host whose queue only this script's worker
polls; the stops it answers are its own run's. Afterwards it takes back all it made: its runs
and the reads of their changes from Temporal — the Workbench lists every run Temporal retains —
their folders, its workers' pid files and its trust records. Needs the stack and both workers up
(`make up`), and restarts all three:

    uv run --locked python tests/acceptance_restart.py
"""
import asyncio
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
REPO = PKG
sys.path[:0] = [PKG, HERE]

from temporalio.client import Client, WorkflowUpdateFailedError  # noqa: E402
from temporalio.exceptions import WorkflowAlreadyStartedError  # noqa: E402

from app.application import client as runs  # noqa: E402
from app.foundation import policy as P  # noqa: E402
from app.agents import trust  # noqa: E402
from app.orchestration import workflow as WF  # noqa: E402
import temporal_cleanup  # noqa: E402

RUNTIME = os.path.join(REPO, "tmp", "orchestration")

# The acceptance's own agent, speaking the turn contract the runner expects: its prompt is the last
# argument and the turn ends through the vendor's own completion wiring, which `fake_cli` owns.
FAKE = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, re, sys, time
    sys.path.insert(0, "{{TESTS}}")
    import fake_cli

    argv = sys.argv[1:]
    prompt = argv[-1]
    brain = "codex" if "codex" in os.path.basename(sys.argv[0]) else "claude"
    complete = fake_cli.completer(brain, argv, prompt)
    fake_cli.draw("fake " + brain + " ready")
    message = "done"
    if brain == "codex":
        message = json.dumps({"verdict": "PASS", "feedback": "Direction: the acceptance change."})
    else:
        todo = re.search(r"write the reviewable todo to exactly: (\\S+)", prompt)
        if todo:
            os.makedirs(os.path.dirname(todo.group(1)), exist_ok=True)
            open(todo.group(1), "w").write("**Status:** DRAFT\\nthe acceptance plan\\n")
        elif "Implement the approved todo" in prompt:
            open("app.txt", "a").write("changed by the engineer\\n")
            # Larger than one part of a change, so the final gate is read in several parts.
            with open("big.txt", "w") as fh:
                for line in range(12000):
                    fh.write("line %05d: the acceptance change, long enough for several parts\\n" % line)
            hang = os.environ.get("FAKE_HANG_FILE")
            if hang and os.path.exists(hang):
                fake_cli.detach(hang + ".grandchild")
                time.sleep(600)
    complete(message)
    time.sleep(0.2)
""").replace("{{TESTS}}", HERE)


def step(text):
    print("\n== %s" % text, flush=True)


def check(condition, text):
    print("  %s %s" % ("PASS" if condition else "FAIL", text), flush=True)
    if not condition:
        raise SystemExit("acceptance failed: %s" % text)


def git(path, *args):
    return subprocess.run(["git", "-C", path] + list(args), capture_output=True, text=True, check=True).stdout


def alive(pid):
    try:
        with open("/proc/%d/stat" % pid) as fh:
            return fh.read().rsplit(")", 1)[1].split()[0] != "Z"
    except (FileNotFoundError, ProcessLookupError, ValueError):
        # A process reaped between the open and the read answers ESRCH.
        return False


class Acceptance:
    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="orch-accept-")
        self.repo = os.path.join(self.tmp, "Repos_Accept", "sample")
        self.root = os.path.join(self.tmp, "worktrees")
        self.bin = os.path.join(self.tmp, "bin")
        self.hang = os.path.join(self.tmp, "hang")
        self.worker = None
        # What the cleanup takes back: each run as soon as its id is known, the command line still
        # following one whose id it has printed, and every worker this script started.
        self.runs = []
        self.follower = None
        self.worker_pids = []

    def setup(self):
        os.makedirs(self.repo)
        os.makedirs(self.bin)
        hooks = os.path.join(self.tmp, "no-hooks")
        os.makedirs(hooks)
        git(self.repo, "init", "-q", "-b", "develop")
        for key, value in (("user.name", "acceptance"), ("user.email", "acceptance@localhost"),
                           ("commit.gpgsign", "false"), ("core.hooksPath", hooks)):
            git(self.repo, "config", key, value)
        with open(os.path.join(self.repo, "app.txt"), "w") as fh:
            fh.write("base\n")
        os.makedirs(os.path.join(self.repo, "todo", "done"))
        with open(os.path.join(self.repo, "todo", "done", ".keep"), "w") as fh:
            fh.write("")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")
        for name in ("claude", "codex"):
            path = os.path.join(self.bin, name)
            with open(path, "w") as fh:
                fh.write(FAKE)
            os.chmod(path, 0o755)
        policy = json.load(open(os.path.join(PKG, "policy.json")))
        for role in policy["roles"].values():
            role["prompt"] = os.path.join(PKG, role["prompt"])
        policy["heartbeat_seconds"] = 10
        policy["timeout_seconds"] = 900
        policy["targets"] = {"wsl": {"host": "accept", "worktree_root": self.root, "terminal_port": 18091},
                             "windows": {"host": "accept", "worktree_root": "C:\\Worktrees", "terminal_port": 18092}}
        self.policy = os.path.join(self.tmp, "policy.json")
        json.dump(policy, open(self.policy, "w"))
        self.descriptors = os.path.join(self.tmp, "repos.json")
        json.dump({"sample": {"path": self.repo, "target": "wsl",
                              "worktree_root": os.path.join(self.root, "sample")}}, open(self.descriptors, "w"))
        self.queue = P.queue(P.load(self.policy), "wsl")

    def env(self):
        return dict(os.environ, PATH=self.bin + os.pathsep + os.environ["PATH"], ORCH_POLICY=self.policy,
                    ORCH_REPOS=self.descriptors, FAKE_HANG_FILE=self.hang,
                    LANGFUSE_TRACING_ENVIRONMENT="fixture")

    def start_worker(self):
        log = open(os.path.join(self.tmp, "worker.log"), "a")
        self.worker = subprocess.Popen([sys.executable, "-m", "app.interfaces.worker", "wsl"], cwd=PKG,
                                       env=self.env(), stdout=log, stderr=log, start_new_session=True)
        self.worker_pids.append(self.worker.pid)

    def kill_worker(self):
        if self.worker and self.worker.poll() is None:
            os.kill(self.worker.pid, signal.SIGKILL)
            self.worker.wait()

    def cli(self, *args):
        done = subprocess.run([sys.executable, "-m", "app.interfaces.cli"] + list(args), cwd=PKG,
                              env=self.env(), capture_output=True, text=True, timeout=900)
        return done.returncode, done.stdout + done.stderr

    async def polled(self, client, queue, seconds=90):
        from app.interfaces import cli
        from temporalio.api.enums.v1 import TaskQueueType
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                await cli.preflight(client, [(queue, TaskQueueType.TASK_QUEUE_TYPE_ACTIVITY),
                                             (WF.TASK_QUEUE, TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW)])
                return True
            except (cli.Refusal, Exception):
                await asyncio.sleep(2)
        return False

    async def connect(self, seconds=120):
        deadline = time.monotonic() + seconds
        while True:
            try:
                return await Client.connect("localhost:7233", namespace=WF.NAMESPACE)
            except Exception:
                if time.monotonic() > deadline:
                    raise
                await asyncio.sleep(2)

    async def events(self, handle):
        return len([event async for event in handle.fetch_history_events()])

    async def run(self):
        self.setup()
        client = await self.connect()
        self.start_worker()
        check(await self.polled(client, self.queue), "the acceptance worker polls %s" % self.queue)

        step("a run stops for approval; a rejected answer writes no event on a real server")
        code, out = self.cli("acceptance change", "--repo", "sample", "--policy", self.policy)
        check(code == 2 and "reason:   approval" in out, "the run stopped for approval (rc %s)" % code)
        run1 = re.search(r"run-id: ([\w-]+)", out).group(1)
        self.runs.append(run1)
        handle = client.get_workflow_handle(run1)
        status = await handle.query(WF.FeatureRun.status)
        before = await self.events(handle)
        try:
            await handle.execute_update(WF.FeatureRun.answer, {"stop": status["stop"]["id"], "action": "discard",
                                                              "confirm": True}, id="answer:rejected-probe")
            check(False, "an answer the stop does not offer is rejected")
        except WorkflowUpdateFailedError:
            check(True, "an answer the stop does not offer is rejected")
        check(await self.events(handle) == before, "and the history is exactly as long as before (%d events)" % before)

        step("the run recorded its repository for the CLIs it uses, so no turn waits at a trust dialog")
        brains = [role["brain"] for role in P.load(self.policy)["roles"].values()]
        check(trust.ensure(self.repo, brains) == [],
              "prepare already recorded this repository for %s" % ", ".join(sorted(set(brains))))

        step("a plan changed after its PASS is assessed again before anything is built")
        worktree = os.path.join(self.root, "sample", run1)
        plan = [name for name in os.listdir(os.path.join(worktree, "todo")) if name.endswith(".md")][0]
        with open(os.path.join(worktree, "todo", plan), "a") as fh:
            fh.write("a line the operator typed into the idle engineer\n")
        code, out = self.cli("--resume", run1, "--answer", "yes")
        logs = os.path.join(RUNTIME, run1, "logs")
        names = sorted(name for name in os.listdir(logs) if name.endswith(".out"))
        check(code == 2 and "reason:   approval" in out, "the run is back at approval, not building (rc %s)" % code)
        check(not any(name.startswith("build") for name in names), "no build turn ran: %s" % ", ".join(names))
        check(any(name.startswith("assess-e2") for name in names), "the architect judged the changed plan")

        step("the server and all three workers restart while the run waits")
        subprocess.run(["docker", "compose", "-f", os.path.join(PKG, "temporal", "compose.yaml"), "restart", "temporal"],
                       check=True, capture_output=True)
        subprocess.run(["bash", os.path.join(PKG, "workers.sh"), "down"], capture_output=True, text=True)
        self.kill_worker()
        subprocess.run(["bash", os.path.join(PKG, "workers.sh"), "up"], capture_output=True, text=True, timeout=600)
        client = await self.connect()
        self.start_worker()
        check(await self.polled(client, self.queue), "after the restart the workers poll again")
        code, out = self.cli("--resume", run1, "--answer", "yes")
        check(code == 0 and "READY_FOR_HUMAN" in out, "the answered run built, verified and reached READY_FOR_HUMAN")

        step("the change at the final gate is read in parts that join into the patch git itself prints")
        parts, snapshots, offset, reads = [], set(), 0, 0
        while reads <= 50:
            # Through the whole path the page uses: the ReviewDiff workflow, the activity on this
            # run's own worker, and a Temporal payload — which is where the size limit bit.
            read = await runs.review_diff(client, run1, offset)
            parts.append(read["patch"])
            snapshots.add(read["snapshot"])
            reads += 1
            if read["next"] >= read["total"]:
                break
            offset = read["next"]
        check(reads > 1, "the change was larger than one payload and came through Temporal in %d parts"
              % reads)
        check(len(snapshots) == 1, "every part named the same change")
        # The same recipe, run by this script rather than by the code under test.
        index = subprocess.run(["git", "-C", worktree, "rev-parse", "--path-format=absolute", "--git-path", "index"],
                               capture_output=True, text=True, check=True).stdout.strip()
        oracle_index = os.path.join(self.tmp, "oracle-index")
        shutil.copyfile(index, oracle_index)
        env = dict(os.environ, GIT_INDEX_FILE=oracle_index)
        subprocess.run(["git", "-C", worktree, "add", "-A"], env=env, check=True, capture_output=True)
        oracle = subprocess.run(["git", "-C", worktree, "diff", "--no-ext-diff", "--no-textconv", "--cached"],
                                env=env, capture_output=True, check=True).stdout.decode("utf-8", "replace")
        check("".join(parts) == oracle, "the parts joined are that patch, byte for byte (%d bytes)" % len(oracle))

        step("a run id is refused while its run is open")
        try:
            await client.start_workflow(WF.FeatureRun.run, {}, id=run1, task_queue=WF.TASK_QUEUE,
                                        id_conflict_policy=__import__("temporalio.common").common.WorkflowIDConflictPolicy.FAIL,
                                        id_reuse_policy=__import__("temporalio.common").common.WorkflowIDReusePolicy.REJECT_DUPLICATE)
            check(False, "the open run's id is refused")
        except WorkflowAlreadyStartedError:
            check(True, "the open run's id is refused")

        step("a worker killed while its role runs takes the role's whole tree with it")
        open(self.hang, "w").close()
        proc = self.follower = subprocess.Popen(
            [sys.executable, "-m", "app.interfaces.cli", "second change", "--repo", "sample", "--policy", self.policy,
             "--auto-proceed"], cwd=PKG, env=self.env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        deadline = time.monotonic() + 300
        while not os.path.exists(self.hang + ".grandchild") and time.monotonic() < deadline:
            time.sleep(1)
        grandchild = int(open(self.hang + ".grandchild").read())
        check(alive(grandchild), "the engineer's grandchild process is running")
        self.kill_worker()
        gone = time.monotonic() + 5
        while alive(grandchild) and time.monotonic() < gone:
            time.sleep(0.1)
        check(not alive(grandchild), "killing the worker ended the grandchild within 5 s, before any timeout")
        out = proc.communicate(timeout=300)[0]
        self.follower = None
        run2 = re.search(r"run-id: ([\w-]+)", out).group(1)
        self.runs.append(run2)
        check("reason:   failed" in out and "heartbeat" in out.lower(),
              "after the heartbeat timeout the run stopped for the operator")
        os.remove(self.hang)
        self.start_worker()
        check(await self.polled(client, self.queue), "the restarted worker polls")
        code, out = self.cli("--continue", run2)
        check(code == 0 and "READY_FOR_HUMAN" in out, "Continue ran the stage once more and reached READY_FOR_HUMAN")
        code, out = self.cli("--resume", run2, "--answer", "discard", "--confirm")
        check(code == 0 and "DISCARDED" in out, "a confirmed discard ended the second run")
        check(not os.path.exists(os.path.join(self.root, "sample", run2)), "and removed its worktree")

        step("the approved merge")
        code, out = self.cli("--resume", run1, "--answer", "merge")
        check(code == 0 and "MERGED" in out, "the first run merged")
        subjects = git(self.repo, "log", "--first-parent", "--format=%s", "develop").splitlines()
        check(subjects[0].startswith("Merge ") and len(git(self.repo, "log", "-1", "--format=%P", "develop").split()) == 2,
              "develop gained an explicit merge commit: %r" % subjects[0])
        check(not os.path.exists(os.path.join(self.root, "sample", run1)), "the merged worktree is gone")
        check(run1 not in git(self.repo, "branch", "--format=%(refname:short)").split(), "and so is its branch")
        check(any(name.startswith("todo/done/") and name.endswith(".md") and ".keep" not in name
                  for name in git(self.repo, "ls-tree", "-r", "--name-only", "develop").split()),
              "the plan sits in todo/done/ inside the merge")

        step("a run id is refused after its run closed, while it is retained")
        try:
            await client.start_workflow(WF.FeatureRun.run, {}, id=run1, task_queue=WF.TASK_QUEUE,
                                        id_conflict_policy=__import__("temporalio.common").common.WorkflowIDConflictPolicy.FAIL,
                                        id_reuse_policy=__import__("temporalio.common").common.WorkflowIDReusePolicy.REJECT_DUPLICATE)
            check(False, "the closed run's id is refused")
        except WorkflowAlreadyStartedError:
            check(True, "the closed run's id is refused")
        return run1, run2

    def cleanup(self):
        """Take back everything this acceptance made, on the host and in Temporal; returns what would not go."""
        self.kill_worker()
        left = []
        if self.follower is not None:
            # The command line still following a run the acceptance never saw end: it printed the run's id.
            if self.follower.poll() is None:
                self.follower.kill()
            printed = re.search(r"run-id: ([\w-]+)", self.follower.communicate()[0] or "")
            if printed:
                self.runs.append(printed.group(1))
        try:
            left += ["%s in Temporal" % workflow_id for workflow_id in asyncio.run(self.forget())[1]]
        except Exception as exc:                   # noqa: BLE001 - reported below, never raised here
            left.append("runs %s in Temporal (%r)" % (", ".join(self.runs), exc))
        for run_id in self.runs:
            shutil.rmtree(os.path.join(RUNTIME, run_id), ignore_errors=True)
        for pid in self.worker_pids:
            # Its workers run under a policy of their own, so each named its pid file after itself, and
            # a killed one could not take it back.
            try:
                os.remove(os.path.join(RUNTIME, "worker-wsl-%d.pid" % pid))
            except FileNotFoundError:
                pass
        left += [name for name in os.listdir(RUNTIME)
                 if name in self.runs or any(name.endswith("-%d.pid" % pid) for pid in self.worker_pids)]
        try:
            trust.forget(self.repo, [role["brain"] for role in P.load(self.policy)["roles"].values()])
        except Exception as exc:                   # noqa: BLE001 - reported below, never raised here
            print("  trust.forget failed: %r" % (exc,))
        left += ["its %s trust record" % brain for brain in self.trust_left()]
        shutil.rmtree(self.tmp, ignore_errors=True)
        return left

    async def forget(self):
        """Delete its runs, and the reads of their changes, from Temporal: what is still held."""
        return await temporal_cleanup.delete_runs(await self.connect(30), self.runs)

    def trust_left(self):
        """Which CLIs still hold a record of this throwaway repository — read, not taken on trust."""
        left = []
        try:
            with open(trust.claude_path(), encoding="utf-8") as fh:
                if trust.claude_key(self.repo) in (json.load(fh).get("projects") or {}):
                    left.append("claude")
        except (OSError, ValueError):
            pass
        try:
            with open(trust.codex_path(), encoding="utf-8") as fh:
                if trust.codex_key(self.repo) in fh.read():
                    left.append("codex")
        except OSError:
            pass
        return left


if __name__ == "__main__":
    acceptance = Acceptance()
    failure, runs_done = None, None
    try:
        runs_done = asyncio.run(acceptance.run())
    except BaseException as exc:                    # noqa: BLE001 - reported after the cleanup runs
        failure = exc
    print("\n== nothing of this acceptance stays, on the host or in Temporal", flush=True)
    remaining = acceptance.cleanup()
    if failure is not None:
        raise failure
    check(not remaining, "its runs, their reads, folders and pid files, and its trust records are gone%s"
          % (": %s left" % "; ".join(remaining) if remaining else ""))
    print("\nACCEPTANCE PASSED: runs %s and %s" % runs_done)
