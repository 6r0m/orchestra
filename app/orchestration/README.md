# orchestration

The run itself: its stages, the routes between them, the stops it waits at and the
final gate. Temporal owns the execution; this owns what Temporal is told to do.

## Owns

| module | responsibility |
|---|---|
| `workflow.py` | the run: `plan → assess → build → verify`, the stops and their named answers, the final gate, the `status` query |
| `routing.py` | which stop a verdict asks for and where it sends the run — two pure functions, no dependencies |

## Does not own

Any effect. No clock, randomness, file, network or process call happens here outside
Temporal's own APIs — every effect is an activity, and the activities are `application`'s.
Judgement about the work: only architect verdicts route (D4).

## Depends on

`foundation`, for the policy. Nothing else.

## Invariants

- **The workflow is deterministic (D25).** A change to what the workflow commands goes
  behind `workflow.patched(...)`, or the recorded histories in `tests/histories/` stop
  replaying. `tests/orchestration/test_replay.py` is the guard, with a control.
- **A stop waits here and nowhere else (D6).** Its answer arrives as an Update carrying
  one of that stop's named actions, with the stable id `answer:<stop-id>`, so an answer
  sent twice is applied once. No activity ever waits for a human.
- **There is no state machine layer**, deliberately, and none is to be added back — the
  reasoning is in [docs/architecture/structure.md](../../docs/architecture/structure.md).
