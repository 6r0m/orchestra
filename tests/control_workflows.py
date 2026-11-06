"""Workflows that each lack one guarantee of the real run: the controls that show a test can fail.

- NoValidatorRun: an answer Update with no validator, recording every answer it is sent.
- NoteDroppingRun: an approval stop as a worker that predates notes publishes it, recording every answer.
- RetryControl: a role activity under Temporal's default retry policy.
- ChangedRun: the run with one more activity before each trace write, unpatched.
- TelemetryInWorkflow: a trace row written from workflow code instead of an activity.
"""
from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    import control_trace_sink
    from app.orchestration import workflow as WF


@workflow.defn
class NoValidatorRun:
    def __init__(self):
        self.answers = []
        self.done = False

    @workflow.run
    async def run(self, start):
        await workflow.wait_condition(lambda: self.done)
        return self.answers

    @workflow.update
    def answer(self, answer):
        self.answers.append(answer)
        return len(self.answers)

    @workflow.signal
    def finish(self):
        self.done = True


@workflow.defn
class NoteDroppingRun:
    """A run whose worker predates notes on approvals: its approval stop says nothing of one, and its answer takes an
    approve with words and records it, saying nothing of them — as the workers before `approve-with-a-note` did."""

    def __init__(self):
        self.answers, self.done, self.stop = [], False, None

    @workflow.run
    async def run(self, start):
        self.stop = {"id": "%s:1" % workflow.info().workflow_id, "reason": "approval", "phase": "plan", "todo": None,
                     "feedback": "", "hint": "", "actions": ["approve", "revise"], "since": "2026-11-06T00:00:00"}
        await workflow.wait_condition(lambda: self.done)
        return self.answers

    @workflow.update
    def answer(self, answer):
        self.answers.append(answer)
        return {"stop": answer["stop"], "action": answer["action"]}

    @workflow.query
    def status(self):
        return {"state": {"run_id": workflow.info().workflow_id}, "stop": self.stop, "lines": [], "timeline": [],
                "queue": None, "workflow_queue": workflow.info().task_queue}

    @workflow.signal
    def finish(self):
        self.done = True


@workflow.defn
class RetryControl:
    @workflow.run
    async def run(self, args):
        return await workflow.execute_activity(
            "run_role", args, task_queue=args["queue"],
            start_to_close_timeout=timedelta(seconds=args["policy"]["timeout_seconds"] + 600),
            heartbeat_timeout=timedelta(seconds=args["policy"]["heartbeat_seconds"]))


@workflow.defn(name="FeatureRun")
class ChangedRun(WF.FeatureRun):
    @workflow.run
    async def run(self, start):
        return await super().run(start)

    async def _trace(self, name, args):
        await workflow.sleep(1)
        return await super()._trace(name, args)


@workflow.defn
class TelemetryInWorkflow:
    @workflow.run
    async def run(self, args):
        control_trace_sink.ROWS.append("work item")
        return len(control_trace_sink.ROWS)


ALL = [NoValidatorRun, NoteDroppingRun, RetryControl, TelemetryInWorkflow]
