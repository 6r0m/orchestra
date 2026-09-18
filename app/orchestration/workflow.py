"""The workflow of one run: plan and assess, the approval, build and verify, the final gate.

Temporal owns it: one workflow execution per run, its Workflow Id the run id. The code
here decides every transition, deterministically — no clock, file, network or process;
every effect is an activity on the run's target host, and every route comes from
`routing`.

A stop waits for an Update carrying one of that stop's named actions, with the stable id
`answer:<stop-id>`, so a repeated answer is applied once. The run's
state, its console lines and its timeline are read through the `status` query.
"""
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, TimeoutError

with workflow.unsafe.imports_passed_through():
    from app.foundation import policy as P
    from app.orchestration import routing

NAMESPACE = "orchestration"
TASK_QUEUE = "orchestration"

# A role-run and every git side effect run once; only reads retry.
ONCE = RetryPolicy(maximum_attempts=1)
READS = RetryPolicy(maximum_attempts=3)
GIT_TIMEOUT = timedelta(hours=2)
SHORT_TIMEOUT = timedelta(minutes=10)

ACTIONS = {
    "approval": ("approve", "revise", "abort"),
    "blocker": ("guide", "abort"),
    "exhausted": ("guide", "abort"),
    "failed": ("continue", "abort"),
    "final": ("merge", "revise", "discard"),
}
HINTS = {
    "approval": "approve to start implementation, revise with feedback for a new plan, or abort",
    "blocker": "guide with your decision to continue, or abort",
    "exhausted": "guide with your decision to continue, or abort",
    "failed": "fix the cause, then continue to run the stage again, or abort",
    "final": "merge into the base branch, revise with feedback to the engineer or the architect, "
             "or discard the worktree",
}
# The stops the trace records, as it always has; the others are the workflow's own.
TRACED_STOPS = ("approval", "blocker", "exhausted")


def _message(error):
    cause = error.cause if isinstance(error, ActivityError) and error.cause else error
    if isinstance(cause, TimeoutError) and cause.type is not None:
        # A heartbeat timeout is how a lost worker shows: say which clock ran out.
        return "%s timeout: the worker running this step stopped responding or ran out of time" % (
            cause.type.name.lower().replace("_", "-"))
    return str(getattr(cause, "message", None) or cause)


