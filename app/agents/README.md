# agents

A role's agent: the live terminal it draws in, the containment it runs inside, the prompt it is given and the answer read back out.

| concern | owner |
|---|---|
| durable documentation: the architecture, its structure and its views | [docs/README.md](docs/README.md) |

Two files here are launched by path, not imported: `ptyhost.py` by the containment, and `turn_hook.py` by the vendors' own hooks. Both import nothing of ours, which is what makes that possible. Everything else is reached through
[application](../application/README.md)'s activities.
