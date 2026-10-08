# A base that moved after the gate takes the change as git merges it

**Status:** IMPLEMENTED — awaiting the external reviewer. The touched tests pass on both hosts. It takes
effect once the stack is restarted on this code, which is the operator's to do.
**Scope:** what a Merge does when the base moved on after the final gate
([worktrees.py](../app/workspace/worktrees.py), `_land`), and the line the run says for it
([workflow.py](../app/orchestration/workflow.py)). Nothing before the gate changes: a base that moved while
the run built is still brought into the worktree and judged.
**Stable documentation owner:** D24 in [structure.md](../docs/architecture/structure.md); for the operator,
[using.md](../docs/using.md).

## Goal

A Merge the operator has given lands, unless git itself cannot merge the change onto the base as it is.

## Authority register

### Operator decisions

- **D1** At the Merge, a base that moved without a conflict is the controller's to merge, and no role works
  again.
  - Date/source: 2026-10-08, operator, on a Merge that sent a change with no conflict back to the architect:
    *"it's very weird after merge instead just controller script deterministically do the job if no
    conflicts - now architector works again"*.
  - Effect: replaces, for the moment after the gate, what the merge flow held until now — that a Merge on a
    base that moved lands nothing ([its record](done/2026-10-07_2000-reconcile-before-the-final-gate.md)).

### Decided under D1 — the agent's

- **"No conflict" is git's own answer** (`merge-tree`), and nothing narrower — no rule of its own about the
  files both sides touched. It is what `git merge` and a hosting service's merge button take by default.
- **Only the Merge changes.** Before the gate a base that moved is still brought in and judged: there the
  run is still making what the operator will be shown, none of the operator's actions is spent on it, and
  the controller would otherwise have to record as verified a tree no role verified.
- **A conflict writes nothing and resolves nowhere in the controller.** It is found by a look that commits
  nothing of the run's, and goes the way it went before: reopened, brought in, resolved, judged, offered
  again.
- **One attempt for one Merge.** A base that moves under the push refuses that push, in words, and the next
  Merge makes its own merge — no loop, since every attempt runs the repository's pre-push check.
- **The workflow commands nothing new**, so recorded runs replay as they are (D25); it gains one line.

### What is given up

- The tree that lands on a base that moved is one no stage read whole and no gate showed — the hazard the
  merge flow's record named as its F1. The change in it is the one the gate showed. What stood against that
  hazard until now was a second reading by the architect, whose verify is told to run no tests: nothing
  tested the merged tree then either.

## Verified evidence (2026-10-08, run `find-one-small-6625194f`)

- Its base moved after its gate by one commit that shared no file with the run's seven. Merge landed
  nothing; the base came into the worktree without a conflict; the architect judged again, the closeout ran
  again, and a second gate asked for a second Merge.
- The verify's prompt ends "Do not run tests or builds" ([stages.py](../app/foundation/stages.py)).

## What changed

- `_land`: where the base moved on from the commit the change was judged on, the merge commit is git's
  merge of the two, its first parent the base as it is, landed by a push — or a fast-forward, or a
  compare-and-swap of the ref — leased on that commit. The change is still one commit on the tip it was
  judged on, its tree the one the gate showed. A conflict, or a base that no longer holds that tip, answers
  `moved` as before, with nothing committed. A base that already holds the change is refused as holding
  nothing new, and one that moves under the push is refused in words.
- A landing's answer names the commit it was merged onto where the base had moved; an adopted one's too.
- The workflow says so in the run's lines. The path a `moved` answer takes is as it was.
- D24, the stops diagram, the using guide, the root README's trust list and the page's confirmation say it.

## Verification

- **Red first:** on the unchanged code six new assertions failed — a base that moved without a conflict
  answered `moved`, and no landing named what it was merged onto.
- **`tests.workspace.test_worktrees`** — `Landing`: a base that moved since the gate takes the change as git
  merges the two, checked out or not; one in conflict takes nothing with nothing written; one that already
  holds the change takes no empty merge; one that moved before the gate is brought in as before. `Remote`:
  a remote that moved takes the merge by a push leased on where it is; one in conflict takes nothing; one
  that moves under the push takes nothing and the next Merge lands on where it is, the change committed
  once.
- **`tests.orchestration.test_stops.Reconciling`**: a merge made onto a base that moved lands at once, with
  the run's line and no role's turn; one git could not make goes to the engineer; a `moved` answer on a
  base git then merges is still judged by the architect.
- **Control:** a controller that answers a conflict with git's conflicted tree fails three of those tests.
- **The touched modules, one host after the other** — the worktrees', the stops', the replay of the
  recorded histories, the workflow's, the activities', the trace's and the architecture's; on WSL the
  Workbench's and the round boundaries' too: WSL: 60 classes, 339 tests, OK; Windows: 46 classes, 263
  tests, OK.

## Completion criteria

- The external reviewer's PASS.
- The whole suite once on both hosts, after it.
- The stack restarted on this code by the operator, and a real Merge onto a base that moved landing at once.

## Not done here

- No setting keeps the stricter form — a Merge that lands nothing on any base that moved — for a
  repository that wants it. Nothing asks for it today.
