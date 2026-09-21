"""The one client of runs, shared by the workbench and the command line.

Start a run, list runs, read a run's status, answer the stop it waits at, and read its
change and its repository's worktrees — each through Temporal, so every write goes
through the workflow's own start rules, Updates and validators. Nothing here prints.
"""
import datetime
import os

from temporalio.api.enums.v1 import TaskQueueType
from temporalio.api.taskqueue.v1 import TaskQueue
from temporalio.api.workflowservice.v1 import DescribeTaskQueueRequest
from temporalio.client import Client, WorkflowUpdateFailedError
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from app.foundation import policy as policy_mod
from app.workspace import repos
from app.orchestration import workflow as WF
from app.workspace import worktrees

ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
NAMESPACE = os.environ.get("TEMPORAL_NAMESPACE", WF.NAMESPACE)
START_WORKERS = "start them with `make orchestration-up`"
# A readable run id's random tail can meet a run still retained; a start draws again this often.
START_ATTEMPTS = 3


class Refusal(RuntimeError):
    """Nothing was started or changed; the message says what to fix."""


class NotWaiting(Refusal):
    """The run does not exist, or waits at no stop this answer is for."""


class NotAccepted(Refusal):
    """The workflow's validator refused the answer."""


async def connect():
    try:
        return await Client.connect(ADDRESS, namespace=NAMESPACE)
    except Exception as exc:                       # noqa: BLE001 - any connection failure refuses
        raise Refusal("Temporal is not reachable at %s (%s) — %s" % (ADDRESS, exc, START_WORKERS))


def work_item_label(run_id, task, now):
    """A name an operator can pick out of a list: when, what, and which run.

    Kept US-ASCII and short because it is the observability session key, a plain
    string with a length limit.
    """
    words = " ".join((task or "").encode("ascii", "ignore").decode().split())
    if len(words) > 70:
        words = words[:70].rstrip() + "..."
    return "%s %s [%s]" % (now.strftime("%Y-%m-%d %H:%M"), words or "(no task)", run_id)


def queues(target_queue):
    return [(WF.TASK_QUEUE, TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW),
            (target_queue, TaskQueueType.TASK_QUEUE_TYPE_ACTIVITY)]


async def preflight(client, needed):
    """Refuse before any work unless a worker polls each queue the run needs.

    Only the workflow queue and the run's own target host: a WSL run does not wait on
    the Windows worker.
    """
    for name, kind in needed:
        reply = await client.workflow_service.describe_task_queue(DescribeTaskQueueRequest(
            namespace=client.namespace, task_queue=TaskQueue(name=name), task_queue_type=kind))
        if not reply.pollers:
            raise Refusal("no worker is polling %s — %s" % (name, START_WORKERS))


async def status(client, run_id):
    """The run's `status` query, or None when no such run exists."""
    try:
        return await client.get_workflow_handle(run_id).query(WF.FeatureRun.status)
    except RPCError as error:
        if error.status == RPCStatusCode.NOT_FOUND:
            return None
        raise


async def start(client, task, repo=None, auto_proceed=False, policy_path=None, check=True):
    """Start a run on `repo` (a repos.json name, a path, or this repository); returns its handle."""
    pol = policy_mod.load(policy_path)
    selected = repos.select(repo)
    queue = policy_mod.queue(pol, selected["target"])
    if check:
        await preflight(client, queues(queue))
    now = datetime.datetime.now()
    for attempt in range(START_ATTEMPTS):
        run_id = worktrees.run_id(task)
        start_input = {"run_id": run_id, "task": task, "label": work_item_label(run_id, task, now),
                       "created": now.isoformat(timespec="minutes"),
                       "auto_proceed": auto_proceed or pol["auto_proceed"],
                       "repository": selected, "policy": pol, "queue": queue}
        try:
            return await client.start_workflow(
                WF.FeatureRun.run, start_input, id=run_id, task_queue=WF.TASK_QUEUE,
                id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE)
        except WorkflowAlreadyStartedError:
            # A random tail met a run Temporal still holds: a fresh id, never that run's.
            if attempt == START_ATTEMPTS - 1:
                raise


