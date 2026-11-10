# Structure

## Purpose

Record what a run did, in enough detail to debug it afterwards, without ever becoming
something the run itself depends on.

## Owns

- `telemetry` — the trace of a run: its work item, phases, role steps, native generations, stops, final diff and scores, written to the [trace contract](../../../../docs/architecture/trace-contract.md), and the per-run settings that let each agent's own tracing plugin nest its turns under the step that caused them.

## Does not own

What a run is doing or what it did: Temporal owns that, and the workflow's `status` query
is what the operator reads (D20). The conversation: the provider's session store owns it
(D21). Git — the change to record is handed in by
[application](../../../application/README.md), and this package cannot read a repository.

## Composition

| part | responsibility |
|---|---|
| `telemetry.py` | the trace of a run, native generation uploads, and the per-run settings an agent's plugin reports through |
| `pricing.py` · `pricing.json` | versioned provider tariff/calendar context for existing generations and the owned Langfuse model definition |
| `accounting.py` | bounded read-only recorded-cost projection for the Workbench; no workflow consumer |

## Relationships

This package's relationships are drawn once, in [the main view](diagrams/main.md).

Through Langfuse's ingestion API: every row. The optional cost display reads recorded generations
through observations v2, preserving provenance and unknown coverage. Its failure can
neither break correctness, reroute a run, nor block one beyond its own bounded timeout.

Through a diff reader handed in by the caller: the final diff. This package records a change
it is given and never learns how git reads one.

Through the trace contract: the names, levels, scores and dimensions the views and the
dashboard select on.

## Invariants

- **Observability only (D20).** Only optional cost display reads back. A run without keys behaves identically.
- **Only activities write it, each run once**, so neither a replayed workflow task nor a retry writes a row twice. `tests/observability/test_trace_parity.py` proves a replay writes none, with a control that writes one again.
- **The only values crossing back into the workflow** are the opaque ids of the work item and its root observation. No route, verdict, budget or stop reads them.
- **No secret leaves in a row.** The credentials this package reads are masked in this process, and a final diff that held one is redacted and marked.

## Accepted decisions

An index. Each decision is written where the project's architecture states it, beside the
boundary or invariant it constrains: see
[the accepted decisions](../../../../docs/architecture/structure.md#accepted-decisions).
The invariants above name the ones that bind this package.

## Risks and technical debt

One module carries the whole trace, and its size is a standing signal to re-review its
ownership. The last review found the ownership correct: the plugin name, the key names and
why a second uploader duplicates immutable observations are all Langfuse's interface, and
splitting them out would make a second module know it.
