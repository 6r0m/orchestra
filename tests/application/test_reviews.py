"""Review ranges use retained evidence, refuse unknown/cross-base history and freeze current endpoints."""
import unittest
from unittest.mock import AsyncMock, patch

from app.application import client as runs


class ReviewRanges(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.record = {"review": {"initial": "base", "boundaries": [
            {"stop": "one", "basis": "base", "tree": "first"},
            {"stop": "two", "basis": "base", "tree": "second"},
            {"stop": "three", "basis": "new-base", "tree": "third"}]}}
        self.history = AsyncMock(return_value=self.record)
        self.diff = AsyncMock(return_value={"base": "first", "tree": "second", "patch": "exact net change"})
        self.status = AsyncMock(return_value={"stop": {"id": "waiting"}, "state": {"base_tip": "base"}})
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
        self.diff.side_effect = [{"base": "base", "tree": "sample"},
                                 {"base": "first", "tree": "sample", "patch": "sampled net change"}]
        result = await runs.review_milestone(None, "run", "one", "current")
        self.assertEqual(result["tree"], "sample")
        self.assertTrue(result["review_range"]["current"])
        self.diff.assert_awaited_with(None, "run", base="first", tree="sample")

    async def test_current_export_refuses_an_executing_or_concurrently_answered_stop(self):
        self.status.return_value = {"stop": None}
        with self.assertRaisesRegex(runs.Refusal, "next operator stop"):
            await runs.review_milestone(None, "run", "one", "current")
        self.diff.assert_not_awaited()
        self.status.return_value = None
        self.status.side_effect = [{"stop": {"id": "old"}, "state": {"base_tip": "base"}}, {"stop": None}]
        self.diff.return_value = {"base": "base", "tree": "sample"}
        with self.assertRaisesRegex(runs.Refusal, "run moved"):
            await runs.review_milestone(None, "run", "one", "current")
        self.assertEqual(self.diff.await_count, 1)

    async def test_a_closed_workflow_query_cannot_supply_a_current_operator_stop(self):
        self.execution.return_value = {"execution": "TERMINATED"}
        self.diff.return_value = {"base": "base", "tree": "sample"}
        with self.assertRaisesRegex(runs.Refusal, "run moved"):
            await runs.review_milestone(None, "run", "one", "current")
        self.assertEqual(self.diff.await_count, 1)
