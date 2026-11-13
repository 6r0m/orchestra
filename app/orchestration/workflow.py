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
lands first and decides how the run ends. One that says the operator rejected the run (`REJECT`) ends
it `REJECTED` instead, and is otherwise the same Stop.
"""
import asyncio
import hashlib
import json
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError, TimeoutError, is_cancelled_exception

with workflow.unsafe.imports_passed_through():
    from app.foundation import flows
    from app.foundation import policy as P
    from app.foundation import stages
    from app.foundation import landing
    from app.orchestration import routing

NAMESPACE = "orchestration"

# A role-run and every git side effect run once; only reads retry.
ONCE = RetryPolicy(maximum_attempts=1)
READS = RetryPolicy(maximum_attempts=3)
GIT_TIMEOUT = timedelta(hours=2)
SHORT_TIMEOUT = timedelta(minutes=10)

# What each stop takes, published with it, so a client shows the stop's own actions. A revise at
# the final gate goes to the role the operator names, and each role is an action of its own:
# `revise:<role>` arrives as the answer's action and role. Guidance goes to the engineer's work, or — as
# `guide:architect`, offered beside it (`GUIDED`) — to the architect, who judges the work as it stands again.
# Ending a run is no stop's answer: a Stop ends it from any state. No stop offers `abort`; a run that took
# one ended `ABORTED`, and its handling stays so those runs still replay.
ACTIONS = {
    "approval": ("approve", "revise"),
    "blocker": ("guide",),
    "exhausted": ("guide",),
    "failed": ("continue",),
    "final": ("merge", "revise:engineer", "revise:architect", "discard"),
}
# The stops whose guidance may go to the architect instead; a run recorded before it offered the one route.
GUIDED = ("blocker", "exhausted")
GUIDE_THE_ARCHITECT = "guide-the-architect"
# A note given with an approval goes on with it, as guidance to the stage approved into; a run recorded before
# kept no note an approval carried — words the command line sent with every answer, `yes` among them. The stop
# says whether it takes one (`noted`), and one sent where it does not is refused, saying so.
APPROVE_WITH_A_NOTE = "approve-with-a-note"
NO_NOTE = ("this approval takes no note — it ends the run, or its run was recorded before approvals took one: "
           "approve without it, or revise with it")
OPERATOR_CONTEXT_VERSION = 1
OPERATOR_NOTES_BUDGET = 64 * 1024
OPERATOR_HISTORY_VERSION = 1
OPERATOR_NOTE_MAX_BYTES = 1024 * 1024
REVIEW_MILESTONES_VERSION = 1
ROLE_ACTIVITIES = ("run_role", "run_role_with_operator_context", "run_role_with_operator_history")


def _note_size(value):
    return len(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _note_refs(notes):
    return [dict({key: note[key] for key in ("stop", "phase", "action", "role")},
                 sha256=hashlib.sha256(note["text"].encode("utf-8")).hexdigest()) for note in notes]


def _has_operator_context(state):
    return "operator_notes" in state or "operator_note_refs" in state


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
# What a Stop says, in Temporal's own record of the cancellation, when the operator rejected the run: the run
# then ends `REJECTED` rather than `STOPPED`. The Stop is the same one, and commands nothing more.
REJECT = "rejected by the operator"


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
        self.review_rounds = None
        self.stop = None
        self.answer_given = None
        self.stops = 0
        self.lines = []
        self.timeline = []
        self.stopping = False
        self.conflict_reopens = True
        self.configuration_revision = 0
        self.operator_notes = []
        self.review_milestones = False

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
        # Runs already in Temporal keep the policy and max_rounds behavior recorded at their start.
        # Only starts carrying the new settings opt into this versioned routing path.
        if "review_rounds" in self.policy and workflow.patched("review-rounds-with-convergence-extension"):
            self.review_rounds = self.policy["review_rounds"]
        repository = start["repository"]
        s = self.state = {"run_id": start["run_id"], "task": start["task"], "label": start["label"],
                          "created": start["created"], "auto_proceed": start["auto_proceed"],
                          "repo": repository["id"], "target": repository["target"], "status": "RUNNING"}
        if "merge_version" in start and (type(start["merge_version"]) is not int or
                start["merge_version"] != landing.VERSION or not isinstance(start.get("short_name"), str)):
            s.update(status="REFUSED", refusal="unsupported named-start protocol or missing short name")
            return s
        if start.get("merge_version") == landing.VERSION:
            s.update(short_name=start["short_name"], merge_version=landing.VERSION)
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
            preparation = {"repository": repository, "policy": self.policy}
            prepare_activity = "prepare"
            if start.get("merge_version") == landing.VERSION:
                preparation["merge_version"] = landing.VERSION
                preparation["short_name"] = start["short_name"]
                preparation["run_id"] = start["run_id"]
                prepare_activity = "prepare_named"
            s.update(await self._activity(prepare_activity, preparation,
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
        if self.review_rounds:
            s.update(convergence=None, convergence_seen=[])
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
                        # The legacy prompt path carried only the note approving this stage.
                        note = (answer.get("text") or "").strip()
                        if note and not _has_operator_context(s) and workflow.patched(APPROVE_WITH_A_NOTE):
                            s["guidance"] = "The %s was approved, with this note for the work after it:\n\n%s" % (
                                work, note)
                    review_next = not stands      # the plan changed: the architect judges it again
                    continue
                # Guidance starts a new bounded episode, with no work turn first when sent to the architect.
                s.update(guidance="" if _has_operator_context(s) else answer["text"],
                         round=0, gate_reason="", episode=s["episode"] + 1)
                if self.review_rounds:
                    s.update(convergence=None, convergence_seen=[])
                review_next = bool(review) and answer.get("role") == "architect"
                continue
            if review and s["verdict"] != "PASS":
                continue
            if gate == "merge":
                s["step"] = segment["gate"][0]
                outcome = await self._final_gate()
                if outcome == "done":
                    return s
                if work in stages.FINAL:
                    # The change is open again: back to the build this work made final, which is made
                    # final anew once the architect passes it.
                    at -= 1
                    s["phase"] = self.segments[at]["work"][1]
                review_next = outcome == "review"
                continue
            stands = await self._plan_stands() if work == "plan" else True
            if stands is None:
                return await self._end("ABORTED")
            if stands:
                if last:
                    return await self._end("DONE")
                if self.segments[at + 1]["work"][1] in stages.FINAL:
                    # Before a build is made final it stands on the base as it is: a base that moved is
                    # brought in, and what it makes of the build is judged before anything goes on.
                    based = await self._reconcile()
                    if based is None:
                        return await self._end("ABORTED")
                    if based != "stands":
                        review_next = based == "review"
                        continue
                at += 1
                await self._next(self.segments[at]["work"][1])
            review_next = not stands

    def _approval(self, work, last, onward):
        """What an approval shows besides the run's own feedback — after research, its brief — and where
        approving goes: on to `onward`, or to the run's end."""
        going = "end the run" if last else "go on to the %s" % onward
        # Whether approving takes a note, the stop says: never at the run's end, which leaves no stage to read
        # one, nor in a run recorded before notes — and a stop that does not say so is sent none, so no client
        # hands a note to a worker that would drop it unsaid.
        noted = {} if last or not workflow.patched(APPROVE_WITH_A_NOTE) else {"noted": True}
        if work in stages.ANSWERS:
            return dict(noted, text=self.state.get("brief") or "",
                        hint="approve to %s, or revise with feedback for new research" % going)
        if work == "plan" and onward == "build":
            return noted                  # HINTS["approval"], as a plan's approval has always read
        return dict(noted, hint="approve to %s, or revise with feedback for a new %s" % (going, work))

    async def _stage(self, stage, gate=None, onward=None):
        """Run one stage to a result, stopping for the operator on each failure. False when aborted.

        A review's verdict is routed by `gate`, the operator's step after it, and a PASS goes `onward`."""
        s = self.state
        label = "[%s e%d r%d]" % (stage, s["episode"], s["round"] + 1)
        self._unless_stopping()
        self._line("%s %s started" % (label, stages.STAGE_ROLE[stage]))
        self._doing(stage, stages.STAGE_ROLE[stage])
        result = await self._until_done(label, lambda: workflow.execute_activity(
            ROLE_ACTIVITIES[2] if "operator_note_refs" in s else
            ROLE_ACTIVITIES[1] if "operator_notes" in s else ROLE_ACTIVITIES[0],
            {"stage": stage, "state": s, "policy": self.policy, "gate": gate},
            task_queue=self.queue,
            start_to_close_timeout=timedelta(seconds=self.policy["timeout_seconds"] + 600),
            heartbeat_timeout=timedelta(seconds=self.policy["heartbeat_seconds"]),
            retry_policy=ONCE))
        if result is None:
            return False
        s["agent_sessions"] = dict(s.get("agent_sessions") or {}, **result["agent_sessions"])
        if self.review_rounds and s.get("convergence") and s["convergence"].get("phase") == s["phase"]:
            role = stages.STAGE_ROLE[stage]
            seen = list(s.get("convergence_seen") or [])
            if role not in seen:
                seen.append(role)
            s["convergence_seen"] = seen
        entry = {"stage": stage, "phase": s["phase"], "episode": s["episode"], "round": s["round"] + 1,
                 "at": workflow.now().isoformat()}
        if "verdict" in result:
            rounds = s["round"] + 1
            phase_rounds = s.get("phase_rounds", 0) + 1
            if self.review_rounds:
                thresholds = self.review_rounds[s["phase"]]
                limit = thresholds["normal"] + thresholds["extended"]
            else:
                limit = self.policy["max_rounds"][s["phase"]]
            reason = routing.gate_reason_for(result["verdict"], gate, rounds, limit, s["auto_proceed"])
            s.update(verdict=result["verdict"], feedback=result["feedback"], round=rounds,
                     phase_rounds=phase_rounds, guidance="", gate_reason=reason)
            if self.review_rounds:
                if (result["verdict"] not in ("PASS", "BLOCKER") and
                        rounds == thresholds["normal"] and thresholds["extended"] > 0):
                    s.update(convergence={"phase": s["phase"], "round": rounds}, convergence_seen=[])
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
            # What the final gate holds from here on: the operator judges it, and a merge commits it or
            # refuses. `closeout_tree` is what the first closeouts named it, in the runs recorded then; those
            # resolved a merge's conflict without reopening the change, so a run holding a tree so named
            # still does, and replays.
            for name in ("final_tree", "closeout_tree"):
                if name in result:
                    s["final_tree"] = result[name]
                    self.conflict_reopens = name == "final_tree"
                    s.pop("commit_draft", None)
                    if "commit_draft" in result:
                        s["commit_draft"] = result["commit_draft"]
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
        if self.review_rounds:
            s.update(convergence=None, convergence_seen=[])
        return False

    async def _next(self, work):
        """On to the flow's next work stage, in a phase of its own."""
        s = self.state
        if "merge_version" in s or "merge_choice" in s:
            s.pop("merge_choice", None)
            s.pop("commit_draft", None)
        # Routing hints and reviewer feedback end here; original operator notes retain their phase provenance.
        s.update(phase=work, round=0, feedback="", guidance="", gate_reason="", episode=s["episode"] + 1)
        if work not in stages.FINAL:
            # The work that makes a build final judges nothing, and a change sent back returns to that
            # build: its count of judgements stays for it.
            s["phase_rounds"] = 0
        if self.review_rounds:
            s.update(convergence=None, convergence_seen=[])
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
                if not await self._reopened():
                    continue
                # A defect found at the gate goes back into the run, to the role the operator names.
                s.update(status="RUNNING", guidance="" if _has_operator_context(s) else answer["text"],
                         round=0, gate_reason="",
                         episode=s["episode"] + 1)
                if self.review_rounds:
                    s.update(convergence=None, convergence_seen=[])
                s.pop("merge_choice", None)
                return "review" if answer["role"] == "architect" else "build"
            if answer.get("landing"):
                selected = answer["landing"]
                attempt = s.get("merge_attempt") if s.get("merge_choice") else answer["stop"]
                s.update(merge_choice=selected, merge_attempt=attempt,
                         merge_execution=workflow.info().run_id, base_branch=selected["branch"],
                         remote=selected["remote"], remote_id=answer["landing_pin"].get("remote_id"),
                         prepush_id=answer["landing_pin"].get("prepush_id"))
            self._doing("merge")
            merged = await self._until_done("merge", lambda: self._git("merge", {"state": s}))
            if merged is None:
                continue
            if merged["result"] == "merged":
                if merged.get("onto"):
                    # No role's turn for a merge git makes by itself: the run says what was landed.
                    self._line("%s had moved since this change was judged on it: git merged the two without a "
                               "conflict" % s["base_branch"])
                s.update(status="MERGED", merge_commit=merged["commit"])
                self._line("MERGED %s" % merged["commit"])
                return "done"
            if merged["result"] == "moved":
                # The base is no longer where this change was judged, and git cannot merge the two — a
                # conflict, or a base that dropped the commit: nothing was merged. The change goes back as
                # one sent back does, the base is brought in, and the two are resolved and judged.
                self._line("%s moved since this change was judged on it: nothing merged" % s["base_branch"])
                if not await self._reopened():
                    continue
                based = await self._reconcile()
                if based is None:
                    continue
                if based == "stands":
                    s.update(status="RUNNING", round=0, gate_reason="", guidance="", episode=s["episode"] + 1)
                return "build" if based == "build" else "review"
            if merged["result"] == "conflict":
                self._line("merge conflict: %s" % ", ".join(merged["files"]))
                # The conflict goes back to the run's agents, never resolved here — reopened first, as a
                # change sent back is: its todo is closed out in the run's commit, and the roles that
                # resolve and verify are asked to read it where it was. Bar the tree the first closeouts
                # left (`_stage`), which is only let go of.
                if not self.conflict_reopens:
                    s.pop("final_tree", None)
                elif not await self._reopened():
                    continue
                s.update(status="RUNNING", round=0, gate_reason="", episode=s["episode"] + 1,
                         guidance="Merging %s conflicts with %s. The base branch is merged into this "
                                  "worktree with conflict markers in: %s. Resolve every conflict in the "
                                  "files; do not stage or commit." % (
                                      s["run_id"], s["base_branch"], ", ".join(merged["files"])))
                if self.review_rounds:
                    s.update(convergence=None, convergence_seen=[])
                return "build"
            s["merge_refusal"] = merged["reason"]
            self._line("merge refused: %s" % merged["reason"])

    async def _reconcile(self):
        """Is the base still where this run stands on it? "stands" when it is — and for a run that recorded
        no tip, which began before runs did. When it moved it is brought into the worktree: "review" where
        git merged it without a conflict, for the architect to judge the two together; "build" where it left
        conflicts, for the engineer. None when the step was aborted."""
        s = self.state
        if not s.get("base_tip"):
            return "stands"
        self._doing("reconcile")
        came = await self._until_done("reconcile", lambda: self._git("reconcile", {"state": s}))
        if came is None:
            return None
        if not came["moved"]:
            return "stands"
        s["base_tip"] = came["base_tip"]
        if came["files"]:
            self._line("%s moved: merged into the worktree with conflicts in %s"
                       % (s["base_branch"], ", ".join(came["files"])))
            guidance = ("%s moved while this change was made. It is merged into this worktree with conflict "
                        "markers in: %s. Resolve every conflict in the files; do not stage or commit."
                        % (s["base_branch"], ", ".join(came["files"])))
        else:
            self._line("%s moved: merged into the worktree without a conflict" % s["base_branch"])
            guidance = ("%s moved while this change was made, and is merged into this worktree without a "
                        "conflict. Judge the change as it now stands on it." % s["base_branch"])
        s.update(status="RUNNING", round=0, gate_reason="", episode=s["episode"] + 1, guidance=guidance)
        if self.review_rounds:
            s.update(convergence=None, convergence_seen=[])
        return "build" if came["files"] else "review"

    async def _reopened(self):
        """Before a change the final gate held goes back into its run: the worktree taken from the tree it
        was offered in to the one the architect verified, so every role reads the todo where it is asked to.
        True once that is so — at once for a run that holds no final tree; False when the step was aborted."""
        s = self.state
        if not s.get("final_tree"):
            return True
        self._doing("reopen")
        reopened = await self._until_done("reopen", lambda: self._git("reopen", {"state": s}))
        if reopened is None:
            return False
        s.pop("final_tree")
        if reopened["kept"]:
            self._line("reopened; changed again since it was offered, and left as they are: %s"
                       % ", ".join(reopened["kept"]))
        return True

    async def _stop(self, reason, text=None, hint=None, noted=False):
        s = self.state
        self._unless_stopping()
        self.stops += 1
        feedback = text if text is not None else {"failed": s.get("error"), "final": s.get("merge_refusal")}.get(
            reason, s.get("feedback"))
        actions = list(ACTIONS[reason])
        if reason in GUIDED and workflow.patched(GUIDE_THE_ARCHITECT):
            actions.append("guide:architect")
        self.stop = {"id": "%s:%d" % (s["run_id"], self.stops), "reason": reason, "phase": s.get("phase"),
                     "todo": s.get("todo_path"), "feedback": feedback or "", "hint": hint or HINTS[reason],
                     "actions": actions, "since": workflow.now().isoformat()}
        if noted:
            self.stop["noted"] = True
        self._line("stopped: %s" % reason)
        if reason in TRACED_STOPS:
            await self._trace("record_stop", {"state": s, "stop": self.stop})
        await workflow.wait_condition(lambda: self.answer_given is not None)
        answer, self.answer_given, self.stop = self.answer_given, None, None
        if self.review_milestones:
            self._doing("review-checkpoint")
            try:
                checkpoint = await workflow.execute_activity(
                    "review_checkpoint", {"worktree_path": s.get("worktree_path"), "base": s.get("base_tip"),
                                          "owner": workflow.info().run_id, "stop": answer["stop"]},
                    task_queue=self.queue, retry_policy=ONCE, start_to_close_timeout=timedelta(seconds=90),
                    schedule_to_start_timeout=timedelta(seconds=10))
            except ActivityError as error:
                if is_cancelled_exception(error):
                    raise
                checkpoint = {"unavailable": _message(error)}
            if checkpoint.get("unavailable"):
                self._line("review checkpoint unavailable: " + checkpoint["unavailable"])
        if reason in TRACED_STOPS:
            said = answer.get("text") or answer["action"]
            if answer["action"] == "approve" and answer.get("text"):
                said = "approve: " + said         # a note with it, never mistaken for a revision
            await self._trace("record_answer", {"state": s, "answer": said})
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
        # The Stop's own reason, as Temporal recorded it with the cancellation, names how the run ended.
        s["status"] = "REJECTED" if workflow.cancellation_reason() == REJECT else "STOPPED"
        self._line(s["status"])

    def _configuration(self):
        policy = self.policy or {}
        engineer = (policy.get("roles") or {}).get("engineer") or {}
        return {"revision": self.configuration_revision, "timeout_seconds": policy.get("timeout_seconds"),
                "engineer": {key: engineer[key] for key in ("agent", "kind", "brain", "model", "provider", "launcher")
                             if key in engineer}}

    @workflow.update
    def use_engineer_defaults(self, request):
        previous = self.policy["roles"]["engineer"]
        engineer = dict(request["engineer"])
        if "persona" in previous:
            engineer["persona"] = previous["persona"]
        changed_role = engineer != previous
        changed = changed_role or request["timeout_seconds"] != self.policy["timeout_seconds"]
        if changed:
            self.policy = dict(self.policy, roles=dict(self.policy["roles"], engineer=engineer),
                               timeout_seconds=request["timeout_seconds"])
            if changed_role:
                self.state["agent_sessions"] = {key: value for key, value in
                    (self.state.get("agent_sessions") or {}).items() if key != "engineer"}
            self.configuration_revision += 1
            self._line("engineer uses %s (%s); turn limit %ds; %s; still waiting at %s" % (
                engineer["agent"], engineer["kind"], request["timeout_seconds"],
                "fresh engineer session next turn" if changed_role else "engineer session retained", self.stop["id"]))
        return dict(self._configuration(), changed=changed)

    @use_engineer_defaults.validator
    def _validate_engineer_defaults(self, request):
        if (not isinstance(request, dict) or self.stopping or self.stop is None or self.answer_given is not None or
                request.get("stop") != self.stop["id"]):
            raise ValueError("the run must still be waiting at the named stop")
        if set(request) != {"stop", "revision", "engineer", "timeout_seconds"}:
            raise ValueError("name only the stop, configuration revision, engineer and turn limit")
        if type(request["revision"]) is not int or request["revision"] != self.configuration_revision:
            raise ValueError("the run's configuration changed; read it again")
        if type(request["timeout_seconds"]) is not int or request["timeout_seconds"] < 1:
            raise ValueError("the turn limit must be a positive integer in seconds")
        engineer = request["engineer"]
        if (not isinstance(engineer, dict) or engineer.get("workspace_access") != P.ROLE_ACCESS["engineer"] or
                not all(isinstance(engineer.get(key), str) and P.NAME.fullmatch(engineer[key]) for key in ("kind", "agent")) or
                not isinstance(engineer.get("persona"), str) or
                len(engineer["persona"].encode("utf-8")) > P.MAX_PERSONA_BYTES):
            raise ValueError("the engineer must be a validated writing profile with its bounded persona")

    @workflow.update
    async def adopt_todo_name(self, request):
        try:
            resolved = await workflow.execute_activity(
                "adopt_todo_name", {"state": dict(self.state), "name": request["name"]}, task_queue=self.queue,
                schedule_to_close_timeout=SHORT_TIMEOUT, retry_policy=READS)
        except ActivityError as error:
            raise ApplicationError(_message(error), type="TodoNameRefused", non_retryable=True) from error
        # The stop may have been answered while its host checked the tree. Never retarget a running turn.
        try:
            self._validate_todo_name(request)
        except ValueError as error:
            raise ApplicationError(str(error), type="TodoNameRefused", non_retryable=True) from error
        changed = resolved["todo_path"] != self.state["todo_path"]
        if changed:
            self.state.update(plan=resolved["plan"], todo_path=resolved["todo_path"])
            self.stop["todo"] = resolved["todo_path"]
            self._line("adopted verified todo name: %s; still waiting at %s" % (resolved["plan"], self.stop["id"]))
        return dict(resolved, changed=changed)

    @adopt_todo_name.validator
    def _validate_todo_name(self, request):
        if (not isinstance(request, dict) or self.stopping or self.stop is None or self.answer_given is not None
                or self.stop["reason"] != "failed" or self.stop["phase"] not in stages.FINAL
                or request.get("stop") != self.stop["id"]):
            raise ValueError("the run must still be waiting at the named failed closeout")
        if set(request) != {"stop", "plan", "name"} or request["plan"] != self.state.get("plan"):
            raise ValueError("the saved todo path changed; read the run again")
        if not isinstance(request["name"], str) or not 1 <= len(request["name"]) <= 255:
            raise ValueError("name the verified todo's filename")

    def _operator_note(self, answer):
        text = answer.get("text") or ""
        if text.strip() and (answer["action"] in ("guide", "revise") or
                             answer["action"] == "approve" and self.stop.get("noted")):
            return {"stop": answer["stop"], "phase": self.state.get("phase"),
                    "action": answer["action"], "role": answer.get("role"), "text": text}
        return None

    @workflow.update
    def answer(self, answer):
        if "landing" in answer:
            raise ValueError("use the supported final Merge Update for destination/message edits")
        return self._accept_answer(answer)

    @workflow.update
    async def answer_merge(self, answer):
        try:
            pin = await workflow.execute_activity(
                "validate_merge_choice", {"state": dict(self.state), "choice": answer["landing"]},
                task_queue=self.queue, schedule_to_close_timeout=SHORT_TIMEOUT, retry_policy=READS)
        except ActivityError as error:
            raise ApplicationError(_message(error), type="MergeChoiceRefused", non_retryable=True) from error
        self._validate_merge_answer(answer)
        return self._accept_answer(dict(answer, landing_pin=pin))

    @answer_merge.validator
    def _validate_merge_answer(self, answer):
        if not answer.get("landing"):
            raise ValueError("name the confirmed final Merge destination and messages")
        self._validate_answer(answer)

    def _accept_answer(self, answer):
        note = self._operator_note(answer)
        if note is not None:
            self.operator_notes.append(note)
        # Older accepted answers reconstruct the originals during replay without changing old commands.
        # A newly recorded protocol version promotes them into subsequent activity inputs, including Continue.
        if answer.get("operator_context_version") == OPERATOR_CONTEXT_VERSION:
            refs = self._history_refs(answer, self.operator_notes)
            if refs is not None:
                self.state.pop("operator_notes", None)
                self.state["operator_note_refs"] = refs
            else:
                self.state["operator_notes"] = list(self.operator_notes)
        if (type(answer.get("review_milestones_version")) is int and
                answer["review_milestones_version"] == REVIEW_MILESTONES_VERSION):
            self.review_milestones = True
        self.answer_given = answer
        return {"stop": answer["stop"], "action": answer["action"]}

    def _history_refs(self, answer, notes):
        if ("operator_note_refs" in self.state or
                type(answer.get("operator_history_version")) is int and
                answer["operator_history_version"] == OPERATOR_HISTORY_VERSION and
                _note_size(notes) > OPERATOR_NOTES_BUDGET):
            return _note_refs(notes)
        return None

    @answer.validator
    def _validate_answer(self, answer):
        if "landing_pin" in answer:
            raise ValueError("landing evidence is controller-owned")
        if self.state.get("merge_version") == landing.VERSION and answer.get("action") == "merge" and "landing" not in answer:
            raise ValueError("confirm the final Merge destination and valid commit messages")
        if "landing" in answer:
            if answer.get("action") != "merge" or self.stop is None or self.stop["reason"] != "final":
                raise ValueError("destination and messages may change only at an unanswered final gate")
            if answer.get("confirm") is not True:
                raise ValueError("confirm the exact destination and commit messages")
            landing.choice(answer["landing"], self.state)
            if self.state.get("merge_choice") and answer["landing"] != self.state["merge_choice"]:
                raise ValueError("this Merge attempt already froze its destination and messages; "
                                 "Continue it unchanged or revise the change before selecting another destination")
        if "operator_history_version" in answer and (type(answer["operator_history_version"]) is not int or
                answer["operator_history_version"] != OPERATOR_HISTORY_VERSION):
            raise ValueError("unsupported operator-note history transport; reload the Workbench or use the current CLI")
        if "review_milestones_version" in answer and (type(answer["review_milestones_version"]) is not int or
                answer["review_milestones_version"] != REVIEW_MILESTONES_VERSION):
            raise ValueError("unsupported review checkpoint protocol; reload the Workbench or use the current CLI")
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
        if action == "approve" and not stop.get("noted") and (answer.get("text") or "").strip():
            raise ValueError(NO_NOTE)
        if action in ("guide", "revise", "approve") and (answer.get("text") or "").strip():
            if (type(answer.get("operator_context_version")) is not int or
                    answer["operator_context_version"] != OPERATOR_CONTEXT_VERSION):
                raise ValueError("operator guidance was not accepted: reload the Workbench or use the current CLI "
                                 "so the original notes are preserved")
        note = self._operator_note(answer)
        notes = self.operator_notes + ([note] if note is not None else [])
        refs = self._history_refs(answer, notes)
        if note is not None and refs is not None and _note_size(refs) > OPERATOR_NOTES_BUDGET:
            raise ValueError("too many retained operator-note references for this workflow execution; "
                             "this answer was not accepted and earlier notes remain unchanged")
        if note is not None:
            if refs is not None and _note_size(note) > OPERATOR_NOTE_MAX_BYTES:
                raise ValueError("this single operator note exceeds the serialized request limit of %d bytes; "
                                 "this answer was not accepted and earlier notes remain unchanged" % OPERATOR_NOTE_MAX_BYTES)
            size = _note_size(notes)
            if refs is None and size > OPERATOR_NOTES_BUDGET:
                raise ValueError("retained operator notes would use %d bytes; the aggregate limit is %d bytes. "
                                 "This answer was not accepted and earlier notes remain unchanged; "
                                 "reload the Workbench and workers to enable large-note history transport"
                                 % (size, OPERATOR_NOTES_BUDGET))
        if action == "discard" and answer.get("confirm") is not True:
            raise ValueError("discard deletes the worktree and its branch, so it must be confirmed")

    @workflow.query
    def status(self):
        # Both queues the run needs: its target host's, and the one it runs on, its policy's own.
        return {"state": self.state, "stop": self.stop, "lines": self.lines, "timeline": self.timeline,
                "queue": self.queue, "workflow_queue": workflow.info().task_queue,
                "operator_context_version": OPERATOR_CONTEXT_VERSION,
                "operator_history_version": OPERATOR_HISTORY_VERSION,
                "review_milestones_version": REVIEW_MILESTONES_VERSION,
                "merge_version": landing.VERSION,
                "configuration": self._configuration()}


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
        if args.get("protocol_probe") == landing.VERSION:
            return {"merge_version": landing.VERSION}
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
