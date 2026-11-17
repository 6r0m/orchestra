# Durable remaining work and accurate closeout outcomes

**Status:** complete — locally verified; production activation not performed

## Scope

Retain the accepted flexible-todo lifecycle. An unfinished closeout must put its declared remaining
work in the Git artifact, and a prepared closeout must not be described as already landed.
No workflow protocol, routing, native session, deployment or external repository changes.

## Acceptance

- [x] Reproduce missing durable remaining work and misleading proposed/discarded display before fixes.
- [x] Require the remaining summary in unfinished Markdown, preserving all verified bytes and accepting
  existing criteria without duplicate sections. Normalize line endings only for summary matching.
- [x] Distinguish proposed, landed, discarded and superseded closeouts in Workbench, CLI and history.
- [x] Verify a newly discovered requirement survives actual Git Merge and worktree cleanup.
- [x] Verify actual Discard leaves Git unchanged and labels the retained proposal accurately in Edge.
- [x] Run affected contracts, both host suites, public safety and final diff review; preserve the index.

## Owners

[Workspace](../../app/workspace/docs/architecture/structure.md#todo-outcomes) owns artifact validation;
[Interfaces](../../app/interfaces/docs/architecture/structure.md) owns the display of workflow evidence.
[Usage](../../docs/using.md) explains the proposed-versus-landed distinction. Temporal retains the existing
status and accepted Merge authority. No additional storage, approval or agent invocation is needed.

## Verification

The missing-summary and CLI regressions failed against the prior implementation for the intended reasons.
A separate multiline-summary regression reproduced a CRLF mismatch before normalization.
The first affected run exposed a negative reason fixture that omitted both remaining work and reason;
the fixture now includes remaining work so it isolates the intended missing-reason refusal.
The first browser probe remained on the list page; after correcting navigation, the old JavaScript
failed the intended proposal-label assertion. The corrected implementation passes real Edge Discard
and revision/Merge checks, including superseded history. The targeted runs passed 20 artifact checks
and 27 CLI, lifecycle, product and browser checks. Public safety and changed-document links pass.

The final sequential full suites passed **773 Windows tests** and **1,006 WSL tests**. Windows includes
the real Edge flows for all four dispositions and Discard. The new portable Git/Temporal regression
lands a newly discovered requirement despite all original steps being checked, then reads that text
from the merged Markdown after cleanup. The existing unchanged-companion, exact-path, revision,
conflict, partial-closeout and replay contracts remain covered. The staged index was preserved.

Both reviewer findings were supported by the code. Architecture: PASS for these local corrections.
Git owns artifact validation, Temporal owns execution status, and interfaces display that evidence.
No reviewer finding required refutation, and no additional lifecycle mechanism was introduced.

Live activation and recovery of previously lost ignored files are outside this review's acceptance.
