# Operator review milestones

**Status:** IMPLEMENTED AND VERIFIED — live current intervals active
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

- **D4** Implement both todos through implement-approved-change.
  - Effect: D3's investigation-only phase is complete; implement T1–T6 within the revised same-base and retention boundaries.
  - Reason: not stated.
  - Date/source: 2026-11-12, current operator implementation request.
- **D5** Show the interval after a submitted revision live while roles work.
  - Effect: the current interval is visible first and follows worktree changes without waiting for another operator stop.
  - Reason: the operator needs to see work responding to their latest submission.
  - Date/source: 2026-11-12, operator follow-up.

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

- [x] **T1 — Contract and red fixtures:** defined accepted-action intervals, bounded capture and explicit unavailable/cross-base refusal; added operator-answer, closeout, cancellation and replay fixtures.
- [x] **T2 — Native snapshot retention:** atomic, execution-scoped private refs retain the original recorded base object and sampled tree. Retry/CAS, unchanged protected Git state, actual garbage collection and safe release are covered; the existing scanner remains unchanged.
- [x] **T3 — Temporal boundary capture:** accepted answers capture before reopen/reconcile/role/cleanup effects. Errors remain visible, cancellation starts no next role, duplicate answers remain idempotent, and the recorded protocol version preserves legacy replay.
- [x] **T4 — History projection:** accepted actions and checkpoint results are associated by recorded stop identity. Initial, historical and current intervals retain explicit evidence quality; per-turn changes remain intact.
- [x] **T5 — Workbench export:** collapsed milestone/range selection reuses the immutable diff and clipboard readers. Whole-run copy, disclosure/selection/focus, current-boundary advancement and explicit unavailable states are verified in the real browser.
- [x] **T6 — Verification and docs:** host suites, focused regressions, replay, browser acceptance and public-safety checks passed. Stable owners are updated; staging and commits remain operator-owned.

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

### 2026-11-12 — Approved implementation

- D4 authorizes implementation. Git capture/ref retention, recorded-protocol workflow activation, history projection and same-base export are implemented through their existing owners. No milestone commits or parallel history store were introduced.
- New accepted actions close intervals before reopen/cleanup. Refused/duplicate answers do not create another capture. Capture failure is visible without losing the answer; cancellation starts no follow-on role. Old histories still replay, and missing old captures remain unavailable.
- Current endpoint exports require a stable operator stop, rechecked against Temporal execution status after sampling; busy current exports wait for a stop while Copy all changes remains available. This refines A3 without claiming an atomic filesystem snapshot.
- Native Git tests cover unchanged protected state, competing capture, worktree removal, real garbage collection and safe owner-scoped release. Windows capture exposed CRLF translation in text-mode subprocess stdin; ref transactions use literal UTF-8 bytes on both hosts.
- Targeted range/copy checks pass, including Unicode, missing/cross-base evidence, concurrent closure, page identity/progress validation and clipboard refusal. The real-browser fixture copied a large exact milestone and a larger net range, using native keyboard activation, and preserved whole-run copy.
- Final review reproduced an additional retention failure: retaining only the base tree lets Git prune the original commit after replaced base history. The new regression failed with `ChangeRefused`; retaining the original base object makes the commit-addressed export survive real garbage collection.
- Full acceptance: `bash run-tests.sh` passed 898 tests; `powershell -NoProfile -ExecutionPolicy Bypass -File run-tests.ps1` passed 671 tests. The initial WSL attempt exposed a stale test wait for queried MERGED status before native closure; waiting for the authoritative closed view fixed that test without weakening production state ownership.
- After the final retention and UI-state corrections, the workspace checkpoint/diff, application-range and browser-copy/cache checks passed 22 tests on WSL and 23 on Windows, including real Edge acceptance. The full-suite counts precede the added base-retention regression.
- Stable documentation is updated in orchestration, workspace, application, interfaces and usage. Public-safety scanning, its known-bad control and an isolated native-ref scanner check passed. No live activation, paid call, worker/WSL restart, staging or commit was performed.

