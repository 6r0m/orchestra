# The engineer closes the todo out after the architect's PASS; the merge commits exactly what the gate showed

**Status:** IMPLEMENTED — awaiting the external review (D3); the full suite on both hosts, `make demo` and the
restart acceptance are not run yet.
**Scope:** the run's finalisation: a `closeout` stage ([stages.py](../app/foundation/stages.py)), its flow rule
([flows.py](../app/foundation/flows.py), [flows/](../flows/README.md)), the workflow's path through it
([workflow.py](../app/orchestration/workflow.py)), its guard and the reopening of a change sent back
([activities.py](../app/application/activities.py), [worktrees.py](../app/workspace/worktrees.py)), what the
history shows of it ([client.py](../app/application/client.py)) and the trace's names for it.
**Stable documentation owner:** architecture D24, with D2, D4 and D13, in
[structure.md](../docs/architecture/structure.md); the stops in
[stops.md](../docs/architecture/diagrams/stops.md); the trace's rows in
[trace-contract.md](../docs/architecture/trace-contract.md).

## Goal

At the final gate the operator reads the change in its final state — the todo closed out, where the
repository keeps finished todos — and Merge commits exactly that tree.

## Authority register

### Operator decisions

- **D1** After the architect passes the implementation, an agent turn closes the todo out before the operator's
  gate: the documentation is up to date, what matters is moved out of the todo, its noise is cut, and it is moved
  to the repository's proper done place. The controller and the operator come after it.
  - Date/source: 2026-10-07, operator: *"agent should move to done when architector pass implementation, operator
    only review files and approves merge"*; *"after architect pass should be agent turn to close todo properly -
    update docs - move important info from todo without noise like implement change skill says and move to proper
    done and then only give to controller to operator"*; *"I think we need better to let agent close out."*
- **D2** The reviewer writes nothing into the todo; the agent sets its status.
  - Date/source: 2026-10-07, operator: *"reviewer doesn't need pass status to todo, agent when see do"*.
- **D3** The external reviewer's brief is evaluated against the code and applied where it holds; a point that is
  wrong is refuted, not applied. Its points: one narrow engineer closeout turn; no implementation change in it;
  the tree it leaves frozen, shown at the final gate, and the only one a merge commits; no architect review after
  it, the operator being the authority over its change; a revise back into the reviewed loop; six named tests.
  - Date/source: 2026-10-07, operator, relaying the brief: *"Critically evaluate the reviewer's feedback against
    the actual code … Update the code/docs … If any reviewer points are incorrect, explicitly highlight and refute
    them"*.

### Open questions

- **Q1 [OPEN - NON-BLOCKING]** Should a new run refuse a building flow that schedules no closeout? Today it holds
  (A1). For the reviewer.

### Working assumptions

- **A1 [ACTIVE]** A closeout is a step a flow schedules, between a `verify` and the merge; both shipped flows
  schedule it. A flow without one still holds and keeps the controller's move of the plan at the merge. The
  workflow checks a run's recorded steps on every replay, so a rule that refused such a flow would stop every
  earlier run from replaying, and a run already waiting at its gate still needs its plan finished.
- **A2 [ACTIVE]** "Implementation" is every path but the repository's todo folders and its documents, told by
  type: `.md`, `.mdx`, `.rst`, `.adoc`. The brief asks for the guard and does not draw its line.
- **A3 [ACTIVE]** A revise undoes the closeout before its role's turn — each path it changed is again as the
  architect verified it, bar one changed again since — and the build closes out anew once it passes. A conflict
  undoes nothing: the closeout is in the run's commit by then.
- **A4 [ACTIVE]** The descriptor's `todo_done_dir` stays the repository's stated convention; the closeout's ask
  names it, and the controller moves nothing for a run that closes out.
- **A5 [ACTIVE]** No skill is bound to the closeout by default: its ask says everything.

## Non-goals

