# Warm role terminals

**Status:** IN PROGRESS — browser persistence verified and activated; native reuse proof awaits probe-hook trust
**Scope:** browser terminal retention and safe reuse of idle role-agent processes  
**Stable documentation owners:** [agents](../app/agents/docs/architecture/structure.md), [interfaces](../app/interfaces/docs/architecture/structure.md), and the [execution contract](../docs/architecture/structure.md)

## Contents

Goal · Authority register · Non-goals · Verified evidence · Current architecture · Problem · Decision · Invariants · Implementation tasks · Verification · Documentation · Rollout · Completion criteria · Review record

## Goal

Switching between roles or active runs immediately restores the latest terminal screen and resumes useful work without replaying the whole recording or needlessly repeating CLI/MCP startup. Temporary retained state is bounded and released when a run closes. A cache miss remains recoverable from the existing terminal record and exact vendor session.

## Authority register

### Operator decisions

- **D1** Returning to a role should show its terminal at the latest working position and reuse already initialized agent state where safe.
  - Effect: address both display replay and actual agent startup; a browser-only optimization does not fulfill the entire goal.
  - Reason: repeated loading when roles switch interrupts observation of the work.
  - Date/source: 2026-11-12, operator terminal-caching request and follow-up investigation request.
- **D2** Retain temporary caches while a run is working or waiting for operator action, and clear them for completed, rejected and other closed runs.
  - Effect: retention follows run lifecycle, with a global resource bound rather than an unbounded cache per job.
  - Reason: not stated.
  - Date/source: 2026-11-12, operator terminal-caching request.
- **D3** Orchestra updates must preserve WSL and unrelated work.
  - Effect: changes may replace Orchestra-owned processes gracefully; they must not restart WSL or interrupt an executing turn to activate caching.
  - Reason: restarting WSL disrupts other entities on a loaded machine.
  - Date/source: operator constraint from the preceding update/reload discussion.
- **D4** Investigate this as its own todo, separately from review milestones; do not implement in this phase.
  - Effect: this document is a proposal, not implementation approval.
  - Reason: not stated.
  - Date/source: 2026-11-12, current request invoking investigate-change.

- **D5** Implement both todos through implement-approved-change.
  - Effect: D4's investigation-only phase is complete; implement this plan under its native feasibility gate, preserving D1–D3.
  - Reason: not stated.
  - Date/source: 2026-11-12, current operator implementation request.

- **D6** Browser display caches must survive refresh and reopening while a run remains open.
  - Effect: retain bounded native serialized screens and confirmed cursors in browser-local storage;
    release them on confirmed closure and preserve record replay as recovery. This extends browser
    retention, not native agent-process reuse.
  - Reason: repeated replay is too slow while the operator continues reviewing the same work.
  - Date/source: 2026-11-12, operator clarification that caching must survive throughout ongoing work.

### Operator gates

- **Q1 [RESOLVED]:** D6 requires persistent browser snapshots across refresh/reopening.
- **Q2 [OPEN - BLOCKING FOR NATIVE REUSE]:** The isolated native Codex profiles require review of two probe hooks before fresh destination/correlation evidence can run. The operator has been asked whether to trust those two test hooks. Do not answer the native trust prompt or promote a warm process pool while that answer is pending. Browser retention and review milestones are independent.

### Working assumptions

- **A1 [SUPERSEDED by D6]:** The initial browser-only delivery retained xterm instances across navigation.
  Persistent delivery uses the compatible native serialize addon, not an alternative terminal emulator.
- **A2 [ACTIVE]:** Native interactive terminal display, keyboard/interrupt behavior and managed launchers remain required. Warm reuse must work for the current Codex/Pi role combination before the whole goal is called complete; other adapters may retain explicitly documented cold-resume behavior until proven compatible.
- **A3 [ACTIVE]:** Waiting includes approval, blocker, exhaustion, failed-step recovery and the final merge gate while the workflow remains open. Cache pressure may evict only idle reusable state; running work is protected.
- **A4 [ACTIVE]:** Browser and worker resources have separate bounded pools at their natural owners, with least-recently-used idle eviction. Choose and justify concrete limits from measurements; do not add a distributed cache manager or an account-admission mechanism.

## Non-goals

