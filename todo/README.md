# Todo

What is being worked on here, in the open. One file per change, named
`<YYYY-MM-DD_HHMM>-<slug>.md` — the convention `repos.py` uses when a run writes a plan into a
repository, and the one this repository keeps for itself.

| what you will find | where |
|---|---|
| the change being worked on now | the dated files beside this one |
| a completed change | [done/](done/) |

A run writes its reviewable plan here. An approved engineering increment can merge while its todo
remains active. Blocked work may move to `parked/`, deferred remaining steps to `backlog/`; those
directories are created when used. Outstanding criteria and decisions stay with the same file.
Only a completed task becomes a receipt in `done/`. The versioned run contract is owned by the
[lifecycle](../docs/architecture/structure.md#relationships-and-dependency-direction).
A hand-written todo follows the same distinction between merging an increment and finishing its task.

An unfinished todo may have a companion folder with the same stem: `todo/task.md` and `todo/task/`.
Its `README.md` indexes the sanitized evidence, fixtures and tools required to continue, with provenance
and resume instructions. The todo links to it; the folder follows a parked or backlog todo unchanged.
Check Git inclusion before review. Disposable scratch stays in ignored `tmp/`; raw logs, transcripts,
private data and secrets are not public continuation materials. Completed work migrates lasting assets
to their stable owners rather than keeping an indiscriminate scratch archive.

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
