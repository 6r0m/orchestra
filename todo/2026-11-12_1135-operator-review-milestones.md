# Operator review milestones

**Status:** REVIEW REQUIRED  
**Scope:** durable review checkpoints, operator-action history projection and milestone diff/copy UI  
**Stable documentation owners:** [orchestration](../app/orchestration/docs/architecture/structure.md), [workspace](../app/workspace/docs/architecture/structure.md), [application](../app/application/docs/architecture/structure.md), and [interfaces](../app/interfaces/docs/architecture/structure.md)

## Contents

Goal · Authority register · Non-goals · Verified evidence · Current architecture · Problem · Decision · Invariants · Implementation tasks · Verification · Documentation · Rollout · Completion criteria · Review record

## Goal

Repeated external review should not require resending the entire accumulated patch. The Workbench automatically groups changes around operator decisions and lets the operator copy the whole run, one milestone, or a range since an earlier milestone. Every exported range identifies the snapshots it describes and stays consistent while the worktree changes.

## Authority register

### Operator decisions

- **D1** Changes should have automatic history blocks around manual operator stages, including revision and approval.
  - Effect: repeated review/revise cycles remain individually understandable rather than showing only one accumulated change.
  - Reason: an external reviewer may already have the previous version.
  - Date/source: 2026-11-12, current operator request.
- **D2** Allow copying either all changes or an exact milestone.
  - Effect: preserve the whole-run export and add a focused export without resending previously shared work unnecessarily.
  - Reason: repeated copy/paste to an external reviewer currently requires copying accumulated changes again.
  - Date/source: 2026-11-12, current operator request.
- **D3** Keep this investigation in a separate todo from terminal caching; do not implement it in this phase.
  - Effect: the plans are independently reviewable and neither file's existence approves implementation.
  - Reason: not stated.
  - Date/source: 2026-11-12, current investigate-change request.

### Operator gates

- **Q1 [OPEN - NON-BLOCKING]:** Should successful clipboard copies also create workflow milestones, or should boundaries follow operator stage answers only? Default while open: A1. The UI must not claim to know what an external reviewer actually received.
- **Q2 [OPEN - NON-BLOCKING]:** Should completed-run milestone snapshots expire automatically? Default while open: A4. This is historical review retention, distinct from the terminal todo's disposable cache cleanup.

### Working assumptions

- **A1 [ACTIVE]:** Boundaries follow accepted Temporal stop answers: approve, revise, guide and continue, plus merge/discard answers when a usable snapshot exists. Terminal keystrokes, reading, scrolling, Refresh and Copy create no milestone. Rejected or duplicate answers create no new milestone.
- **A2 [ACTIVE]:** A milestone is an operator-action interval, not every architect round, phase or episode. Automatic PATCH loops remain together unless another human action separates them. The original all-changes view remains available.
- **A3 [ACTIVE]:** Capture the worktree at an accepted answer before reopening, reconciliation, another role or destructive cleanup can change it. The last interval can show a clearly labelled current snapshot while still open. A capture is an immutable Git sample, not a claim of filesystem-wide atomicity or architect approval.
- **A4 [ACTIVE]:** Preserve new checkpoint trees with private repository-local Git refs, including after ordinary merge/worktree cleanup. Do not add an automatic expiry service; retain refs until an explicit artifact-retention/purge operation removes them. Document the disk-retention consequence and keep this policy separate from browser/agent cache eviction.
- **A5 [ACTIVE]:** External review remains manual. Copy exports a patch plus minimal range labels, not full operator notes, agent transcripts or a message sent to another service.

## Non-goals

- Automatic intermediate commits, staging the real index, stash operations, rebasing a historical patch for presentation, or changes to the final merge gate.
- A billing/observability dependency, another database/history service, AI-generated milestone summaries, or automatic contact with an external reviewer.
- Inferring that Copy means the reviewer received or approved its contents.
- Fabricating exact operator-time snapshots for legacy events that never recorded one.

## Verified evidence

