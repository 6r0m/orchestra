"""A host's Temporal worker.

    python -m app.interfaces.worker wsl | windows | check

The WSL worker runs the workflows and the WSL host's activities; the Windows worker
runs only the Windows host's activities. Each polls its own host's task queue and no
other. It records its process id while it runs, so the Make target can stop it.
ORCH_POLICY names another policy file, whose target hosts give the worker other queues.
`check` reports which of the three queues a worker polls, and fails unless all do.
"""
import asyncio
import concurrent.futures
import os
import sys

from temporalio.worker import Worker

from app.application import activities
from app.application import client as runs
from app.application import stack
from app.foundation import policy as P
from app.foundation import paths
from app.agents import terminal
from app.orchestration import workflow as WF



def pid_file(target):
    """The deployment's worker records its pid where workers.sh looks; a worker for another policy apart from it."""
    if os.environ.get("ORCH_POLICY"):
        return os.path.join(paths.RUNTIME_ROOT, "worker-%s-%d.pid" % (target, os.getpid()))
    return os.path.join(paths.RUNTIME_ROOT, "worker-%s.pid" % target)


async def main(target):
    policy = P.load()
    client = await runs.connect()
    queue = P.queue(policy, target)
    host = activities.Activities()
    # This host's live agent terminals, for the workbench page.
    terminal.serve(policy["targets"][target]["terminal_port"], policy["workbench_port"])
    # Role-runs are sequential by policy; the pool only keeps a long one from blocking the trace writes.
    workers = [Worker(client, task_queue=queue, activities=host.all(),
                      activity_executor=concurrent.futures.ThreadPoolExecutor(max_workers=8))]
    if target == runs.WORKFLOW_HOST:
        workers.append(Worker(client, task_queue=WF.TASK_QUEUE,
                              workflows=[WF.FeatureRun, WF.WorktreeView, WF.ReviewDiff]))
    os.makedirs(paths.RUNTIME_ROOT, exist_ok=True)
    with open(pid_file(target), "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))
    print("worker for %s polling %s%s" % (target, queue,
                                          " and %s" % WF.TASK_QUEUE if target == runs.WORKFLOW_HOST else ""),
          flush=True)
    try:
        await asyncio.gather(*(worker.run() for worker in workers))
    finally:
        try:
            os.remove(pid_file(target))
        except OSError:
            pass


async def check():
    try:
        client = await runs.connect()
    except runs.Refusal as exc:
        print(exc)
        return 1
    reading = await stack.health(client, P.load())
    for row in reading["queues"]:
        print("%-22s %s" % (row["queue"], "polled" if row["polled"] else "NO WORKER"))
    return 0 if all(row["polled"] for row in reading["queues"]) else 1


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in P.TARGETS + ("check",):
        sys.exit("usage: python -m app.interfaces.worker %s|check" % "|".join(P.TARGETS))
    if sys.argv[1] == "check":
        sys.exit(asyncio.run(check()))
    asyncio.run(main(sys.argv[1]))
