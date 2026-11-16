# Worktree review scope

**Status:** DONE — implemented, verified on both hosts and activated through graceful Orchestra controls.

## Authority register

- **D1:** Export this run's worktree changes relative to its working base, excluding unrelated base
  changes and edits from other checkouts. This supersedes the original-start total-export default.
- **D2:** Apply that scope to milestone copies as well. Keep existing snapshots and native Git tools.
- **D3:** Verify final merge isolation without merging, revising or answering the actual paused run.

## Acceptance

- [x] Reproduce the incorrect total-export baseline with a real-browser regression.
- [x] Show only worktree changes against its current or retained final base in the total export.
- [x] Align cross-base milestone baselines using native Git without touching a real index or worktree.
- [x] Refuse conflicting alignment and mixed-version results instead of returning an unscoped patch.
- [x] Cover overlapping-file changes, other-checkout edits, historical retention and final merge isolation.
- [x] Verify both hosts, browser copy and actual paused-flow readback; preserve model sessions and WSL.
- [x] Update the existing stable owners and complete a final architectural review.

## Ownership

The [workspace](../../app/workspace/docs/architecture/structure.md) owns native Git comparison/alignment;
the [application](../../app/application/docs/architecture/structure.md) composes retained/current evidence;
the [interface](../../app/interfaces/docs/architecture/structure.md) identifies the exported review scope.

## Verification

The initial real-browser regression rejected the original-start total export. Native Git regressions
then proved scoped cross-base comparison, disjoint upstream/run edits within the same file, conflict
refusal without index mutation, reconstruction after worktree removal and actual garbage collection,
and a disposable final merge whose delta excluded upstream and main-checkout-only changes.
Application and browser controls rejected missing working-base evidence and older readers returning
unscoped results; refused copies preserved the clipboard.

Final focused checks passed 33 tests. Full suites passed 739 Windows tests and 970 WSL tests.
The public-safety check passed. Live native Edge readback copied a four-file total and a two-file
latest milestone, both byte-identical to their native Git comparisons and excluding the unrelated
incoming work. Main-checkout and worktree indexes, saved run state and paused stop remained unchanged.
An initial live probe timed out because it replaced the array captured by its clipboard stand-in;
correcting only that disposable probe made the same user-route check pass.

Existing graceful stack controls replaced both workers and restarted Workbench after confirming no
role was executing. Queue health, replacement worker processes, unchanged paused workflow/stop and
unchanged WSL boot identity were verified afterward. No real run was approved or merged; no model
request, remote write, staging operation or WSL restart occurred.

Final architectural judgment: PASS for this scope. Git comparison remains with Workspace, retained
evidence composition with Application and presentation with Interfaces. No workflow command, vendor
session contract or pricing authority changed. A conflicting cross-base alignment remains an explicit
limitation rather than a guessed patch; the total worktree export remains available.
