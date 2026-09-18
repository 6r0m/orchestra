# app

Orchestra's production source. One package per concern; the folder is the ownership
boundary, and each package's own README is the contract for what is inside it.

| package | owns | README |
|---|---|---|
| `foundation/` | the host and deployment facts every other package reads: where this checkout is, where each checkout's environment lives, and the validated policy | [foundation/README.md](foundation/README.md) |
| `orchestration/` | the run itself — its stages, its routes, its stops, its final gate — deterministic under Temporal | [orchestration/README.md](orchestration/README.md) |
| `workspace/` | the repositories a run operates on, and its worktree through their own git | [workspace/README.md](workspace/README.md) |
| `agents/` | a role's agent: its live terminal, its containment, the prompt it is given and the answer read back | [agents/README.md](agents/README.md) |
| `observability/` | the optional trace of a run, and nothing that a run depends on | [observability/README.md](observability/README.md) |
| `application/` | where the concerns are composed: the activities a run executes on its host, and the one client of runs | [application/README.md](application/README.md) |
| `interfaces/` | what a human or a process manager starts: the command line, the worker, the workbench | [interfaces/README.md](interfaces/README.md) |

Configuration is not here: `policy.json`, `repos.json` and `roles/` sit at the checkout
root, because they are the operator's to edit (D13).

## Dependency direction

Enforced by `tests/test_architecture.py`, which reads `app/` and fails on an import that
crosses a boundary this table does not allow. Each check carries a control.

```
foundation     <- everything. Reads nothing of ours.
orchestration  -> foundation
workspace      -> foundation
agents         -> foundation
observability  -> foundation
application    -> foundation, orchestration, workspace, agents, observability
interfaces     -> all of the above
```

Nothing imports `interfaces`, which is what keeps argparse and console output out of the
worker and the workbench. Imports inside a package are that package's own business.

The table records the imports that exist. Nothing here is indirection added to satisfy a
diagram: `agents` and `observability` do not reach into `workspace` because neither needs
a repository fact, not because a rule forbade it and an adapter was inserted.

## Running it

Entry points are modules, so the checkout is the working directory:

```bash
python -m app.interfaces.cli "fix X in Y"      # or: make feature TASK="fix X in Y"
python -m app.interfaces.worker wsl            # started by workers.sh / workers.ps1
python -m app.interfaces.workbench.server
```

Three files are launched by path instead, because whatever runs them cannot import this
package: `app/foundation/envpath.py` runs before any environment exists, and
`app/agents/ptyhost.py` and `app/agents/turn_hook.py` are started by the agent's own
containment and by the vendors' hooks. None of the three imports anything of ours, and
that is what keeps them launchable that way.
