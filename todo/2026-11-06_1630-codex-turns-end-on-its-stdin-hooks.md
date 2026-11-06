# Codex turns end on its stdin hooks

**Status:** BUILT 2026-11-06 — red, then green on both hosts; real Codex turns, fresh and resumed, ended on both;
the workers restarted on it, and the operator's run, continued, ended the turn that had hung. The reviewer's
BLOCKER on its trust gate is fixed, red then green; the workers do not run that fix yet. It awaits the external
reviewer and the operator's word to close it.
**Scope:** how a Codex turn's end is wired and read ([codex.py](../app/agents/adapters/codex.py) `hook_flags`,
`wire`, `completion`, `reply`, `hooks_trust`, `held`), the turn's events file in its environment, the hooks
trusted before it and a start still held ([terminal.py](../app/agents/terminal.py) `run_turn`, `_Briefly`,
`BEGIN_SECONDS`; [turn_hook.py](../app/agents/turn_hook.py)
`-`), the adapter contract ([adapters](../app/agents/adapters/__init__.py)), and the stand-ins
([fake_cli.py](../tests/fake_cli.py), [demo.py](../tools/demo.py)).
**Stable documentation owner:** D17 in the [architecture](../docs/architecture/structure.md); the agents'
[structure](../app/agents/docs/architecture/structure.md); [using.md](../docs/using.md) for a review that waits.

## Goal

No Codex turn hangs because its end could not be recorded, however long its session grows; and no turn waits on
Codex's review of hooks.

## Authority register

### Operator decisions

- **D1** Understand the stuck turn and fix it properly, so future turns do not get stuck; fix every hook that
  needs it.
  - 2026-11-06, operator: *"I want to you understand the problem with /architect and immedeiately fix it properly
    so in future turns will not stucks"*; *"also fix all hooks what needed"*

### Decided by the agent, by the direction set

- **Codex's own hooks, on stdin:** its documented `UserPromptSubmit` and `Stop` — the event on stdin, so its size
  never meets a command line — read as Claude's are, a turn's id for a prompt's.
- **One definition, its target in the environment, trusted once:** Codex runs a hook only once it has trusted that
  exact definition; the turn's events file comes in `ORCHESTRA_TURN_EVENTS`, which Codex passes to its hooks on
  both hosts (measured), so one definition serves every turn.
- **Trusted by Codex's own dialog, for our hooks only:** never `--dangerously-bypass-hook-trust`, which would also
  run a repository's hooks unreviewed, outside the sandbox; never a hash computed here, whose inputs change between
  Codex releases. Its *Trust all* trusts every hook waiting, so it is answered only once Codex, started a moment
  before without ours, asked to review nothing — never on a count of the hooks waiting, which one of ours trusted
  and another's new can match (the reviewer's BLOCKER). Anything else fails the turn, saying to review it.
- **A start still held fails, saying why:** what the record remembers cannot see a hook new since, nor Codex no
  longer trusting ours; such a start records no event, so the turn's screen is read once it should long have begun
  (`BEGIN_SECONDS`, 60 s; before, it may show the prompt, which can quote any dialog), the step failed, and the
  record dropped for the next turn to check afresh.

## Verified evidence

- **The stuck turn.** The operator's run's architect turn `assess-e8-3` answered PASS at 15:05 but never ended: no
  events file. Codex's own log, 15:05:41: *after_agent hook failed … hook_name=legacy_notify error=The filename or
  extension is too long. (os error 206)*. `notify` gives the hook its event as the last argument, and the event
  carries every input of the thread: its size per architect turn grew 17,485 → 21,827 → 32,180 → 32,292
  characters, past Windows' 32,767 with the next. The turn ran to its 3,600 s limit and failed at 16:03:49.
- **Codex's hooks, measured on 0.159 (Windows) and 0.166 (WSL):** a hook given with `-c hooks.<Event>=…` runs;
  untrusted, Codex draws *Hooks need review — N hooks are new or changed* and waits; *Trust all and continue*
  records `[hooks.state."<root><session-flags>…config.toml:<event>:0:0"] trusted_hash`; the same definition runs
  unasked after, the events file changing through the environment. `UserPromptSubmit` gives `session_id`,
  `turn_id`, `prompt`; `Stop` gives `session_id`, `turn_id`, `last_assistant_message`.
- **Refuted:** the adapter's note that Codex *does not pass its environment to hook subprocesses* — the hooks got
  `ORCHESTRA_TURN_EVENTS` on both hosts.
- **Claude's hooks** already take their event on stdin; nothing in them meets a command line.

## What changed

- Codex's turn ends on `Stop` for the turn its `UserPromptSubmit` began with our prompt, or with one the operator
  typed after it, in its thread; `notify` is gone. Its reply reader reads the hooks, and a turn recorded through
  `notify` still.
