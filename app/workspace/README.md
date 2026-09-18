# workspace

The repositories a run operates on, and its worktree through their own git.

## Owns

| module | responsibility |
|---|---|
| `repos.py` | which repository, target host, base branch, worktree root and todo convention a run uses — configured in `repos.json`, detected otherwise, refused when neither |
| `worktrees.py` | the run's worktree through the target's own git: create, guard, merge, discard, the view |

## Does not own

Where Orchestra itself is installed or where its runs write — that is `foundation.paths`.
A descriptor file happens to sit beside this checkout; that is a default, not ownership.
The decision to merge: the operator makes it at the final gate, and `application` carries
it here.

## Depends on

`foundation`, for the checkout root and for the environment path a discarded worktree
takes with it. Nothing else.

## Invariants

- **Only the controller changes a worktree's git state (D27).** Agents never stage, commit,
  merge or push (D11). Around every role-run a digest of HEAD, the run's branch, `MERGE_HEAD`
  and the staged content is compared; a change fails the stage.
- **Every git side effect reads what git already holds first (D24)**, so an attempt whose
  worker died after git wrote is adopted when it runs again, never applied twice.
- **One authority per repository fact, refusing when there is none (D26).** A Windows target
  refuses a path Windows cannot use as a working directory, which it would otherwise
  silently replace with `C:\Windows`.

The full lifecycle and the final gate are in
[docs/architecture/structure.md](../../docs/architecture/structure.md).
