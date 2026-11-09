# Claude turns auto-compact

**Status:** DONE 2026-11-09 — the goal met in the code: red, then green, the agents' and the workflow's tests
green on both hosts; two reviewer PATCHes taken — the claim that a context-limit stop cannot occur corrected and
its detection built, which the first pass had left out; then that detection held to a turn gone silent, so a
tool printing the line never ends a working turn; closed on the operator's word, without the full suite. A
worker runs it from its next restart.
**Scope:** a Claude turn's own settings and its stop at the context limit
([claude_code.py](../../app/agents/adapters/claude_code.py) `TURN_SETTINGS`, `wire`, `halted`), the quiet turn's
screen read ([terminal.py](../../app/agents/terminal.py) `run_turn`, `HALT_SECONDS`), the adapter contract
([adapters](../../app/agents/adapters/__init__.py)).
**Stable documentation owner:** the agents' [structure](../../app/agents/docs/architecture/structure.md), beside how
a turn ends.

## Goal

A Claude session that fills its context does not hold its turn until the turn's limit: its turns compact, and a
stop at the limit all the same fails the step within minutes, saying how to go on.

## Authority register

### Operator decisions

- **D1** Fix it in the orchestra: auto-compact on for the orchestra's own turns, and a context-limit stop noticed
  within minutes.
  - 2026-11-09, operator: *"also give orchestra fix"*, of that proposal.

### Decided by the agent, by the direction set

- **Auto-compact on in the turn's own settings**, which outrank the operator's user settings (documented: a
  `--settings` file *can set any key your user settings file can set*, and sits above them).
- **Compaction can still stop** (the reviewer's PATCH, checked in the vendor's docs): `DISABLE_AUTO_COMPACT` or
  `DISABLE_COMPACT` in the environment turns it off (set on neither host's worker, checked), and Claude *stops
  auto-compacting after a few attempts and shows an error* when the context refills at once after each summary.
- **The stop read only once the turn is silent, and exactly** (the reviewer's bounds, two rounds): in the existing
  turn loop, a begun turn with no new event *and nothing drawn* for `HALT_SECONDS` (120 s) has what it drew read;
  it fails only on an exact stop — *Context limit reached · /compact or /clear to continue*, measured, its words
  spaced or run together, or *Autocompact is thrashing*, as documented — with Claude's working line (*esc to
  interrupt*) nowhere after it, and its answer not ended by a `Stop`. What it drew is a stream, not the screen as it
  stands, and Claude redraws only what changes: a tool printing the line, its spinner going on, leaves the line
  last with no working line after it (the reviewer's counterexample) — so silence is the evidence of the stop.
  Measured on the build: while it worked its spinner's timer kept redrawing (*20m54s, 21m5s, 21m9s, 21m13s*); after
  its stop its terminal's record was last written at 22:52, silent to its end at 23:22.

## Verified evidence

- **The stuck build.** The operator's run's build turn `build-e10-1` (2026-11-06, Windows) wrote its files, then
  stopped at 22:43 with *Context limit reached · /compact or /clear to continue · auto-compact is off*; a background
  check's notification, submitted at 22:48, worked a moment and stopped the same. No `Stop`, `StopFailure` or
  `Notification` event came, and the turn failed at its 3,600 s limit, 23:22. On its screen, Claude's working line
  showed between the two stops and never after the last. The engineer's session had carried nine plan rounds.
- **The setting:** `autoCompactEnabled` is a settings key, default on, which `/config` writes to user settings; the
  operator's was off on both hosts (an older `~/.claude.json` copy still says off), on in their user settings since
  2026-11-09.

## What changed

- A Claude turn's settings — its own, or a traced turn's private file, which keeps what it held — carry
  `autoCompactEnabled: true` beside its hooks.
- The agent's terminal records when it last drew anything; `claude_code.halted` reads the stop; `run_turn` asks
  it once a begun turn has gone silent for `HALT_SECONDS`, and fails the step saying to continue and, if it stops
  again, type `/compact` in the role's terminal.

## Verification

- **Red:** `tests.agents.test_adapters.ClaudeCompacts` — the settings asked for no auto-compact; no stop was read.
  With `claude_code.halted` taken away (`tmp/agent/approve-note/red_no_halted.py`, throwaway), a fake Claude stopped
  at its context limit waited out its limit (`RoleTimeout`).
- **Red, the reviewer's counterexample:** `Turns.test_a_working_claude_whose_tool_prints_that_line_is_never_ended_for_it`
  — a fake Claude whose long tool prints the line, its timer redrawing and no hook for longer than the quiet, was
  ended after 2 s.
- **Green:** `ClaudeCompacts` — both settings paths, and the stop read as measured and as documented, never with
  the working line after it nor after a `Stop`; `Turns.test_a_claude_turn_stopped_at_its_context_limit_fails_once_quiet_not_at_its_limit`
  — failed within seconds, its agent ended; the counterexample's test — the turn ran to its own end.
- **Not measured:** a real Claude honouring the turn's setting over a user setting that is off — it would take
  turning the operator's own setting off, or a profile with their credentials copied in; documented by the vendor.
  The thrashing error's exact rendering on screen — written from the vendor's docs.
