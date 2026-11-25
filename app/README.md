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
