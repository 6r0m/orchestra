"""Only recorded, attributable generation costs enter the optional operator projection."""
import unittest
from types import SimpleNamespace
from unittest import mock

from app.observability import accounting as A


class Accounting(unittest.TestCase):
    def row(self, id="g", amount=0.1, **changes):
        return dict(dict(id=id, type="GENERATION", parentObservationId="role", totalCost=amount,
                    model="deepseek-flash", usageDetails={"input": 20, "output": 5},
                    usagePricingTierName="peak",
                    metadata={"provider": "deepseek", "pricing_status": "matched", "tariff_period": "peak", "usage_complete": True,
                              "cost_source": "model_price_inference"}), **changes)

    def project(self, *rows):
        parent = {"id": "role", "type": "AGENT", "metadata": {"role": "engineer", "stage": "plan",
                  "episode": 2, "round": 4, "episode_round": 1, "activity_id": "a1"}}
        return A.project([parent, *rows])

    def test_unique_generations_use_stored_cost_and_parent_identity_not_parent_rollups(self):
        result = self.project(self.row(), self.row())
        self.assertEqual(result["total"]["usd"], 0.1)
        self.assertEqual(result["total"]["requests"], 1)
        self.assertEqual(result["turns"]["plan:2:1"]["usd"], 0.1)
        self.assertEqual(result["activities"]["a1"]["tokens"], 25)
        self.assertEqual(result["total"]["provenance"], "estimated")
        self.assertEqual(result["total"]["coverage"], "unknown")

    def test_zero_is_preserved_and_unknown_inference_is_excluded(self):
        zero = self.row(amount=0, metadata={"cost_source": "provider_reported"})
        for amount in (None, -1, True, float("nan"), float("inf")):
            with self.subTest(amount=amount):
                result = self.project(zero, self.row(id="bad", amount=amount))
                self.assertEqual(result["total"]["usd"], 0)
                self.assertEqual(result["total"]["unpriced"], 1)
        result = self.project(self.row(metadata={"pricing_status": "unknown"}))
        self.assertIsNone(result["total"]["usd"])
        self.assertEqual(result["total"]["unpriced"], 1)
        self.assertIsNone(self.project()["total"]["usd"])

    def test_unattributed_requests_remain_visible_and_cycles_terminate(self):
        result = A.project([self.row(parentObservationId="g")])
        self.assertEqual(result["roles"]["unassigned"]["requests"], 1)

    def test_a_direct_tariff_with_a_different_or_unknown_provider_is_excluded(self):
        for provider in ("openrouter", None):
            with self.subTest(provider=provider):
                row = self.row()
                row["metadata"]["provider"] = provider
                result = self.project(row)
                self.assertIsNone(result["total"]["usd"])
                self.assertEqual(result["total"]["unpriced"], 1)
                row["metadata"]["cost_source"] = "provider_reported"
                self.assertEqual(self.project(row)["total"]["usd"], 0.1)

    def test_a_failed_role_upload_marks_the_known_subtotal_partial_without_inventing_requests(self):
        result = A.project([self.row(), {"id": "role", "type": "AGENT", "metadata": {
            "role": "architect", "error_type": "telemetry_degraded"}}])
        self.assertEqual(result["total"]["requests"], 1)
        self.assertTrue(result["total"]["partial"])
        self.assertEqual(result["incomplete_steps"], 1)

    def test_catalog_reference_provenance_survives_every_aggregate(self):
        result = self.project(self.row(model="gpt-6.1-sol", usagePricingTierName="Standard API equivalent"))
        for summary in (result["total"], result["roles"]["engineer"], result["turns"]["plan:2:1"],
                        result["activities"]["a1"]):
            self.assertTrue(summary["api_equivalent"])
        reported = self.project(self.row(amount=0, model="gpt-6.1-sol",
                                usagePricingTierName="Standard API equivalent", metadata={"cost_source": "provider_reported"}))
        self.assertFalse(reported["total"].get("api_equivalent"))

    def test_missing_native_usage_does_not_appear_as_measured_zero_tokens(self):
        unknown = self.project(self.row(usageDetails=None, totalUsage=0, metadata={"usage_complete": False}))
        self.assertTrue(unknown["total"]["tokens_unknown"])
        known = self.project(self.row(usageDetails={"input": 0, "output": 0}, totalUsage=0))
        self.assertFalse(known["total"].get("tokens_unknown"))
        self.assertEqual(known["total"]["tokens"], 0)

    def test_reader_filters_and_paginates_then_keeps_stale_value_on_failure(self):
        api = mock.Mock()
        api.get_many.side_effect = [SimpleNamespace(data=[self.row()], meta=SimpleNamespace(cursor="next")),
                                    SimpleNamespace(data=[], meta=SimpleNamespace(cursor=None)), RuntimeError("offline")]
        client = SimpleNamespace(api=SimpleNamespace(observations=api))
        reader = A.Reader(client, ttl=0)
        first = reader.read("1" * 32)
        self.assertTrue(first["available"])
        self.assertEqual(api.get_many.call_args_list[1].kwargs["cursor"], "next")
        self.assertEqual(api.get_many.call_args.kwargs["trace_id"], "1" * 32)
        stale = reader.read("1" * 32)
        self.assertTrue(stale["stale"])
        self.assertEqual(stale["total"]["usd"], first["total"]["usd"])
        self.assertFalse(A.Reader(None).read("1" * 32)["available"])
