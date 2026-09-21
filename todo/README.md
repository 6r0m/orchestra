# Todo

What is being worked on here, in the open. One file per change, named
`<YYYY-MM-DD_HHMM>-<slug>.md` — the convention `repos.py` uses when a run writes a plan into a
repository, and the one this repository keeps for itself.

| what you will find | where |
|---|---|
| the change being worked on now | the dated files beside this one |
| what a merged change left behind | [done/](done/) |

A run started against this repository writes its reviewable plan here and, once the operator
merges it, moves it to `done/` with a finished status line. A todo written by hand follows the
same shape.

## What a todo here may not contain

This repository is public, and a todo is committed like anything else. It carries the steps, the
progress, the blockers and the open questions of work in flight — and never:

- credentials, tokens or anything from `.env`, `secrets/` or a vendor's session store;
- absolute paths from a machine, a user profile, or a private repository's name or layout;
- terminal or run transcripts, or an agent's raw output;
- anything copied out of a private repository.

Use `/path/to/repo`, `you` and `localhost`, as everywhere else here. Durable facts do not belong
in a todo at all: when something here is still true after the change lands, move it to the owner
that keeps it — [the architecture](../docs/architecture/README.md), a concern's own structure
document, or the code — and let the todo point at that owner instead.
