# A base that moved after the gate takes the change as git merges it

**Status:** PASS 2026-10-08 — the external reviewer's PASS, and the release acceptance: the whole suite on
both hosts, the stack restarted on this code, and a real run merged at once onto a base that had moved.
**Scope:** what a Merge does when the base moved on after the final gate
([worktrees.py](../../app/workspace/worktrees.py), `_land`), and the line the run says for it
([workflow.py](../../app/orchestration/workflow.py)). Nothing before the gate changes: a base that moved while
the run built is still brought into the worktree and judged.
**Stable documentation owner:** D24 in [structure.md](../../docs/architecture/structure.md); for the operator,
[using.md](../../docs/using.md).

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
    base that moved lands nothing ([its record](2026-10-07_2000-reconcile-before-the-final-gate.md)).

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
  hazard until now was a second judgement by the architect: its own verify runs no tests, but it can send
  the change back for the engineer to run them on the merged tree — as it did on the run below.

## Verified evidence (2026-10-08, run `find-one-small-6625194f`)

- Its base moved after its gate by one commit that shared no file with the run's seven. Merge landed
  nothing; the base came into the worktree without a conflict; the architect judged again and sent the
  change back once — its recorded test results were the old base's — the engineer ran the suites again on
  the merged tree, which found no defect, the closeout ran again, and a second gate asked for a second
  Merge.
- The verify's prompt ends "Do not run tests or builds" ([stages.py](../../app/foundation/stages.py)).

## What changed

- `_land`: where the base moved on from the commit the change was judged on, the merge commit is git's
  merge of the two, its first parent the base as it is, landed by a push — or a fast-forward, or a
  compare-and-swap of the ref — leased on that commit. The change is still one commit on the tip it was
  judged on, its tree the one the gate showed. A conflict, or a base that no longer holds that tip, answers
  `moved` as before, with nothing committed. A base that already holds the change is refused as holding
  nothing new, and one that moves under the push is refused in words.
- A checked-out local base is fast-forwarded only once it is seen to be at the commit the merge was made
  onto: git's fast-forward asks only that the commit descend from where the branch is, and gave a branch
  taken back since the look what it had dropped — on the path as it was before this change, too.
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
- **The checked-out base taken back, red first:** with the branch reset in its checkout between the look and
  the landing, the fast-forward landed and the dropped commit was back. Now that Merge is refused, the base
  is where it was put, and the next Merge lands the final tree on it.
- **The touched modules, one host after the other** — the worktrees', the stops', the replay of the
  recorded histories, the workflow's, the activities', the trace's and the architecture's; on WSL the
  Workbench's and the round boundaries' too: WSL: 60 classes, 339 tests, OK; Windows: 46 classes, 263
  tests, OK. After the reviewer's PATCH, the worktrees' and the architecture's: 20 classes, 122 tests, OK
  on each.

## Review

- **External reviewer, 2026-10-08 — PATCH.** The design stands, the tree nobody read whole an accepted
  price. One gap, older than this change: a checked-out local base was fast-forwarded from wherever it
  stood. Reproduced and closed as the reviewer set out — a look as the last thing before the
  fast-forward; a look and a step, not a compare-and-swap, which git has none of for a branch together
  with its checkout.
- **External reviewer, 2026-10-08 — PASS** on that, with the release acceptance below still to do.

## Release acceptance (2026-10-08)

- **The whole suite, one host after the other:** WSL: 141 classes, 696 tests, OK; Windows: 97 classes, 496
  tests, OK.
- **The stack restarted on this code** with the run `find-one-small-6625194f` waiting at its final gate: it
  waited there afterwards, its history the same event for event.
- **The operator's one Merge of that run.** It had been judged on a commit its remote base had since moved
  three commits past, two of them changing a file the run changes too. A look beforehand said git merges
  the two. The Merge landed at once: the remote's base is a merge commit named for the run's plan, its
  first parent the base as it was at the Merge, its second one commit on the commit the run was judged on
  with the tree its gate held, its own tree git's merge of the two, and what it adds to the base the run's
  seven files. No stage ran between the gate and the landing. The run's worktree, its branch and its
  environment are gone, and the remote holds no branch of the run. The repository's own checkout was left
  where it was; the operator's own pull moved it, twenty seconds on.
- **Not exercised on the live stack:** a conflict, and a base taken back, at the Merge. Both are held by the
  tests above, on real repositories.

## Not done here

- No setting keeps the stricter form — a Merge that lands nothing on any base that moved — for a
  repository that wants it. Nothing asks for it today.
