# Large retained operator guidance

**Status:** DONE — implemented, activated and verified on both hosts, 2026-11-12

## Goal and authority

The operator requested fixing revision refusal in an existing run whose accepted notes exceed the
inline allowance. Preserve every original note for both roles and retain automatic prompt attachments;
do not shorten accepted text or submit the pending operator answer. The completed long-prompt change
remains the owner of command-line attachment behavior, not this upstream retention boundary.

## Implementation

- [x] Reproduce a new revision refused solely because legacy retained notes exceed the inline allowance.
- [x] Version the transition through a recorded answer field, preserving old workflow replay.
- [x] Retain accepted Update text in Temporal and send ordered provenance/hash references for large context.
- [x] Resolve references against the scheduling execution on the target worker, before any agent starts.
- [x] Preserve the existing executor, cancellation, native sessions and prompt-file delivery.
- [x] Cover corruption, missing/foreign evidence, payload bounds, Stop, recovery and retrying a rejected Update ID.
- [x] Run host acceptance and public checks, record their results, and activate without answering the live run.

## Evidence

- Red: the large-legacy-context regression failed at aggregate-note validation. The corrected test
  accepts another decision and sends small references while retaining the full originals.
- Real workflow integration sends large notes through both role prompts as whole attachments, checks
  compact scheduled inputs, resolves history from the exact execution and replays the resulting commands.
- Refused requests preserve workflow state. Missing history starts no agent; Continue recovers after
  the source is available. Stop cancels the pending read. A rejected stop Update can be retried with
  the supported transport and retains normal accepted-answer idempotence.
- Focused acceptance passed 177 tests across workflow stops/replay, activities, history, worker
  admission and architecture. The additional rejected-Update retry regression passed separately.
- A read-only check resolved all existing legacy notes exactly and locally validated a further
  revision; no live Update or model request was issued.
- Initial full WSL acceptance passed 910 tests. Initial Windows acceptance ran 683 tests with one
  `ProcessTree.test_stop_ends_the_whole_tree` failure (`Stop not raised`). Forty concurrent isolated
  Stop trials passed. A diagnostic full Windows run passed that test but failed the harness's orphan
  check after native handles had already proved termination.
- Deterministic red controls exposed two Windows test defects: fixture cleanup could terminate another
  process through a stale PID, and the orphan check could mistake a reused PID for its original process.
  Cleanup now uses existing job ownership and the owner's process handle; termination evidence uses
  held original handles. POSIX checks remain. Both controls passed after the corrections, along with
  all 34 focused Windows process-tree and harness tests. No production launch behavior was changed.
- The original Stop failure did not retain its child's exit details, so its exact historical cause
  remains unproven. Unexpected fixture exits now report return code, stdout, stderr and marker state;
  the strict Stop assertion remains, without retries or suppression.
- Final acceptance after all corrections: `powershell -NoProfile -ExecutionPolicy Bypass -File
  run-tests.ps1` passed 686 Windows tests; `bash run-tests.sh` passed 913 WSL tests. No failures remained
  in either run.
- Compatibility review preserved note-free actions for legacy reference metadata already over the
  new allowance. Eight WSL budget/replay checks and five Windows budget checks passed for that correction,
  which is also included in final full acceptance. Public-safety scanning and separate scanning of new files passed.
- Scoped worker reloads and Workbench service reload completed while the existing workflow waited.
  Queue health and the new transport capability were confirmed. Its state, stop and configuration hash
  remained unchanged. Original notes resolved exactly after activation, and local revision validation passed.
  WSL and Temporal stayed running; no pending operator answer or paid model request was submitted.

## Durable owners

[Orchestration](../../app/orchestration/docs/architecture/structure.md) owns acceptance, bounds and replay.
[Application](../../app/application/docs/architecture/structure.md) owns exact-history resolution and execution.
[Usage](../../docs/using.md) explains large guidance and older-worker recovery.
