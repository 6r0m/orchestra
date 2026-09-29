# workspace

The repositories a run operates on, and its worktree through their own git.

| concern | owner |
|---|---|
| durable documentation: the architecture, its structure and its views | [docs/README.md](docs/README.md) |

Nothing here is started directly. A run reaches it through the activities in
[application](../application/README.md). Which repositories exist is `.orchestra/repos.json`, copied
from [`.orchestra/repos.example.json`](../../.orchestra/repos.example.json); `ORCHESTRA_REPOS` can
name a separate descriptor file for a stack of its own.
