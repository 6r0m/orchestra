# A Merge at the final gate lands what the gate showed, on the base as it is — or lands nothing

**Status:** INVESTIGATED. One part is implemented and awaits review — the change the gate reads after a
conflict (task 1). The reconciliation flow is a plan: it waits for the operator's answers to Q1–Q3. No
workflow code is changed.
**Scope:** how a run meets a base that moved: the merge and the hand-back of a conflict
([worktrees.py](../app/workspace/worktrees.py)), the workflow's path around the final gate
([workflow.py](../app/orchestration/workflow.py)), the change the gate and the history read
([client.py](../app/application/client.py), the Workbench's change view).
**Stable documentation owner:** architecture D24, with D25 for how the change keeps recorded runs replaying,
in [structure.md](../docs/architecture/structure.md); the stops in
[stops.md](../docs/architecture/diagrams/stops.md).

## Goal (proposed — Q1)

At the final gate the operator reads what the run adds to the base as it is now, judged on that base; Merge
lands exactly that tree, or — the base having moved since — lands nothing and says so.

## Authority register

### Operator decisions

- **D1** The external reviewer's feedback is evaluated against the code and applied where it holds; a point
  that is wrong is refuted, not applied.
  - Date/source: 2026-10-07, operator, relaying the review of the merge flow.
- **D2** Agents and the controller reach no remote; a run merges into the local base branch, and publishing
  is the operator's.
  - Date/source: accepted architecture (D24); kept by the reviewer's brief — *"Do not introduce PRs, remote
    credentials, a new integration service"*.

What prompted this, in the operator's words at a gate after a conflict, 2026-10-07: *"why a lot of stages
files? we should only 3 files to merge?"*; *"weird after merge a lot of changes and worktree still there"*.

### Open questions — the operator's

- **Q1** Is the goal above adopted: a base that moved is reconciled before the final gate, and a Merge either
  lands or changes nothing?
- **Q2** The base moved and git merges it without a conflict. Who judges the combined tree before the gate?
  - **(a) the architect alone, again** — one turn; the engineer only on its `PATCH`, or on a conflict.
    *Recommended:* nothing unjudged lands, at the least cost.
  - **(b) the engineer, then the architect, always** — the reviewer's diagram. Two turns for every base move.
  - **(c) nobody** — the gate says the combination is unjudged, and the operator decides. No turn; the
    unjudged tree can still land.
- **Q3** What the base's history gains per run.
  - **(a) the run's change as one commit on the base tip it was judged on, then the merge commit named for
    the plan** — every run the same two commits, and no "Merge base into run" commit. *Recommended.*
  - **(b) the base fast-forwarded to the run's reconciliation commit** — the reviewer's. Refuted below.
  - **(c) as today.**

### Working assumptions

- **A1 [ACTIVE]** Reconciling is the controller's step, not a role's stage: no flow file changes, and a run
  is told the base came in by the words of its next turn, as a conflict is today.
- **A2 [ACTIVE]** The base is looked at twice only — after a verify's `PASS` and at the Merge — never watched.
- **A3 [ACTIVE]** A run started before this keeps the path it recorded: what tells it apart is that it
  recorded no base tip (D25's second way), so no marker is needed.

## Non-goals

- Pull requests, a remote, credentials for the controller, a merge queue or an integration service (D2).
- Rebasing a run's work.
- Putting the todo of a run started before closeouts back at its path during a conflict (F9): those runs end.

## Verified evidence

- **F1** `merge` commits the run's tree on its branch, then merges that into the base: `git merge --no-ff` in
  the base's checkout, or `merge-tree`, `commit-tree` and a compare-and-swap of the ref where it is checked
  out nowhere. When the base moved and git finds no conflict, the base gains a tree no stage judged and no
  gate showed. "A merge commits exactly the tree the final gate showed" holds for the run's commit only.
- **F2** A conflict is aborted on the base, and the base is merged into the run's worktree, uncommitted
  (`_hand_back`); the workflow reopens the change and returns to the build, its review, the closeout and the
  gate, where a second Merge is asked.
- **F3** Measured on the live stack, 2026-10-07, a run fourteen base commits behind: its first Merge met one
  conflicting file. Its worktree then held 70 staged files and 1 unmerged — exactly the 71 the base had
  changed — and differed from the base by 3 files, +382 lines.
- **F4** The gate read its change from the worktree's own commit, which by then held the run's change: 71
  files, none of them the run's. Fixed here (task 1): read against the base brought in, the same worktree
  shows its 3 files.
- **F5** The history's rows after that conflict, measured the same day: the plan's row, whose base is "the
  worktree's last commit" at the time it is read, showed 3 files, +16 −96, where the plan was 1 file, +302;
  and the row of the build that resolved the conflict showed 72 files, +11255 −537 — the base's commits. A
  run records no commit it started from.
- **F6** The reconciliation commit's first parent is the run's commit and its second the base's tip. A base
  fast-forwarded to it would have its first-parent history run through the run's branch, its own commits on
  the merged side; and `_adopted_merge`, which keeps a retried merge from landing twice, looks for a merge on
  the base's first-parent line whose second parent is the run's tip.
- **F7** Two Merges at one moment are kept apart by git's own lock in a checkout and by the compare-and-swap
  elsewhere; the loser fails and is pressed again. There is no queue, and none is needed for that.
- **F8** A run's stages judge only its own base: two runs that pass alone and break together are caught by
  nothing before the base holds both.
- **F9** Every role's ask names the todo by its first path. The controller's finish of a run started before
  closeouts moves it at the first Merge, so in the conflict's turns it is not there — seen live.

### Refuted

- **"The 71-file change at the gate is cosmetic."** The agent's own earlier reading, and wrong: F4 — the gate
  is where the operator judges what lands, and it showed everything but that. The reviewer's finding stands.
- **"Finalize by fast-forwarding the base to the run's reconciliation commit" (Q3b).** F6: it flips the
  base's first-parent history and breaks the check that makes a retried merge safe; and D24 keeps an explicit
  merge commit named for the plan, which the proposal drops without arguing it. The aim — no ceremonial
  second merge around an integration already made — is met by Q3a, which makes no reconciliation commit.
- **"The gate shows the current base tip → the final tree."** Nearly: the base tip the run was reconciled
  with. Against a tip that moved again, the change would show that later work undone. The two are the same
  tip whenever a Merge may land (invariant 2).

## Proposed design (on Q1–Q3)

1. **A run records the base tip it stands on** — at its worktree's creation, and again each time the base is
   brought in.
2. **Reconcile** after a verify's `PASS`, before the work that makes the build final: the base's tip is that
   one — on; it moved — it is merged into the worktree, uncommitted, as a conflict's is today, and the
   combined tree is judged (Q2) before the run goes on. Until the base stands still across a `PASS`.
3. **The gate's change** is from the recorded tip to the final tree.
4. **Merge**, under one check that the base's tip is still the recorded one: the final tree lands as one
   commit on that tip and the merge commit named for the plan, whose tree is the final tree exactly. Moved:
   nothing is committed or merged, the change is reopened and the run reconciles again.
5. **The history** reads a run's first change from the commit it started from, and a turn after the base
   came in from the tree reconciled, never across it.

## Required invariants

1. Nothing lands on the base that a stage did not judge on that base and the gate did not show.
2. A Merge lands only while the base's tip is the one the run recorded; otherwise it changes nothing,
   anywhere.
3. The base's first-parent history is its own; a run adds the same two commits whatever the base did
   meanwhile.
4. A conflict never resolves on the base or in the controller.
5. Every recorded history replays as it was written (D25); a run started before this takes no new step.
6. No remote is reached (D2).

## Implementation tasks

- [x] 1. The gate's change after a conflict is read against the base brought in (F4), and the page says which
      it read against.
- [ ] 2. The recorded base tip; the reconcile step and its place in the workflow (Q1, Q2).
- [ ] 3. The Merge that lands or changes nothing; the landing as Q3 decides.
- [ ] 4. The history's rows (F5).
- [ ] 5. D24, the stops' view, `using.md`, the tests' index.

## Test-first and verification plan

| case | wrong behaviour it captures | state |
|---|---|---|
| a conflict handed back: the change read is the run's files, against the base brought in | the base's commits shown as the run's change (F4) | done — `test_worktrees.Merge`, with its control: against the run's own commit the base's files are what shows |
| two runs, the second in conflict with the first once it landed | a conflict met only at the operator's Merge | red first |
| two runs, the second merging cleanly onto the first | a combined tree landing unjudged (F1, F8) | red first |
| a Merge after the base moved again | anything committed or merged | red first |
| the base's tree after a landing | any tree but the final one | red first |
| the base's first-parent history after a conflict's run landed | a "Merge base into run" commit, or the run's branch on the first-parent line | red first |
| a run recorded before this, replayed | a new step commanded | the recorded histories |
| the history's rows after the base came in | the base's commits as a turn's change; a first row read from a later commit (F5) | red first |

## Review record

### 2026-10-07 — investigation, and the first task

- **Trigger:** the operator's questions at a gate after a conflict; the external reviewer's `PATCH` on the
  merge flow.
- **Applied now:** the gate's change after a conflict (F4). Red first; then on the live run's worktree, read
  with this code and changing nothing there: 3 files against the base brought in, where the running page
  showed 71.
- **Planned, not built:** the reconciliation flow — a change to what the workflow commands and to what a
  Merge means, which waits for Q1–Q3.
- **Refuted:** see [Refuted](#refuted).
- **Verification, the modules the first task touches:** Windows — worktrees, activities, architecture: 21
  classes, 104 tests, OK. WSL — those, the workbench and the public check's own tests: 35 classes, 182 tests,
  OK. Control: read against the worktree's own commit again, the new test fails on the comparison itself.
  `make demo`, the page's change view in a real browser on this code: passed. `make public-check`: passed.
- **Not run:** the full suite; a restart — the live Workbench and workers still run the code from before
  this, so the running page shows the old comparison until they are restarted.
