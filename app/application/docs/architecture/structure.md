# Structure

## Purpose

Put the concerns together: carry out on a target host what the workflow commanded, and
give the operator's two surfaces one way to start, read and answer a run, and to read the stack.

## Owns

- `activities` — everything a run does on its target host: resolve the repository, make the worktree, record trust, run a role turn, merge, discard, read the change for review, write the trace.
- `client` — the one client of runs: start, list, status, what a run is doing now, answer, the change and the worktrees, shared by the page and the command line.
- `stack` — the stack's health: whether Temporal answers, and whether each host's worker polls its queues.

## Does not own

Any decision the workflow makes — an activity is told what to do, and
[orchestration](../../../orchestration/README.md) decides it. Printing: nothing here writes
to a console, which is what keeps `client` usable by both the page and the CLI. Any
mechanism of its own: every concern this composes is owned by the package it came from.

## Composition

| part | responsibility |
|---|---|
| `activities.py` | what a run does on its target host, one activity at a time |
| `client.py` | the one client of runs, for the page and the command line alike |
| `stack.py` | the one reading of the stack's health, printed by `make check` and shown by the page |

## Relationships

This package's relationships are drawn once, in [the main view](diagrams/main.md).

Through an activity name and its payload: what the workflow commanded. Through Temporal's
client API: a start, an Update carrying an answer, the `status` query, a run's description, and
whether a worker polls each task queue.

Composition belongs here rather than inside a concern. `telemetry.final_diff(client, state,
worktrees.review_diff)` is written that way on purpose: the trace records a change it is
handed, and never learns how git reads one.

## Invariants

- **A role-run and every git side effect are single-attempt (D5).** A failure stops the run for the operator; there is no automatic retry and no retry ledger (D16).
- **Every write goes through the workflow's own start rules, Updates and validators**, so the page can do nothing the workflow does not allow.
- **An activity never waits for a human** (D6).
- **A persona file is resolved by `foundation.policy.prompt_path` and nowhere else**, on the host that runs the role and inside the step, so a policy that host cannot read, or a host copy that differs from the run's, fails the step before an agent starts.

## Accepted decisions

An index. Each decision is written where the project's architecture states it, beside the
boundary or invariant it constrains: see
[the accepted decisions](../../../../docs/architecture/structure.md#accepted-decisions).
The invariants above name the ones that bind this package.

## Risks and technical debt

This package imports every other concern, which is what it is for, and also what makes it
the easiest place for a responsibility to settle that belongs somewhere else. A new
mechanism appearing here rather than a composition of existing ones is the signal to watch.
