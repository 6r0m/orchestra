"""Check/apply Orchestra's versioned provider prices and verify the live pricing engine without a model call."""
import argparse
import datetime
from decimal import Decimal
import json
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.foundation import paths
from app.observability import pricing, telemetry as T


def definition(values=None):
    from langfuse.api.models.types.create_model_request import CreateModelRequest
    values = pricing.model_definition() if values is None else dict(values)
    owned = values.pop("id")
    request = CreateModelRequest.model_validate(values)
    return owned, request.model_dump(exclude_none=True)


def apply(client, candidate):
    owned, values = definition(candidate)
    try:
        before = client.api.models.get(owned)
    except Exception as error:
        if getattr(error, "status_code", None) != 404:
            raise
        before = None
    if before is not None and before.model_name != values["model_name"]:
        raise ValueError("the model id belongs to another definition; nothing changed")
    folder = os.path.join(paths.REPO, "tmp", "pricing")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "before-" + uuid.uuid4().hex + ".json"), "w", encoding="utf-8") as fh:
        json.dump(before.model_dump(mode="json", by_alias=True) if before else None, fh)
    client.api.models.upsert(owned, **values)
    print("applied one Orchestra-owned model definition")


def verify(client):
    rates = pricing.schedule()
    trace_id = uuid.uuid4().hex
    usage = {"input": 1000, "input_cached_tokens": 2000, "output": 500, "input_cache_creation_tokens": 0}
    expected = {}
    with client.start_as_current_observation(name="Pricing verification", as_type="span",
            trace_context={"trace_id": trace_id}, metadata={"synthetic": True}) as root:
        for hour, period in ((2, "peak"), (12, "off_peak")):
            stamp = datetime.datetime(2026, 11, 10, hour, tzinfo=datetime.timezone.utc).timestamp() * 1000
            meta = pricing.context("deepseek-flash", stamp)
            meta.update(synthetic=True, role="engineer", stage="plan", episode=1, round=1)
            with client.start_as_current_observation(name="Pricing " + period, as_type="generation",
                    model="deepseek-flash", usage_details=usage, metadata=meta):
                pass
            expected["Pricing " + period] = sum(Decimal(str(rates["usd_per_million"][period][key]))
                                                 * usage[key] / 1_000_000
                                                 for key in rates["usd_per_million"][period])
        with client.start_as_current_observation(name="Pricing missing", as_type="generation",
                model="orchestra-unpriced-" + uuid.uuid4().hex, usage_details=usage, metadata={"synthetic": True}):
            pass
        with client.start_as_current_observation(name="Pricing provider zero", as_type="generation",
                model="orchestra-provider-zero", cost_details={"total": 0},
                metadata={"synthetic": True, "cost_source": "provider_reported"}):
            pass
        with client.start_as_current_observation(name="Pricing unclassified", as_type="generation",
                model="deepseek-flash", usage_details=usage,
                metadata={"synthetic": True, "pricing_status": "unknown"}):
            pass
        for name, tokens in (("Pricing API equivalent", 1000), ("Pricing API large", 273000)):
            reference = rates["api_equivalent"]
            with client.start_as_current_observation(name=name, as_type="generation", model=reference["model"],
                    usage_details={"input": tokens, "input_cached_tokens": 2000, "output": 500,
                                   "output_reasoning_tokens": 100}, metadata={"synthetic": True}):
                pass
            large = tokens > reference["long_context_above"]
            prices = reference["usd_per_million"]
            expected[name] = (Decimal(tokens) * Decimal(str(prices["input"])) +
                              2000 * Decimal(str(prices["input_cached_tokens"]))) * (2 if large else 1) / 1_000_000
            expected[name] += (500 * Decimal(str(prices["output"])) +
                               100 * Decimal(str(prices["output_reasoning_tokens"]))) * Decimal("1.5" if large else "1") / 1_000_000
    client.flush()
    deadline = time.monotonic() + 60
    while True:
        found = client.api.observations.get_many(trace_id=trace_id, fields="core,basic,metadata,model,usage", limit=100)
        rows = {row.name: row.model_dump(mode="json", by_alias=True) for row in found.data if row.type == "GENERATION"}
        ready = all(name in rows and rows[name].get("totalCost") is not None for name in expected)
        if ready and all(name in rows for name in ("Pricing missing", "Pricing provider zero", "Pricing unclassified")):
            for name, amount in expected.items():
                actual = Decimal(str(rows[name]["totalCost"]))
                if abs(actual - amount) > Decimal("0.000000000001"):
                    raise AssertionError("stored pricing differs from the selected tariff")
            if rows["Pricing missing"].get("totalCost") is not None:
                raise AssertionError("an unmatched model was priced instead of remaining unknown")
            if rows["Pricing provider zero"].get("totalCost") != 0:
                raise AssertionError("the confirmed zero was lost")
            from app.observability import accounting
            unknown = accounting.project([rows["Pricing unclassified"]])["total"]
            if unknown["usd"] is not None or unknown["unpriced"] != 1:
                raise AssertionError("the fallback tier was presented as an applicable tariff")
            folder = os.path.join(paths.REPO, "tmp", "pricing")
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, "verification.json"), "w", encoding="utf-8") as fh:
                json.dump({"trace_id": trace_id, "observations": rows}, fh, indent=2)
            print("synthetic pricing verified: peak/off-peak, missing price, confirmed zero, fallback exclusion and both API-reference tiers")
            return
        if time.monotonic() >= deadline:
            raise TimeoutError("pricing verification did not settle within 60 seconds")
        time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    candidates = (pricing.model_definition(), pricing.api_equivalent_definition())
    for candidate in candidates:
        definition(candidate)
    if not args.apply and not args.verify:
        validated = [definition(candidate) for candidate in candidates]
        print(json.dumps([{"id": owned, **values} for owned, values in validated], default=str, indent=2))
        return
    if args.verify:
        os.environ["LANGFUSE_TRACING_ENVIRONMENT"] = "fixture"
    client = T.resolve()
    if client is None:
        raise RuntimeError("Langfuse is not configured")
    try:
        if args.apply:
            for candidate in candidates:
                apply(client, candidate)
        if args.verify:
            verify(client)
    finally:
        client.shutdown()


if __name__ == "__main__":
    main()