- A second architect review after the closeout (D3).
- A check that the closeout did its job — that the todo left its working folder. A repository's convention may be
  another; the operator judges the closeout's change.
- Removing the controller's move of the plan: runs already started hold it (A1).
- The Workbench's Plan fact, which names the plan where the run wrote it.

## Verified evidence

- **F1** The controller finished the plan inside the merge, after the operator's answer (`_finish_plan`), so the
  commit was the verified tree plus that move — not the tree the final gate showed — and the gate showed the todo
  in its working folder under the status its plan stage gave it.
- **F2** Nothing could write that status between the plan's approval and the merge: the architect is read-only
  and a `PASS` on a tree that moved during its turn fails the step; the build's ask did not name the status line.
- **F3** The merge was the last step right after a `verify` (`flows.check`), and a worktree that no longer matched
  the verified tree was refused by the merge. A writing turn after `PASS` therefore needs a new stage and a
  different tree for the merge to hold.
- **F4** Where a repository keeps a finished todo is already its descriptor's: `todo_dir`, `todo_done_dir`
  (null deletes), `todo_name` ([repos.py](../app/workspace/repos.py)).
- **F5** `flows.steps_of` runs in the workflow on each replay, and the status query of a closed run replays it.
- **F6** Found on the way, and fixed here because the merge's exactness rests on it: `work_tree` computed the
  tree on a copy of the index stamped when the copy was made, so git trusted the stat of a file rewritten to the
  same size in the second the index was written and left that edit out of the tree. Measured with git 2.55 on
  Windows; the copy now keeps the index's time.

### Refuted

- **"The script cannot know which folder a finished todo goes to."** F4: the descriptor says it. What the script
  could not do is cut a todo to its record or move what stays true to its owner — which is D1's real ground.
- **The brief's "architect verified tree == merged tree" as the old invariant.** F1: the merged tree was already
  the verified tree plus the controller's move. The new rule is the stricter one: the merge commits the gate's
  tree exactly.
- **The brief's "reuse the existing implementation skill" read as binding it to the closeout.** That skill's
  procedure is a red test and an implementation, which a closeout may not make; the engineer's session already
  holds it from the build. The closeout's ask stands alone (A5), and a skill can still be bound to the stage.

## Decision

A sixth stage, `closeout`, the engineer's. A flow schedules it between the `verify` and the merge. Its turn may
change only the todo folders and documents (A2): the activity reads what changed from the verified tree to the
tree the turn left and fails the step — `closeout_violation`, the files named — on anything else. The tree it
left is recorded as the run's `closeout_tree`: the final gate holds it and the merge commits it, finishing no
plan itself. A revise reopens the change first (A3). The closeout is a phase of its own in the trace and judges
nothing; the build's count of judgements stays across it, so that build's first judgement is scored once.

### Premise / KISS gate

No framework: one stage ask, one flow rule, one check, one git function to undo. The reopening exists because
the roles' asks name the todo by its path, and a todo moved or deleted by the closeout is not there to read.
Knowingly given up: the architect's eyes on what the closeout writes (D3), and one mechanism — two now close a
plan, by the run's flow (A1).

## Required invariants

1. A closeout changes nothing the architect verified but the todo folders and documents; a turn that did holds
   no tree for the gate.
2. The merge commits exactly the tree the run holds — the closeout's, or for a flow without one the verified
   tree with the controller's move — and refuses a worktree that is no longer it, changing nothing.
3. A change sent back is reopened before any role's turn; a reopening that fails stops the run there.
4. Every recorded history replays; a run started before closeouts takes no new step.
5. The architect stays read-only and writes nothing (D2).

## Implementation tasks

- [x] The stage, its ask, what a closeout may change; the flow rule; both shipped flows.
- [x] `changed`, `reopen` and the merge's two ways of holding a tree; the tree computed on an index copy that
      keeps its time (F6).
