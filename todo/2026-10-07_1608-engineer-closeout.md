# The engineer closes the todo out after the architect's PASS; the merge commits exactly what the gate showed

**Status:** IMPLEMENTED, the external reviewer's third PATCH applied, documents only — awaiting its re-review
(D3). The full suite on both hosts, the restart acceptance and a run with real agents are not run yet.
**Scope:** the run's finalisation: a `closeout` stage ([stages.py](../app/foundation/stages.py)), its flow rules
([flows.py](../app/foundation/flows.py), [flows/](../flows/README.md)), the workflow's path through it
([workflow.py](../app/orchestration/workflow.py)), its checks and the reopening of a change that goes back
([activities.py](../app/application/activities.py), [worktrees.py](../app/workspace/worktrees.py)), the
repository's own closeout documents ([repos.py](../app/workspace/repos.py)), what the history shows of it
([client.py](../app/application/client.py)) and the trace's names for it.
**Stable documentation owner:** architecture D24, with D2, D4, D13 and D25, in
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
- **D3** The external reviewer's feedback is evaluated against the code and applied where it holds; a point that
  is wrong is refuted, not applied.
  - Date/source: 2026-10-07, operator, relaying each round: *"Critically evaluate the reviewer's feedback against
    the actual code … Update the code/docs … If any reviewer points are incorrect, explicitly highlight and refute
    them"*.

### Open questions

- **Q1 [CLOSED by D3 — the reviewer's and the agent's decision]** A flow read to start a run that builds must
  close out; only a run's recorded steps may lack it.

### Working assumptions

- **A1 [RESOLVED by Q1]** A closeout sits between a `verify` and the merge. `flows.load` refuses a building flow
  without one; `flows.check`, which the workflow runs on a run's recorded steps at every replay, does not — so
  the runs started before closeouts go on replaying, and the controller still finishes their plan at the merge.
- **A2 [RESOLVED by D3 — the reviewer's and the agent's decision]** What a closeout may change besides the todo
  folders is the repository's to name: `closeout_docs` in its descriptor, each a path as git globs it. An entry
  that names none, or no entry, leaves a closeout the todo alone: no code calls a file a document.
- **A3 [ACTIVE]** A change that goes back from the final gate — a revise, or a merge in conflict — is reopened
  before its role's turn: each path changed since the verified tree is again as the architect verified it, bar
  one changed again since. The build closes out anew once it passes. The one exception is A6.
- **A4 [ACTIVE]** The descriptor's `todo_done_dir` is the repository's stated convention: the closeout's ask
  names it, the controller moves nothing for a run that closes out, and the turn is checked against it.
- **A5 [ACTIVE]** The closeout's ask says what must be left and what may be touched; how a todo is finished is
  the engineer's persona's. No skill is bound to the stage here: skills are the host's, not this repository's,
  and a bound skill a host lacks refuses every run on it (`prepare`). Binding one is a line in `stage_skills`.
- **A6 [ACTIVE]** A run of the first closeouts is told by the name its closeout recorded for the tree it left,
  `closeout_tree` (F10). Such a tree is held as a final tree is, and a conflict over it reopens nothing, as those
  runs recorded. No run of that shape is known outside the recordings, so one still open gains no reopening.

## Non-goals

- A second architect review after the closeout (D3).
- Judging how well a todo was closed — what was cut, what was moved to a stable document. The operator does.
- Removing the controller's move of the plan: runs already started hold it (A1).
- Keeping the verified tree's objects from git's pruning. A run sent back long after its closeout, in a
  repository git has pruned meanwhile, fails its reopening and says so.
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
- **F4** Where a repository keeps a finished todo is its descriptor's: `todo_dir`, `todo_done_dir` (null
  deletes), `todo_name` ([repos.py](../app/workspace/repos.py)).
- **F5** `flows.steps_of` runs in the workflow on each replay, and the status query of a closed run replays it.
- **F6** Found on the way, and fixed here because the merge's exactness rests on it: `work_tree` computed the
  tree on a copy of the index stamped when the copy was made, so git trusted the stat of a file rewritten to the
  same size in the second the index was written and left that edit out of the tree. Measured with git 2.55 on
  Windows; the copy now keeps the index's time.
