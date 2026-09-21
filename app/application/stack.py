"""The Orchestra stack's health: whether Temporal answers, and whether each host's worker polls.

The one reading of it — `make check` prints it and the Workbench shows it — and it changes nothing.
"""
from temporalio.api.enums.v1 import TaskQueueType

from app.application import client as runs
from app.foundation import policy as P
from app.orchestration import workflow as WF


def queues(policy):
    """Every queue the stack serves, and the kind of task on it: the workflows', and each host's."""
    return [(WF.TASK_QUEUE, TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW)] + [
        (P.queue(policy, target), TaskQueueType.TASK_QUEUE_TYPE_ACTIVITY) for target in P.TARGETS]


async def health(client, policy):
    """Temporal up, each queue with whether a worker polls it, and each host's worker up or down."""
    rows = [{"queue": name, "host": runs.host_of(name), "polled": await runs.polled(client, name, kind)}
            for name, kind in queues(policy)]
    return {"temporal": "up", "error": None, "queues": rows, "hosts": _hosts(rows)}


def unreachable(policy, error):
    """The same reading when Temporal cannot be reached: nothing about the workers can be known."""
    rows = [{"queue": name, "host": runs.host_of(name), "polled": None} for name, _ in queues(policy)]
    return {"temporal": "down", "error": error, "queues": rows,
            "hosts": {row["host"]: "unknown" for row in rows}}


def _hosts(rows):
    """A host's worker is up only while it polls every queue that is its own."""
    hosts = {}
    for row in rows:
        hosts[row["host"]] = "up" if row["polled"] and hosts.get(row["host"], "up") == "up" else "down"
    return hosts
