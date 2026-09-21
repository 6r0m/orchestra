# workspace

The repositories a run operates on, and its worktree through their own git.

| concern | owner |
|---|---|
| durable documentation: the architecture, its structure and its views | [docs/README.md](docs/README.md) |

Nothing here is started directly. A run reaches it through the activities in [application](../application/README.md). Which repositories exist is `repos.json`, copied from `repos.example.json` at the checkout root.
