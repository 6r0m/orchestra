# Structure

## Purpose

Answer which repository a run targets and on which host, then carry that run's change
through that repository's own git — create the worktree, guard it, merge it or discard it.

## Owns

- `repos` — which repository, target host, base branch, worktree root and todo convention a run uses: configured in `repos.json`, detected otherwise, and refused when neither.
- `worktrees` — the run's worktree through the target's own git: create, guard, merge, discard, and the view the page lists.

## Does not own

Where Orchestra itself is installed or where its runs write — that is
[foundation](../../../foundation/README.md)'s `paths`. A descriptor file happens to sit
beside this checkout; that is a default, not ownership. The decision to merge: the operator
makes it at the final gate, and [application](../../../application/README.md) carries it
here. What an agent does inside the worktree, which is
[agents](../../../agents/README.md).

## Composition

| part | responsibility |
|---|---|
| `repos.py` | the run's repository, target, base branch, worktree root and todo convention |
| `worktrees.py` | the run's worktree through the target host's own git |

## Relationships

This package's relationships are drawn once, in [the main view](diagrams/main.md).

Through `git` on the target host: every worktree, commit and merge. This package never
reads another host's git — a Windows worktree is read by a Windows process only.

Through the descriptor file: `repos.json` names the operator's own repositories, and a
missing file means no descriptors rather than an error.

## Invariants

- **Only the controller changes a worktree's git state (D27).** Agents never stage, commit, merge or push (D11). Around every role-run a digest of HEAD, the run's branch, `MERGE_HEAD` and the staged content is compared; a change fails the stage.
- **Every git side effect reads what git already holds first (D24)**, so an attempt whose worker died after git wrote is adopted when it runs again, never applied twice.
- **One authority per repository fact, refusing when there is none (D26).** A Windows target refuses a path Windows cannot use as a working directory, which it would otherwise silently replace with `C:\Windows`.

## Accepted decisions

An index. Each decision is written where the project's architecture states it, beside the
boundary or invariant it constrains: see
[the accepted decisions](../../../../docs/architecture/structure.md#accepted-decisions).
The invariants above name the ones that bind this package.

## Risks and technical debt

The agent's git guards are its environment, not a security boundary: a role that clears
them can reach a remote, and only a protected branch on the remote prevents that. They hold
against a role that pushes without meaning to, which is the failure they exist for (D28).
