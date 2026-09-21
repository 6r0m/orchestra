# app

Orchestra's production source. One package per concern; the folder is the ownership boundary, and
each concern states its own boundaries, parts and invariants at its own level.

| concern | owner |
|---|---|
| the contract every other package reads: the checkout, the policy, the stages of a run | [foundation/README.md](foundation/README.md) |
| the run itself — its stages, routes, stops and final gate | [orchestration/README.md](orchestration/README.md) |
| the repositories a run operates on, and its worktree | [workspace/README.md](workspace/README.md) |
| a role's agent: its terminal, containment, prompt and answer | [agents/README.md](agents/README.md) |
| the optional trace of a run | [observability/README.md](observability/README.md) |
| where the concerns are composed into what a run does | [application/README.md](application/README.md) |
| what a human or a process manager starts | [interfaces/README.md](interfaces/README.md) |
| the direction these depend in, and the participants outside them | [the main view](../docs/architecture/diagrams/main.md) |

Configuration is not here: `policy.json`, `repos.json` and `roles/` sit at the checkout root,
because they are the operator's to edit (D13). The direction the packages depend in is enforced by
`tests/test_architecture.py`, which fails on an import that crosses a boundary.

## Running it

Entry points are modules, so the checkout is the working directory:

```bash
python -m app.interfaces.cli "fix X in Y"      # or: make feature TASK="fix X in Y"
python -m app.interfaces.worker wsl            # started by workers.sh / workers.ps1
python -m app.interfaces.workbench.server
```

Three files are launched by path instead, because whatever runs them cannot import this package:
`app/foundation/envpath.py` runs before any environment exists, and `app/agents/ptyhost.py` and
`app/agents/turn_hook.py` are started by the agent's own containment and by the vendors' hooks.
None of the three imports anything of ours, and that is what keeps them launchable that way.
