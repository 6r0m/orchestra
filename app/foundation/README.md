# foundation

The host and deployment facts every other package reads, and their validation.

## Owns

| module | fact |
|---|---|
| `paths.py` | where this checkout is (`REPO`), where its runs write (`RUNTIME_ROOT`), and where this deployment keeps its credentials (`SECRETS`) |
| `envpath.py` | where each checkout's uv-managed environment lives on this host, and its guarded removal |
| `policy.py` | the validated policy: roles, brains, budgets, access, target hosts, and the queue each target polls |

`paths.REPO` is the only derivation of the checkout root in the repository. Every other
root path is built from it, including `policy.POLICY_FILE` and `workspace.repos.DESCRIPTORS`.
`tests/test_architecture.py` proves the derivation still lands on a real checkout, so
moving this file fails the suite instead of silently pointing one directory too high.

## Does not own

Which repositories a run may operate on — that is `workspace`, and a descriptor file
sitting beside the checkout does not make it a foundation fact. Anything that acts on
these facts: no git, no process, no network.

## Depends on

Nothing of ours, and that is the invariant: every other package reads this one, so a
single import from here into any of them would make the graph a cycle. Enforced by
`tests/test_architecture.py`.

`envpath.py` is standard library only and is run by path, by the wrappers, before any
environment exists — keep it that way.

## Invariants

- One authority per fact, refusing when there is none (D26); the decisions are in
  [docs/architecture/structure.md](../../docs/architecture/structure.md).
- Policy validation is strict: an unknown top-level or role key is rejected, so a typo
  cannot silently do nothing (D18).
- A run worktree's environment is removed only when the derived path lies under this
  host's environment root, crosses no link or reparse point, and holds `pyvenv.cfg` (D22).
