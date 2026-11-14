# Run setup and skill instructions

**Status:** PASS — implemented, verified and activated; scope closed by the operator.

## Goal and scope

Choose several exact repository/global skill references alongside operator instructions without typing names;
choose a compatible preferred Merge destination at setup; distinguish worktree names from commit messages.

## Authority and architecture

- The operator requested visible skills for repository/global sources and clarified multiple skills with
  instructions at start, revision and guidance turns. The picker inserts visible, editable references
  rather than changing global stage bindings. Existing original-task and accepted-note delivery remains authoritative.
- The operator requested local/remote/exact-branch choice when the destination preview fails. Setup offers
  cached compatible choices and explicit refresh; the final approved Merge still owns the actual landing.
- The worktree name identifies the run's temporary folder/branch. Actual completed-change messages remain
  independently proposed and approved at the final gate, as in the existing naming agreement.
- [Interfaces](../../app/interfaces/docs/architecture/structure.md) owns input composition;
  [application](../../app/application/docs/architecture/structure.md) routes read-only discovery to the target;
  [agents](../../app/agents/docs/architecture/structure.md) owns native skill roots;
  [orchestration](../../app/orchestration/docs/architecture/structure.md) retains the recorded preference;
  [workspace](../../app/workspace/docs/architecture/structure.md) keeps Git admission and landing.

## Implementation and acceptance

- [x] Read-only host-local skill catalog with origins, exact references and alias deduplication.
- [x] Multiple searchable skill checkboxes; stage/current-request context; visible task/note insertion.
- [x] Setup destination list, explicit refresh, saved final-gate preference and unknown-target refusal.
- [x] Clear worktree naming label and separate commit-message explanation.
- [x] Eight-line task preview with reversible expansion, preserved original text and stable polling.
- [x] Focused native Edge revision proves both selected references and original note reach both roles.
- [x] Focused setup, catalog, Git, admission and replay checks passed (38 Windows tests).
- [x] Final both-host checks, public-safety/document validation and main-stack activation/readback.
- [x] Refuse skill insertion after the originating stop/form changes; preserve the current draft.
- [x] Capture one Start submission before asynchronous reads and preserve later form edits.

## Evidence and limits

The live main API already returned a valid destination; the reported screenshot retained the earlier error.
The form's failed preview lacked a direct recovery action. Refresh preserves task/name and never submits a run.
The initial Edge fixture lacked a selected repository; selecting its disposable path fixed the fixture.
The direct existing-run catalog test caught a missing adapter import, which was corrected before final checks.
Earlier Windows suites failed browser assertions against hidden or unpainted terminal panels. The fixture now
foregrounds the document, proves unopened warm parsing by the xterm-confirmed cursor, opens panels before
checking painted text, and identifies sampled file rows independently of viewport virtualization. The focused
12-test browser/stream group then passed, including actual browser restart and replaced-record recovery.
Parallel acceptance now explicitly emulates a focused foreground page. One full Windows run also left a native
test process hanging after both persona-snapshot tests reported success; its diagnostic had no Python frame.
Only that identified disposable process was ended. The persona class and final browser fixture then passed
together (four tests); the native exit hang's deeper cause remains unproven.
Candidate secret scanning ran successfully on WSL; the initial Windows invocation had no Docker executable.
All automated checks use scripted agents; no new paid model call or trust approval is needed.
Skills remain operator instructions: selection does not override stage contracts, native trust or sandboxing.

## Final acceptance

- Follow-up UI review: both reported races reproduced in focused module tests before their fixes.
  The 24-test Windows group covering setup, native browser flows, operator-note resolution and accepted
  answers passed; the corresponding 19-test WSL group passed. Three additional approval-note, cross-phase
  retention and Pi compaction checks passed on each host. A further native two-tab regression advanced a
  disposable run through its normal Revise
  action, then proved that the older picker refused insertion into the newer stop without changing its draft.
  A live note-delivery audit matched accepted originals with the current role's guidance attachment and
  confirmed its successful native read returned every complete note. No recovery turn was needed.

- Full WSL suite: 952 tests passed.
- Initial setup full Windows run: 722 tests executed; every class except the real-worker cleanup class passed.
  Activation overlapped that class's orphan-settings assertion. The production worker log confirms it removed
  the exact disposable folder before the test's own sweep. With no reload running, the complete 10-test class
  passed. The subsequent task-preview change passed the complete 723-test Windows suite. Its focused
  browser regression also checked keyboard expansion, polling, short tasks, mobile width and navigation.
  The later two UI race fixes passed the focused checks above; no production cleanup boundary was weakened.
- Public-safety checks, candidate-file secret scanning, whitespace and 55 local documentation links passed.
- Graceful reload completed for both workers; their assigned queues poll and the Workbench service is active.
  Reload waited for an ongoing assessment. The operator advanced the live run independently; these checks
  sent no answers and preserved its saved worktree and sessions.
- The live browser listed the actual native skills, inserted two selected references scoped to an architect
  stage while preserving task/name, and displayed compatible local/remote destinations with push wording.
  The existing run's own worktree catalog also resolved. The dialog and list fit a 320-pixel viewport.
  Only the automation tab's disposable unsent draft was cleared; no new run or paid request was submitted.
