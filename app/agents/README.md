# agents

A role's agent: the live terminal it draws in, the containment it runs inside, the
prompt it is given and the answer read back out.

## Owns

| module | responsibility |
|---|---|
| `terminal.py` | each role's live terminal on its host — its record, its WebSocket, a role turn run in it, and that turn's completion |
| `launch.py` | one agent process from an argv list, with its whole descendant tree contained |
| `ptyhost.py` | the pseudo-terminal the agent draws in; launched by path, inside the containment |
| `turn_hook.py` | the vendors' own completion wiring, writing a turn's events into that turn's file; launched by path, by the vendor |
| `nodes.py` | prompt composition, the agent argv, session identity, verdict parsing and the failure classes |
| `trust.py` | telling this host's agent CLIs that a run's repository is one the operator works in, so no turn stops at their trust dialog |

`nodes.py` also holds `STAGE_ASK` and `STAGE_SKILL` — what each stage asks its role for.
That is workflow contract in agent-facing form, and it lives here because the prompt is
composed from it; changing an ask is a code change, never configuration (D13).

## Does not own

The agent's reasoning, which runs in its CLI, and its durable conversation, which the
vendor's own session store owns (D21). Which role runs when: that is `orchestration`.
Any repository fact — this package reads none, and must not start.

## Depends on

`foundation`, for the policy and for the runtime root. Nothing else.

`ptyhost.py` and `turn_hook.py` import nothing of ours at all, because the containment
and the vendors' hooks start them by path. Keep it that way.

## Invariants

- **The vendor is the run's decision.** A turn is driven as the brain the run chose,
  passed explicitly; an agent this host cannot wire is refused before the turn leaves
  anything behind. Guarded in `tests/test_architecture.py`.
- **A turn ends on the vendor's own completion (D17)** — Claude's `Stop` for its own
  prompt id, Codex's `agent-turn-complete` in its own thread — never on a first event.
- **An agent's whole descendant tree is contained** by a primitive native to the host: a
  transient systemd user scope on POSIX, a job object on Windows. A launch no scope can
  hold is refused before the agent runs.
- **Sessions resume by exact id (D7)**, never `--last`.
- **A trust record that cannot be written costs a dialog, never the run.**

The execution seam in full is in
[docs/architecture/structure.md](../../docs/architecture/structure.md).
