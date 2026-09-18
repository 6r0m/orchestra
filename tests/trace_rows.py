"""A run's trace rows reduced to what the contract promises, so two emitters can be compared row by row.

Kept: each row's name, type, version, level, whether it has a parent, the keys of its
input, output and metadata, and the values views filter on. Dropped: ids, paths, the
label and the texts, which differ between any two runs.
"""
FILTERED = ("phase", "stage", "role", "round", "verdict", "gate_reason", "error_type", "brain", "model",
            "reasoning_effort")
GOLDEN = "fixtures/trace_rows.json"


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
