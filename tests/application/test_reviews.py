"""Review ranges use retained evidence, refuse unknown/cross-base history and freeze current endpoints."""
import unittest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

from temporalio.api.history.v1 import HistoryEvent
from temporalio.converter import DataConverter

from app.application import client as runs


class MergeHistory(unittest.IsolatedAsyncioTestCase):
    async def test_only_a_successfully_completed_merge_update_becomes_a_boundary(self):
        converter = DataConverter.default
        events = []
        for number, completion in ((10, None), (20, 'failure'), (30, 'success')):
            event = HistoryEvent(event_id=number)
            request = event.workflow_execution_update_accepted_event_attributes.accepted_request
            request.meta.update_id = 'update-%s' % number
            request.input.name = 'answer_merge'
            request.input.args.payloads.extend(await converter.encode([{'stop': 'stop-%s' % number, 'action': 'merge'}]))
            events.append(event)
            if completion:
                done = HistoryEvent(event_id=number + 1)
                attributes = done.workflow_execution_update_completed_event_attributes
                attributes.meta.update_id = request.meta.update_id
                getattr(attributes.outcome, completion).SetInParent()
                events.append(done)

        async def history():
            for event in events:
                yield event

        client = SimpleNamespace(data_converter=converter,
                                 get_workflow_handle=lambda _: SimpleNamespace(fetch_history_events=history))
        record = await runs.history(client, 'run')
        self.assertEqual([row['stop'] for row in record['answers']], ['stop-30'])
        self.assertEqual([row['stop'] for row in record['review']['boundaries']], ['stop-30'])


class ReviewRanges(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.record = {"review": {"initial": "base", "boundaries": [
            {"stop": "one", "basis": "base", "tree": "first"},
            {"stop": "two", "basis": "base", "tree": "second"},
            {"stop": "three", "basis": "new-base", "tree": "third"}]}}
        self.history = AsyncMock(return_value=self.record)
        self.diff = AsyncMock(return_value={"base": "first", "tree": "second", "patch": "exact net change"})
        self.waiting = {"stop": {"id": "waiting"}, "state": {"base_tip": "base", "worktree_path": "worktree"}}
        self.working = {"stop": None, "state": {"base_tip": "base", "worktree_path": "worktree",
                        "current": {"stage": "build", "role": "engineer", "since": "now"}}}
        self.status = AsyncMock(return_value=self.waiting)
        self.execution = AsyncMock(return_value={"execution": "RUNNING"})
        for name, mock in (("history", self.history), ("review_diff", self.diff), ("readable_status", self.status),
                           ("execution", self.execution)):
            owner = patch.object(runs, name, mock)
            owner.start()
            self.addCleanup(owner.stop)

    async def test_same_base_range_uses_exact_endpoints_without_concatenating_turns(self):
        result = await runs.review_milestone(None, "run", "one", "two")
        self.diff.assert_awaited_once_with(None, "run", base="first", tree="second")
        self.assertEqual(result["patch"], "exact net change")
        self.assertEqual(result["review_range"], {"from": 1, "through": 2, "current": False})

    async def test_cross_base_unknown_and_invalid_ranges_are_refused_before_reading_a_diff(self):
        self.record["review"]["boundaries"].append({"stop": "legacy", "unavailable": "no snapshot"})
        for first, last in (("one", "three"), ("three", "legacy"), ("two", "one"), ("missing", "two")):
            with self.subTest(first=first, last=last), self.assertRaises(runs.Refusal):
                await runs.review_milestone(None, "run", first, last)
        self.diff.assert_not_awaited()

    async def test_current_range_freezes_one_sample_at_a_stable_stop(self):
        self.diff.return_value = {"base": "first", "tree": "sample", "patch": "sampled net change"}
        result = await runs.review_milestone(None, "run", "one", "current")
        self.assertEqual(result["tree"], "sample")
        self.assertTrue(result["review_range"]["current"])
        self.diff.assert_awaited_once_with(None, "run", base="first")

    async def test_current_interval_is_readable_during_either_role_without_an_operator_stop(self):
        self.status.return_value = self.working
        for role in ("engineer", "architect"):
            self.working["state"]["current"]["role"] = role
            with self.subTest(role=role):
                result = await runs.review_milestone(None, "run", "one", "current")
                self.assertTrue(result["review_range"]["current"])
                self.assertEqual(result["base"], "first")
                self.diff.assert_awaited_with(None, "run", base="first")

    async def test_missing_or_cross_base_start_refuses_before_sampling_the_worktree(self):
        self.record["review"]["boundaries"][0] = {"stop": "one", "unavailable": "no checkpoint was recorded"}
        with self.assertRaisesRegex(runs.Refusal, "starting checkpoint.*no checkpoint"):
            await runs.review_milestone(None, "run", "one", "current")
        with self.assertRaisesRegex(runs.Refusal, "crosses a base update"):
            await runs.review_milestone(None, "run", "three", "current")
        self.diff.assert_not_awaited()

    async def test_current_export_refuses_setup_or_concurrently_answered_stop(self):
        self.status.return_value = {"stop": None}
        with self.assertRaisesRegex(runs.Refusal, "role or operator stop"):
            await runs.review_milestone(None, "run", "one", "current")
        self.diff.assert_not_awaited()
        self.status.return_value = None
        self.status.side_effect = [self.waiting, self.working]
        with self.assertRaisesRegex(runs.Refusal, "run moved"):
            await runs.review_milestone(None, "run", "one", "current")
        self.assertEqual(self.diff.await_count, 1)

    async def test_stage_base_or_worktree_changes_invalidate_a_live_sample(self):
        import copy
        for field, value in (("base_tip", "new-base"), ("worktree_path", "other"),
                             ("current", {"stage": "merge", "since": "later"})):
            after = copy.deepcopy(self.working)
            after["state"][field] = value
            self.status.side_effect = [self.working, after]
            with self.subTest(field=field), self.assertRaisesRegex(runs.Refusal, "run moved"):
                await runs.review_milestone(None, "run", "one", "current")

    async def test_a_closed_workflow_query_cannot_supply_a_current_operator_stop(self):
        self.execution.return_value = {"execution": "TERMINATED"}
        with self.assertRaisesRegex(runs.Refusal, "run moved"):
            await runs.review_milestone(None, "run", "one", "current")
        self.assertEqual(self.diff.await_count, 1)