- **F7** Every role's ask names the todo by the path the run began with. Once a closeout has moved or deleted
  it, that path holds nothing — after a conflict as after a revise; and a todo its repository deletes is then
  in no folder and no commit, only in the tree the architect verified.
- **F8** In this repository a persona, a skill and an agent's instructions are Markdown: a file's type does not
  tell a document from behaviour.
- **F9** Git's own pathspecs leave out a folder taken literally and a glob — `docs/` the folder, `**/README.md`
  the file wherever it is — from a tree-to-tree diff, measured with git 2.55 and 2.54.
- **F10** Two recordings of a run that closes out are published, each by the code of its round. The first names
  the closeout's tree `closeout_tree` and goes from its conflict straight to the engineer; the second names it
  `final_tree` and commands a `reopen` there. Both carry the same three patch markers and none for that
  reopening, so no marker tells them apart; the name their closeout recorded does. The workflow as the second
  round left it failed the first's replay at its revise: *activity type of scheduled event 'reopen' does not
  match*.

### Refuted

- **"The script cannot know which folder a finished todo goes to."** F4: the descriptor says it. What the script
  could not do is cut a todo to its record or move what stays true to its owner — which is D1's real ground.
- **The brief's "architect verified tree == merged tree" as the old invariant.** F1: the merged tree was already
  the verified tree plus the controller's move. The new rule is the stricter one.
- **"Use the existing stage-skill mechanism for the closeout procedure."** In part. The method is out of the
  code-owned ask, as asked; it went to the persona, the method's owner when no skill is bound. A closeout skill
  is not created or bound here (A5): it belongs to the host's skills, outside this repository.
- **"Rerun … `make demo` + acceptance" before the PASS, then "only then restart".** The acceptance restarts the
  live stack — its own first lines say so — which would put the live workers on this code before the PASS. It
  waits; `make demo`, a stack of its own beside the live one, does not. The reviewer accepted both.
- **"Put the conflict's reopening behind a named `workflow.patched` branch."** Its aim is met; its mechanism
  would break the rule it serves. F10: the second recording reopens at its conflict with no marker, and a
  history without a patch's marker replays that patch as absent — so the second published recording would stop
  replaying, as the first had. The recorded name decides instead (A6), and both replay as they were written.
  The reviewer accepted it, and D25 now says both ways.

## Decision

A sixth stage, `closeout`, the engineer's, and the one work that makes a build final (`stages.FINAL`). A flow
that builds schedules it between the `verify` and the merge. Once its turn ends two facts are checked, by the
repository's own descriptor: nothing changed from the verified tree but the todo folders and the documents the
repository names; and the todo is gone from its path and, where the repository keeps it, in the done folder.
Either failing fails the step, `closeout_violation`. The tree it left is the run's `final_tree`: the final gate
holds it and the merge commits it, finishing no plan itself. A change that goes back is reopened first (A3),
bar a conflict over a tree the first closeouts left (A6).
The closeout is a phase of its own in the trace and judges nothing; the build's count of judgements stays
across it, so that build's first judgement is scored once.

### Premise / KISS gate

No framework: one stage ask, two flow rules, two checks, one git function to undo. The reopening exists because
of F7. Knowingly given up: the architect's eyes on what the closeout writes (D3); and until the runs started
before closeouts are gone, two ways a plan is finished, by the steps a run recorded (A1).

## Required invariants

1. A closeout changes nothing the architect verified but the todo folders and the documents its repository
   names, and leaves the todo closed as its repository closes one; a turn that did otherwise offers the gate no
   tree.
2. The merge commits exactly the tree the run holds — its final tree, or for a run started before closeouts the
   verified tree with the controller's move — and refuses a worktree that is no longer it, changing nothing.
3. A change that goes back from the final gate after a closeout is reopened before any role's turn, and a
   reopening that fails stops the run there. One exception, as recorded: a conflict over a tree the first
   closeouts left reopens nothing (A6).
4. Every recorded history replays as it was written, none recorded over; a run started before closeouts takes
   no new step. No flow file starts another run like them.
5. The architect stays read-only and writes nothing (D2).

