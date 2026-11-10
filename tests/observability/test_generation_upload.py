"""Recorded native usage reaches the existing trace writer; unavailable prices are never invented."""
import unittest
from unittest import mock

from app.observability import telemetry as T


class RecordedGenerations(unittest.TestCase):
    def test_provider_charge_and_native_request_time_reach_the_existing_generation(self):
        client = mock.Mock()
        metadata = {"request_timestamp_ms": 1700000000123, "cost_source": "provider_reported",
                    "billing_coverage": "unknown"}
        # A MagicMock supplies the context-manager protocol used by the real SDK.
        client.start_as_current_observation = mock.MagicMock()
        row = client.start_as_current_observation.return_value.__enter__.return_value
        span = T._Span(client=client)
        T.run_upload({"traceparent": "00-" + "1" * 32 + "-" + "2" * 16 + "-01", "generations": [
            {"model": "a-model", "usage_details": {"input": 5, "output": 3},
             "cost_details": {"total": 0}, "metadata": metadata}]}, span)
        self.assertEqual(client.start_as_current_observation.call_count, 1)
        self.assertEqual(row.update.call_args.kwargs.get("cost_details"), {"total": 0})
        self.assertEqual(row.update.call_args.kwargs["metadata"], metadata)
        self.assertFalse(span.warnings)

    def test_an_export_failure_warns_without_failing_the_run(self):
        client = mock.Mock()
        client.start_as_current_observation.side_effect = RuntimeError("offline")
        stage = mock.Mock()
        span = T._Span(client=client, span=stage)
        T.run_upload({"traceparent": "00-" + "1" * 32 + "-" + "2" * 16 + "-01",
                      "generations": [{"model": "a-model"}]}, span)
        self.assertEqual(len(span.warnings), 1)
        self.assertEqual(stage.update.call_args.kwargs["level"], "WARNING")

    def test_usage_is_recorded_under_its_role_step_without_supplying_catalog_costs_as_billing(self):
        calls = []

        class Row:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def update(self, **values):
                calls.append(values)

        class Client:
            def start_as_current_observation(self, **values):
                calls.append(values)
                return Row()

        span = T._Span(client=Client())
        T.run_upload({"traceparent": "00-" + "1" * 32 + "-" + "2" * 16 + "-01", "generations": [
            {"model": "a-model", "output": "answer", "usage_details": {"input": 12, "output": 3},
             "metadata": {"usage_complete": True}},
            {"model": "another-model", "output": "answer", "usage_details": None,
             "metadata": {"usage_complete": False}}]}, span)
        self.assertEqual(calls[0]["trace_context"], {"trace_id": "1" * 32, "parent_span_id": "2" * 16})
        self.assertEqual(calls[1]["usage_details"], {"input": 12, "output": 3})
        self.assertIsNone(calls[3]["usage_details"])
        self.assertFalse(any("cost_details" in call for call in calls))
