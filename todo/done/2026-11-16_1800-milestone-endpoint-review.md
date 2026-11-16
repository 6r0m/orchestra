# Milestone endpoint review

**Status:** DONE — implemented, locally verified and activated for the existing paused flow.
**Scope:** milestone endpoint comparisons and deterministic role/iteration labels.

## Authority register

- **D1:** Compare adjacent saved snapshots even when the base changed between them. The operator
  approved the audited Git endpoint model; this supersedes the earlier same-base display restriction.
- **D2:** Give milestones readable names identifying the operator iteration and architect/engineer
  context. Use recorded history, without an additional model request.
- **D3:** Keep the existing Git snapshots, retention refs, Temporal action boundaries and diff reader.

## Implementation and acceptance

- [x] Prove historical and current cross-base comparisons with focused failing regressions.
- [x] Retain missing-object, stable-sample, ordering and immutable pagination safeguards.
- [x] Label imported base changes in the view and copied patch.
- [x] Name intervals from their opening operator action and expose exact completed role iterations.
- [x] Prove the UI with disposable Git snapshots and the existing real-browser fixture.
- [x] Update the existing application/interface architecture and usage owners.
- [x] Run required host suites, public-safety checks and a final architectural review.

## Ownership

The [application](../../app/application/docs/architecture/structure.md) composes recorded answers and
Git evidence. The [interface](../../app/interfaces/docs/architecture/structure.md) owns names and display.
The [workspace](../../app/workspace/docs/architecture/structure.md) continues to own snapshot bytes and retention.
No workflow commands, model sessions, real index, merge approval or push authority change.

## Verification record

- Baseline: five focused existing range, stable-read and checkpoint-retention tests passed.
- Red: both saved/current cross-base regressions hit the old refusal; iteration naming lacked the
  recorded completed-turn identity; browser and clipboard assertions rejected the previous output.
  An unknown-current-base regression also failed before the explicit refusal was added.
- Green: 36 focused tests across application ranges, history projection, disposable Git retention,
  native Edge and immutable clipboard reads passed.
- Full acceptance: `powershell -NoProfile -ExecutionPolicy Bypass -File run-tests.ps1` passed 733
  Windows tests; `bash run-tests.sh` passed 964 WSL tests, including workflow replay.
- Final UI review replaced sequence-like arrows between unique stage types with a labelled stage
  summary. Exact chronological turns remain in the disclosure. The final
  `tests.interfaces.test_review_browser` and `tests.interfaces.test_diff_browser` run passed all
  three tests after that wording correction.
- Existing-flow acceptance: the current interval showed eight files and five completed role turns.
  Its 235,853-byte copied patch matched native Git exactly, with the base-update label.
- Activation reloaded only Workbench through the existing lifecycle while holding its native stack
  exclusion. Both worker PIDs/health, the paused run's state and its stop stayed unchanged.
  No paid calls, operator answers, worker replacement or WSL restart occurred.
- An auxiliary command mistakenly used uv's default environment path. The legacy local `.venv`
  was restored from the declared lock and runtime imports verified; live services use their separate
  host-managed environments. No source or workflow repair was needed for that command error.
- Architect review: PASS for the bounded implementation. Ownership, endpoint identity, unknown-state
  refusals, retained evidence and current-read concurrency guards remain intact. No required findings remain.
- Public-safety checks passed; the Git index and commits were left operator-owned and unchanged.