- `turn_hook.py` takes `-` for the events file `ORCHESTRA_TURN_EVENTS` names; `run_turn` puts the turn's file there.
- Before each Codex turn, `hooks_trust`: while Codex still holds the hashes remembered for this definition and
  config (`tmp/orchestration/hook-trust.json`), nothing; otherwise Codex started for a moment twice, no prompt —
  without ours, refused at any review it asks; then with ours, its dialog answered — and what it records
  remembered. A folder it asks to trust, or other hooks, fail the turn saying so.
- A Codex turn with no event after `BEGIN_SECONDS` whose screen shows its review of hooks or of the folder
  (`codex.held`, an optional part of the adapter contract) fails as an executor error naming what to review, and
  drops the record.
- The demo's Codex home is its own, its skills linked to the host's; the fake Codex draws the review as Codex does.

## Verification

- **Red:** `tests.agents.test_adapters.CodexHooks` — the definition changed per turn and went through `notify`;
  `tests.agents.test_terminal.Hook` — no `TURN_EVENTS`.
- **Green:** on WSL `tests.agents.test_adapters`, `tests.agents.test_terminal`, `tests.test_architecture`,
  `tests.test_demo`, `tests.application.test_activities` — 116 tests, OK; on Windows `tests.agents.test_adapters`,
  `tests.agents.test_terminal` — 11 classes, 52 tests, OK; the terminal's real PTY turns trust the fake Codex's
  hooks by its dialog first.
- **Real Codex, through `run_turn`** (`tmp/agent/codex-hooks/real_turns.py`, throwaway): on Windows its dialog
  trusted our two hooks — the config's diff only their two hashes — then a fresh turn ended in 17 s and its thread
  resumed in 11 s, each on `UserPromptSubmit` and `Stop`; on WSL, in a folder of its own, 8 s and 8 s.
- **`make demo`:** a first run failed — the demo's own Codex home moved where its skills are found (*the assess
  stage's skill architect is in none of …/codex-home/skills/architect*); its skills are now linked to the host's.
  Then DEMO PASSED, 117 checks, none failed, its Codex turns trusting the fake's hooks by its dialog; the operator's
  Codex configs hold only the two entries the real checks made, on each host.
- **The operator's run, the workers restarted on it:** Continue reran its architect's assessment in the thread
  whose `notify` had outgrown the command line; the turn ended in 67 s on its `UserPromptSubmit` and `Stop`,
  verdict PASS, and the run waits at the plan's approval. The Windows worker found Codex trusting its hooks
  already — no dialog — and remembered it.
- **The record keeps only configs that exist:** a demo's entry, its temporary home gone, is dropped at the next
  write (`tests.agents.test_adapters.CodexHooks`, red then green).
- **Found on WSL:** resuming a session on the Windows drive it mounts, Codex named the repository in lower case and
  asked to trust it again — a scratch folder's artifact, a run's worktree on WSL being WSL's own; the trust step now
  fails at once on that question rather than waiting.
- **The reviewer's BLOCKER, both halves confirmed red:** with the staged gate swapped in
  (`tmp/agent/codex-hooks/red_old_gate.py`, throwaway), one of ours trusted and another's waiting — two, as many as
  ours — had *Trust all* answered (`[b'2\r']`), refused only after it;
  `CodexHooks.test_one_of_ours_trusted_and_anothers_waiting_never_answers_trust_all`. With `codex.held` taken away
  (`red_no_held.py`), a turn whose start Codex held at its review of a repository's hook new since waited out its
  limit (`RoleTimeout`, 20 s); `Turns.test_a_start_held_by_codexs_review_of_anothers_hook_fails_at_once_and_trusts_nothing`.
- **Green:** WSL `tests.agents.test_adapters`, `tests.agents.test_terminal`, `tests.test_architecture`,
  `tests.application.test_activities` — 25 classes, 117 tests, OK; Windows `tests.agents.test_adapters`,
  `tests.agents.test_terminal` — 11 classes, 56 tests, OK.
- **Real Codex, no prompt submitted, no model** (`real_probe.py`, `real_held.py`, throwaway, each config compared
  before and after — unchanged on both hosts): the trust step, its record a temporary one, started Codex alone and
  then with ours, neither drawing a dialog, ours trusted already — 14.7 s on Windows, 9.6 s on WSL. In a scratch
  repository whose `.codex/hooks.json` held a hook of its own, the step refused at the first start — *1 hook is
  new or changed* — in 4.3 s on Windows and 2.3 s on WSL, nothing answered; a turn's start there, prompt given,
  held at that review with no event, and `held` read it off the real screen.
- **`make demo`, after the fix:** DEMO PASSED, 117 checks, none failed, its Codex turns trusting the fake's hooks by
  the two starts; `make public-check` passed.
