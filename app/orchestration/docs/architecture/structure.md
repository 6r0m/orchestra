# Structure

## Purpose

Decide what happens next in a run — which stage, which stop, which answer ends it — and
do so deterministically, so Temporal can replay the decision and reach the same place.

## Owns

- `workflow` — the run: the steps of its flow in order — each work stage, the review that judges it and the operator's approval where the flow schedules one — the stops and their named answers, the final gate and the reopening of a change it sends back, what a Stop does to it, and the `status` query — which also says what the run is doing now, since when, and which queues it needs. Beside it, three short workflows that reach a target host's git for a client, because only a workflow can start an activity: a run's change read for review, a repository's worktrees, and the removal of what a closed run kept.
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
| `workflow.py` | one run's execution: its flow's stages, stops, answers, the final gate or its `DONE` end, the status query |
| `routing.py` | which gate a verdict asks for and where it sends the run — no dependencies |

## Relationships

This package's relationships are drawn once, in [the main view](diagrams/main.md).

Through Temporal's workflow API: this package *is* the workflow. Its event history is the
run's durable state, so a process that exits at a stop loses nothing and any later process
answers it.

Through `app.foundation.stages` and `app.foundation.flows`: the stage vocabulary a route is
expressed in, and the rules of the flow a run is handed — checked again when the run begins, and
`LEGACY_FLOW` for a run started before flows. The workflow never reads a flow's file.

Through an activity name and its payload: every effect. This package names the activity and
the queue; what the activity does is the other side's.

## Invariants

- **Review checkpoints describe accepted actions; they never route work.** After consuming an accepted
  stop answer, before reopening, reconciliation, another role or cleanup, an opted-in run asks its target
  to retain an immutable Git sample. A failed or timed-out capture is explicitly unavailable and leaves
  the accepted answer effective. Cancellation still interrupts the wait. The recorded answer protocol
  activates this behavior on existing runs without adding commands while replaying older answers;
  historical boundaries without a capture remain unknown. Copying, viewing and terminal typing create
  no checkpoint. Git retention and release belong to
  [workspace](../../../workspace/docs/architecture/structure.md#review-snapshot-retention).

- **Accepted operator notes remain original inputs.** A revision, guidance or approval note retains its
  exact text, originating stop, phase, action and chosen recipient. Subsequent work, review and closeout
  receive the originals in order, across rounds and phases. A later note does not erase earlier choices;
  applying a note still requires interpreting its scope and distinguishing quoted evidence from an
  explicit operator decision. Workflow-generated routing context stays separate from those notes.
  Notes are accepted human inputs, not accumulated prompts or vendor transcripts (D8).
  Historical answers reconstruct this projection during replay without changing recorded activity
  inputs. A new answer's recorded context-protocol version activates the projection for later work,
  including an existing run's earlier notes when it Continues without another note.
  Retained-context turns use a distinct role-activity type on the same target queue. A target worker
  without that contract fails the activity before starting an agent; Continue retries it after the
  worker is upgraded. The legacy activity type remains registered for recorded commands.
  The status query advertises support; the shared client
  refuses guidance to an older worker, and the validator refuses unversioned new notes. Rejected and
  duplicate answers add no notes. No activity reads a vendor conversation to recover operator intent.
  The Update validator bounds new additions by `OPERATOR_NOTES_BUDGET` in
  [workflow.py](../../workflow.py), counting the full retained list as compact, ASCII-escaped JSON,
  including provenance. Overflow rejects the answer before acceptance and leaves the stop, notes and
  execution unchanged; nothing is truncated or summarized. Historical accepted notes replay unchanged
  even if already over budget. Such runs may still take note-free answers but cannot add another note.
  This bounds retained-note payload growth, not total workflow-history size or unrelated payloads.
- **The workflow is deterministic (D25).** A change to what it commands keeps the recorded histories in `tests/histories/` replaying — behind `workflow.patched(...)`, or behind what those histories themselves record — and `tests/orchestration/test_replay.py` is the guard, with a control.
- **A stop waits here and nowhere else (D6).** Each stop publishes the actions it takes, a revise at the final gate named per role, and its answer arrives as an Update carrying one of them, with the stable id `answer:<stop-id>`, so an answer sent twice is applied once. No activity ever waits for a human.
- **Adopting a verified todo name does not answer a stop.** At a failed closeout, an explicit operator
  Update asks the target host to validate the selected filename against the architect's verified tree.
  Only Temporal updates the saved todo path and the stop's displayed path. The update rechecks the stop
  and original path after the host answers, so a concurrent Continue or Stop cannot retarget a running
  turn. It moves no files, starts no agent and leaves the sessions and verified tree unchanged.
- **A Stop is Temporal's cancellation, heard wherever the run waits (D31).** It ends the run `STOPPED` — `REJECTED` when the cancellation's own reason says the operator rejected the run, the same Stop otherwise — and runs no git; a git side effect already running lands first and decides how the run ends, and one no worker has taken fails within the policy's heartbeat interval, never having run; the cleanup waits a bounded time, so a host whose worker is gone never holds it.
- **Only architect verdicts route (D4).** An engineer's blocker reaches a human only through the architect. A closeout routes nothing: it goes on to the final gate, where the operator judges it (D24).
- **A run keeps the flow it started with (D13).** Its steps are in its start input, taken as given: a flow of another shape than `{name, steps}`, or one that breaks a rule, ends it `REFUSED` before any step — never stuck retrying its first workflow task — and one without a build ends it `DONE`, merging nothing.
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
