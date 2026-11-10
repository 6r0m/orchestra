"""Request-time pricing evidence uses the response model and never the delayed upload time."""
import datetime
import unittest
from unittest import mock

from app.observability import telemetry as T
from app.observability import pricing


class PricingIngestion(unittest.TestCase):
    def test_both_owned_definitions_validate_against_the_installed_sdk(self):
        from langfuse.api.models.types.create_model_request import CreateModelRequest
        for candidate in (pricing.model_definition(), pricing.api_equivalent_definition()):
            candidate.pop("id")
            CreateModelRequest.model_validate(candidate)

    def test_calendar_and_unknown_evidence_fail_closed(self):
        rates = pricing.schedule()
        rates["valid_from"] = "2026-01-01T00:00:00+00:00"
        for day, expected in (((2026, 10, 1), "off_peak"), ((2026, 11, 14), "off_peak"),
                              ((2026, 11, 10), "peak")):
            stamp = datetime.datetime(*day, 2, tzinfo=datetime.timezone.utc).timestamp() * 1000
            self.assertEqual(pricing.context("deepseek-flash", stamp, rates)["tariff_period"], expected)
        for stamp in (None, True, float("nan"), float("inf"), -1,
                      datetime.datetime(2027, 1, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000):
            self.assertEqual(pricing.context("deepseek-flash", stamp, rates)["pricing_status"], "unknown")
        definition = pricing.model_definition()
        self.assertEqual(sum(tier["is_default"] for tier in definition["pricing_tiers"]), 1)
        self.assertTrue(all(type(price) in (int, float) and price >= 0 for tier in definition["pricing_tiers"]
                            for price in tier["prices"].values()))

    def upload(self, timestamp, actual="deepseek-flash"):
        client = mock.Mock()
        client.start_as_current_observation = mock.MagicMock()
        row = client.start_as_current_observation.return_value.__enter__.return_value
        generation = {"model": "deepseek-flash", "usage_details": {"input": 100, "output": 20,
                       "input_cached_tokens": 50, "input_cache_creation_tokens": 0},
                      "metadata": {"provider": "deepseek", "response_model": actual,
                                   "request_timestamp_ms": timestamp, "cost_source": "model_price_inference"}}
        T.run_upload({"traceparent": "00-" + "1" * 32 + "-" + "2" * 16 + "-01",
                      "generations": [generation]}, T._Span(client=client))
        return client.start_as_current_observation.call_args.kwargs, row.update.call_args.kwargs

    def test_request_time_selects_both_tariffs_with_exact_window_boundaries(self):
        for hour, period in ((0, "off_peak"), (1, "peak"), (4, "off_peak"),
                             (6, "peak"), (10, "off_peak")):
            with self.subTest(hour=hour):
                when = datetime.datetime(2026, 11, 10, hour, tzinfo=datetime.timezone.utc)
                _, values = self.upload(when.timestamp() * 1000)
                self.assertEqual(values["metadata"].get("tariff_period"), period)
                self.assertEqual(values["metadata"].get("pricing_status"), "matched")

    def test_an_unknown_actual_model_or_timestamp_is_not_priced_as_the_requested_model(self):
        when = datetime.datetime(2026, 11, 10, 2, tzinfo=datetime.timezone.utc).timestamp() * 1000
        for timestamp, model in ((when, "a-different-model"), (None, "deepseek-flash")):
            with self.subTest(timestamp=timestamp, model=model):
                call, values = self.upload(timestamp, model)
                self.assertEqual(call["model"], model)
                self.assertEqual(values["metadata"].get("pricing_status"), "unknown")
                self.assertNotIn("tariff_period", values["metadata"])

    def test_a_broken_tariff_file_preserves_native_usage_and_reports_degradation(self):
        with mock.patch("app.observability.pricing.schedule", side_effect=ValueError("invalid tariff")):
            call, values = self.upload(None, "another-actual-model")
        self.assertEqual(call["model"], "another-actual-model")
        self.assertEqual(values["usage_details"]["input"], 100)
        self.assertEqual(values["metadata"]["pricing_status"], "unknown")
