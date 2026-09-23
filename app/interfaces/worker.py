"""A host's Temporal worker.

    python -m app.interfaces.worker wsl | windows | sweep [pid ...]

The WSL worker runs its policy's workflows and the WSL host's activities; the Windows worker
runs only the Windows host's activities. Each polls its own host's task queue and no other. It
records its process id while it runs where the stack's lifecycle scripts look for it
(`stack.pid_file`), and names itself `<pid>@<host>` to Temporal, so the stack can tell its polls
from a dead worker's. ORCH_POLICY names another policy file: a stack of its own, on queues of its
own. `sweep` removes what the stages of dead workers on this host left, as a worker does when it
starts and the stack does once it has stopped one — naming the worker it has proven gone.
"""
import asyncio
import concurrent.futures
import os
import socket
import sys
import tempfile

from temporalio.worker import Worker

from app.application import activities
from app.application import client as runs
from app.application import stack
from app.foundation import policy as P
from app.foundation import paths
from app.agents import terminal
from app.observability import telemetry
from app.orchestration import workflow as WF


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
    policy = P.load()
    sweep()
    # This host's live agent terminals, for the workbench page. Before the pid file: a second worker
    # of this policy stops here, on the port the first holds, and never touches the first one's record.
    terminal.serve(policy["targets"][target]["terminal_port"], policy["workbench_port"])
    os.makedirs(paths.RUNTIME_ROOT, exist_ok=True)
    record = stack.pid_file(policy, target)
    with open(record, "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))
    try:
        client = await runs.connect(identity="%d@%s" % (os.getpid(), socket.gethostname()))
        queue = P.queue(policy, target)
        host = activities.Activities()
        # Role-runs are sequential by policy; the pool only keeps a long one from blocking the trace writes.
        workers = [Worker(client, task_queue=queue, activities=host.all(),
                          activity_executor=concurrent.futures.ThreadPoolExecutor(max_workers=8))]
        if target == runs.WORKFLOW_HOST:
            workers.append(Worker(client, task_queue=P.workflow_queue(policy),
                                  workflows=[WF.FeatureRun, WF.WorktreeView, WF.ReviewDiff, WF.RemoveWorktree]))
        # Where its stages' settings go, which is where the sweep after its stop must look.
        print("worker for %s polling %s; stage settings under %s" % (
            target, ", ".join(name for name, _ in stack.worker_queues(policy, target)), tempfile.gettempdir()),
            flush=True)
        await asyncio.gather(*(worker.run() for worker in workers))
    finally:
        try:
            os.remove(record)
        except OSError:
            pass


if __name__ == "__main__":
    if not (len(sys.argv) == 2 and sys.argv[1] in P.TARGETS
            or len(sys.argv) >= 2 and sys.argv[1] == "sweep" and all(pid.isdigit() for pid in sys.argv[2:])):
        sys.exit("usage: python -m app.interfaces.worker %s | sweep [pid ...]" % "|".join(P.TARGETS))
    if sys.argv[1] == "sweep":
        # A stop is reported done only once its stages' settings are gone: one still there fails it.
        sys.exit(0 if sweep(tuple(int(pid) for pid in sys.argv[2:])) else 1)
    asyncio.run(main(sys.argv[1]))
