"""A host's Temporal worker.

    python -m app.interfaces.worker wsl | windows | sweep [pid ...]

The WSL worker runs its settings' workflows and the WSL host's activities; the Windows worker
runs only the Windows host's activities. Each polls its own host's task queue and no other. It
records its process id while it runs where the stack's lifecycle scripts look for it
(`stack.pid_file`), and names itself `<pid>@<host>` to Temporal, so the stack can tell its polls
from a dead worker's. ORCHESTRA_SETTINGS names another settings file: a stack of its own, on queues
of its own. `sweep` removes what the stages of dead workers on this host left, as a worker does when it
starts and the stack does once it has stopped one — naming the worker it has proven gone.
"""
import asyncio
import concurrent.futures
import datetime
import os
import socket
import sys
import tempfile

from temporalio.worker import Worker

from app.application import activities
from app.application import changes
from app.application import client as runs
from app.application import settings
from app.application import stack
from app.foundation import policy as P
from app.foundation import paths
from app.agents import terminal
from app.observability import telemetry
from app.orchestration import workflow as WF


async def drain(workers, record):
    """The host scripts request shutdown locally; Temporal owns stopping polls and flushing activities."""
    while not stack.drain_requested(record, os.getpid()):
        await asyncio.sleep(0.5)
    print("worker draining; current activities finish before exit", flush=True)
    # Keep the workflow poller available for status and Stop while host activities drain. Its
    # next activities queue normally, without being picked up by the retiring activity worker.
    await workers[0].shutdown()
    await asyncio.gather(*(worker.shutdown() for worker in workers[1:]))


def sweep(gone=()):
    """A worker stopped mid-stage never removed that stage's settings, which hold the trace store's
    key; whatever a dead worker on this host left goes — those of the processes in `gone` whatever
    now holds their pids. True when none is left."""
    removed, left = telemetry.discard_stale_settings(gone)
    for stale in removed:
        print("removed the settings a dead worker's stage left: %s" % stale, flush=True)
    for stale in left:
        print("could not remove the settings a dead worker's stage left: %s" % stale, flush=True)
    return not left


async def main(target):
    policy = settings.load()
    sweep()
    # This host's live agent terminals, and the change of each run whose worktree is here, for the workbench
    # page. Before the pid file: a second worker of this policy stops here, on the port the first holds, and
    # never touches the first one's record.
    change = changes.ChangeFeed(target)
    terminal.serve(policy["targets"][target]["terminal_port"], policy["workbench_port"], feeds={"change": change.poll})
    os.makedirs(paths.RUNTIME_ROOT, exist_ok=True)
    record = stack.pid_file(policy, target)
    with open(record, "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))
    try:
        client = await runs.connect(identity="%d@%s" % (os.getpid(), socket.gethostname()))
        change.bind(client, asyncio.get_running_loop())
        queue = P.queue(policy, target)
        host = activities.Activities()
        host.bind(client, asyncio.get_running_loop())
        # Runs sequence their own roles; different runs share this pool. Admit work only when a thread
        # can execute it, so overflow cannot lose its heartbeat while still waiting for a thread.
        activity_slots = 8
        # An update adds no practical shorter deadline than an activity's own. The public SDK's
        # duration, rather than module reload or cancellation suppression, keeps the running code intact.
        workers = [Worker(client, task_queue=queue, activities=host.all(),
                          graceful_shutdown_timeout=datetime.timedelta.max,
                          max_concurrent_activities=activity_slots,
                          activity_executor=concurrent.futures.ThreadPoolExecutor(max_workers=activity_slots))]
        if target == runs.WORKFLOW_HOST:
            workers.append(Worker(client, task_queue=P.workflow_queue(policy),
                                  graceful_shutdown_timeout=datetime.timedelta.max,
                                  workflows=[WF.FeatureRun, WF.WorktreeView, WF.ReviewDiff, WF.RemoveWorktree]))
        # Where its stages' settings go, which is where the sweep after its stop must look.
        print("worker for %s polling %s; activity slots %d; stage settings under %s" % (
            target, ", ".join(name for name, _ in stack.worker_queues(policy, target)), activity_slots, tempfile.gettempdir()),
            flush=True)
        stack.drain_ready(record, os.getpid())
        await asyncio.gather(*(worker.run() for worker in workers), drain(workers, record))
    finally:
        for path in (record + ".ready", record + ".drain", record):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "drain" and sys.argv[3].isdigit() \
            and sys.argv[2] == os.path.basename(sys.argv[2]) and sys.argv[2].startswith("worker-"):
        try:
            stack.request_drain(os.path.join(paths.RUNTIME_ROOT, sys.argv[2] + ".pid"), int(sys.argv[3]))
        except runs.Refusal as exc:
            sys.exit(str(exc))
        print("drain requested; waiting for current activities", flush=True)
        sys.exit(0)
    if not (len(sys.argv) == 2 and sys.argv[1] in P.TARGETS
            or len(sys.argv) >= 2 and sys.argv[1] == "sweep" and all(pid.isdigit() for pid in sys.argv[2:])):
        sys.exit("usage: python -m app.interfaces.worker %s | sweep [pid ...]" % "|".join(P.TARGETS))
    if sys.argv[1] == "sweep":
        # A stop is reported done only once its stages' settings are gone: one still there fails it.
        sys.exit(0 if sweep(tuple(int(pid) for pid in sys.argv[2:])) else 1)
    asyncio.run(main(sys.argv[1]))
