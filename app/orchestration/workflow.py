"""The workflow of one run: its flow's stages in order — work, the review that judges it, the
operator's approval where the flow schedules one — and the final gate.

Temporal owns it: one workflow execution per run, its Workflow Id the run id. The code
here decides every transition, deterministically — no clock, file, network or process;
every effect is an activity on the run's target host, and every route comes from
`routing`. The run's flow is in its start input, so it never reads one; a run started
before flows follows the order that code took (`flows.LEGACY_FLOW`).

A stop waits for an Update carrying one of that stop's named actions, with the stable id
`answer:<stop-id>`, so a repeated answer is applied once. The run's
state, its console lines and its timeline are read through the `status` query.

A Stop is Temporal's cancellation of the run, heard wherever the run waits: it ends the run
`STOPPED` after a bounded cleanup and runs no git, except that a git side effect already running
lands first and decides how the run ends.
"""
import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, TimeoutError, is_cancelled_exception

with workflow.unsafe.imports_passed_through():
    from app.foundation import flows
    from app.foundation import policy as P
    from app.foundation import stages
    from app.orchestration import routing

NAMESPACE = "orchestration"

# A role-run and every git side effect run once; only reads retry.
ONCE = RetryPolicy(maximum_attempts=1)
READS = RetryPolicy(maximum_attempts=3)
GIT_TIMEOUT = timedelta(hours=2)
SHORT_TIMEOUT = timedelta(minutes=10)

# What each stop takes, published with it, so a client shows the stop's own actions. A revise at
# the final gate goes to the role the operator names, and each role is an action of its own:
# `revise:<role>` arrives as the answer's action and role. Ending a run is no stop's answer: a Stop
# ends it from any state. No stop offers `abort`; a run that took one ended `ABORTED`, and its handling
# stays so those runs still replay.
ACTIONS = {
    "approval": ("approve", "revise"),
    "blocker": ("guide",),
    "exhausted": ("guide",),
    "failed": ("continue",),
    "final": ("merge", "revise:engineer", "revise:architect", "discard"),
}
HINTS = {
    "approval": "approve to start implementation, or revise with feedback for a new plan",
    "blocker": "guide with your decision to continue",
    "exhausted": "guide with your decision to continue",
    "failed": "fix the cause, then continue to run the stage again",
    "final": "merge into the base branch, revise with feedback to the engineer or the architect, "
             "or discard the worktree",
}
# The stops the trace records, as it always has; the others are the workflow's own.
TRACED_STOPS = ("approval", "blocker", "exhausted")


def _message(error):
    cause = error.cause if isinstance(error, ActivityError) and error.cause else error
    if isinstance(cause, TimeoutError) and cause.type is not None:
        clock = cause.type.name.lower().replace("_", "-")
        if clock == "schedule-to-start":
            return "%s timeout: no worker of the run's host took this step; start it, then continue" % clock
        # A heartbeat timeout is how a lost worker shows: say which clock ran out.
        return "%s timeout: the worker running this step stopped responding or ran out of time" % clock
    return str(getattr(cause, "message", None) or cause)


def _heard():
    """A Stop's cancellation has been caught: let the next await run, as the SDK's own awaits do."""
    task = asyncio.current_task()
    if task is not None:
        task.uncancel()


