"""Versioned provider tariffs enrich observations; no price is an input to a workflow."""
import datetime
import json
import os
import re


def schedule():
    with open(os.path.join(os.path.dirname(__file__), "pricing.json"), encoding="utf-8") as fh:
        return json.load(fh)


def known_model(model, rates=None):
    rates = schedule() if rates is None else rates
    return isinstance(model, str) and model.lower() in {name.lower() for name in rates["models"]}


def context(model, timestamp, rates=None):
    rates = schedule() if rates is None else rates
    unknown = {"pricing_provider": "deepseek", "pricing_status": "unknown", "tariff_revision": rates["revision"]}
    if not known_model(model, rates) or type(timestamp) not in (int, float) or not 0 <= timestamp <= 2 ** 53 - 1:
        return unknown
    try:
        when = datetime.datetime.fromtimestamp(timestamp / 1000, datetime.timezone.utc)
    except (ValueError, OverflowError, OSError):
        return unknown
    if when.year != rates["calendar_year"] or when < datetime.datetime.fromisoformat(rates["valid_from"]):
        return unknown
    holiday = any(datetime.date.fromisoformat(start) <= when.date() <= datetime.date.fromisoformat(end)
                  for start, end in rates["holidays"])
    peak = when.weekday() < 5 and not holiday and any(start <= when.hour < end for start, end in rates["peak_utc_hours"])
    return dict(unknown, pricing_status="matched", tariff_period="peak" if peak else "off_peak")


def enrich(generation):
    result = dict(generation)
    metadata = dict(generation.get("metadata") or {})
    actual = metadata.get("response_model") or generation.get("model")
    if metadata.get("provider") != "deepseek":
        return result
    metadata["requested_model"] = generation.get("model")
    result["model"] = actual
    metadata.update(context(actual, metadata.get("request_timestamp_ms")))
    if (generation.get("usage_details") or {}).get("input_cache_creation_tokens", 0):
        metadata["pricing_status"] = "unknown"
        metadata.pop("tariff_period", None)
    result["metadata"] = metadata
    return result


def model_definition():
    rates = schedule()
    def prices(period):
        return {key: value / 1_000_000 for key, value in rates["usd_per_million"][period].items()}

    # Langfuse requires a priced default. Its fallback is explicitly unclassified: the reader
    # excludes it unless native request evidence established an applicable tariff.
    tiers = [{"name": "Unclassified", "is_default": True, "priority": 0, "conditions": [], "prices": prices("peak")}]
    for priority, period in enumerate(("peak", "off_peak"), 1):
        tiers.append({"name": period, "is_default": False, "priority": priority,
                      "conditions": [{"source": "metadata", "key": key, "operator": "in", "values": [value]}
                                     for key, value in (("pricing_status", "matched"), ("tariff_period", period),
                                                        ("tariff_revision", rates["revision"]))],
                      "prices": prices(period)})
    return {"id": "orchestra-" + rates["revision"], "model_name": "Orchestra " + rates["revision"],
            "match_pattern": "(?i)^(?:" + "|".join(re.escape(name) for name in rates["models"]) + ")$",
            "unit": "TOKENS", "start_date": rates["valid_from"], "pricing_tiers": tiers}


def api_equivalent_definition():
    """A Standard API reference for Codex usage, never a subscription charge or reported bill."""
    rates = schedule()
    reference = rates["api_equivalent"]
    prices = {key: value / 1_000_000 for key, value in reference["usd_per_million"].items()}
    large = {key: value * (2 if key.startswith("input") else 1.5) for key, value in prices.items()}
    return {"id": "orchestra-" + reference["revision"], "model_name": "Orchestra " + reference["revision"],
            "match_pattern": "(?i)^" + re.escape(reference["model"]) + "$", "unit": "TOKENS",
            "start_date": rates["valid_from"], "pricing_tiers": [
                {"name": "Standard API equivalent", "is_default": True, "priority": 0, "conditions": [], "prices": prices},
                {"name": "Large context API equivalent", "is_default": False, "priority": 1,
                 "conditions": [{"usage_detail_pattern": "(input|cache_write)", "operator": "gt",
                                 "value": reference["long_context_above"], "case_sensitive": False}], "prices": large}]}
