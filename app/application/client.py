"""The one client of runs, shared by the workbench and the command line.

Start a run, list runs, read a run's status and what it is doing now, answer the stop it waits
at, stop it or force it to terminate, and read its change and its repository's worktrees — each
through Temporal, so every write goes through the workflow's own start rules, Updates and
validators, or Temporal's own lifecycle. Nothing here prints.
"""
import datetime
import os

from temporalio.api.enums.v1 import TaskQueueType
from temporalio.api.taskqueue.v1 import TaskQueue
from temporalio.api.workflowservice.v1 import DescribeTaskQueueRequest
from temporalio.client import Client, WorkflowExecutionStatus, WorkflowFailureError, WorkflowUpdateFailedError
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import (ApplicationError, TimeoutError as StepTimeout, TimeoutType,
                                   WorkflowAlreadyStartedError)
from temporalio.service import RPCError, RPCStatusCode

from app.application import settings as S
from app.foundation import flows
from app.foundation import paths
from app.foundation import policy as policy_mod
from app.foundation import stages
from app.workspace import repos
from app.orchestration import workflow as WF
from app.workspace import worktrees

ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
NAMESPACE = os.environ.get("TEMPORAL_NAMESPACE", WF.NAMESPACE)
START_WORKERS = "start it from the Workbench, or with `make up`"
# The workflows run on the WSL host's worker, which polls its policy's workflow queue beside its own
# target queue; every other host's worker polls only its own target queue.
WORKFLOW_HOST = "wsl"
# A live worker polls each of its queues again at least once a long poll — measured: an idle one's
# last poll up to 54 s old — while Temporal lists a dead worker's pollers for minutes. A poller seen
# within this long is one that still polls.
POLLING = datetime.timedelta(seconds=90)
# A readable run id's random tail can meet a run still retained; a start draws again this often.
START_ATTEMPTS = 3
# The longest a removal of what a run kept may take, its host's git removing a large worktree.
REMOVAL = datetime.timedelta(minutes=10)
# How long a removal waits for a worker of the run's host to take it: the preflight still counts a worker
# dead for less than POLLING as polling, and a live one takes it at once.
TAKEN = datetime.timedelta(minutes=1)
# How long an action waits for a run's status once a worker polls to answer it: the preflight still counts
# a worker dead for less than POLLING as polling.
READ = datetime.timedelta(seconds=30)


class Refusal(RuntimeError):
    """Nothing was started or changed; the message says what to fix."""


class NotWaiting(Refusal):
    """The run does not exist or has closed, or waits at no stop this answer is for."""


class NotAccepted(Refusal):
    """The workflow's validator refused the answer."""


async def connect(identity=None):
    """A client of Temporal; `identity` is how a worker names itself to it, the SDK's own otherwise."""
    try:
        return await Client.connect(ADDRESS, namespace=NAMESPACE, **({"identity": identity} if identity else {}))
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


def queues(workflow_queue, target_queue):
    """The two queues a run needs polled: the one it runs on, and its target host's."""
    return [(workflow_queue, TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW),
            (target_queue, TaskQueueType.TASK_QUEUE_TYPE_ACTIVITY)]


def host_of(queue):
    """The host whose worker polls `queue`: a target queue is named `target:<host>:<name>`, and
    any other is a workflow queue, the WSL worker's."""
    return queue.split(":")[1] if queue.startswith("target:") else WORKFLOW_HOST


async def pollers(client, name, kind):
    """Who has polled the task queue `name` lately, as Temporal lists them: identity and last poll."""
    reply = await client.workflow_service.describe_task_queue(DescribeTaskQueueRequest(
        namespace=client.namespace, task_queue=TaskQueue(name=name), task_queue_type=kind))
    return [{"identity": poller.identity,
             "polled": poller.last_access_time.ToDatetime(tzinfo=datetime.timezone.utc)}
            for poller in reply.pollers]


async def polled(client, name, kind):
    """Whether a worker polls the task queue `name` now: one Temporal saw poll it within POLLING."""
    since = datetime.datetime.now(datetime.timezone.utc) - POLLING
    return any(poller["polled"] >= since for poller in await pollers(client, name, kind))


