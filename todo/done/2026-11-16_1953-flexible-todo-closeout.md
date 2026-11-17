# Keep unfinished work visible after run closeout

**Status:** DONE вЂ” implementation and isolated acceptance complete; production activation excluded.
**Scope:** todo disposition at closeout, final-gate display and revision recovery.  
**Stable owner:** [run lifecycle](../../docs/architecture/structure.md#relationships-and-dependency-direction).

## Goal

Finish and merge an authorized engineering increment without falsely completing its unfinished todo.

## Authority register

- **D1:** Keep the todo active when work remains; parked may hold blocked work, and backlog may hold
  deliberately deferred remaining steps instead of requiring the entire todo to be completed.
  - Effect: closing an Orchestra run must support these outcomes independently of done.
  - Reason: flexibility and KISS.
  - Date/source: 2026-11-16, operator instruction following investigation of premature todo closure.
- **A1 [ACTIVE]:** With remaining work and no attributable decision to park or defer it, keep the same
  todo active. Park/backlog require a stated reason and preserve the outstanding steps and decisions.
- **A2 [ACTIVE]:** Move the same file rather than generate a second follow-up todo or duplicate its steps.
  Use repository-owned locations; default optional parked/backlog locations beneath its todo directory,
  with descriptor overrides where conventions differ. A disabled/unavailable location refuses that choice.
- **A3 [ACTIVE]:** Show the closeout outcome and remaining work at the existing final gate; no extra
  mandatory approval, agent stage, browser selector or post-merge task manager.

## Non-goals

No retroactive repair in other repositories, automatic experimentation/deployment, new memory store,
automatic inference from unchecked Markdown boxes, or guarantee that an agent's semantic judgment is true.

## Evidence at investigation and root cause

- [Stage asks](../../app/foundation/stages.py) require moving/deleting the todo on every closeout.
- [Role activity](../../app/application/activities.py), `Activities.run_role`, accepts closeout only when
  the active path is absent and the configured done path exists (or the repository deletes completed todos).
- [Workspace](../../app/workspace/worktrees.py), `todo_paths`, defines only active and done identities.
  `reopen` restores closeout changes from the architect-verified snapshot without changing the index.
- [Engineer](../../roles/engineer.md) and [architect](../../roles/architect.md) already distinguish completion
  criteria from operator-approved exceptions. They do not provide unfinished closeout destinations.
- [D24](../../docs/architecture/structure.md#relationships-and-dependency-direction) explicitly describes
  this unconditional relocation. This repository currently documents only active and done locations.
  The defect is the closeout contract, not a Git merge moving files independently.

## Proposed design and KISS gate

Extend the existing closeout product with a bounded disposition: active, parked, backlog or completed,
the remaining-work summary and applicable reason. Keep commit-message proposals independent: an invalid
message can still be entered manually, but an invalid todo product cannot bypass closeout validation.
Foundation owns the shape; Workspace owns allowed paths and Git evidence; Application checks the resulting
artifact; Temporal records the accepted result; Workbench displays it at the existing final gate.
No service, database, watcher or second todo is added. Give up automatic follow-up splitting and resumption.
Merely changing prompt wording is insufficient because the current postflight rejects active/parked/backlog.
Do not change architect PASS into permission to abandon required work: unresolved required scope still
needs PATCH/BLOCKER unless the operator has accepted deferral or a smaller mergeable increment.

## Invariants

1. Completed means the defined task is complete or its remaining criteria were explicitly waived;
   deferral is not a waiver. A finished run does not establish that its original problem is solved.
2. Unfinished dispositions retain outstanding steps, acceptance criteria and decisions in one file.
   Active preserves the assigned path; parked records a blocker/resumption condition; backlog records deferral.
3. Validate the verified todo identity before a model starts. Validate the declared disposition against
   exactly one allowed resulting artifact, including retry after partial closeout. Reject duplicate copies,
   deletion of unfinished work, unknown paths, traversal, collisions and unrelated changes.
4. Preserve final-tree checks, index ownership, operator Merge approval, scoped exports and session recovery.
   Delete-on-completion policy never permits deleting an unfinished todo.
5. Legacy histories keep their recorded closeout contract. Use an explicit recorded capability/version
   for new behavior; never silently reinterpret a completed activity or apply new command sequences on replay.

## Implementation tasks

- [x] Write the regression cases below before changing production behavior.
- [x] Extend repository convention validation and the portable closeout product, then update stage asks
  and role instructions together. Preserve final-assistant-only parsing and independent commit drafts.
- [x] Admit the new contract through the existing workflow/activity boundaries, recording disposition and
  resulting path. Preserve legacy handling and explicit renamed-todo recovery.
- [x] Replace unconditional done-path postflight with disposition/path checks. Preserve permitted-document
  scope; include configured parked/backlog paths narrowly rather than allowing arbitrary directories.
- [x] Show the outcome and remaining-work summary at the final gate and in retained run history. Revisions
  and conflict reconciliation restore the actual verified todo location before roles resume, for every disposition.
- [x] Update the stable owners and run the declared checks; inspect the final diff and replay compatibility.

## Test-first and verification

Red acceptance: a real disposable worktree closes an approved increment with an active unfinished todo;
today postflight refuses it. Repeat for parked/backlog. Add known-bad controls for wrong/duplicate paths,
missing remaining work, deleted unfinished todo, collisions and unauthorized scope reduction. Verify refusal
does not stage, merge, advance the final gate or mutate protected workflow state.

Green: complete a scripted Temporal flow through final Merge for each allowed disposition, then assert
the actual landed file, preserved remaining steps and worktree cleanup. Cover revise-to-each-role,
conflict reconciliation, partial-closeout Continue, deletion policies, absent/invalid products and old histories.
Use real Git and browser acceptance for final-gate visibility, not paid models.

Start with `tests.application.test_activities.Closeout`, `tests.workspace.test_worktrees.Closeout`,
`tests.orchestration.test_stops` and `tests.orchestration.test_replay`, adding parser/descriptor/browser tests
at their existing owners. Run through the [host test entrypoints](../../tests/README.md), narrow tests first,
then full Windows and WSL suites sequentially, and `make public-check`. Isolated runtime acceptance is recorded below.

## Documentation, rollout and completion

Update the lifecycle owner, package architecture contracts, existing stage/role instructions, descriptor
example, user guide and todo router. Keep executable schema fields at their code owner, not duplicated here.
Do not migrate existing repository todos or change live run disposition automatically. Activate only through
existing graceful controls after verification; never restart WSL or interrupt an executing turn.

Completion requires the real Git/Temporal/browser cases above, legacy replay, both host suites, public checks
and an architectural review. No staging, commits, pushes, paid calls or production activation in this plan.

## Review record

### 2026-11-16 вЂ” investigation

The operator selected D1. Repository inspection confirmed the deterministic active/done-only postflight;
the existing lifecycle must change alongside prompts. Plan written; no production behavior changed.

### 2026-11-16 вЂ” implementation and acceptance

- **Authority:** the operator invoked `implement-approved-change` for this plan. The reviewer required
  exact source/destination protection, restoration of the actual verified location and informed partial
  Merge presentation. All three are implemented; the activity-name typo was corrected to `Activities.run_role`.
- **Implementation:** new named starts record the versioned closeout capability. A distinct target activity
  refuses incompatible workers instead of silently falling back. Active, parked and backlog retain the
  complete verified todo; parked/backlog also retain the reason in the file. Completed uses the repository's
  done/deletion policy. Exact path checks protect other todos even under broad document globs. The frozen
  outcome appears at Merge, in its confirmation, in CLI output and retained history. Commit proposals remain
  independent. Explicit rename recovery recognizes unfinished locations; revisions restore the actual
  verified source. Existing unversioned histories retain their recorded contract.
- **Red evidence:** real-Git regressions exposed rejection of unfinished outcomes and acceptance of an
  unrelated todo edit. Native Edge rejected a missing final-gate outcome. Further known-bad controls proved
  that a workflow-only parked reason and a pre-existing destination collision needed refusal.
- **Green evidence:** focused ownership/recovery checks passed, including deletion policy, partial-closeout
  Continue, both revision routes, selected-base conflict reconciliation, actual landed todo contents and
  replay of new executions. Edge drove four actual disposable merges, one per disposition, and checked the
  unfinished-task warning before approval. The legacy recorded-history suite also passed.
- **Full verification:** `powershell -NoProfile -ExecutionPolicy Bypass -File run-tests.ps1` passed
  **762 tests**; `bash -l run-tests.sh` passed **994 tests**. The host suites ran sequentially. Public-safety,
  local Markdown links and `git diff --check` passed.
- **Resolved test setup failures:** early fixtures used the wrong target queue and a native path separator
  in a Git-path assertion; both fixtures were corrected. A non-login WSL shell lacked `uv` before any test
  began; the login-shell invocation ran the suite successfully without installing or changing dependencies.
- **Architecture/UI review:** PASS within this implementation scope. Foundation owns the product,
  Workspace owns artifact evidence, Application composes checks, Temporal records the outcome, and the
  existing interfaces present it. The pinned UI checklist found no required findings in the changed UI.
- **Limits:** preserving declared unfinished content is mechanical; deciding that a task is semantically
  complete remains the architect/operator's responsibility. No actual model obedience is claimed from
  scripted tests. No production reload, live-run migration, paid call, WSL restart, staging, commit or push
  was performed by this implementation. Those operations are outside the approved implementation scope.
