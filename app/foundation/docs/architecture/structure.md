# Structure

## Purpose

Answer the questions every other concern asks before it can do anything: where this
checkout is, where this host keeps its environments, what this deployment allows, what the
stages of a run are, and the flows a run may take them in.

## Owns

- `paths` — the one derivation of the checkout root, the runtime root a run writes under, and the directory this deployment keeps credentials in.
- `envpath` — where each checkout's uv-managed environment lives on this host, and its guarded removal.
- `policy` — this host's validated policy (the file `ORCH_POLICY` names, else the checkout's own): roles, brains, budgets, access, target hosts, the queue each target polls, and the one resolver for a role's persona file.
- `stages` — the five stages, which role runs each, which work each review judges, which work answers with its product, what each asks its role for, and the verdicts a review may answer with.
- `flows` — the flows in `flows/` a run may follow, the rules each keeps, the one grammar of a flow's name, the shape a run is handed its flow in — `{name, steps}` — the order runs took before flows, and how a run takes a flow's steps: each work, the review that judges it and the operator's step after them.

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
| `stages.py` | the stage contract: the stages, their roles, their reviews, their asks, and the verdicts |
| `flows.py` | the flows: each file in `flows/` read and checked against the stage contract |

## Relationships

This package's relationships are drawn once, in [the main view](diagrams/main.md).

Through the filesystem: `policy` reads the deployment's `policy.json`, `flows` the files in
`flows/`, and `envpath` removes an environment only under this host's environment root.

This package reads nothing of ours, and that is the invariant the whole graph rests on —
every other concern reads this one, so a single import outward would make the graph a
cycle. `tests/test_architecture.py` enforces it.

The stage contract is here, beside the policy, because the policy is validated against it —
which stages a skill may lead, which phases have a round budget — and every concern that reads
the stages reads the policy too. A package of its own would sit below the policy and add an
edge to the graph without separating an owner. The policy's `default_flow` is checked by the
flows' own grammar for a name, `flows.is_name`, for the same reason: one owner of what can name
a flow.

## Invariants

- **One authority per fact, refusing when there is none (D26).** `paths.REPO` is the only derivation of the checkout root; every other root path is built from it.
- **Policy validation is strict (D18).** An unknown top-level or role key is rejected, so a typo cannot silently do nothing.
- **A role's persona file has one resolver, and what crosses hosts is readable on both.** `policy.prompt_path` answers for validation and for whichever host runs the role. A policy crosses hosts as data, so it carries no path resolved on either host: only its origin, relative to the checkout when it came from inside one, which each host reads against its own checkout. A host's `ORCH_POLICY` is its copy of the run's policy — where to find the personas, never a second policy — and a copy that says anything else is refused. An origin only the other host can spell, and a persona file that is not there, are refused before an agent starts — never replaced by another file.
- **Stage asks are code, never configuration (D13).** Each ask names the artifact its stage produces or judges, and a new stage is a change to the code. The order a run takes the stages in is configuration — its flow — and a flow that breaks a rule is refused, naming the rule, before a run starts on it.
- **A flow's name is its file's, and never a path.** One grammar, `flows.is_name`, decides it wherever a name is taken — a file, the policy's `default_flow`, a run's own flow; `flows.load` reads only a file directly in `flows/`, and one it cannot read or parse is refused like one that breaks a rule.
- **A run's flow is taken as given (D13).** `flows.steps_of` accepts `{name, steps}` and nothing else, and never makes another shape into one — a dict of steps into its keys, a string into its characters.
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