async def preflight(client, needed):
    """Refuse before any work unless a worker polls each queue the run needs.

    Only the workflow queue and the run's own target host: a WSL run does not wait on
    the Windows worker.
    """
    for name, kind in needed:
        if not await polled(client, name, kind):
            raise Refusal("no worker is polling %s — the %s worker is not running; %s"
                          % (name, host_of(name), START_WORKERS))


async def status(client, run_id, timeout=None):
    """The run's `status` query, or None when no such run exists. A query is answered by a worker of the
    run's own workflow queue, replaying its history, so with none polling it waits — for `timeout`
    at most, when one is given."""
    try:
        return await client.get_workflow_handle(run_id).query(WF.FeatureRun.status, rpc_timeout=timeout)
    except RPCError as error:
        if error.status == RPCStatusCode.NOT_FOUND:
            return None
        raise


async def readable_status(client, run_id):
    """The run's status, asked only once a worker polls its own workflow queue — the one that answers the
    query — and for READ at most: refused, naming that worker, while none polls or none answers in time,
    rather than waiting for one. Its `workflow_queue` is Temporal's own record of the run's. None when
    Temporal holds no such run."""
    listed = await execution(client, run_id)
    if listed is None:
        return None
    await preflight(client, [(listed["task_queue"], TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW)])
    try:
        current = await status(client, run_id, READ)
    except RPCError as error:
        raise Refusal("run %s's status did not come (%s): the %s worker may be down; %s"
                      % (run_id, error, host_of(listed["task_queue"]), START_WORKERS)) from error
    if current is not None:
        current["workflow_queue"] = listed["task_queue"]
    return current


async def execution(client, run_id):
    """One run's execution as the listing reads it, or None when Temporal holds no such run."""
    try:
        return _listed(await client.get_workflow_handle(run_id).describe())
    except RPCError as error:
        if error.status == RPCStatusCode.NOT_FOUND:
            return None
        raise


async def started(client, run_id):
    """What a run was started with — its policy, each role's kind among it — as Temporal recorded that start,
    whatever the settings say now; None when Temporal holds no such run."""
    try:
        async for event in client.get_workflow_handle(run_id).fetch_history_events(page_size=1):
            payloads = event.workflow_execution_started_event_attributes.input.payloads
            return (await client.data_converter.decode(payloads))[0]
    except RPCError as error:
        if error.status == RPCStatusCode.NOT_FOUND:
            return None
        raise
    return None


def view(listed, status, health):
    """What a run is now — the one reading every surface shows, derived from facts that exist.

    `listed` is the run's execution as the listing or `execution` reads it, `status` its `status`
    query (None when it could not be read), `health` the stack's reading (`stack.status`). A run is
    closed once Temporal no longer runs it, stopping from a Stop until then, failed or waiting while
    it stops for the operator, and running otherwise. It is blocked by each host whose worker is
    down and polls a queue the run needs — the one it runs on, known from the listing even when its
    status cannot be read, and its target host's. A run on another stack's queues is not this
    reading's to judge.
    """
    state = (status or {}).get("state") or {}
    stop = (status or {}).get("stop")
    closed = listed["execution"] not in (None, "RUNNING")
    if closed:
        kind = "closed"
    elif state.get("status") == "STOPPING":
        kind = "stopping"
    elif stop:
        kind = "failed" if stop["reason"] == "failed" else "waiting"
    else:
        kind = "running"
    working = {} if closed or stop else (state.get("current") or {})
    stack_hosts = {row["queue"]: row["host"] for row in health["queues"]}
    needed = [queue for queue in (listed.get("task_queue"), (status or {}).get("queue")) if queue in stack_hosts]
    return {"run_id": listed["run_id"], "execution": listed["execution"], "started": listed["started"],
            "closed": listed["closed"], "goal": state.get("task"), "repo": state.get("repo"),
            "host": state.get("target"), "worktree": state.get("worktree_path"), "state": kind,
            "status": state.get("status"), "phase": state.get("phase"), "round": state.get("round"),
            "episode": state.get("episode"), "stage": working.get("stage"), "role": working.get("role"),
            "flow": state.get("flow"), "step": state.get("step"),
            "since": stop.get("since") if stop else working.get("since"),
            "stop": stop and {key: stop.get(key) for key in ("id", "reason", "hint", "feedback", "todo")},
            "failure": stop["feedback"] if kind == "failed" else None,
            "blocked_by": [] if closed else sorted({stack_hosts[queue] for queue in needed
                                                    if health["hosts"].get(stack_hosts[queue]) == "down"}),
            "actions": list(stop["actions"]) if stop and not closed else []}