@workflow.defn
class FeatureRun:
    def __init__(self):
        self.state = {}
        self.segments = []
        self.queue = None
        self.policy = None
        self.stop = None
        self.answer_given = None
        self.stops = 0
        self.lines = []
        self.timeline = []
        self.stopping = False

    @workflow.run
    async def run(self, start):
        try:
            return await self._run(start)
        except (asyncio.CancelledError, ActivityError) as error:
            if not is_cancelled_exception(error):
                raise
            _heard()
            await self._stopped()
            # Temporal's own record of the run says it was cancelled, as the Stop asked.
            raise asyncio.CancelledError() from error

    async def _run(self, start):
        self.policy, self.queue = start["policy"], start["queue"]
        repository = start["repository"]
        s = self.state = {"run_id": start["run_id"], "task": start["task"], "label": start["label"],
                          "created": start["created"], "auto_proceed": start["auto_proceed"],
                          "repo": repository["id"], "target": repository["target"], "status": "RUNNING"}
        # A start with no flow at all is a run started before flows, which follows the order that code took.
        legacy = "flow" not in start
        flow = start.get("flow")
        try:
            # A flow given, null too, is checked here as the client checked it, taken as given whatever its
            # shape: one the run cannot follow ends it refused before any step, rather than stuck retrying
            # its first workflow task.
            steps = list(flows.LEGACY_FLOW) if legacy else flows.steps_of(flow)
        except flows.InvalidFlow as error:
            s.update(status="REFUSED", refusal="its flow: %s" % error)
            self._line("refused: %s" % s["refusal"])
            return s
        s["flow"] = {"name": None, "steps": steps} if legacy else flow
        self.segments = flows.segments(steps)
        try:
            s.update(await self._activity("prepare", {"repository": repository, "policy": self.policy},
                                          READS, SHORT_TIMEOUT))
        except ActivityError as error:
            if is_cancelled_exception(error):
                raise
            s.update(status="REFUSED", refusal=_message(error))
            self._line("refused: %s" % s["refusal"])
            return s
        self._doing("setup")
        created = await self._until_done("setup", lambda: self._git("create_worktree", {"state": s}))
        if created is None:
            return await self._end("ABORTED")
        s.update(created)
        first = self.segments[0]["work"][1]
        s.update(await self._trace("open_run", {"state": s, "phase": first}) or {})
        s.update(phase=first, round=0, phase_rounds=0, episode=1, agent_sessions={})
        return await self._loop()

    async def _loop(self):
        """The run's flow, one segment at a time: a work stage, the review that judges it, and the
        operator's step after them, where the flow has them (`flows.segments`)."""
        s = self.state
        at, review_next = 0, False
        while True:
            segment = self.segments[at]
            work, review, gate = (part and part[1] for part in (segment["work"], segment["review"], segment["gate"]))
            last = at == len(self.segments) - 1
            onward = "READY_FOR_HUMAN" if gate == "merge" else "DONE" if last else self.segments[at + 1]["work"][1]
            if not review_next:
                s["step"] = segment["work"][0]
                if not await self._stage(work):
                    return await self._end("ABORTED")
            review_next = False
            if review:
                s["step"] = segment["review"][0]
                if not await self._stage(review, gate, onward):
                    return await self._end("ABORTED")
            else:
                # Work no review judges — research: its answer goes to the operator's approval, if the
                # flow schedules one and the run does not skip it.
                s["gate_reason"] = routing.gate_reason_for("PASS", gate, 1, 1, s["auto_proceed"])
            if s["gate_reason"]:
                shown = {}
                if s["gate_reason"] == "approval":
                    s["step"] = segment["gate"][0]
                    shown = self._approval(work, last, onward)
                answer = await self._stop(s["gate_reason"], **shown)
                if answer["action"] == "abort":
                    return await self._end("ABORTED")
                if answer["action"] == "approve":
                    stands = await self._plan_stands() if work == "plan" else True
                    if stands is None:
                        return await self._end("ABORTED")
                    if stands:
                        if last:
                            return await self._end("DONE")
                        at += 1
                        await self._next(self.segments[at]["work"][1])
                    review_next = not stands      # the plan changed: the architect judges it again
                    continue
                # Guidance, or a revised plan or research: a new bounded episode. The operator's words
                # survive the worker and are consumed by the architect that judges next.
                s.update(guidance=answer["text"], round=0, gate_reason="", episode=s["episode"] + 1)
                continue
            if review and s["verdict"] != "PASS":
                continue
            if gate == "merge":
                s["step"] = segment["gate"][0]
                outcome = await self._final_gate()
                if outcome == "done":
                    return s
                review_next = outcome == "review"
                continue
            stands = await self._plan_stands() if work == "plan" else True
            if stands is None:
                return await self._end("ABORTED")
            if stands:
                if last:
                    return await self._end("DONE")
                at += 1
                await self._next(self.segments[at]["work"][1])
            review_next = not stands

    def _approval(self, work, last, onward):
        """What an approval shows besides the run's own feedback — after research, its brief — and where
        approving goes: on to `onward`, or to the run's end."""
        going = "end the run" if last else "go on to the %s" % onward
        if work in stages.ANSWERS:
            return {"text": self.state.get("brief") or "",
                    "hint": "approve to %s, or revise with feedback for new research" % going}
        if work == "plan" and onward == "build":
            return {}                     # HINTS["approval"], as a plan's approval has always read
        return {"hint": "approve to %s, or revise with feedback for a new %s" % (going, work)}

    async def _stage(self, stage, gate=None, onward=None):
        """Run one stage to a result, stopping for the operator on each failure. False when aborted.

        A review's verdict is routed by `gate`, the operator's step after it, and a PASS goes `onward`."""
        s = self.state
        label = "[%s e%d r%d]" % (stage, s["episode"], s["round"] + 1)
        self._unless_stopping()
        self._line("%s %s started" % (label, stages.STAGE_ROLE[stage]))
        self._doing(stage, stages.STAGE_ROLE[stage])
        result = await self._until_done(label, lambda: workflow.execute_activity(
            "run_role", {"stage": stage, "state": s, "policy": self.policy, "gate": gate},
            task_queue=self.queue,
            start_to_close_timeout=timedelta(seconds=self.policy["timeout_seconds"] + 600),
            heartbeat_timeout=timedelta(seconds=self.policy["heartbeat_seconds"]),
            retry_policy=ONCE))
        if result is None:
            return False
        s["agent_sessions"] = dict(s.get("agent_sessions") or {}, **result["agent_sessions"])
        entry = {"stage": stage, "phase": s["phase"], "episode": s["episode"], "round": s["round"] + 1,
                 "at": workflow.now().isoformat()}
        if "verdict" in result:
            rounds = s["round"] + 1
            reason = routing.gate_reason_for(result["verdict"], gate, rounds,
                                             self.policy["max_rounds"][s["phase"]], s["auto_proceed"])
            s.update(verdict=result["verdict"], feedback=result["feedback"], round=rounds,
                     phase_rounds=s.get("phase_rounds", 0) + 1, guidance="", gate_reason=reason)
            for judged in ("assessed_tree", "verified_tree"):
                if judged in result:
                    s[judged] = result[judged]
            self._line("%s %s -> %s" % (label, result["verdict"], routing.route_label(
                result["verdict"], reason, onward, stages.REVIEWS[stage])))
            entry.update(verdict=result["verdict"], gate=reason, feedback=result["feedback"])
        else:
            if "output" in result:
                # The work's answer is its product: the run keeps it, the approval shows it and the next
                # stage's prompt carries it.
                s["brief"] = result["output"]
                entry["brief"] = result["output"]
            self._line("%s completed" % label)
        self.timeline.append(entry)
        return True

    async def _until_done(self, label, attempt):
        """Await `attempt`; on a failure stop for the operator, who continues it — or, on a run that was
        offered one, aborts."""
        s = self.state
        while True:
            try:
                return await attempt()
            except ActivityError as error:
                if is_cancelled_exception(error):
                    raise
                s["error"] = _message(error)
                self._line("%s failed: %s" % (label, s["error"]))
                answer = await self._stop("failed")
                s.pop("error", None)
                if answer["action"] == "abort":
                    return None

    async def _plan_stands(self):
        """Is the worktree still the plan the architect passed? True, False (judge it again), None (aborted).

        The terminals stay live and writable to the end (D21), so the plan can change between the
        architect's `PASS` and the operator's approval — and that `PASS` summary is what the operator
        approves from. A changed plan therefore goes back through assessment before anything is built,
        exactly as a change during verification never reaches a merge.
        """
        s = self.state
        if not s.get("assessed_tree") or not workflow.patched("approval-holds-the-assessed-plan"):
            return True
        checked = await self._until_done("[plan]", lambda: self._activity(
            "work_tree", {"worktree_path": s["worktree_path"]}, READS, SHORT_TIMEOUT))
        if checked is None:
            return None
        if checked["tree"] == s["assessed_tree"]:
            return True
        self._line("the plan changed after the architect passed it; assessing it again")
        # A new bounded attempt, as a revised plan is: its own episode, its own rounds and logs.
        s.update(gate_reason="", feedback="", assessed_tree=None, round=0,
                 episode=s["episode"] + 1,
                 guidance="The plan in this worktree changed after your last assessment. "
                          "Judge it as it stands now.")
        return False

    async def _next(self, work):
        """On to the flow's next work stage, in a phase of its own."""
        s = self.state
        # The operator's words were for the stage just approved, never for the next one.
        s.update(phase=work, round=0, phase_rounds=0, feedback="", guidance="", gate_reason="",
                 episode=s["episode"] + 1)
        opened = await self._trace("open_phase", {"state": s, "phase": work})
        s["trace_phases"] = dict(s.get("trace_phases") or {}, **{work: (opened or {}).get("id")})

    async def _final_gate(self):
        """READY_FOR_HUMAN, then the operator's merge, revise or discard."""
        s = self.state
        s["status"] = "READY_FOR_HUMAN"
        self._line("READY_FOR_HUMAN")
        await self._trace("finish_trace", {"state": s})
        while True:
            answer = await self._stop("final")
            s.pop("merge_refusal", None)
            if answer["action"] == "discard":
                self._doing("discard")
                if await self._until_done("discard", lambda: self._git("discard", {"state": s})) is None:
                    continue
                s["status"] = "DISCARDED"
                self._line("DISCARDED")
                return "done"
            if answer["action"] == "revise":
                # A defect found at the gate goes back into the run, to the role the operator names.
                s.update(status="RUNNING", guidance=answer["text"], round=0, gate_reason="",
                         episode=s["episode"] + 1)
                return "review" if answer["role"] == "architect" else "build"
            self._doing("merge")
            merged = await self._until_done("merge", lambda: self._git("merge", {"state": s}))
            if merged is None:
                continue
            if merged["result"] == "merged":
                s.update(status="MERGED", merge_commit=merged["commit"])
                self._line("MERGED %s" % merged["commit"])
                return "done"
            if merged["result"] == "conflict":
                # The conflict goes back to the run's agents, never resolved here.
                s.update(status="RUNNING", round=0, gate_reason="", episode=s["episode"] + 1,
                         guidance="Merging %s conflicts with %s. The base branch is merged into this "
                                  "worktree with conflict markers in: %s. Resolve every conflict in the "
                                  "files; do not stage or commit." % (
                                      s["run_id"], s["base_branch"], ", ".join(merged["files"])))
                self._line("merge conflict: %s" % ", ".join(merged["files"]))
                return "build"
            s["merge_refusal"] = merged["reason"]
            self._line("merge refused: %s" % merged["reason"])

    async def _stop(self, reason, text=None, hint=None):
        s = self.state
        self._unless_stopping()
        self.stops += 1
        feedback = text if text is not None else {"failed": s.get("error"), "final": s.get("merge_refusal")}.get(
            reason, s.get("feedback"))
        self.stop = {"id": "%s:%d" % (s["run_id"], self.stops), "reason": reason, "phase": s.get("phase"),
                     "todo": s.get("todo_path"), "feedback": feedback or "", "hint": hint or HINTS[reason],
                     "actions": list(ACTIONS[reason]), "since": workflow.now().isoformat()}
        self._line("stopped: %s" % reason)
        if reason in TRACED_STOPS:
            await self._trace("record_stop", {"state": s, "stop": self.stop})
        await workflow.wait_condition(lambda: self.answer_given is not None)
        answer, self.answer_given, self.stop = self.answer_given, None, None
        if reason in TRACED_STOPS:
            await self._trace("record_answer", {"state": s, "answer": answer.get("text") or answer["action"]})
        return answer

    async def _end(self, status):
        self.state["status"] = status
        self._line(status)
        await self._trace("finish_trace", {"state": self.state})
        return self.state

    def _line(self, text):
        self.lines.append(text)

    def _doing(self, stage, role=None):
        """What the run is doing now, and since when — for whoever shows it; nothing reads it here."""
        self.state["current"] = {"stage": stage, "role": role, "since": workflow.now().isoformat()}

    async def _activity(self, name, args, retry, timeout):
        self._unless_stopping()
        return await workflow.execute_activity(name, args, task_queue=self.queue,
                                               start_to_close_timeout=timeout, retry_policy=retry)

    async def _trace(self, name, args):
        """A trace write: best-effort, so its failure costs a row and never the run."""
        try:
            return await self._activity(name, args, ONCE, SHORT_TIMEOUT)
        except ActivityError as error:
            if is_cancelled_exception(error):
                raise
            return None

    async def _git(self, name, args):
        """A git side effect, which a Stop never cuts off: the run shows the Stop as requested, waits for
        what git did, and returns it — a merge or discard that landed ends the run as it always does,
        and anything else meets the Stop at the run's next step."""
        self._unless_stopping()
        # It waits for its host's worker to take it as long as a role's step may go unheard: past that the
        # worker is gone, and the step fails never having run — it neither holds a Stop until a worker
        # comes back nor lands after the run was stopped.
        waits = (timedelta(seconds=self.policy["heartbeat_seconds"])
                 if workflow.patched("a-git-step-waits-for-its-worker-at-most") else None)
        effect = workflow.start_activity(name, args, task_queue=self.queue, start_to_close_timeout=GIT_TIMEOUT,
                                         schedule_to_start_timeout=waits, retry_policy=ONCE)
        try:
            return await asyncio.shield(effect)
        except asyncio.CancelledError:
            _heard()
            self._stopping()
        try:
            return await effect
        except ActivityError as error:
            # Git's own failure, not the Stop's: the Stop still ends the run.
            self._line("%s failed: %s" % (name, _message(error)))
            raise asyncio.CancelledError() from error

    def _unless_stopping(self):
        """Once a Stop is requested nothing more starts: the next thing the run would wait on is the Stop."""
        if self.stopping:
            raise asyncio.CancelledError()

    def _stopping(self):
        """The Stop is heard: the run says so and waits at no stop — again after a git result that
        would have sent it on."""
        if not self.stopping:
            self._line("stopping")
        self.stopping, self.stop = True, None
        self.state["status"] = "STOPPING"

    async def _stopped(self):
        """End the run stopped, its worktree and branch as they are. Its terminals and its trace close on
        its target host, within a bound: a host whose worker is gone never holds a Stop."""
        s = self.state
        self._stopping()
        self._doing("cleanup")
        try:
            # Best-effort, and bounded (P.STOP_CLEANUP_SECONDS): a run recorded before a policy could
            # shorten it carries no bound of its own, and waits exactly the minute.
            bound = timedelta(seconds=self.policy.get("stop_cleanup_seconds", P.STOP_CLEANUP_SECONDS))
            await workflow.execute_activity("finish_trace", {"state": dict(s, status="STOPPED")},
                                            task_queue=self.queue, schedule_to_close_timeout=bound,
                                            retry_policy=ONCE)
        except ActivityError as error:
            self._line("the %s host's cleanup did not run: %s" % (s["target"], _message(error)))
        s["status"] = "STOPPED"
        self._line("STOPPED")

    @workflow.update
    def answer(self, answer):
        self.answer_given = answer
        return {"stop": answer["stop"], "action": answer["action"]}

    @answer.validator
    def _validate_answer(self, answer):
        stop = self.stop
        if stop is None or self.answer_given is not None or answer.get("stop") != stop["id"]:
            raise ValueError("run %s is not waiting at stop %s" % (self.state.get("run_id"), answer.get("stop")))
        action = answer.get("action")
        named = "%s:%s" % (action, answer["role"]) if answer.get("role") else action
        if named not in stop["actions"]:
            raise ValueError("%r does not answer this stop; answer one of: %s"
                             % (named, ", ".join(stop["actions"])))
        if action in ("guide", "revise") and not (answer.get("text") or "").strip():
            raise ValueError("%s needs the feedback to act on" % action)
        if action == "discard" and answer.get("confirm") is not True:
            raise ValueError("discard deletes the worktree and its branch, so it must be confirmed")

    @workflow.query
    def status(self):
        # Both queues the run needs: its target host's, and the one it runs on, its policy's own.
        return {"state": self.state, "stop": self.stop, "lines": self.lines, "timeline": self.timeline,
                "queue": self.queue, "workflow_queue": workflow.info().task_queue}


@workflow.defn
class ReviewDiff:
    """A run's change as its target host's git reads it, for review before the merge."""

    @workflow.run
    async def run(self, args):
        return await workflow.execute_activity(
            "review_diff", args, task_queue=args["queue"], start_to_close_timeout=SHORT_TIMEOUT,
            retry_policy=READS)


@workflow.defn
class WorktreeView:
    """Every worktree of a repository and its merge state, read by the target's own git."""

    @workflow.run
    async def run(self, args):
        return await workflow.execute_activity(
            "worktree_view", args, task_queue=args["queue"], start_to_close_timeout=SHORT_TIMEOUT,
            retry_policy=READS)


@workflow.defn
class RemoveWorktree:
    """What a closed run kept — its worktree, its branch, the worktree's environment — removed by its
    target host's own git, as a discard removes them; once, like every git side effect. A removal no
    worker of that host takes within `waits` seconds fails never having run, as a run's git step does."""

    @workflow.run
    async def run(self, args):
        return await workflow.execute_activity(
            "discard", {"state": args["state"]}, task_queue=args["queue"], start_to_close_timeout=SHORT_TIMEOUT,
            schedule_to_start_timeout=timedelta(seconds=args["waits"]), retry_policy=ONCE)
