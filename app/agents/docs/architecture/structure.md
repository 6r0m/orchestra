# Structure

## Purpose

Run one turn of one role as the vendor's own interactive CLI, in a terminal the operator
can watch and type into, contained so the worker's death is the agent's death — and read
the turn's explicit result back out.

## Owns

- `terminal` — each role's live terminal on this host: its record, its WebSocket, a role turn run in it, and that turn's completion.
- `launch` — one agent process from an argv list, with its whole descendant tree contained.
- `ptyhost` — the pseudo-terminal the agent draws in; launched by path, inside the containment.
- `turn_hook` — the vendors' own completion wiring, writing a turn's events into that turn's file; launched by path, by the vendor.
- `nodes` — the prompt a turn is given, the agent argv, session identity, verdict parsing and the failure classes.
- `trust` — telling this host's agent CLIs that a run's repository is one the operator works in, so no turn stops at their trust dialog.

## Does not own

What a stage asks for — that is [foundation](../../../foundation/README.md)'s `stages`;
this package renders it and parses the reply. The agent's reasoning, which runs in its CLI,
and its durable conversation, which the vendor's own session store owns (D21). Which role
runs when, which is [orchestration](../../../orchestration/README.md). Any repository fact
— this package reads none, and must not start.

## Composition

| part | responsibility |
|---|---|
| `terminal.py` | the role's live terminal, its WebSocket, and a turn run in it |
| `launch.py` | one contained process tree per agent |
| `ptyhost.py` | the pseudo-terminal the agent draws in — launched by path |
| `turn_hook.py` | the vendor's completion, written into the turn's events file — launched by path |
| `nodes.py` | prompt rendering, agent argv, session identity, verdict parsing |
| `trust.py` | this host's CLI trust records for a run's repository |

## Relationships

This package's relationships are drawn once, in [the main view](diagrams/main.md).

Through the vendor CLI's own argv and its session store: a turn is that CLI started again
with the role's session resumed by exact id and the prompt as its last argument. No shell
sits between, so no task text is ever parsed as shell syntax.

Through the vendor's own completion hook: a turn ends on Claude's `Stop` for its own
prompt id, or Codex's `agent-turn-complete` in its own thread — never on a first event.

Through a host containment primitive: a transient systemd user scope on POSIX, a job object
on Windows. A launch no scope can hold is refused before the agent runs.

Through the worker's WebSocket: the terminal's record and its live bytes reach the page, and
keystrokes come back.

## Invariants

- **The vendor is the run's decision.** A turn is driven as the brain the run chose, passed explicitly; an agent this host cannot wire is refused before the turn leaves anything behind.
- **A turn ends on the vendor's own completion of its own prompt (D17).** A completion from another session, an earlier prompt, a background task finishing later or Codex's title turn never ends it; neither does an interrupt.
- **An agent's whole descendant tree is contained.** A turn's end, a timeout, the run's close and the worker's own death all end the tree.
- **Sessions resume by exact id (D7)**, never `--last`.
- **A trust record that cannot be written costs a dialog, never the run.**

## Accepted decisions

An index. Each decision is written where the project's architecture states it, beside the
boundary or invariant it constrains: see
[the accepted decisions](../../../../docs/architecture/structure.md#accepted-decisions).
The invariants above name the ones that bind this package.

## Risks and technical debt

A POSIX host needs a reachable systemd user manager to run any role at all; without one
every launch is refused, which is the intended failure but a hard one. What a Claude
engineer may do beyond editing its worktree is what the host's own Claude settings allow
and deny: those rules are part of its boundary, and they are not this repository's (D28).
