# observability

The optional trace of a run, and nothing a run depends on.

## Owns

| module | responsibility |
|---|---|
| `telemetry.py` | the trace of a run — its work item, phases, role steps, stops, final diff and scores — written to the [trace contract](../../docs/architecture/trace-contract.md), and the per-run settings that let each agent's tracing plugin nest its turns there |

## Does not own

What a run is doing or what it did: Temporal owns that, and the workflow's `status` query
is what the operator reads (D20). The conversation: the provider's session store owns it
(D21). Git: the change to record is handed in by `application`, and this package cannot
read a repository.

## Depends on

`foundation`, for the checkout root, the environment root the Codex plugin lives under,
and the policy. Nothing else.

## Invariants

- **Observability only (D20).** Nothing is ever read back. A run without keys records
  nothing and behaves identically. Failure can neither break correctness, reroute a run,
  nor block one beyond its own bounded timeout.
- **Only activities write it, each run once**, so neither a replayed workflow task nor a
  retry writes a row twice. `tests/observability/test_trace_parity.py` proves a replay
  writes none, with a control that writes one again.
- **The only values crossing back into the workflow** are the opaque ids of the work item
  and its root observation. No route, verdict, budget or stop reads them.
