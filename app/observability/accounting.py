"""Optional, read-only recorded-cost projection. Never imported by workflow code."""
from collections import OrderedDict
import datetime
import re
import sys
import threading
import time

from app.observability import telemetry as T


def _number(value):
    return type(value) in (int, float) and 0 <= value <= sys.float_info.max


def _empty():
    return {"usd": None, "requests": 0, "priced": 0, "unpriced": 0, "tokens": 0,
            "provenance": "unknown", "coverage": "unknown"}


def _add(summary, row):
    metadata = row.get("metadata") or {}
    amount = row.get("totalCost")
    reported = metadata.get("cost_source") == "provider_reported"
    deepseek = metadata.get("provider") == "deepseek" or "deepseek" in (row.get("model") or "").lower()
    matched = (metadata.get("provider") == "deepseek" and metadata.get("pricing_status") == "matched" and
               row.get("usagePricingTierName") == metadata.get("tariff_period") and
               row.get("usagePricingTierName") in ("peak", "off_peak"))
    priced = _number(amount) and (reported or (metadata.get("usage_complete") is not False and (not deepseek or matched)))
    summary["requests"] += 1
    if not reported and "API equivalent" in (row.get("usagePricingTierName") or ""):
        summary["api_equivalent"] = True
    usage = row.get("usageDetails") or {}
    tokens = row.get("totalUsage")
    if metadata.get("usage_complete") is False or (not usage and (not _number(tokens) or tokens == 0)):
        summary["tokens_unknown"] = True
    summary["tokens"] += tokens if _number(tokens) else sum(
        usage[key] for key in ("input", "output", "input_cached_tokens", "input_cache_creation_tokens")
        if _number(usage.get(key)))
    if priced:
        summary["usd"] = (summary["usd"] or 0) + amount
        summary["priced"] += 1
        if not reported or summary["provenance"] == "estimated":
            summary["provenance"] = "estimated"
        else:
            summary["provenance"] = "provider_reported"
    else:
        summary["unpriced"] += 1


def project(rows):
    """Sum each generation once; role/stage context follows its recorded parent ancestry."""
    indexed = {row["id"]: row for row in rows if row.get("id")}
    result = {"total": _empty(), "roles": {}, "turns": {}, "activities": {}, "incomplete_steps": 0}
    for row in indexed.values():
        metadata = row.get("metadata") or {}
        if row.get("type") == "AGENT" and metadata.get("error_type") == "telemetry_degraded":
            result["incomplete_steps"] += 1
            result["total"]["partial"] = True
            result["roles"].setdefault(metadata.get("role") or "unassigned", _empty())["partial"] = True
    for row in indexed.values():
        if row.get("type") != "GENERATION":
            continue
        context, seen, current = {}, set(), row
        while current and current.get("id") not in seen:
            seen.add(current.get("id"))
            # The generation's native context takes precedence over its ancestors.
            for key, value in (current.get("metadata") or {}).items():
                if value is not None:
                    context.setdefault(key, value)
            current = indexed.get(current.get("parentObservationId"))
        role = context.get("role") or "unassigned"
        _add(result["total"], row)
        _add(result["roles"].setdefault(role, _empty()), row)
        if context.get("stage") and context.get("episode") is not None:
            key = "%s:%s:%s" % (context["stage"], context["episode"], context.get("episode_round", context.get("round")))
            _add(result["turns"].setdefault(key, _empty()), row)
        if context.get("activity_id"):
            _add(result["activities"].setdefault(context["activity_id"], _empty()), row)
    return result


class Reader:
    """A bounded per-process cache. An outage retains evidence, visibly stale, and never fabricates zero."""
    def __init__(self, client, ttl=10):
        self.client, self.ttl = client, ttl
        self.cache = OrderedDict()
        self.lock = threading.Lock()

    def read(self, trace_id):
        if not isinstance(trace_id, str) or not re.fullmatch(r"[0-9a-f]{32}", trace_id):
            return {"available": False, "reason": "No trace is recorded for this run."}
        with self.lock:
            cached = self.cache.get(trace_id)
            if cached and time.monotonic() - cached[0] < self.ttl:
                return cached[1]
            try:
                if self.client is None:
                    return {"available": False, "reason": "Langfuse accounting is not configured."}
                rows, cursor, seen = [], None, set()
                deadline = time.monotonic() + 8
                for page in range(50):
                    args = {"trace_id": trace_id, "fields": "core,basic,metadata,usage,model", "limit": 100,
                            "request_options": {"timeout_in_seconds": 3, "max_retries": 0}}
                    if cursor:
                        args["cursor"] = cursor
                    response = self.client.api.observations.get_many(**args)
                    rows.extend(row if isinstance(row, dict) else row.model_dump(mode="json", by_alias=True)
                                for row in response.data)
                    cursor = response.meta.cursor
                    if not cursor:
                        break
                    if cursor in seen:
                        raise ValueError("observation cursor repeated")
                    seen.add(cursor)
                    if time.monotonic() >= deadline:
                        break
                value = dict(project(rows), available=True, stale=False, truncated=bool(cursor),
                             updated=datetime.datetime.now(datetime.timezone.utc).isoformat())
                if cursor:
                    for collection in (value["roles"], value["turns"], value["activities"]):
                        for summary in collection.values():
                            summary["partial"] = True
                    value["total"]["partial"] = True
            except Exception as error:
                T._warn_once("accounting read", type(error).__name__)
                value = dict(cached[1], stale=True, reason="Recorded costs cannot be refreshed; retrying.") if cached else {
                    "available": False, "reason": "Recorded costs cannot be read; retrying."}
            self.cache[trace_id] = (time.monotonic(), value)
            self.cache.move_to_end(trace_id)
            while len(self.cache) > 128:
                self.cache.popitem(last=False)
            return value
