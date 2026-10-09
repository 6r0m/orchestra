"""A run's trace rows reduced to what the contract promises, so two emitters can be compared row by row.

Kept: each row's name, type, version, level, whether it has a parent, the keys of its
input, output and metadata, and the values views filter on. Dropped: ids, paths, the
label and the texts, which differ between any two runs.

The kept rows hold no role's agent profile: which kind, profile, model and effort ran a role is the
settings' to say, so `expected` gives each role's row the one its run's policy held.
"""
PROFILE = ("kind", "agent", "model", "effort")
FILTERED = ("phase", "stage", "role", "round", "verdict", "gate_reason", "error_type") + PROFILE
GOLDEN = "fixtures/trace_rows.json"


def expected(kept, policy):
    """The kept rows, each role's row with the profile `policy` hands that role."""
    rows = []
    for row in kept["rows"]:
        role = policy["roles"].get(row["filtered"].get("role"))
        if role is not None:
            profile = {key: role[key] for key in PROFILE if role.get(key) is not None}
            row = dict(row, filtered=dict(row["filtered"], **profile))
        rows.append(row)
    return dict(kept, rows=rows)


def reduce(recorder):
    rows = []
    for event in recorder.events:
        metadata = event.get("metadata") or {}
        rows.append({
            "name": event["name"], "as_type": event.get("as_type"), "version": event.get("version"),
            "level": event.get("level", "DEFAULT"),
            "parent": bool((event.get("trace_context") or {}).get("parent_span_id")),
            "input": sorted(event.get("input") or {}), "output": sorted(event.get("output") or {}),
            "metadata": sorted(metadata), "filtered": {key: metadata[key] for key in FILTERED if key in metadata}})
    scores = [{"name": score["name"], "value": score["value"], "data_type": score["data_type"],
               "on_step": bool(score.get("observation_id")), "keyed": "score_id" in score}
              for score in recorder.scores]
    return {"rows": rows, "scores": scores}


def script():
    """A round sent back, the approval, a build whose session was lost and rehydrated, a verified build."""
    from fakes import codex_review_first, codex_review_resumed
    a1, _ = codex_review_first("PATCH", "tighten the plan")
    return [["plan-e1-1", 0, "planned\n"], ["assess-e1-1", 0, a1],
            ["plan-e1-2", 0, "replanned\n"], ["assess-e1-2", 0, codex_review_resumed("PASS", "Direction: B.")],
            ["build-e2-1", 1, "Error: No conversation found with session ID: dead\n"],
            ["build-e2-1-rehydrated", 0, "built\n"], ["verify-e2-1", 0, codex_review_resumed("PASS")]]