- [client.py](../app/application/client.py), `history` and `_changes`, already derive completed turns, original accepted answers, their event ordering and per-turn Git tree ranges from Temporal. Answers have stable stop identity and an `after` relationship to completed work. New role-activity names are already recognized there.
- [run.js](../app/interfaces/workbench/static/run.js), `renderHistory`, `answerRow`, `roundChange`, already shows operator rows and engineer changes since a prior review. It does not aggregate automatic rounds into operator milestones or offer a milestone copy control.
- [change.js](../app/interfaces/workbench/static/change.js) keeps a selected snapshot for Refresh/file reads; its top-level Copy all changes deliberately reads a fresh whole-run snapshot. That live command is not a historical checkpoint.
- [diff.js](../app/interfaces/workbench/static/diff.js), `copyPatch`, already reads a large patch in bounded chunks against one immutable base/tree pair. Reuse that route; do not concatenate per-round patches and call them one net change.
- [worktrees.py](../app/workspace/worktrees.py), `work_tree` and `review_diff`, creates Git trees using a private index and reads named snapshots after worktree removal when the repository still holds them. `held` explicitly reports objects Git has pruned. Current tree hashes are not durable retention roots.
- Native [Git ref updates](https://git-scm.com/docs/git-update-ref) can retain object references; [Git GC](https://git-scm.com/docs/git-gc) preserves objects reachable through the refs namespace. This avoids milestone commits. Compatibility with this project's scanners and supported Git versions still needs the planned regression evidence.
- [workflow.py](../app/orchestration/workflow.py), `_stop`, `_final_gate`, `_reopened` and `_reconcile`, owns accepted answers, closeout reopening and base movement. None currently records a Git sample for every operator boundary.
- Existing history projection intentionally separates base updates from engineer work and closeout changes from verified implementation. Milestones must preserve those distinctions.
- Baseline: 29 existing tests passed across terminal streaming, history projection, snapshot diff reads and completed-turn lifetime. They establish reusable seams, not the new milestone feature. No exact-boundary or pinned-after-GC acceptance was run in this investigation.
- The existing uncommitted prompt/context changes are a dependency to preserve. A milestone must never narrow the operator notes delivered independently to either role.

## Current architecture and source of truth

Temporal owns operator answers and the run's sequence; Git owns bytes and snapshot objects. Application composes those into the read model and target-host activities. The Workbench renders/copies the resulting ranges through the existing diff API. Langfuse remains optional observability and owns neither milestone order nor source snapshots.

Primary routes: [workflow](../app/orchestration/workflow.py), [activities](../app/application/activities.py), [history projection](../app/application/client.py), [worktree operations](../app/workspace/worktrees.py), [Workbench server](../app/interfaces/workbench/server.py), [run history](../app/interfaces/workbench/static/run.js), [Change view](../app/interfaces/workbench/static/change.js), and [shared diff reader](../app/interfaces/workbench/static/diff.js).

## Problem and root cause

The existing UI has cumulative changes and per-engineer-turn review ranges, but no operator-level review iteration. Several automatic rounds may answer one pasted review, while approvals, guidance or failures may cross phases without producing a reviewed tree. Grouping solely by episode, time or the nearest review would produce misleading boundaries. A recorded object ID can also become unreadable after Git prunes an unreferenced tree.

## Decision

### Premise / KISS gate

Extend the existing Temporal/Git/read-model owners. Record a bounded checkpoint reference at each accepted operator boundary, derive intervals from those events, and reuse the existing paged diff and copy components. Add a target-host checkpoint operation and private Git refs only where current review references do not provide the required boundary/retention. Store metadata and object IDs in Temporal, never patches or transcripts.

This adds no service, process, queue, credential, model call or alternate workflow. It adds one lifecycle-bound snapshot operation, a history projection and a small UI selector/disclosure. A failed optional checkpoint is recorded as unavailable rather than changing execution decisions or pretending the interval is empty.

Knowingly give up tracking an external reviewer's actual memory and exact pre-feature action-time snapshots. Under A1, Copy is not an additional operator stage. Under A4, history refs are retained rather than governed by a newly invented cleanup daemon.

### Milestone semantics

1. Initial work starts from the run's recorded base. Each accepted answer closes the preceding interval at its checkpoint and starts an interval labelled by that action, recipient and time, using a stable stop/update identity rather than a clock-derived key.
2. Capture after the answer is consumed and before its follow-on side effects. Keep capture separate from the answer Update's acceptance: an async read failure must not turn an accepted-history event into a fictitious successful checkpoint. Persist a success or explicit unavailable result in normal workflow history.
3. A revision at the final gate snapshots the offered closeout tree before `reopen` restores the verified todo. The next interval includes the net work through the following boundary; it does not rewrite that original checkpoint.
4. An open interval can be copied to a newly read immutable endpoint. Freeze that endpoint for all chunks/file reads and identify it as current/unverified where appropriate. Do not silently move the export baseline after Copy or claim it equals an external reviewer's last paste.
5. An exact milestone diff is the net Git change between its endpoints: repeated edits/reverts collapse naturally. A selectable earlier checkpoint supports skipped/intermediate review stages; whole-run copy keeps its established current-base meaning.
6. Initially, selection and exact copy support ranges within one recorded base. A range crossing base reconciliation is explicitly unavailable, with the base boundary identified; never silently attribute upstream changes to the engineer or manufacture a rebased single patch. Multi-section cross-base export is deferred until a concrete need justifies it.
7. Identical available endpoints mean a proven empty change. Missing, failed or pruned endpoints mean unavailable, not empty. Preserve existing per-review history for old runs and label any legacy reconstructed review boundary accurately rather than inventing an operator-time sample.

### Alternatives considered

- Group only existing turns by episode or phase: no new snapshots, but automatic episodes and missing review trees do not reliably match D1.
- Use only current Copy all changes or concatenate round patches: either resends accumulated work or produces a different result from a net snapshot diff.
- Commit/stash after every approval: creates code-history/index effects unrelated to final merge and violates the existing ownership model.
- Archive full patches in a separate database or runtime store: duplicates Git content, adds retention machinery and still needs immutable range semantics. Prefer native tree references.

## Required invariants

1. The display projection cannot approve work, route a verdict, merge, modify a todo or change which operator notes a role receives. Accepted original notes remain complete across all milestone boundaries.
2. Each accepted answer contributes at most one boundary. Refused/stale/duplicate requests produce none; capture retries reuse an already pinned result for the same boundary rather than redefine it from later files.
3. Snapshot capture changes neither HEAD, the real index, branches, MERGE_HEAD nor worktree content. Its only Git retention mutations are validated, run-scoped private refs; no intermediate commit or ref is pushed.
4. A private ref keeps both required endpoints reachable. Concurrent runs sharing one repository cannot collide or release each other's references. Normal worktree cleanup must not erase retained review history.
5. Capture has a finite owned bound. Failure/outage remains observable and the ordinary operator action can progress with an unavailable checkpoint; Stop/cancellation cannot be held indefinitely for a display artifact.
6. The snapshot is evidence of sampled bytes, not independent verification. Existing assessed/verified/final tree guards remain the only corresponding execution checks.
7. All chunks, file reads and clipboard output use the same chosen endpoints and match Git's output byte for byte, including Unicode, binary markers, renames, deletes, modes and large patches.
8. Successful Copy is reported only after the whole selected range is read and clipboard writing succeeds. A failed copy does not advance a baseline or create a successful-share claim.
9. Replay compatibility is required. New capture commands must be gated by recorded capabilities/version data or a replay-safe patch whose behavior on existing paused runs is proven. Do not assume a patch first seen absent during replay will later enable itself.
10. Historical rendering is a read: it never creates retrospective milestones, repins arbitrary objects or calls a model. Missing legacy evidence remains explicit.

## Implementation tasks

- [ ] **T1 — Contract and red fixtures:** define operator-interval versus per-review meaning, exact accepted-event identity, capture timing, pending/unavailable states and cross-base refusal. Add realistic approve/revise/continue/closeout histories and Git fixtures before production changes.
- [ ] **T2 — Native snapshot retention:** extend the workspace owner with bounded private-index capture and run-scoped immutable ref retention. Establish idempotent retry/CAS behavior, safe identity validation and A4's ownership. Document a run-scoped release procedure which validates the exact namespace and expected object IDs, refuses other runs' refs, and never removes branches. Prove ref-backed reads after worktree removal and actual garbage collection, with the existing public scanner unchanged.
- [ ] **T3 — Temporal boundary capture:** integrate capture after consuming an accepted stop answer and before advancing to reopen/reconcile/role/merge/discard effects. Record references or an explicit failure, preserve original notes and existing answer idempotence, and handle cancellation without a new state-machine layer. Publish/gate version compatibility for old and paused runs.
- [ ] **T4 — History projection:** extend the existing history reader to associate accepted actions, checkpoint outcomes and reconciliation boundaries by recorded event order. Keep old per-turn changes intact. Produce initial, closed and open intervals with explicit evidence quality; omit no failed or zero-change stage merely because it has no new file.
- [ ] **T5 — Workbench export:** keep the collapsed Change disclosure and Copy all changes. Add concise milestone selection, a per-milestone disclosure and Copy this milestone; allow a range from an earlier checkpoint without adding a graph editor. Reuse `fileList`/`copyPatch`, preserve navigation/disclosure state, show current/unverified/unavailable distinctions and avoid long operator text in default clipboard exports.
- [ ] **T6 — Verification and docs:** prove the matrix, relevant consumers and replay; update only the stable owners below. Inspect the whole diff, preserve pre-existing work and leave staging/commits to the operator.

## Test-first and verification plan

Observe each permanent guard failing against current code before its production change. These are feature acceptance cases, not a claim that an external reviewer already received anything.

| Case | Red evidence today / required failing assertion | Green evidence |
|---|---|---|
| Two external revise cycles | no operator-level range/export; only accumulated or per-review changes | initial work and each revision are independently selectable; exact delta and all-changes exports match expected Git ranges |
| Approval, guidance, continue | not every accepted boundary records a tree | all selected actions have a stable boundary or explicit unavailable outcome; automatic rounds stay within their operator interval |
| Duplicate/refused answer | no milestone contract exists | one boundary for idempotent acceptance, none for refusal; protected state and notes unchanged by rejected capture requests |
| Concurrent editing/copy | live snapshot can change between separate reads | one immutable sample throughout pagination, file opening and clipboard completion; cancellation/failure never yields a successful partial copy |
| Closeout and reopen | existing history exposes closeout separately, not an operator span | the accepted revision freezes the offered tree first; later todo restoration/closeout is attributed to the correct interval without losing prior work |
| Base reconciliation | a naive endpoint diff includes upstream changes | cross-base selection/copy explicitly unavailable with its boundary identified; same-base exports remain exact and no hidden rebasing occurs |
| Snapshot failure/legacy | absence cannot prove no change | unavailable/read-only legacy states stay explicit; failure does not discard the answer, block execution indefinitely or invoke a model |
| Retention and isolation | hashes alone do not pin snapshots | milestone survives worktree removal and real `git gc`; same repository/two runs stay independent; releasing one approved ref cannot remove another |

Use [test_stops.py](../tests/orchestration/test_stops.py) and [test_replay.py](../tests/orchestration/test_replay.py) for sequencing, refusal, cancellation and old histories; [test_worktrees.py](../tests/workspace/test_worktrees.py) for Git state, GC and immutable diff reads; [test_workbench.py](../tests/interfaces/test_workbench.py), especially `HistoryRead` and `Transcript`, for the projection/API; and [demo_press.py](../tools/demo_press.py) or the existing browser acceptance owner for real keyboard/disclosure/clipboard behavior. Extend the existing owner or add a focused test module there rather than building another harness.

Run targeted cases first, then `bash run-tests.sh` and `powershell -NoProfile -ExecutionPolicy Bypass -File run-tests.ps1` sequentially under [tests/README.md](../tests/README.md). Run the applicable isolated browser scenario and `bash tools/public_check.sh`. No paid model call or external reviewer API is required.

## Documentation plan

- **Orchestration:** accepted-action boundaries, capture failure semantics and replay/version behavior in its existing [structure](../app/orchestration/docs/architecture/structure.md).
- **Workspace:** private snapshot retention and explicit release semantics in its existing [structure](../app/workspace/docs/architecture/structure.md); Git object/ref behavior remains that owner's responsibility.
- **Application:** the projection from Temporal/Git into review intervals in its existing [structure](../app/application/docs/architecture/structure.md).
- **Interfaces and usage:** milestone selection, snapshot quality and clipboard behavior in the existing [interface structure](../app/interfaces/docs/architecture/structure.md) and [using.md](../docs/using.md). Preserve the current Change spoiler; do not create another history store or duplicate architecture graph.
- Stable docs and code must not link to this todo. Historical review retention must not be conflated with the separate terminal-cache policy.

## Rollout and rollback

Use additive, versioned workflow behavior that replays old histories; existing paused runs begin exact capture at an eligible future accepted action, without fabricating earlier samples. New history readers continue accepting the existing turn/change records. Load new code through existing graceful Orchestra controls, with no WSL restart or interrupted role turn. Rolling the UI back may hide milestone controls but must not delete pinned objects or operator notes; do not roll a workflow worker back to code unable to replay commands already recorded.

## Completion criteria

- D1–D2 work through the real browser with two revise cycles and an approval, including a large patch; selected ranges match immutable Git endpoints rather than concatenated round outputs.
- Failure, duplicate, legacy, reconciliation, GC and same-repository concurrent-run cases pass, with no real-index/worktree/branch mutation from capture.
- Existing original operator-note delivery, workflow gates, timing/accounting and per-turn history remain correct. Snapshot failure does not become approval or a lost answer.
- Durable docs state the chosen retention and interval semantics. Relevant suites, browser acceptance, replay and public-safety checks pass; new refs remain private and no runtime content enters the public diff.

## Review record

### 2026-11-12 — Investigation

- Authority D1–D3 recorded. Q1/Q2 remain non-blocking under A1/A4; they are explicit defaults for review, not inferred operator decisions.
- Existing event history, reviewed trees and diff components provide most of the mechanism. Exact operator boundary capture, aggregation/export and GC-safe retention are the identified additions.
- The 29-test baseline passes. New milestone and GC-pin regressions remain implementation work. No production code, live workflow or external review service was changed.

### 2026-11-12 — Review reconciliation

- Only accepted Temporal stop actions create milestones; terminal keystrokes and clipboard operations cannot supply workflow authority.
- Same-base exact exports are the initial delivery. Cross-base ranges remain explicitly unavailable; multi-section bundles are deferred.
- Private ref retention requires a safe per-run release procedure. Reviewer GO does not authorize implementation; status remains REVIEW REQUIRED.