@workflow.defn
class FeatureRun:
    def __init__(self):
        self.state = {}
        self.queue = None
        self.policy = None
        self.stop = None
        self.answer_given = None
        self.stops = 0
        self.lines = []
        self.timeline = []

    @workflow.run
    async def run(self, start):
        self.policy, self.queue = start["policy"], start["queue"]
        repository = start["repository"]
        s = self.state = {"run_id": start["run_id"], "task": start["task"], "label": start["label"],
                          "created": start["created"], "auto_proceed": start["auto_proceed"],
                          "repo": repository["id"], "target": repository["target"], "status": "RUNNING"}
        try:
            s.update(await self._activity("prepare", {"repository": repository, "policy": self.policy},
                                          READS, SHORT_TIMEOUT))
        except ActivityError as error:
            s.update(status="REFUSED", refusal=_message(error))
            self._line("refused: %s" % s["refusal"])
            return s
        created = await self._until_done("setup", lambda: self._activity(
            "create_worktree", {"state": s}, ONCE, GIT_TIMEOUT))
        if created is None:
            return await self._end("ABORTED")
        s.update(created)
        s.update(await self._trace("open_run", {"state": s}) or {})
        s.update(phase="plan", round=0, phase_rounds=0, episode=1, agent_sessions={})
        return await self._loop()

    async def _loop(self):
        s = self.state
        review_next = False
        while True:
            worker, reviewer = ("plan", "assess") if s["phase"] == "plan" else ("build", "verify")
            if not review_next and not await self._stage(worker):
                return await self._end("ABORTED")
            review_next = False
            if not await self._stage(reviewer):
                return await self._end("ABORTED")
            if s["gate_reason"]:
                answer = await self._stop(s["gate_reason"])
                if answer["action"] == "abort":
                    return await self._end("ABORTED")
                if answer["action"] == "approve":
                    stands = await self._plan_stands()
                    if stands is None:
                        return await self._end("ABORTED")
                    if stands:
                        await self._to_build()
                    review_next = not stands      # the plan changed: the architect judges it again
                    continue
                # Guidance, or a revised plan: a new bounded episode. The operator's words
                # survive the worker and are consumed by the architect that judges next.
                s.update(guidance=answer["text"], round=0, gate_reason="", episode=s["episode"] + 1)
                continue
            if s["verdict"] != "PASS":
                continue
            if s["phase"] == "plan":
                stands = await self._plan_stands()
                if stands is None:
                    return await self._end("ABORTED")
                if stands:
                    await self._to_build()
                review_next = not stands
                continue
            outcome = await self._final_gate()
            if outcome == "done":
                return s
            if outcome == "abort":
                return await self._end("ABORTED")
            review_next = outcome == "review"

    async def _stage(self, stage):
        """Run one stage to a result, stopping for the operator on each failure. False when aborted."""
        s = self.state
        label = "[%s e%d r%d]" % (stage, s["episode"], s["round"] + 1)
        self._line("%s %s started" % (label, P.STAGE_ROLE[stage]))
        result = await self._until_done(label, lambda: workflow.execute_activity(
            "run_role", {"stage": stage, "state": s, "policy": self.policy}, task_queue=self.queue,
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
            gate = routing.gate_reason_for(result["verdict"], s["phase"], rounds,
                                           self.policy["max_rounds"][s["phase"]], s["auto_proceed"])
            s.update(verdict=result["verdict"], feedback=result["feedback"], round=rounds,
                     phase_rounds=s.get("phase_rounds", 0) + 1, guidance="", gate_reason=gate)
            for judged in ("assessed_tree", "verified_tree"):
                if judged in result:
                    s[judged] = result[judged]
            self._line("%s %s -> %s" % (label, result["verdict"],
                                        routing.route_label(stage, result["verdict"], gate)))
            entry.update(verdict=result["verdict"], gate=gate, feedback=result["feedback"])
        else:
            self._line("%s completed" % label)
        self.timeline.append(entry)
        return True

    async def _until_done(self, label, attempt):
        """Await `attempt`; on a failure stop for the operator, who continues it or aborts."""
        s = self.state
        while True:
            try:
                return await attempt()
            except ActivityError as error:
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

    async def _to_build(self):
        s = self.state
        s.update(phase="build", round=0, phase_rounds=0, feedback="", gate_reason="",
                 episode=s["episode"] + 1)
        opened = await self._trace("open_phase", {"state": s, "phase": "build"})
        s["trace_phases"] = dict(s.get("trace_phases") or {}, build=(opened or {}).get("id"))

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
                if await self._until_done("discard", lambda: self._activity(
                        "discard", {"state": s}, ONCE, GIT_TIMEOUT)) is None:
                    continue
                s["status"] = "DISCARDED"
                self._line("DISCARDED")
                return "done"
            if answer["action"] == "revise":
                # A defect found at the gate goes back into the run, to the role the operator names.
                s.update(status="RUNNING", guidance=answer["text"], round=0, gate_reason="",
                         episode=s["episode"] + 1)
                return "review" if answer["role"] == "architect" else "build"
            merged = await self._until_done("merge", lambda: self._activity(
                "merge", {"state": s}, ONCE, GIT_TIMEOUT))
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

    async def _stop(self, reason):
        s = self.state
        self.stops += 1
        feedback = {"failed": s.get("error"), "final": s.get("merge_refusal")}.get(reason, s.get("feedback"))
        self.stop = {"id": "%s:%d" % (s["run_id"], self.stops), "reason": reason, "phase": s.get("phase"),
                     "todo": s.get("todo_path"), "feedback": feedback or "", "hint": HINTS[reason],
                     "actions": list(ACTIONS[reason])}
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

    async def _activity(self, name, args, retry, timeout):
        return await workflow.execute_activity(name, args, task_queue=self.queue,
                                               start_to_close_timeout=timeout, retry_policy=retry)

    async def _trace(self, name, args):
        """A trace write: best-effort, so its failure costs a row and never the run."""
        try:
            return await self._activity(name, args, ONCE, SHORT_TIMEOUT)
        except ActivityError:
            return None

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
        if action not in stop["actions"]:
            raise ValueError("%r does not answer this stop; answer one of: %s"
                             % (action, ", ".join(stop["actions"])))
        if action in ("guide", "revise") and not (answer.get("text") or "").strip():
            raise ValueError("%s needs the feedback to act on" % action)
        if stop["reason"] == "final" and action == "revise" and answer.get("role") not in ("engineer", "architect"):
            raise ValueError("revise at the final gate names the role: engineer or architect")
        if action == "discard" and answer.get("confirm") is not True:
            raise ValueError("discard deletes the worktree and its branch, so it must be confirmed")

    @workflow.query
    def status(self):
        return {"state": self.state, "stop": self.stop, "lines": self.lines, "timeline": self.timeline,
                "queue": self.queue}


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