async def start(client, task, repo=None, auto_proceed=False, settings_path=None, check=True, flow=None,
                settings_root=paths.REPO, settings_environ=os.environ):
    """Start a run on `repo` (a descriptor's name, a path, or this repository), following `flow` (a file in
    `flows/`, the settings' `default_flow` when none is named); returns its handle.

    The flow is read and checked here, once, and the run is handed its steps and its policy made whole —
    each role's agent and persona's text among it: it never reads a flow, settings or a persona file, so
    none edited later changes a run already started."""
    settings = S.load(settings_path, root=settings_root, environ=settings_environ)
    selected = repos.select(repo)
    queue = policy_mod.queue(settings, selected["target"])
    name = flow or settings.get("default_flow")
    chosen = {"name": name, "steps": flows.load(name)} if name else None
    pol = S.run_policy(settings, chosen["steps"] if chosen else None)
    if check:
        await preflight(client, queues(policy_mod.workflow_queue(pol), queue))
    now = datetime.datetime.now()
    for attempt in range(START_ATTEMPTS):
        run_id = worktrees.run_id(task)
        # `auto_proceed` skips every approval the flow schedules — never an emergency stop or the merge.
        start_input = {"run_id": run_id, "task": task, "label": work_item_label(run_id, task, now),
                       "created": now.isoformat(timespec="minutes"),
                       "auto_proceed": auto_proceed or pol["auto_proceed"],
                       "repository": selected, "policy": pol, "queue": queue}
        if chosen:
            start_input["flow"] = chosen
        try:
            return await client.start_workflow(
                WF.FeatureRun.run, start_input, id=run_id, task_queue=policy_mod.workflow_queue(pol),
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
    current = await (readable_status(client, run_id) if check else status(client, run_id))
    if current is None:
        raise NotWaiting("no run %r" % run_id)
    stop = current["stop"]
    if stop is None or (only and stop["reason"] != only):
        raise NotWaiting("run %s is not waiting for %s" % (run_id, "a %s answer" % only if only else "an answer"))
    if answer.get("stop") not in (None, stop["id"]):
        raise NotWaiting("run %s no longer waits at stop %s" % (run_id, answer["stop"]))
    if check:
        await preflight(client, queues(current["workflow_queue"], current["queue"]))
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


async def stop(client, run_id):
    """Stop a run, whatever it is doing: Temporal's cancellation, which the workflow ends `STOPPED`
    with its worktree and branch as they are. Temporal takes it with no worker polling; the run ends
    once its workflow worker reads it."""
    await _while_open(client, run_id, lambda handle: handle.cancel())


async def force_terminate(client, run_id, reason):
    """Close a run at once — Temporal's termination — for one a Stop cannot finish. None of the run's
    own cleanup runs, and termination cannot stop what its host is already doing: an agent at work
    ends at its turn's next heartbeat, but a git side effect already running goes on to its end and
    may still change the repository."""
    await _while_open(client, run_id, lambda handle: handle.terminate(reason=reason))


async def _while_open(client, run_id, end):
    """End the run with `end(handle)` if it is still open; a closed one is refused, whether or not
    Temporal would take the request — its test server takes a cancellation of a closed run."""
    handle = client.get_workflow_handle(run_id)
    try:
        if (await handle.describe()).status != WorkflowExecutionStatus.RUNNING:
            raise NotWaiting("run %s has closed" % run_id)
        await end(handle)
    except RPCError as error:
        if error.status == RPCStatusCode.NOT_FOUND:
            raise NotWaiting("run %s has closed, or never existed" % run_id) from error
        raise


ALL_RUNS = "WorkflowType = 'FeatureRun'"
# One page owns each run: the open ones are always in the first page, the rest are paged on their
# own, so none is listed twice and none is left showing a state it has since left.
OPEN_RUNS = ALL_RUNS + " AND ExecutionStatus = 'Running'"
CLOSED_RUNS = ALL_RUNS + " AND ExecutionStatus != 'Running'"


def _listed(execution):
    return {"run_id": execution.id, "execution": execution.status.name if execution.status else None,
            "started": execution.start_time.isoformat() if execution.start_time else None,
            "closed": execution.close_time.isoformat() if execution.close_time else None,
            "task_queue": execution.task_queue or None}


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


async def review_diff(client, run_id, offset=0, base=None, tree=None, file=None, files_from=None):
    """The run's change as its target host's git reads it (`worktrees.review_diff`): the change now, or the
    snapshot `base` and `tree` name, from `offset` bytes into its patch — or its file list from `files_from`, or
    its one `file`. The change now is read against the commit of its base the run stands on, where it recorded
    one: what the run adds to that base, whatever git holds in its worktree meanwhile. A snapshot is read from
    the run's repository once its worktree is gone. A read naming what that git cannot read is refused, saying
    why."""
    current = await readable_status(client, run_id)
    if current is None:
        raise NotWaiting("no run %r" % run_id)
    path = current["state"].get("worktree_path")
    if not path:
        raise Refusal("run %s has no worktree yet" % run_id)
    await preflight(client, queues(current["workflow_queue"], current["queue"]))
    if base is None and tree is None:
        base = current["state"].get("base_tip")
    named = {key: value for key, value in (("base", base), ("tree", tree), ("file", file), ("files_from", files_from))
             if value is not None}
    try:
        # On the run's own workflow queue: its own stack's worker reads its change.
        return await client.execute_workflow(
            WF.ReviewDiff.run, dict(named, worktree_path=path, repo_path=current["state"].get("repo_path"),
                                    queue=current["queue"], offset=offset),
            id="diff-%s-%s" % (run_id, os.urandom(4).hex()), task_queue=current["workflow_queue"],
            execution_timeout=datetime.timedelta(minutes=5))
    except WorkflowFailureError as error:
        cause = error.cause.cause if error.cause is not None and error.cause.cause is not None else error.cause
        if isinstance(cause, ApplicationError) and cause.type == "ChangeRefused":
            raise Refusal(cause.message) from error
        raise


async def history(client, run_id):
    """What the run's Temporal history holds that its status does not: each turn that completed — its stage,
    episode, round, when a worker took it and when it ended, and for a review the tree it judged — and each
    answer the run accepted, with its words, when, and the phase of the step it answered. None when Temporal
    holds no such run.

    A turn's start is its started event's time — when a worker took it, which Temporal records as such even
    though it writes that event only once the step ends — never when it was queued. A review's tree is the one
    its result names — `judged_tree`, or for a pass `assessed_tree` or `verified_tree` — and a review whose
    result names none has none; the work that makes a build final names the one it left, `final_tree` — or
    `closeout_tree`, as the first closeouts named it. An answer is the `answer:<stop-id>` Update the workflow
    accepted, as its accepted event recorded the request; one its validator refused never entered the history.
    Its phase is the one of the last role turn begun before it, failed or not, and it comes `after` the last turn
    completed before it, by its key `stage:episode:round` — the transcript's order is the history's own, never one
    read from clocks. Each engineer turn carries its `change` (`_changes`), which begins from the commit the
    run's worktree was made at and, each time its base was brought into that worktree, from the tree that left
    there — both as those steps recorded them."""
    def at(event):
        return event.event_time.ToDatetime(tzinfo=datetime.timezone.utc).isoformat()

    async def decoded(payloads):
        return (await client.data_converter.decode(payloads))[0]

    turns, answers, scheduled, started, phase = [], [], {}, {}, None
    steps, began, came = {}, None, []
    try:
        async for event in client.get_workflow_handle(run_id).fetch_history_events():
            if event.HasField("activity_task_scheduled_event_attributes"):
                attributes = event.activity_task_scheduled_event_attributes
                if attributes.activity_type.name == "run_role":
                    args = await decoded(attributes.input.payloads)
                    scheduled[event.event_id] = (args, at(event))
                    phase = args["state"].get("phase") or phase
                elif attributes.activity_type.name in ("create_worktree", "reconcile"):
                    steps[event.event_id] = attributes.activity_type.name
            elif event.HasField("activity_task_started_event_attributes"):
                started[event.activity_task_started_event_attributes.scheduled_event_id] = at(event)
            elif event.HasField("activity_task_completed_event_attributes"):
                attributes = event.activity_task_completed_event_attributes
                if attributes.scheduled_event_id in scheduled:
                    args, queued = scheduled.pop(attributes.scheduled_event_id)
                    result, state = await decoded(attributes.result.payloads), args["state"]
                    turn = {"stage": args["stage"], "episode": state.get("episode", 1),
                            "round": state.get("round", 0) + 1,
                            "started": started.get(attributes.scheduled_event_id, queued), "ended": at(event)}
                    tree = (result.get("judged_tree") or result.get("assessed_tree") or result.get("verified_tree")
                            or result.get("final_tree") or result.get("closeout_tree"))
                    if tree:
                        turn["tree"] = tree
                    turns.append(turn)
                elif attributes.scheduled_event_id in steps:
                    result = await decoded(attributes.result.payloads)
                    if steps.pop(attributes.scheduled_event_id) == "create_worktree":
                        began = result.get("base_tip")
                    elif result.get("moved") and result.get("tree"):
                        came.append((len(turns), result["tree"]))
            elif event.HasField("workflow_execution_update_accepted_event_attributes"):
                request = event.workflow_execution_update_accepted_event_attributes.accepted_request
                if request.meta.update_id.startswith("answer:"):
                    answer = await decoded(request.input.args.payloads)
                    answers.append({"stop": answer.get("stop"), "action": answer.get("action"),
                                    "role": answer.get("role"), "text": answer.get("text"), "at": at(event),
                                    "phase": phase, "after": _turn_key(turns[-1]) if turns else None})
    except RPCError as error:
        if error.status == RPCStatusCode.NOT_FOUND:
            return None
        raise
    _changes(turns, began, came)
    return {"turns": turns, "answers": answers}


def _turn_key(turn):
    return "%s:%d:%d" % (turn["stage"], turn["episode"], turn["round"])


def _changes(turns, began=None, came=()):
    """Give each engineer turn the change the reviews around it judged: from the tree the last review before it
    recorded — before any, the commit the run began from (`began`; `base` None for a run that recorded none, read
    then as its worktree's last commit) — to the tree the first review after it recorded, with the turns it holds.
    Where the run's base was brought into its worktree (`came`: after how many turns, and the tree that left), the
    next change starts from that tree: the base's own commits are no turn's change.
    Engineer turns with a review between them that recorded no tree cannot be told apart, so
    their change is one, given to the last of them, which the others point to (`with`); never the same change twice.
    A turn no review has judged since is `pending`; one only reviews that recorded no tree have judged, `unrecorded`.
    The turn that makes a build final has no review after it and records the tree it left itself: its change is
    from the tree the last review recorded to that one — what the operator alone judges — and it moves no later
    turn's start, since a change sent back is reopened to the tree that review judged."""
    base, waiting, judged, came = began, [], set(), list(came)
    for at, turn in enumerate(turns):
        while came and came[0][0] <= at:
            # Turns no review's tree had judged before the base came in cannot be told from it.
            for each in waiting:
                each["change"] = {"unrecorded": True}
            waiting, judged, base = [], set(), came.pop(0)[1]
        if stages.STAGE_ROLE.get(turn["stage"]) == "engineer" and turn.get("tree"):
            turn["change"] = {"base": base, "tree": turn["tree"], "turns": [_turn_key(turn)]}
        elif stages.STAGE_ROLE.get(turn["stage"]) == "engineer":
            waiting.append(turn)
        elif turn["stage"] in stages.REVIEWS and turn.get("tree"):
            if waiting:
                last = _turn_key(waiting[-1])
                waiting[-1]["change"] = {"base": base, "tree": turn["tree"],
                                         "turns": [_turn_key(each) for each in waiting]}
                for each in waiting[:-1]:
                    each["change"] = {"with": last}
            waiting, judged, base = [], set(), turn["tree"]
        elif turn["stage"] in stages.REVIEWS:
            judged.update(_turn_key(each) for each in waiting)
    for turn in waiting:
        turn["change"] = {"unrecorded": True} if _turn_key(turn) in judged else {"pending": True}


def not_kept(listed, status, removal=None):
    """Why a run has no work of its own to remove, or None when it has: the one rule the page, the
    worktree view and the removal itself read. `removal` is how the removal of it went, if one ran."""
    state = (status or {}).get("state") or {}
    if listed is None:
        return "no run %r" % ((status or {}).get("state") or {}).get("run_id")
    if listed["execution"] == "RUNNING":
        return "run %s is still open: stop it first, and its worktree and branch stay for you" % listed["run_id"]
    if state.get("status") in ("MERGED", "DISCARDED"):
        return "run %s was %s, so nothing of it was kept" % (listed["run_id"], state["status"].lower())
    if not state.get("worktree_path"):
        return "run %s never made a worktree" % listed["run_id"]
    if removal == "COMPLETED":
        return "run %s's worktree and branch were removed already" % listed["run_id"]
    return None


async def removal(client, run_id):
    """How the removal of what `run_id` kept went — its workflow's status — or None if none ran."""
    removed = await execution(client, "remove-%s" % run_id)
    return removed and removed["execution"]


async def remove_worktree(client, run_id):
    """Remove what a closed run kept — its worktree, its branch and the worktree's environment — through
    its target host's own git, as a discard removes them; refused as `not_kept` says. A git side effect
    of the run still running on its host — a terminated run's merge goes on — refuses it there."""
    listed = await execution(client, run_id)
    if listed is None:
        raise NotWaiting("no run %r" % run_id)
    if listed["execution"] == "RUNNING":
        raise Refusal(not_kept(listed, None))
    current = await readable_status(client, run_id)
    reason = not_kept(listed, current, await removal(client, run_id))
    if reason:
        raise Refusal(reason)
    state = current["state"]
    await preflight(client, queues(current["workflow_queue"], current["queue"]))
    try:
        return await client.execute_workflow(
            WF.RemoveWorktree.run, {"state": {key: state[key] for key in ("run_id", "repo_path", "worktree_path")},
                                    "queue": current["queue"], "waits": TAKEN.total_seconds()},
            id="remove-%s" % run_id, task_queue=current["workflow_queue"],
            id_conflict_policy=WorkflowIDConflictPolicy.FAIL, execution_timeout=REMOVAL)
    except WorkflowAlreadyStartedError as error:
        raise Refusal("run %s's worktree is being removed already" % run_id) from error
    except WorkflowFailureError as error:
        # Its host's git refused, and says why: nothing is retried, as with every git side effect.
        cause = error.cause.cause if error.cause is not None and error.cause.cause is not None else error.cause
        if isinstance(cause, StepTimeout) and cause.type == TimeoutType.SCHEDULE_TO_START:
            raise Refusal("run %s's worktree was not removed: no %s worker took the removal; %s, then remove it"
                          % (run_id, host_of(current["queue"]), START_WORKERS)) from error
        raise Refusal("run %s's worktree was not removed: %s" % (run_id, getattr(cause, "message", cause))) from error


async def worktrees_of(client, repo=None, settings_path=None, check=True):
    """Every worktree of a repository and whether it is merged, read by its target host's git."""
    pol = S.load(settings_path)
    selected = repos.select(repo)
    queue = policy_mod.queue(pol, selected["target"])
    if check:
        await preflight(client, queues(policy_mod.workflow_queue(pol), queue))
    view = await client.execute_workflow(
        WF.WorktreeView.run, {"repository": selected, "queue": queue,
                              "worktree_root": pol["targets"][selected["target"]]["worktree_root"]},
        id="worktrees-%s" % os.urandom(6).hex(), task_queue=policy_mod.workflow_queue(pol))
    return selected, view
