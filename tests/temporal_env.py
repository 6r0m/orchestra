"""One Temporal time-skipping test server per test process, and workers over the fake seams.

The server and every worker live on one event loop in a background thread, so the
synchronous tests drive them through `run`. Setting ORCH_WORKFLOW_UNDER_TEST=empty
registers a workflow with no logic instead of the real one: the scenarios' red control.
"""
import asyncio
import concurrent.futures
# Imported first, so its join of every pool's threads at exit is registered before this module's own
# shutdowns, which then run ahead of it (`_at_exit`).
import concurrent.futures.thread  # noqa: F401
import contextlib
import datetime
import io
import os
import shutil
import sys
import threading
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
for path in (PKG, HERE):
    if path not in sys.path:
        sys.path.insert(0, path)

from temporalio.testing import WorkflowEnvironment  # noqa: E402
from temporalio.worker import Worker  # noqa: E402

from app.application import activities as A  # noqa: E402
from app.interfaces import cli  # noqa: E402
from app.foundation import policy as policy_mod  # noqa: E402
from app.orchestration import workflow as WF  # noqa: E402

# As a host that binds its own methodology to each stage does; the shipped policy binds none, and
# `test_workflow` proves both — that a bound skill leads the prompt, and that none appears without one.
POLICY = dict(policy_mod.load(),
              stage_skills={"plan": "/investigate-change", "assess": "/architect",
                            "build": "/implement-approved-change", "verify": "/architect"})
WSL_QUEUE = policy_mod.queue(POLICY, "wsl")
WORKFLOW_QUEUE = policy_mod.workflow_queue(POLICY)
WINDOWS_QUEUE = policy_mod.queue(POLICY, "windows")
# Polled by its own host: the control that shows the queue, not the target, decides where a role runs.
SHARED_QUEUE = "target:shared:test"

_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, name="temporal-test-loop", daemon=True).start()
_env = None


def run(coro, timeout=300):
    return asyncio.run_coroutine_threadsafe(coro, _loop).result(timeout)


def _at_exit(stop):
    """Run `stop` as the interpreter begins to shut down, before it joins every thread pool's threads.
    An activity still running holds one of them, and only its worker's shutdown cancels it; an atexit
    handler would come after that join, which would then wait on the activity for good. The last
    registered runs first: the workers, then the server. `threading._register_atexit` is CPython's own hook
    for that moment, the one `concurrent.futures` registers its join with; proven on the pinned 3.13."""
    def guarded():
        try:
            stop()
        except Exception as exc:                    # noqa: BLE001 - reported; the exit goes on
            print("temporal_env: a shutdown at exit failed: %r" % (exc,), file=sys.stderr, flush=True)
    threading._register_atexit(guarded)


def env():
    global _env
    if _env is None:
        _env = run(WorkflowEnvironment.start_time_skipping())
        _at_exit(lambda: run(_env.shutdown()))
    return _env


def client():
    """The test server's client, with the workers already polling: a workflow started with none would never run."""
    hosts()
    return env().client


def workflows():
    import control_workflows
    run_class = WF.FeatureRun
    if os.environ.get("ORCH_WORKFLOW_UNDER_TEST") == "empty":
        import empty_workflow
        run_class = empty_workflow.EmptyRun
    return [run_class, WF.WorktreeView, WF.ReviewDiff, WF.RemoveWorktree] + control_workflows.ALL


def _unexpected(*args, **kwargs):
    raise AssertionError("a role ran on a host this test did not configure")


# One activity host per target queue, started once per process: each test swaps the
# seams behind them, because a worker's start and stop cost seconds each.
_hosts = {}