async def answer(client, run_id, answer, check=True, only=None):
    """Answer the stop `run_id` waits at with `answer` (its action and fields); returns that stop.

    The answer names the stop it is for, so it is applied at most once and never to a later stop.
    """
    current = await status(client, run_id)
    if current is None:
        raise NotWaiting("no run %r" % run_id)
    stop = current["stop"]
    if stop is None or (only and stop["reason"] != only):
        raise NotWaiting("run %s is not waiting for %s" % (run_id, "a %s answer" % only if only else "an answer"))
    if answer.get("stop") not in (None, stop["id"]):
        raise NotWaiting("run %s no longer waits at stop %s" % (run_id, answer["stop"]))
    if check:
        await preflight(client, queues(current["queue"]))
    answer = dict(answer, stop=stop["id"])
    # An action is named as the stop publishes it; `revise:engineer` travels as the action and the
    # role the workflow's answer has always carried.
    action, _, role = (answer.get("action") or "").partition(":")
    if role:
        answer.update(action=action, role=role)
    try:
        await client.get_workflow_handle(run_id).execute_update(
            WF.FeatureRun.answer, answer, id="answer:%s" % stop["id"])
    except WorkflowUpdateFailedError as error:
        raise NotAccepted(error.cause.message if error.cause else str(error))
    except RPCError as error:
        # A closed run still answers the status query from its history, with the stop it closed
        # at, so the stop was read; it is the Update that finds no open run. Only that is a
        # refusal — any other RPC failure is the page's to report.
        if error.status == RPCStatusCode.NOT_FOUND:
            raise NotWaiting("run %s has closed and waits for no answer" % run_id) from error
        raise
    return stop


ALL_RUNS = "WorkflowType = 'FeatureRun'"
# One page owns each run: the open ones are always in the first page, the rest are paged on their
# own, so none is listed twice and none is left showing a state it has since left.
OPEN_RUNS = ALL_RUNS + " AND ExecutionStatus = 'Running'"
CLOSED_RUNS = ALL_RUNS + " AND ExecutionStatus != 'Running'"


def _listed(execution):
    return {"run_id": execution.id, "execution": execution.status.name if execution.status else None,
            "started": execution.start_time.isoformat() if execution.start_time else None,
            "closed": execution.close_time.isoformat() if execution.close_time else None}


async def runs(client, limit=200, cursor=None):
    """A page of the runs Temporal holds, newest first, as `(runs, cursor)`.

    Every open run is in the first page, however old — a run waiting for the operator must never
    fall off the list — and the finished ones are paged separately, `limit` at a time, so the whole
    of Temporal's retained history is reachable and no run is ever in two pages.
    """
    found = {}
    if cursor is None:
        async for execution in client.list_workflows(OPEN_RUNS):
            found[execution.id] = _listed(execution)
    page = client.list_workflows(CLOSED_RUNS, page_size=limit, next_page_token=cursor)
    read = 0
    async for execution in page:
        found.setdefault(execution.id, _listed(execution))
        read += 1
        if read >= limit:
            break
    listed = sorted(found.values(), key=lambda run: run["started"] or "", reverse=True)
    # A token only where the page was full: the last page of history ends the listing.
    return listed, (page.next_page_token or None) if read >= limit else None


async def review_diff(client, run_id, offset=0):
    """The run's change as its target host's git reads it, from `offset` bytes into the patch."""
    current = await status(client, run_id)
    if current is None:
        raise NotWaiting("no run %r" % run_id)
    path = current["state"].get("worktree_path")
    if not path:
        raise Refusal("run %s has no worktree yet" % run_id)
    await preflight(client, queues(current["queue"]))
    return await client.execute_workflow(
        WF.ReviewDiff.run, {"worktree_path": path, "queue": current["queue"], "offset": offset},
        id="diff-%s-%s" % (run_id, os.urandom(4).hex()), task_queue=WF.TASK_QUEUE,
        execution_timeout=datetime.timedelta(minutes=5))


async def worktrees_of(client, repo=None, policy_path=None, check=True):
    """Every worktree of a repository and whether it is merged, read by its target host's git."""
    pol = policy_mod.load(policy_path)
    selected = repos.select(repo)
    queue = policy_mod.queue(pol, selected["target"])
    if check:
        await preflight(client, queues(queue))
    view = await client.execute_workflow(
        WF.WorktreeView.run, {"repository": selected, "queue": queue,
                              "worktree_root": pol["targets"][selected["target"]]["worktree_root"]},
        id="worktrees-%s" % os.urandom(6).hex(), task_queue=WF.TASK_QUEUE)
    return selected, view