- [x] The activity's guard and the `reopen` activity; the workflow's closeout segment, the reopening on a
      revise, the conflict path, the build's count kept.
- [x] The history's closeout change; the trace's phase and error type; the page's words for the stage.
- [x] The demo's and the acceptance's fake engineer close out.
- [x] The stable documents ([Documentation plan](#documentation-plan)).

## Test-first and verification plan

Red, before any of it existed: the six new test classes failed on the missing stage, rule and functions — the
flow refused with *no such action*, `KeyError: 'closeout'`, no `changed` or `reopen`.

Green, the modules the change touches, named to the repository's own runners, one host after the other:

- WSL, `bash run-tests.sh` on flows, policy, workflow, stops, replay, round boundaries, worktrees, activities,
  settings, workbench, settings delivery, cli, observability, trace parity, terminals, architecture and the
  public check's own tests: **102 classes, 495 tests, OK**.
- Windows, `run-tests.ps1` on terminals, worktrees, workflow, stops, replay, trace parity, policy, flows,
  activities and architecture: **58 classes, 296 tests, OK**.
- `make public-check`: passed. It reads tracked files, so the new todo and the new history were read by hand:
  the history's payloads, decoded, hold the fakes' paths and the recorder's name only.

Controls. With four guards taken out together — the activity's check of what a closeout changed, the merge's
check of the closeout's tree, the flow rule, the reopening on a revise — seven tests failed, each on its own
guard, and the working tree was byte for byte as before once they were put back. The index copy's control is in
its test: a copy stamped when it was made leaves the edit out. A new recorded history,
`closeout_revise_conflict_merge`, replays with the others and fails on `ChangedRun`.

What each of the brief's six tests is, here:

| the brief's test | where |
|---|---|
| PASS → closeout → final gate | `test_stops.Closeout`, and its control: a flow with no closeout |
| the todo moved to the repository's done place | `test_worktrees.Closeout`: the merge commits the closeout's tree, the todo where its engineer put it; the ask names the place (`test_stops.Closeout`) |
| a closeout cannot change implementation | `test_activities.Closeout` on a real repository; `test_stops.Closeout` in a run |
| the final gate shows the post-closeout tree | `test_worktrees.Closeout`: a read of the change is the closeout's tree |
| a change after the snapshot refuses the merge | `test_worktrees.Closeout`, nothing committed, merged or staged |
| a revise returns to the reviewed loop | `test_stops.Closeout`, both roles; `test_worktrees.Closeout` for the undo |

Not proven here: how a real agent closes a todo out — what it cuts, what it moves to a stable document. That is
a live run's to show. `make demo` and `tests/acceptance_restart.py` hold a closing-out fake engineer and were
not run.

## Documentation plan

- **Owner:** D24 for the lifecycle; D2 the stages, D4 what an architect judges, D13 the flow's rules.
- **Updated:** [stops.md](../docs/architecture/diagrams/stops.md), [trace-contract.md](../docs/architecture/trace-contract.md),
  [decisions.md](../docs/history/decisions.md), [using.md](../docs/using.md), the [README](../README.md),
  [flows/README.md](../flows/README.md), [todo/README.md](README.md), [tests/README.md](../tests/README.md), each
  concern's own structure note, and [the engineer's persona](../roles/engineer.md).

## Completion criteria

- The external reviewer's PASS (D3); then the full suite once on both hosts, `make demo` and the acceptance.
- A live run closes its todo out and merges the tree its gate showed.

## Review record

### 2026-10-07 — implementation

- **Trigger:** D1–D3.
- **Residual risk, said once:** what a closeout writes lands with no architect's review, and a document is told
  by its type — a persona, a skill or an agent's instructions in Markdown is one too. The operator reads the
  closeout's own change in its turn's row.
- **Deployment note:** a Workbench and workers started before this change refuse both shipped flows — *no such
  action* — until they are restarted. A run started before it keeps the controller's move at its merge.