## Implementation tasks

- [x] The stage, its ask, the flow rules; both shipped flows.
- [x] `changed`, `holds`, `reopen` and the merge's two ways of holding a tree; the tree computed on an index
      copy that keeps its time (F6).
- [x] The activity's checks and the `reopen` activity; the workflow's closeout segment, the reopening on a
      revise and on a conflict, the build's count kept.
- [x] The descriptor's `closeout_docs` and its validation; none unless the entry names them.
- [x] The first closeouts' recording as it was written, the second under a name of its own; the tree's first
      name read by the workflow and the history, the first closeouts' conflict path kept.
- [x] The history's closeout change; the trace's phase and error type; the page's words for the stage.
- [x] The demo's and the acceptance's fake engineer close out.
- [x] The stable documents ([Documentation plan](#documentation-plan)).

## Test-first and verification plan

What each of the reviewer's tests is, here:

| asked for | where |
|---|---|
| PASS → closeout → final gate | `test_stops.Closeout`, and its control: a run started before closeouts |
| the todo moved to the repository's done place | checked after the turn: `test_activities.Closeout` on a real repository — still at its path, elsewhere than the done folder, and a repository that deletes; `test_stops.Closeout` in a run |
| a closeout cannot change implementation | `test_activities.Closeout`: code, a test and a persona in Markdown refused, the named documents not; `test_worktrees.Closeout` for git's matching |
| the final gate shows the post-closeout tree | `test_worktrees.Closeout`: a read of the change is the final tree |
| a change after the snapshot refuses the merge | `test_worktrees.Closeout`, nothing committed, merged or staged |
| a revise returns to the reviewed loop | `test_stops.Closeout`, both roles; `test_worktrees.Closeout` for the undo |
| the todo is at its path when the conflict's build starts | `test_worktrees.Closeout` on a real conflict, the merge still under way; `test_stops.Closeout`: reopened before that turn |
| a new building flow requires a closeout | `test_flows`, with its control: the same steps hold as recorded ones; `test_workflow.Flows`: its file starts no run |
| a run of the first closeouts still replays, and shows its closeout's change | `test_replay`, both recordings; `test_workbench.HistoryRead` |
| no file is a document unless the repository names it | `test_repos`: an entry that names none, and no entry; `test_activities.Closeout`: such a repository's closeout has the todo alone |

The results of each run, the controls and what was not run are in the [review record](#review-record).

Not proven here: how a real agent closes a todo out — what it cuts, what it moves to a stable document. That is
a live run's to show.

## Documentation plan

- **Owner:** D24 for the lifecycle; D2 the stages, D4 what an architect judges, D13 the flow's rules, D25 how
  a change to the workflow keeps every recording replaying.
- **Updated:** [stops.md](../docs/architecture/diagrams/stops.md), [trace-contract.md](../docs/architecture/trace-contract.md),
  [decisions.md](../docs/history/decisions.md), [using.md](../docs/using.md), the [README](../README.md),
  [flows/README.md](../flows/README.md), [todo/README.md](README.md), [tests/README.md](../tests/README.md), each
  concern's own structure note, [the example descriptors](../.orchestra/repos.example.json) and
  [the engineer's persona](../roles/engineer.md).

## Completion criteria

- The external reviewer's PASS (D3); then the full suite once on both hosts, then the restart acceptance.
- A run with real agents closes its todo out and merges the tree its gate showed.

## Review record

### 2026-10-07 — implementation, and the external reviewer's PATCH

- **Trigger:** D1–D3; then the reviewer's PATCH: two correctness gaps, two of ownership, two of naming and
  placement.
- **Applied:** a conflict reopens the change before the engineer's turn (F7); a closeout that left the todo
  unclosed fails; the documents a closeout may change are the repository descriptor's, no file type (F8, F9); a
  flow read to start a run must close out (Q1); the run's tree is `final_tree`, and the workflow, the flow rules
  and the activity name `stages.FINAL`, never the stage; the closeout's method left the ask for the persona.
- **Refuted:** see [Refuted](#refuted) — the skill, in part, and the acceptance before the PASS.
- **Verification, the modules the change touches, by the repository's own runners, one host after the other:**
  WSL — flows, policy, workflow, stops, replay, round boundaries, worktrees, repos, activities, settings,
  workbench, settings delivery, cli, observability, trace parity, terminals, architecture and the public
  check's own tests: 107 classes, 527 tests, OK. Windows — terminals, worktrees, repos, workflow, stops, replay,
  trace parity, policy, flows, activities and architecture: 63 classes, 328 tests, OK.
- **Controls:** with four of this round's guards taken out together — the closed-todo check, the reopening on a
  conflict, the rule a flow file keeps, the repository's documents replaced by any Markdown — their tests
  failed, the replay of the new history among them, and the working tree was byte for byte as before once they
  were put back. The first round's four — the check of what a closeout changed, the merge's check of its tree,
  the flow rule, the reopening on a revise — were shown the same way.
- **`make demo`**, a stack of its own beside the live one: passed — real workflow, worker, git and Workbench,
  the engineer's closeout a turn of the run that merges, its todo in the done folder inside the merge.
- **Not run:** the full suite; `tests/acceptance_restart.py`, which restarts the live stack; a run with real
  agents.
- **Residual risk, said once:** what a closeout writes lands with no architect's review. The operator reads the
  closeout's own change in its turn's row.
- **Deployment note:** a Workbench and workers started before this change refuse both shipped flows — *no such
  action* — until they are restarted. A run started before it keeps the controller's move at its merge. A
  repository whose closeouts are to bring documents up to date names them in its own entry of the operator's
  `.orchestra/repos.json` — this one's are `**/README.md` and `**/docs/**` — and only once the stack runs this
  code: the code before it refuses an entry with a key it does not know.

### 2026-10-07 — the external reviewer's second PATCH

- **Trigger:** two findings. The round before had recorded over a published history, against the replay rule;
  and a repository that named no documents was given every `README.md` and `docs/` folder by the code.
- **Applied:** the first recording is back as it was written, byte for byte, and replays; the second is kept,
  byte for byte, under a name of its own (F10, A6); the history reads a closeout's tree under either name. No
  default names a document (A2); the persona says what to do where the stage names none.
- **Refuted:** the marker, in mechanism only — see [Refuted](#refuted).
- **Red first:** with the first recording back and the workflow as the round before left it, the replay failed
  on that recording alone (F10).
- **Verification, the modules the change touches, one host after the other:** Windows — replay, stops,
  workflow, repos, worktrees, activities, flows, policy, trace parity, architecture and the history's reading:
  57 classes, 307 tests, OK. WSL — those and round boundaries, settings, workbench, settings delivery, cli,
  observability and the public check's own tests: 100 classes, 496 tests, OK.
- **Controls, one guard out at a time, each put back and the tree byte for byte as before:** the tree's first
  name unread by the workflow, and a conflict over such a tree reopened — the first recording stops replaying
  either way; a patch marker deciding the conflict's reopening instead of the recorded name — the second
  recording stops replaying, *scheduled event 'reopen' does not match activity command 'run_role'*; the first
  name unread by the history, and documents named by default — their tests fail.
- **`make demo`:** passed, the closeout a turn of the run that merges and its todo in the done folder inside the
  merge. **`make public-check`:** passed; the second recording, not yet tracked under its new name, is the blob
  the round before published.
- **Not run:** the full suite; `tests/acceptance_restart.py`; a run with real agents.

### 2026-10-07 — the external reviewer's third PATCH, documents only

- **Trigger:** the code accepted, the recorded name as what decides included. Two statements said more than
  the code does: D25, that every change to the workflow's commands goes behind `workflow.patched`; and
  invariant 3 here, that every change sent back is reopened.
- **Applied:** D25 states what it protects — every recorded history replaying as it was written, none recorded
  over — and the two ways that is kept, a patch marker or what the histories themselves record; each place
  that repeats the rule says the same. Invariant 3, A3 and the stops' view name A6's exception. No code.
- **Verification:** the checks that read these files — the architecture's routing and links, the replay and
  the public check's own tests: WSL 9 classes, 47 tests, OK; Windows, replay and architecture, 8 classes, 41
  tests, OK. `make public-check`: passed.
