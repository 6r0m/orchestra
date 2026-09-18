# application

Where the concerns are composed. Nothing below this package knows about another one;
here they are put together into the things a run actually does.

## Owns

| module | responsibility |
|---|---|
| `activities.py` | everything a run does on its target host: resolve the repository, make the worktree, record trust, run a role turn, merge, discard, read the change for review, write the trace |
| `client.py` | the one client of runs — start, list, status, answer, the change, the worktrees — shared by the workbench and the command line |

Composition belongs here rather than inside a concern. `telemetry.final_diff(client, state,
worktrees.review_diff)` is written that way on purpose: the trace records a change it is
handed, and never learns how git reads one.

## Does not own

Any decision the workflow makes — an activity is told what to do. Printing: nothing here
writes to a console, which is what keeps `client.py` usable by both the page and the CLI.

## Depends on

`foundation`, `orchestration`, `workspace`, `agents`, `observability`. All five, by design.

## Invariants

- **A role-run and every git side effect are single-attempt (D5).** A failure stops the run
  for the operator; there is no automatic retry and no retry ledger (D16).
- **Every write goes through the workflow's own start rules, Updates and validators**, so
  the page can do nothing the workflow does not allow.
- **An activity never waits for a human** (D6).
