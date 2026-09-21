# Structure

## Purpose

Answer the questions every other concern asks before it can do anything: where this
checkout is, where this host keeps its environments, what this deployment allows, and
what the four stages of a run are.

## Owns

- `paths` — the one derivation of the checkout root, the runtime root a run writes under, and the directory this deployment keeps credentials in.
- `envpath` — where each checkout's uv-managed environment lives on this host, and its guarded removal.
- `policy` — the validated policy: roles, brains, budgets, access, target hosts, the queue each target polls, and the one resolver for a role's persona file.
- `stages` — the four stages, which role runs each, what each asks its role for, and the verdicts a review may answer with.

## Does not own

Which repositories a run may operate on — that is [workspace](../../../workspace/README.md),
and a descriptor file sitting beside this checkout does not make it a foundation fact.
Anything that acts on these facts: no git, no process, no network, no trace. Rendering a
stage's ask into a vendor prompt, which is [agents](../../../agents/README.md).

## Composition

| part | responsibility |
|---|---|
| `paths.py` | the checkout root, the runtime root, the secrets directory |
| `envpath.py` | each checkout's environment path on this host, and its guarded removal |
| `policy.py` | the deployment's validated policy, and `prompt_path`, the one persona-file resolver |
| `stages.py` | the stage contract: the stages, their roles, their asks, and the verdicts |

## Relationships

This package's relationships are drawn once, in [the main view](diagrams/main.md).

Through the filesystem: `policy` reads the deployment's `policy.json`, and `envpath`
removes an environment only under this host's environment root.

This package reads nothing of ours, and that is the invariant the whole graph rests on —
every other concern reads this one, so a single import outward would make the graph a
cycle. `tests/test_architecture.py` enforces it.

## Invariants

- **One authority per fact, refusing when there is none (D26).** `paths.REPO` is the only derivation of the checkout root; every other root path is built from it.
- **Policy validation is strict (D18).** An unknown top-level or role key is rejected, so a typo cannot silently do nothing.
- **A role's persona file has one resolver.** `policy.prompt_path` answers for validation and for whichever host runs the role; a policy crosses hosts as data and an absolute path from the other host means nothing here.
- **Stage asks are code, never configuration (D13).** Each ask names the artifact its stage produces or judges, and a new stage is a change to the workflow.
- **A worktree's environment is removed only** when the derived path lies under this host's environment root, crosses no link or reparse point, and holds `pyvenv.cfg` (D22).

## Accepted decisions

An index. Each decision is written where the project's architecture states it, beside the
boundary or invariant it constrains: see
[the accepted decisions](../../../../docs/architecture/structure.md#accepted-decisions).
The invariants above name the ones that bind this package.

## Risks and technical debt

`envpath` and the two files launched by path elsewhere are the only code that runs before
an environment exists, so it must stay standard library only. Nothing enforces that today
beyond this sentence and the boundary check that keeps it from importing our own packages.
