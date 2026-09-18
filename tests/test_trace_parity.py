"""The run writes the trace its contract fixes, row by row, and never writes a row twice.

The expected rows for one scenario are kept in `fixtures/trace_rows.json`, and this run is
compared with them row by row. Rows are written only
by activities that are never retried, so neither a replayed workflow task nor a retry can
repeat one. The control writes a row from workflow code, and replay writes it again.
"""
import asyncio
import json
import os
import sys
import time
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

from temporalio.api.enums.v1 import EventType  # noqa: E402
from temporalio.worker import Replayer  # noqa: E402

import control_trace_sink  # noqa: E402
import control_workflows  # noqa: E402
import temporal_env as E  # noqa: E402
import trace_rows  # noqa: E402
import workflow as WF  # noqa: E402
from fakes import Recorder  # noqa: E402
from test_workflow import Scenario  # noqa: E402

SCHEDULED = EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED
TRACE_ACTIVITIES = {"open_run", "open_phase", "record_stop", "record_answer", "finish_trace"}


class TraceParity(Scenario):
    def traced_run(self):
        self.recorder = Recorder()
        run = self.drive(trace_rows.script(), telemetry=self.recorder)
        self.assertEqual(run.stop["reason"], "approval")
        code, out = run.answer("yes")
        self.assertEqual((code, run.stop["reason"]), (0, "final"), out)
        return run

    def test_the_temporal_run_writes_the_graphs_rows(self):
        self.traced_run()
        with open(os.path.join(HERE, trace_rows.GOLDEN), encoding="utf-8") as fh:
            expected = json.load(fh)
        got = trace_rows.reduce(self.recorder)
        self.assertEqual([row["name"] for row in got["rows"]], [row["name"] for row in expected["rows"]])
        for index, (row, want) in enumerate(zip(got["rows"], expected["rows"])):
            self.assertEqual(row, want, "row %d, %s" % (index, want["name"]))
        self.assertEqual(got["scores"], expected["scores"])

    def test_the_trace_names_the_runs_repository_and_target_never_this_processs(self):
        """Repo, target and base branch come from the descriptor and the run's target."""
        import telemetry
        from fakes import FakeRepos, codex_review_first
        recorder = Recorder()
        a1, _ = codex_review_first("PASS")
        self.host, self.agent = E.host([("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, a1)],
                                       repositories=FakeRepos(), telemetry=recorder, queue=E.WINDOWS_QUEUE)
        run = E.Run(target="windows", repo="example")
        self.addCleanup(run.cleanup)
        work_item = recorder.events[0]
        self.assertEqual(work_item["name"], "orchestration-run")
        self.assertEqual({key: work_item["input"][key] for key in ("repo", "target", "base_branch")},
                         {"repo": "example", "target": "windows", "base_branch": "develop"})
        self.assertEqual(telemetry.tags(run.state)[1:3], ["repo:example", "target:windows"])
        saved = os.environ.get("LANGFUSE_RELEASE")
        os.environ["LANGFUSE_RELEASE"] = "0123456789ab"
        try:
            self.assertEqual(telemetry.harness_env({"brain": "claude"}, telemetry._Span(traceparent="00-%032x-%016x-01" % (1, 2)),
                                                   run.state, "plan", "engineer")["LANGFUSE_RELEASE"], "0123456789ab",
                             "release stays the orchestration code's revision, whatever the repository")
        finally:
            if saved is None:
                os.environ.pop("LANGFUSE_RELEASE", None)
            else:
                os.environ["LANGFUSE_RELEASE"] = saved

    def test_no_trace_write_is_ever_retried(self):
        run = self.traced_run()
        scheduled = [event.activity_task_scheduled_event_attributes
                     for event in E.run(run.handle.fetch_history()).events if event.event_type == SCHEDULED]
        traced = [attrs for attrs in scheduled if attrs.activity_type.name in TRACE_ACTIVITIES]
        self.assertTrue(traced)
        for attrs in traced:
            self.assertEqual(attrs.retry_policy.maximum_attempts, 1, attrs.activity_type.name)

    def test_replaying_a_run_writes_no_row(self):
        run = self.traced_run()
        rows = len(self.recorder.events)
        history = E.run(run.handle.fetch_history())
        asyncio.run(Replayer(workflows=[WF.FeatureRun]).replay_workflow(history))
        self.assertEqual(len(self.recorder.events), rows)

    def test_control_a_row_written_from_workflow_code_is_written_again_on_replay(self):
        control_trace_sink.ROWS.clear()
        handle = E.run(E.client().start_workflow(control_workflows.TelemetryInWorkflow.run, {},
                                                 id="trace-control-%s" % uuid.uuid4().hex[:8],
                                                 task_queue=WF.TASK_QUEUE))
        deadline = time.monotonic() + 30
        while E.run(handle.describe()).close_time is None and time.monotonic() < deadline:
            time.sleep(0.2)
        self.assertEqual(len(control_trace_sink.ROWS), 1)
        history = E.run(handle.fetch_history())
        asyncio.run(Replayer(workflows=[control_workflows.TelemetryInWorkflow]).replay_workflow(history))
        self.assertEqual(len(control_trace_sink.ROWS), 2, "replay ran the workflow code, and the row, again")


if __name__ == "__main__":
    unittest.main()
