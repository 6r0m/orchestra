"""Recorded histories of full runs replay on the current workflow.

A change to the workflow that alters what it commands must go behind
`workflow.patched`, or these histories stop replaying. Recorded by
`record_histories.py`; the control is the same workflow with one unpatched change.
"""
import asyncio
import glob
import os
import sys
import unittest

# The suite's own folder, reached from this concern's folder inside it, and the
# checkout above both: the shared harness and the fixtures live at the suite root.
HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

from temporalio.client import WorkflowHistory  # noqa: E402
from temporalio.worker import Replayer  # noqa: E402

import control_workflows  # noqa: E402
from app.orchestration import workflow as WF  # noqa: E402

PATHS = sorted(glob.glob(os.path.join(HERE, "histories", "*.json")))


def histories():
    for path in PATHS:
        with open(path, encoding="utf-8") as fh:
            yield WorkflowHistory.from_json(os.path.basename(path), fh.read())


class Replay(unittest.TestCase):
    def test_every_recorded_history_replays_on_the_current_workflow(self):
        self.assertGreaterEqual(len(PATHS), 3, "the recorded histories are missing")
        for history in histories():
            with self.subTest(history.workflow_id):
                asyncio.run(Replayer(workflows=[WF.FeatureRun]).replay_workflow(history))

    def test_a_history_replays_on_its_own_steps_whatever_the_flow_files_say(self):
        """The workflow never reads a flow: a run started before flows replays on the order those runs took,
        though today's `engineer-code` names a different one."""
        import json
        import shutil
        import tempfile
        from app.foundation import flows
        folder = tempfile.mkdtemp(prefix="orch-flows-")
        self.addCleanup(shutil.rmtree, folder, True)
        self.addCleanup(setattr, flows, "FLOWS_DIR", flows.FLOWS_DIR)
        flows.FLOWS_DIR = folder
        with open(os.path.join(folder, "engineer-code.json"), "w", encoding="utf-8") as fh:
            json.dump(["architect:research", "you:approve"], fh)
        for history in histories():
            with self.subTest(history.workflow_id):
                asyncio.run(Replayer(workflows=[WF.FeatureRun]).replay_workflow(history))

    def test_control_an_unpatched_change_fails_replay(self):
        for history in histories():
            with self.subTest(history.workflow_id), self.assertRaises(Exception) as raised:
                asyncio.run(Replayer(workflows=[control_workflows.ChangedRun]).replay_workflow(history))
            self.assertIn("nondetermin", str(raised.exception).lower())


if __name__ == "__main__":
    unittest.main()
