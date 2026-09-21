# Structure

## Purpose

Decide what happens next in a run — which stage, which stop, which answer ends it — and
do so deterministically, so Temporal can replay the decision and reach the same place.

## Owns

- `workflow` — the run: `plan → assess → build → verify`, the stops and their named answers, the final gate, and the `status` query.
- `routing` — which stop a verdict asks for and where it sends the run: two pure functions with no dependencies at all.

## Does not own

Any effect. No clock, randomness, file, network or process call happens here outside
Temporal's own APIs — every effect is an activity, and the activities belong to
[application](../../../application/README.md). What a stage asks its role for, which is
[foundation](../../../foundation/README.md)'s `stages`. Judgement about the work: only an
architect's verdict routes (D4), and the architect runs in
[agents](../../../agents/README.md).

## Composition

| part | responsibility |
|---|---|
| `workflow.py` | one run's execution: stages, stops, answers, the final gate, the status query |
| `routing.py` | which gate a verdict asks for and where it sends the run — no dependencies |

## Relationships

This package's relationships are drawn once, in [the main view](diagrams/main.md).

Through Temporal's workflow API: this package *is* the workflow. Its event history is the
run's durable state, so a process that exits at a stop loses nothing and any later process
answers it.

Through `app.foundation.stages`: the stage vocabulary a route is expressed in.

Through an activity name and its payload: every effect. This package names the activity and
the queue; what the activity does is the other side's.

## Invariants

- **The workflow is deterministic (D25).** A change to what it commands goes behind `workflow.patched(...)`, or the recorded histories in `tests/histories/` stop replaying — `tests/orchestration/test_replay.py` is the guard, with a control.
- **A stop waits here and nowhere else (D6).** Each stop publishes the actions it takes, a revise at the final gate named per role, and its answer arrives as an Update carrying one of them, with the stable id `answer:<stop-id>`, so an answer sent twice is applied once. No activity ever waits for a human.
- **Only architect verdicts route (D4).** An engineer's blocker reaches a human only through the architect.
- **There is no state machine layer**, deliberately. Do not re-derive one; the reasoning is in [the project's structure document](../../../../docs/architecture/structure.md).

## Accepted decisions

An index. Each decision is written where the project's architecture states it, beside the
boundary or invariant it constrains: see
[the accepted decisions](../../../../docs/architecture/structure.md#accepted-decisions).
The invariants above name the ones that bind this package.

## Risks and technical debt

The determinism boundary is Temporal's to enforce at runtime, not this package's to prove
statically. A non-deterministic call added inside workflow code fails at replay, which is
late; the recorded histories are what turn that into a test failure instead of a broken run.
