# Retain the materials needed to continue unfinished tasks

**Status:** DONE — prompt, Git lifecycle and isolated acceptance complete; activation excluded.

## Goal and authority

The operator requires unfinished investigations to survive Merge and worktree cleanup. Material needed
to continue belongs in a versioned folder beside the todo, with the same stem, before the engineer
hands work to the architect. Completed work does not require an archive of disposable scratch files.
This repository's public-safety rules remain binding: preserve curated, sanitized evidence and reusable
tools, not raw transcripts, credentials, private content or bulk generated logs.

## Design

Extend the existing build/verify asks and role guidance. The engineer identifies remaining work and
retains its required materials before review, with an index and repository-relative links. The architect
checks actual files and Git inclusion; unavailable essential evidence cannot support PASS.
No new workflow stage, task registry, manifest protocol or automatic scratch-copy service is needed.

Versioned closeout recognizes only this todo's companion folder. Its verified files may move unchanged
alongside the todo; other todos and their materials remain protected. Do not create, rewrite or delete
reviewed materials in closeout. Revision restores the verified paths through the existing Git reopen.
Completed tasks migrate lasting assets to stable owners during build; closeout never silently discards
an already-reviewed evidence bundle. Ordinary temporary files remain disposable.

## Verification and tasks

- [x] Add failing prompt-delivery and real-Git companion-relocation regressions.
- [x] Update the build handoff and architect verification instructions, with public-safe retention rules.
- [x] Permit exact, unchanged companion relocation and refuse collisions, tampering and ignored targets.
- [x] Verify Merge, worktree cleanup, both revision routes and actual verified source locations.
- [x] Update [Workspace](../../app/workspace/docs/architecture/structure.md#todo-outcomes), the
  [user guide](../../docs/using.md) and the [todo router](../README.md); preserve the earlier implementation.
- [x] Run focused checks, both full host suites sequentially, public safety and final review.

## Limits

Artifact guards can preserve the Git evidence the architect actually reviewed. They cannot decide which
incident material is sufficient, sanitize arbitrary logs automatically, recover already deleted files,
or establish model obedience from scripted tests. Missing/inaccessible required evidence stays explicit.
No production reload, real-run answer, paid model call or recovery in another repository is in scope.

## Implementation and verification record

- **Prompt delivery:** the build ask requires a public-safe continuation bundle before engineer handoff,
  names its derived location, requires an index and Git-inclusion checks, and distinguishes completed work
  from pending work and missing evidence. Verify independently checks the actual material before PASS.
  These code-owned asks refresh on each invocation for the existing harnesses. Role guidance reinforces
  the same boundary; native sessions, hooks and accepted operator-note transport are unchanged.
- **Git lifecycle:** verified companion paths, modes and blob IDs govern relocation. Closeout cannot add,
  rewrite or drop these files, even under broad document globs. Preflight refuses destination collisions;
  an ignored destination cannot produce an accepted final tree. Ordinary reopen restores reviewed paths
  and preserves later operator edits. Completed deletion policies retain previously reviewed material.
- **Red evidence:** the new prompt regression rejected the old asks, real Git rejected a valid companion
  move under the old scope guard, and the collision regression exposed missing before-agent protection.
- **Focused acceptance:** 44 prompt, lifecycle, replay and browser checks passed; the broader affected
  acceptance passed 119 tests. Real Git/Temporal flows verified parked and backlog evidence after cleanup,
  both revision routes, partial-closeout Continue and conflict reconciliation. Edge checked all four todo
  outcomes and the resulting evidence in the actual landed Git tree.
- **Resolved failures:** the first mover fixture nested a source folder inside an empty destination left
  by reopen; a file-by-file fixture move preserves exact relative paths, and the closeout ask warns against
  nesting. The guard continued to refuse the invalid layout. The initial reopen assertion was corrected
  to check removal of files, rather than physical removal of empty directories that Git does not track.
  The first Windows full run found one stale
  golden-prompt fixture; regeneration from the existing composer/case matrix changed exactly five build,
  verify and closeout cases, leaving the other cases unchanged. The focused snapshot check then passed.
- **Final suites:** `powershell -NoProfile -ExecutionPolicy Bypass -File run-tests.ps1` passed **768 tests**;
  `bash -l run-tests.sh` passed **1,000 tests**. Suites ran sequentially. Public-safety, local-link and
  `git diff --check` checks passed. No public-safety control was disabled.
- **Architecture:** PASS for this scope. Foundation owns prompt/path vocabulary, Workspace owns immutable
  Git identities, Application composes preflight/postflight, and the existing workflow still owns routing.
  No new artifact registry, workflow stage, metadata protocol or scratch archive was introduced.
- **Operational boundary:** implementation remains local. Production activation and recovery of already
  missing incident files were not performed; neither staging, commits, remote writes nor WSL restarts were
  part of this work. Scripted tests establish delivery and artifact retention, not autonomous model judgment
  about evidence sufficiency or sanitization.