### 2026-11-12 — Completed-run visibility correction

- Confirmed the reviewer finding: the worktree-only visibility gate also hid historical milestones after cleanup. The disclosure now remains available for recorded intervals; only the live-worktree reader and actions depend on retaining the worktree. Visibility is refreshed when asynchronous history arrives.
- Red: `tests.interfaces.test_review_browser.ReviewBrowser.test_discarded_run_keeps_historical_exports_on_its_normal_page_after_cleanup` reached a genuinely closed DISCARDED Temporal execution, removed its real Git worktree and failed because the ordinary page hid retained milestones. The corrected implementation passes the same scenario and copies the retained patch with worktree actions hidden. The test server's unsupported listing API is substituted with that real execution's description; run status, history, Git lifecycle and exports use their production owners.
- Focused verification: 26 WSL tests and 28 Windows tests passed across history, milestone ranges, clipboard, terminal caching and real Edge scenarios. Earlier full-suite results remain the baseline; no execution contract or native process-reuse code changed. Stable interface and usage documentation now states historical visibility after cleanup.

### 2026-11-12 — Authorized live activation

- Operator requested activation for the existing paused workflow. Preflight confirmed no pending activities and settled role turns. `make reload` gracefully replaced both Orchestra workers; `make workbench-restart` loaded the shared client and server. `make check` confirmed the service and each assigned queue polling. WSL, Temporal and unrelated workloads were not restarted.
- The existing workflow now advertises the milestone protocol. A hash comparison of its state, stop and configuration is unchanged across activation. Its live Workbench page exposes Review milestones and Current milestone, and the new endpoint returns its expected range-validation refusal. No answer, model call or retrospective snapshot was submitted. Future accepted revisions capture their own baseline; missing earlier snapshots remain unavailable.

### 2026-11-12 — Live current-interval follow-up

- The latest accepted revision has a valid retained checkpoint. The previous historical interval cannot export from its missing legacy start; that does not invalidate the latest checkpoint. No historical capture is fabricated.
- The original stop-only current export did not satisfy D5. Current reads now sample during a stable role or stop, refuse changed stage/base/worktree identity, and freeze the resulting tree for subsequent file and patch reads.
- The current interval appears first and opens on a new accepted boundary. Visible updates reuse the existing worktree feed, coalesce in-flight reads, and retain historical controls. The normal run renderer reloads history on stage changes to resolve pending capture metadata.
- Regression-first evidence: application tests rejected running-role reads under the old stop-only implementation; the real Edge fixture failed waiting for automatic current-interval display. Both pass after their respective changes. The fixture adds a real Git file after the boundary, observes it via the change feed, copies its exact patch excluding earlier work, and checks pending-to-recorded metadata through the normal run renderer.
- Full suites passed: 919 WSL tests and 692 Windows tests. A subsequent browser-only refinement refreshes on stage transitions as well as feed events, so the final edits cannot be missed before a stop. Its regression failed without that refresh; the final application/Edge run passed all 10 tests, including exact live copy, metadata completion, closed-history exports and persistent terminal restoration. No broad suite was repeated for those three UI lines.
- The existing Workbench service loaded the application reader without replacing either worker. Live browser checks confirmed the current interval is first and open, has the latest accepted checkpoint as its base, lists the actual revision's files, and matches immutable patch readback. The workflow state, stop and configuration hash stayed unchanged across activation. Health checks confirmed both assigned queues polling; no WSL restart, agent interruption, answer submission or paid call occurred.
- Public-safety checks and diff validation passed. Native process reuse and account admission remain outside this scope.
- Subsequent live acceptance observed another operator Merge capture a valid checkpoint; the new current interval correctly showed no additional files. The Git commit stopped on missing author configuration, independently of checkpoint capture; no identity or repository configuration was changed during this work.