- Replacing the vendor terminal with a custom chat/log renderer, running speculative model turns, or introducing a host-wide shared agent daemon.
- Deleting vendor conversations, terminal recordings or review history when an ephemeral cache is released.
- Changing account admission, workflow routing, role selection, API pricing, or the 48-hour policy used by an existing run.
- Keeping warm processes across worker death/reload or reusing a process after a failed/interrupted controller turn whose safe settlement is unknown.

## Verified evidence

- [terminals.js](../app/interfaces/workbench/static/terminals.js), `showTerminals`, `make`, `connect`, `close`: role panels already retain their xterm within one selected run. Navigating to another run disposes both emulators; a new entry starts its confirmed cursor at zero.
- The same module already resumes streaming from xterm-confirmed bytes, waits for pending parsing, and refuses invalid cursors. Its current run-navigation disposal is explicitly asserted in [test_terminal_browser.py](../tests/interfaces/test_terminal_browser.py); that assertion needs deliberate replacement, not accidental removal.
- [terminal.py](../app/agents/terminal.py), `Terminal.start`, calls `end_agent()` before every launch. `run_turn` launches a new CLI even when an existing vendor session is resumed. Successful turns can leave a process live, but its next controller turn replaces it.
- [adapters](../app/agents/adapters/__init__.py), [turn_hook.py](../app/agents/turn_hook.py), and [pi_events.mjs](../app/agents/pi_events.mjs): event destinations, initial prompt transport, current contract and completion correlation are bound during process startup. Reusing only the PID would retain stale control data.
- [activities.py](../app/application/activities.py), `run_role`, also creates per-turn trace context and private settings. Warm reuse must preserve their attribution and cleanup; it is not merely a change to `Terminal.start`.
- Installed Codex CLI help reports version 0.159.0, `queue --thread ... --message ...`, native remote TUI attachment, and app-server transports. The [official command documentation](https://developers.openai.com/codex/cli/reference) documents queueing to an exact session. Queue-command success alone does not prove that the intended contained process accepted or completed work; documented resume options also differ from this installed help.
- [Official app-server documentation](https://developers.openai.com/codex/app-server) provides explicit thread/turn lifecycle control. It does not by itself prove preservation of Orchestra's native TUI, containment, hooks or tracing. A shared daemon or headless-only migration is not an accepted shortcut under A2.
- Pi's [versioned native extension example](https://github.com/earendil-works/pi/blob/v1.5.0/packages/coding-agent/examples/extensions/send-user-message.ts) provides commands and user-message submission. The current bridge must still be redesigned to refresh its per-turn state safely.
- The shipped xterm version is recorded in [VERSION](../app/interfaces/workbench/static/vendor/xterm/VERSION). Upstream [serialization support](https://github.com/xtermjs/xterm.js) is available if Q1 changes the scope; compatibility with the shipped version must be checked before adding it.
- Baseline: the existing terminal-stream, history-read, Git-diff tests and the completed-turn-stays-live test passed together: 29 tests across four classes. This proves their present contracts, not warm multi-turn reuse or a latency improvement.
- The checkout contains pre-existing prompt-context, activity, test and documentation modifications. This investigation preserves them; implementation must integrate with those contracts rather than overwrite them.

## Current architecture and source of truth

[Temporal](../app/orchestration/docs/architecture/structure.md) owns when a role runs and the accepted original operator notes. [Agents](../app/agents/docs/architecture/structure.md) own processes, PTYs, recordings, exact session identity and completion evidence. Vendor differences stay in the existing adapters. [Application](../app/application/docs/architecture/structure.md) composes execution and per-turn observability. [Workbench](../app/interfaces/docs/architecture/structure.md) owns its disposable display state.

The current project decision D17 explicitly describes a fresh process per turn. A reviewed warm path must update that mechanism while preserving why it exists: fresh instructions, turn-specific completion, permissions, containment and recovery. D7 exact-session recovery, D18b current contract delivery and the existing operator-note lifetime remain binding.

## Problem and root cause

The investigation identified two costs: browser navigation discarded parsed display state, while controller
invocation discarded initialized agent runtime state. The screenshot's MCP initialization evidenced the
latter. Browser delivery now follows D6; per-turn environment and bridge state still make blind native
process reuse incorrect.

## Decision

### Premise / KISS gate

Use the existing owners: retain their objects rather than introduce a terminal service, another workflow, a memory database or a new scheduler. A browser cache removes repeated parsing on navigation. A worker-owned idle-role pool removes compatible cold launches. Adapter-specific native submission and an acknowledged per-turn control envelope are necessary for the latter; they must be proven before production changes.

The proposal adds bounded cache bookkeeping and a turn-rebinding contract inside existing components. Prefer Codex's native exact-thread queue or supported local lifecycle interface and Pi's existing native extension facilities over simulated blind typing. Any native backend required for TUI attachment must remain inside the role's existing containment, with private local transport and the same permissions; do not attach Orchestra to a user's shared daemon.

Knowingly give up guaranteed zero-startup behavior after eviction, configuration change, process failure or
worker reload. D6 preserves committed browser screens across refresh/reopening; missing or incompatible
snapshots recover from the recording. These cache misses do not lose the native session.

### Alternatives considered

- Browser caching alone: smallest display fix, but leaves D1's CLI/MCP startup cost.
- Keeping only durable session IDs: already implemented; it does not keep a process initialized.
- Blind PTY resubmission into a live process: cannot establish refreshed instructions, correct hook destination or settlement; reject.
- Shared vendor daemon or headless app-server plus a custom terminal: introduces ownership/containment or UI changes that A2 does not accept.

## Required invariants

1. Every execution receives the original task, all applicable operator notes, current stage, selected skill and persona independently of a previous summary. Warm reuse acknowledges their fresh delivery before work starts.
2. Reuse identity includes run, role, target, worktree, exact vendor session, launcher/profile/access and relevant runtime generation. No process or input is shared across jobs or permissions.
3. Per-turn hook events, output, usage, tracing and errors belong to that invocation. Late completions, manual replies, background work and interrupts never masquerade as its successful completion.
4. No automatic paid warm-up or retry after uncertain admission/work. Unknown settlement fails closed through existing recovery; a definitively unavailable idle cache may cold-resume by exact session.
5. Preserve native trust decisions, read-only enforcement, process-tree containment, worker-death cleanup, Git guards and final merge checks. Never use broader access or a global daemon to obtain reuse.
6. Budget eviction never interrupts active work. Confirmed workflow closure follows normal termination/cleanup semantics; unavailable lifecycle information is not treated as confirmed closure.
7. Observe closed runs even when no browser is open, including force termination which cannot execute a workflow finalizer. After native reuse passes its feasibility gate, select the smallest mechanism that satisfies the closure tests, reusing normal cleanup events first. A native Temporal close-event watch is a candidate, not a required watcher per cached run; add no cleanup daemon.
8. Browser snapshots/cursors advance only after complete parsing. Restore geometry before state and replay; stale identity, truncation or invalid cursor discards the cache and performs an honest replay. Never claim cached content is live before the worker confirms it.
9. Keep current-role tail following on automatic activation; preserve deliberate scrollback while that view stays open. Resizing, maximize, copy, Esc and report filtering continue to work.
10. Closed-run eviction disposes cache objects and idle processes, not durable records. Cache metadata contains no copied authentication or environment settings.

## Implementation tasks

Deliver browser retention first as an independently verified improvement. It does not require native process reuse. Run T1's native feasibility research separately; T2 and the worker warm pool in T3 are blocked until that proof passes. If native reuse is unsupported, keep exact-session cold resumption and report the startup portion as unsupported rather than calling the entire goal complete.

- [ ] **T1 — Baseline and capability proof:** measure cold launch/MCP initialization and real xterm replay separately. With local fake providers and blocked external networking, prove two controlled turns in one contained native process for Codex and managed Pi on both hosts. Verify native TUI, exact session, refreshed notes/skill/stage, unique turn admission, hook trust and trace attribution. Queue exit status is not acceptance evidence. If no compatible primitive exists, stop this branch for renewed architectural review; do not substitute a headless UI or silently call the whole todo complete.
- [ ] **T2 — Adapter admission contract:** define the smallest optional warm capability in the existing adapter contract. Separate stable reuse identity from fresh per-turn control data; implement acknowledged admission and explicit unavailable/unsupported/failed outcomes. Preserve cold behavior for unproven adapters and invalidation cases.
- [ ] **T3 — Worker retention, after native feasibility:** extend the existing terminal registry with bounded idle reuse and confirmed-close observation. Choose closure observation from measured need rather than preselecting per-run watchers. Integrate normal merge/discard/end, force termination, cancellation, failure, worker drain and identity changes. Keep execution admission and account admission outside this cache.
- [x] **T4 — Browser retention:** retained emulators by run/host/role; parked runs disconnect, unopened roles warm,
  and committed native snapshots survive refresh/browser restart under D6. Confirmed closure and LRU pressure
  release retained displays. Original byte cursors and isolated input are preserved; stale open reads cannot
  re-enable closed-run input. Browser-only completion does not claim native process reuse.
- [ ] **T5 — Correct display and cleanup:** browser reconnect/replay, persistence, cleanup, shared sizing and
  streaming are verified with the pinned native serializer. Native warm-execution labels and cleanup
  remain subject to T1's feasibility proof.
- [ ] **T6 — Verification and durable documentation:** complete the matrix below, update the owners listed under Documentation, inspect the complete diff, and keep the index and commits operator-owned.

## Test-first and verification plan

Write guards and observe them fail for the actual current behavior before implementing the corresponding production path. Performance claims need the same native/real-browser measurement before and after; fake timing is only functional evidence.

| Case | Red evidence today / required failing assertion | Green evidence |
|---|---|---|
| Navigate run A → B → A | A's emulator is disposed and its next confirmed cursor starts at zero | same retained screen, bounded incremental bytes, correct end position; exercise actual xterm and the Node browser seam |
| Alternate role turns | returning role starts another process/MCP initialization | same compatible role process and exact session; one initialization, two distinct acknowledged controller turns |
| Refresh contract | current bridge/hook data is startup-bound | second turn uses new task parts/notes/skill/stage/event destination and trace parent; original notes remain independent of feedback |
| Wrong/stale completion | warm late events have no proven turn rebinding | late prior Stop/Pi settlement, manual input and interrupts cannot complete the new activity; rejected admission starts no work |
| Concurrent runs and identities | no cross-navigation retention pool exists | independent screens/input/sessions; profile, launcher, access, worktree or runtime changes invalidate reuse |
| Bounds and closure | no bounded reusable pool with all requested lifecycle behavior | deterministic idle eviction, no active eviction, closed cache disposal, force termination observed without a browser, unknown lifecycle handled explicitly |
| Failure/reload | only cold lifecycle has existing proof | crash, timeout, cancellation, worker death and graceful reload preserve containment and exact-session cold recovery; WSL stays up |

Relevant owners: [test_terminal.py](../tests/agents/test_terminal.py), [test_adapters.py](../tests/agents/test_adapters.py), [test_pi.py](../tests/agents/test_pi.py), [test_prompt_size.py](../tests/agents/test_prompt_size.py), [test_terminal_browser.py](../tests/interfaces/test_terminal_browser.py), [test_activities.py](../tests/application/test_activities.py), [test_reload.py](../tests/application/test_reload.py), [test_stops.py](../tests/orchestration/test_stops.py), [test_replay.py](../tests/orchestration/test_replay.py), and native tracing/upload tests under [observability](../tests/observability).

Run narrow cases first, then `bash run-tests.sh` and `powershell -NoProfile -ExecutionPolicy Bypass -File run-tests.ps1` sequentially as [tests/README.md](../tests/README.md) requires. Include an isolated real-browser switch/reconnect/resize acceptance and `bash tools/public_check.sh`. These tests use stand-ins or local fake providers; a paid smoke is not needed to prove lifecycle reuse.

## Documentation plan

- **Agents:** update process lifetime, warm admission, fallback, native bridge refresh, containment and recording semantics in the existing [structure](../app/agents/docs/architecture/structure.md).
- **Interfaces:** document display retention/invalidation in its [structure](../app/interfaces/docs/architecture/structure.md); keep vendor internals out of it.
- **Project architecture:** amend D17's unconditional process-replacement description once equivalence is proven; retain D7/D18b/D25 rather than inventing another state owner.
- **Using:** update [using.md](../docs/using.md) with observable cache behavior and recovery. Add no new document/router unless a real owner requires it; stable documents must not link back to this todo.

## Rollout and rollback

Activate only through existing graceful Orchestra-owned reloads, preserving D3. Do not mutate an executing process into the warm protocol mid-turn. Treat unsupported/mismatched worker or bridge versions explicitly before admission. Rollback releases idle reusable processes, restores ordinary exact-session cold launches and disposes disposable browser state; it never rewinds files, drops operator notes or removes vendor sessions.

## Completion criteria

- D1 and D2 are demonstrated independently for browser display and the required native role processes; a browser-only result is partial.
- Every invariant has relevant positive and refusal/recovery evidence, including both hosts and compatible per-turn tracing.
- Memory/process counts stay within the justified pools; closed jobs leave no warm resources. Full-reload behavior is explicit under Q1.
- Current architecture and instructions agree with implementation; relevant suites, browser acceptance and public check pass. No unrelated changes, paid requests or runtime transcripts enter the public diff.

## Review record

### 2026-11-12 — Investigation

- Authority D1–D4 recorded; Q1 remains non-blocking under A1.
- Two distinct causes established from the browser and worker owners. Installed CLI help and upstream native interfaces establish candidates, not an end-to-end warm implementation.
- The 29-test baseline passes. New red/green acceptance remains implementation work. No production change, live-run answer or worker restart is part of this investigation.

### 2026-11-12 — Review reconciliation

- Browser retention is the first independent delivery; native process reuse remains behind T1's hard proof gate.
- Closure tests remain binding, but the proposal no longer preselects a Temporal watcher per cached run.
- Reviewer GO is technical input, not operator authorization to implement either workstream. Status remains REVIEW REQUIRED.

### 2026-11-12 — Approved implementation

- D5 authorizes implementation. Browser work is implemented in the existing terminal owner and rail event, without a new service, persistent browser store or dependency.
- Red: `tests.interfaces.test_terminal_browser.TerminalStream.test_navigation_reuses_bounded_open_run_displays_and_evicts_only_confirmed_closed_runs` failed because navigation disposed the emulator. The module's four stream/cache tests pass after the change.
- Native admission/MCP preservation was observed with local-only fake responses on installed Codex 0.159.0 and 0.167.0: two completed tasks, refreshed second prompt and second answer in the original terminal, with one MCP initialization. Provider-request counts alone were not used as turn evidence.
- Fresh hook-destination and completion-correlation proof is blocked by the native review of the isolated probe hooks (Q2). No production native reuse, worker idle pool or D17 lifetime change has been enabled. Exact-session cold resumption remains current behavior.
- Real-browser acceptance is reproducible through `tests.interfaces.test_review_browser`: actual xterm A/B/A node reuse and confirmed-cursor reconnect passed alongside milestone exports. Browser cache coverage includes hidden pending parses, LRU eviction, closure, stale responses and isolated input.
- Full host suites passed 898 WSL and 671 Windows tests. Final focused workspace/export/cache tests passed 22 WSL and 23 Windows tests, including the real Edge scenario. Public-safety checks passed; live activation was not performed.
- Independent managed Pi proof used native extension submission with a local fake provider on both hosts: two settled turns in one live process and session, a refreshed stage contract, all original/new notes, separate event destinations/parent markers and the second answer in the original terminal. This prototype establishes feasibility only; it does not yet prove production bridge rebinding, native skill changes, MCP preservation or real uploader attribution. T1 remains open alongside Codex's hook-trust gate.

### 2026-11-12 — Authorized browser activation

- The operator requested live activation. Scoped graceful worker reloads and the independent Workbench service reload completed while the workflow waited, preserving its state and stop. The live page loads the browser retention code. Native process reuse remains disabled and its feasibility/trust gate remains open; activation did not approve probe hooks or enable a worker pool.

### 2026-11-12 — Unopened-role replay correction

- The reported large catch-up was inspected in the live browser: retention code was loaded, and both
  displays had caught up through nonzero confirmed cursors. The screenshot alone does not establish a
  cursor reset. A distinct reproducible gap existed: a role's first unopened panel had no emulator or
  connection, so it could stay cold through an entire review and begin replay only when its turn started.
- Both open-run roles now begin parsing on selection, including while waiting for operator action.
  Closed panels stay closed, focus stays put, and closed runs do not prefetch unopened roles. The existing
  run/host/role identities, bounded retention, navigation disconnect and confirmed-byte resume remain.
- Red evidence: the unopened-role regression found no engineer connection during architect review;
  actual Edge acceptance timed out waiting for its hidden replay. Both passed after the local correction.
  The stream fixture distinguishes manually injected cache data from automatic replay; connection and
  renderer counts are asserted per role now that both are initialized.
- Full-page reload remains a cold replay under A1; this correction uses review and operator-wait time
  to warm the selected run, rather than promising persisted browser snapshots. No native process-reuse gate is crossed.

### 2026-11-12 — Persistent browser scope approved

- D6 resolves Q1. Implement the native xterm 5.5-compatible serializer with bounded IndexedDB snapshots,
  original run/host/role keys, monotonic confirmed cursors and closed-run invalidation. This cache stores
  display evidence only; Temporal, workers and native sessions retain their existing ownership.
- Snapshot only complete parser/UTF-8 boundaries, validate compatibility and bounds before restoration,
  and account for native state the serializer does not preserve. Restore before requesting incremental
  bytes; reject stale/truncated or unsupported cached state through cold replay, without sending cached
  terminal responses as operator input. Storage failure must remain observable and never stop the run.
- Prove actual refresh/new-page restoration, independent roles/runs/hosts, multi-tab monotonic writes,
  closure racing a pending save, cache pressure, partial ANSI/UTF-8 and native mode/size continuity.
  Reuse the existing real-browser fixture and stream tests. No paid calls or worker/WSL restart.

### 2026-11-12 — Persistent browser delivery

- Red: refreshing the real browser requested cursor zero rather than the completed recording's cursor.
  The corrected acceptance now survives both refresh and an actual isolated Edge shutdown/restart.
- The pinned native serialization addon is used with a version-bound continuation adapter. Independent
  native comparisons cover normal/alternate buffers, color, cursor, character sets, mouse modes, scrolling
  regions, saved positions, resized geometry and subsequent output. Fragmented UTF-8/ANSI and unfinished
  parser callbacks cannot advance a stored cursor. Corrupt identity is refused before restoration.
- Browser-local IndexedDB retains bounded screen snapshots rather than copying complete recordings.
  Transaction controls prove monotonic cross-tab writes, host/role isolation, late-write refusal after
  closure, independent screen-count and byte-pressure eviction, quota-abort preservation and observable
  denied/hung storage. Startup reconciliation checks cached runs missing from the rail instead of treating
  missing rows as closed. A truncated recording recovers through a fresh cursor-zero replay.
- The initial narrow green fixture mixed manually injected bytes with automatic replay; separating those
  transport modes corrected its byte assertion. Final focused Windows acceptance passed 15 tests.
- Full browser-delivery acceptance passed 688 Windows tests and 915 WSL tests. A subsequent investigated
  scanner false positive required a local public-gate correction, verified by focused checks below.
  No production worker/WSL restart or paid call was made; operator answers and repository staging/commits
  were left to the operator.
- Workbench's independent HTTP service was reloaded to expose the new static assets. Existing parsed live
  displays seeded their native snapshots before page activation, avoiding a new full-record replay.
  A disposable verification probe failed on a timer absent from its tool sandbox after the first refresh;
  the page remained live. A corrected temporary send observer was then removed after proving that both
  role streams resumed from nonzero saved cursors in about one second. The same engineer build turn
  remained running and browser storage reported no failure. No terminal contents entered repository files.
- These results close the browser delivery under D6. T1–T3 and native portions of T5/T6 remain open behind
  their original native feasibility/trust gate; no warm process pool or account-admission guarantee is enabled.

### 2026-11-12 — Public dependency acceptance

- The separate new-file scan detected the pinned serializer's minified map-export initializer as a
  generic API key. This is the same inspected JavaScript initializer already present in the renderer;
  registry integrity and unmodified bundle bytes establish its provenance, not a credential exemption.
- The prior whole-directory renderer exception is narrowed to the exact inspected match, named rule and
  three exact bundle paths, including the historical renderer path. Other findings inside those files
  are scanned. The public gate proves acceptance of that export, rejection outside its vendor path,
  and refusal of a real generic-key-shaped control in the same bundle. No folder is exempted.
- Red: the gate did not detect a scanner that ignored the same-file generic-key control. Adding that
  control fixed the gap. An initial test-double shell pattern used invalid multi-line case alternatives;
  separate case arms corrected it. The subsequent focused checks passed 22 WSL tests (public gate,
  architecture routing and shell checks) and 19 Windows public-gate tests. The real scanner and separate
  new-file scan passed. The full host suites above preceded this scanner-only correction.
- Vendored addon files retain published LF bytes on either host. The native artifact and its license
  remain version-pinned, with provenance recorded beside the dependency. No bundled code was rewritten
  to change scanner results.
