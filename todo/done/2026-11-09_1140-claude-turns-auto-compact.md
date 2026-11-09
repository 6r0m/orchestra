# Claude turns auto-compact

**Status:** DONE 2026-11-09 — the goal met in the code: red, then green, the agents' and the workflow's tests
green on both hosts; closed on the operator's word, without the external reviewer or the full suite. A worker
runs it from its next restart.
**Scope:** a Claude turn's own settings ([claude_code.py](../../app/agents/adapters/claude_code.py) `TURN_SETTINGS`,
`wire`).
**Stable documentation owner:** the agents' [structure](../../app/agents/docs/architecture/structure.md), beside how a
turn ends.

## Goal

No Claude turn waits out its limit because its session filled its context.

## Authority register

### Operator decisions

- **D1** Fix it in the orchestra.
  - 2026-11-09, operator: *"also give orchestra fix"*, of the proposal to turn auto-compact on for the
    orchestra's own turns and to notice a context-limit stop within minutes.

### Decided by the agent, by the direction set

- **Auto-compact on in the turn's own settings**, which outrank the operator's user settings (documented: a
  `--settings` file *can set any key your user settings file can set*, and sits above them), so a turn compacts
  whatever the operator chose for their own sessions. Its one documented override, `DISABLE_AUTO_COMPACT` in the
  environment, is set on neither host's worker (checked), so nothing strips it.
- **No detection of the stop, against the proposal:** the one stop measured — *Context limit reached · /compact or
  /clear to continue*, with auto-compact off — cannot occur once turns ask for it; any other way a full session
  stops is unmeasured, and reading a working Claude's screen mid-turn for words it may be writing itself would end
  healthy turns. The turn's own limit stays the backstop.

## Verified evidence

- **The stuck build.** The operator's run's build turn `build-e10-1` (2026-11-06, Windows) wrote its files, then
  stopped at 22:43 with *Context limit reached · /compact or /clear to continue · auto-compact is off*; a background
  check's notification, submitted at 22:48, was answered the same. No `Stop`, `StopFailure` or `Notification`
  event came, and the turn failed at its 3,600 s limit, 23:22. The engineer's session had carried nine plan rounds
  before the build.
- **The setting:** `autoCompactEnabled` is a settings key, default on, which `/config` writes to user settings; the
  operator's was off on both hosts (an older `~/.claude.json` copy still says off), and is on in their user
  settings since 2026-11-09.

## What changed

- A Claude turn's settings — its own, or a traced turn's private file, which keeps what it held — carry
  `autoCompactEnabled: true` beside its hooks.

## Verification

- **Red:** `tests.agents.test_adapters.ClaudeCompacts` — neither the turn's own settings nor a traced turn's file
  asked for auto-compact.
- **Green:** the same, both.
- **Not measured:** a real Claude honouring the turn's setting over a user setting that is off — it would take
  turning the operator's own setting off, or a profile of its own with their credentials copied in. Documented by
  the vendor, as above.
