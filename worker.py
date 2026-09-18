"""A host's Temporal worker. `python worker.py wsl`, `python worker.py windows`, or `python worker.py check`.

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

from temporalio.client import Client
from temporalio.worker import Worker

import activities
import policy as P
import terminal
import workflow as WF

ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
NAMESPACE = os.environ.get("TEMPORAL_NAMESPACE", WF.NAMESPACE)


def pid_file(target):
    """The deployment's worker records its pid where workers.sh looks; a worker for another policy apart from it."""
    if os.environ.get("ORCH_POLICY"):
        return os.path.join(activities.RUNTIME_ROOT, "worker-%s-%d.pid" % (target, os.getpid()))
    return os.path.join(activities.RUNTIME_ROOT, "worker-%s.pid" % target)


async def main(target):
    policy = P.load(os.environ.get("ORCH_POLICY"))
    client = await Client.connect(ADDRESS, namespace=NAMESPACE)
    queue = P.queue(policy, target)
    host = activities.Activities()
    # This host's live agent terminals, for the workbench page.
    terminal.serve(policy["targets"][target]["terminal_port"], policy["workbench_port"])
    # Role-runs are sequential by policy; the pool only keeps a long one from blocking the trace writes.
    workers = [Worker(client, task_queue=queue, activities=host.all(),
                      activity_executor=concurrent.futures.ThreadPoolExecutor(max_workers=8))]
    if target == "wsl":
        workers.append(Worker(client, task_queue=WF.TASK_QUEUE,
                              workflows=[WF.FeatureRun, WF.WorktreeView, WF.ReviewDiff]))
    os.makedirs(activities.RUNTIME_ROOT, exist_ok=True)
    with open(pid_file(target), "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))
    print("worker for %s polling %s%s" % (target, queue, " and %s" % WF.TASK_QUEUE if target == "wsl" else ""),
          flush=True)
    try:
        await asyncio.gather(*(worker.run() for worker in workers))
    finally:
        try:
            os.remove(pid_file(target))
        except OSError:
            pass


async def check():
    import cli
    from temporalio.api.enums.v1 import TaskQueueType
    try:
        client = await Client.connect(ADDRESS, namespace=NAMESPACE)
    except Exception as exc:                       # noqa: BLE001 - any connection failure is reported
        print("Temporal is not reachable at %s: %s" % (ADDRESS, exc))
        return 1
    policy = P.load(os.environ.get("ORCH_POLICY"))
    queues = [(WF.TASK_QUEUE, TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW)] + [
        (P.queue(policy, target), TaskQueueType.TASK_QUEUE_TYPE_ACTIVITY) for target in P.TARGETS]
    missing = 0
    for name, kind in queues:
        try:
            await cli.preflight(client, [(name, kind)])
            print("%-22s polled" % name)
        except cli.Refusal:
            print("%-22s NO WORKER" % name)
            missing += 1
    return 1 if missing else 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in P.TARGETS + ("check",):
        sys.exit("usage: worker.py %s|check" % "|".join(P.TARGETS))
    if sys.argv[1] == "check":
        sys.exit(asyncio.run(check()))
    asyncio.run(main(sys.argv[1]))