def _start_workers():
    async def build():
        # A worker validates its workflows on the running loop, so it is built there.
        made = [Worker(env().client, task_queue=WORKFLOW_QUEUE, workflows=workflows())]
        for queue in (WSL_QUEUE, WINDOWS_QUEUE, SHARED_QUEUE):
            _hosts.setdefault(queue, A.Activities(runner=_unexpected, telemetry=None))
            made.append(Worker(env().client, task_queue=queue, activities=_hosts[queue].all(),
                               activity_executor=concurrent.futures.ThreadPoolExecutor(max_workers=4)))
        return made

    env()
    started = run(build())
    for worker in started:
        run(worker.__aenter__())
    _at_exit(lambda: [run(worker.__aexit__(None, None, None)) for worker in reversed(started)])


def hosts():
    if not _hosts:
        _start_workers()
    return _hosts


def own_host(test, queue, script, git=None, telemetry=None):
    """A host of the test's own on `queue`, whose worker the test can take away: its activities, over a
    fake agent playing `script`, and the function that stops its worker — which the test's cleanup calls
    too, and which does nothing a second time."""
    from fakes import FakeAgent, FakeRepos, FakeWorktrees
    host = A.Activities(runner=FakeAgent(script), git=git or FakeWorktrees(), repositories=FakeRepos(),
                        telemetry=telemetry)
    # Outside the loop: the first call starts the test server, and waits on that loop to do it.
    connected = client()

    async def build():
        return Worker(connected, task_queue=queue, activities=host.all(),
                      activity_executor=concurrent.futures.ThreadPoolExecutor(max_workers=2))
    worker = run(build())
    run(worker.__aenter__())
    stopped = []

    def stop():
        if not stopped:
            stopped.append(True)
            run(worker.__aexit__(None, None, None))
    test.addCleanup(stop)
    return host, stop


def configure(queue, script, git=None, repositories=None, telemetry=None):
    """Point one host's seams at fresh fakes; returns the host and its agent."""
    from fakes import FakeAgent, FakeRepos, FakeWorktrees
    activities = hosts()[queue]
    agent = FakeAgent(script)
    activities.runner, activities.git = agent, git or FakeWorktrees()
    activities.repositories = repositories or FakeRepos()
    activities._telemetry, activities._client, activities._resolved = telemetry, None, False
    return activities, agent


def start_input(run_id, task="toy task", auto=False, policy=None, target="wsl", queue=None, repo="example"):
    policy = policy or POLICY
    now = datetime.datetime(2026, 9, 15, 12, 0)
    return {"run_id": run_id, "task": task, "label": cli.work_item_label(run_id, task, now),
            "created": now.isoformat(timespec="minutes"), "auto_proceed": auto,
            "repository": {"id": repo, "path": "/fake/repo", "target": target},
            "policy": policy, "queue": queue or policy_mod.queue(policy, target)}


class Run:
    """One workflow execution in the test server, driven the way the CLI drives it."""

    def __init__(self, **kwargs):
        self.run_id = uuid.uuid4().hex[:12]
        self.handle = run(client().start_workflow(WF.FeatureRun.run, start_input(self.run_id, **kwargs),
                                                  id=self.run_id, task_queue=WORKFLOW_QUEUE))
        self.answered = None
        self.status = run(cli.follow(self.handle))

    @property
    def stop(self):
        return self.status["stop"]

    @property
    def state(self):
        return self.status["state"]

    def answer(self, text, confirm=False):
        """Answer the current stop as `--resume --answer` does; returns the CLI's return code and output."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = run(cli._answer(client(), self.run_id, text, confirm, None, False))
        self.status = run(self.handle.query(WF.FeatureRun.status))
        return code, out.getvalue()

    def closed(self):
        return run(self.handle.describe()).close_time is not None

    def cleanup(self):
        shutil.rmtree(A.run_dir(self.run_id), ignore_errors=True)


def host(script, git=None, repositories=None, telemetry=None, queue=WSL_QUEUE):
    """The one configured host for a test: every other host refuses to run a role."""
    for other in hosts().values():
        other.runner = _unexpected
    return configure(queue, script, git=git, repositories=repositories, telemetry=telemetry)
