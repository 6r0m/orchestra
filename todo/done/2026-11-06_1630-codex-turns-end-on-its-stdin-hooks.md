# Codex turns end on its stdin hooks

**Status:** DONE 2026-11-09 — the goal met: red, then green on both hosts; real Codex turns, fresh and resumed,
ended on both, and the operator's run ended the turn that had hung; after two review rounds the orchestra no
longer answers Codex's review of hooks at all, reviewer PASS; the full suite green on both hosts; both workers
run it, the WSL worker since the operator restarted WSL; closed on the operator's word.
**Scope:** how a Codex turn's end is wired and read ([codex.py](../../app/agents/adapters/codex.py) `hook_flags`,
`wire`, `completion`, `reply`, `held`), the turn's events file in its environment and a start held for the
operator ([terminal.py](../../app/agents/terminal.py) `run_turn`, `BEGIN_SECONDS`;
[turn_hook.py](../../app/agents/turn_hook.py) `-`), the adapter contract ([adapters](../../app/agents/adapters/__init__.py)),
and the stand-ins ([fake_cli.py](../../tests/fake_cli.py), [demo.py](../../tools/demo.py)).
**Stable documentation owner:** D17 in the [architecture](../../docs/architecture/structure.md); the agents'
[structure](../../app/agents/docs/architecture/structure.md); [using.md](../../docs/using.md) for the review in the
role's terminal.

## Goal

No Codex turn hangs because its end could not be recorded, however long its session grows; no hook is ever
trusted for the operator; and a turn Codex holds at its review of hooks fails promptly, saying what waits and
where to answer it, rather than at the turn's limit.

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
  both hosts (measured), so one definition serves every turn and the operator trusts it once per host.
- **Trusted by the operator, at Codex's own review in the role's terminal; never answered here** (the reviewer's
  BLOCKER, twice): Codex's *Trust all* trusts every hook waiting, whoever's, and Codex trusts no hook by name, so
  no automatic answer can be kept to ours. A count of the hooks waiting was not (one of ours trusted and another's
  new make two); nor was Codex started first without ours (a hook new between the two starts passes). Never
  `--dangerously-bypass-hook-trust`, which runs a repository's hooks unreviewed, outside the sandbox; never a hash
  written here. The review is where the operator already is: Codex draws it in the role's terminal before the
  prompt goes.
- **A held start fails, saying why:** it records no event, so once it should long have begun (`BEGIN_SECONDS`,
  120 s: Codex submits within seconds, measured, and the rest is the operator's to answer) the screen is read
  (`held`; before then it may show the prompt, which can quote any dialog) and the step fails, saying what waits
  and where to answer it when the run continues.

## Verified evidence

- **The stuck turn.** The operator's run's architect turn `assess-e8-3` answered PASS at 15:05 but never ended: no
  events file. Codex's own log, 15:05:41: *after_agent hook failed … hook_name=legacy_notify error=The filename or
  extension is too long. (os error 206)*. `notify` gives the hook its event as the last argument, and the event
  carries every input of the thread: its size per architect turn grew 17,485 → 21,827 → 32,180 → 32,292
  characters, past Windows' 32,767 with the next. The turn ran to its 3,600 s limit and failed at 16:03:49.
- **Codex's hooks, measured on 0.159 (Windows) and 0.166 (WSL):** a hook given with `-c hooks.<Event>=…` runs;
  untrusted, Codex draws *Hooks need review — N hooks are new or changed. Hooks can run outside the sandbox after
  you trust them* with *Review hooks*, *Trust all and continue*, *Continue without trusting* — before a prompt given
  on its command line goes (no event, so no model); *Trust all* records
  `[hooks.state."<root><session-flags>…config.toml:<event>:0:0"] trusted_hash`, after which the same definition
  runs unasked, the events file changing through the environment. A repository's `.codex/hooks.json` hook, new,
  draws the same review. `UserPromptSubmit` gives `session_id`, `turn_id`, `prompt`; `Stop` gives `session_id`,
  `turn_id`, `last_assistant_message`.
- **Plain `/hooks` cannot approve ours:** they exist only in a Codex started with them, so the reviewer's *require
  a one-time manual `/hooks` approval* happens in the role's terminal, where Codex runs with them.
- **Refuted:** the adapter's note that Codex *does not pass its environment to hook subprocesses* — the hooks got
  `ORCHESTRA_TURN_EVENTS` on both hosts.
- **Claude's hooks** already take their event on stdin; nothing in them meets a command line.

## What changed

- Codex's turn ends on `Stop` for the turn its `UserPromptSubmit` began with our prompt, or with one the operator
  typed after it, in its thread; `notify` is gone. Its reply reader reads the hooks, and a turn recorded through
  `notify` still.
- `turn_hook.py` takes `-` for the events file `ORCHESTRA_TURN_EVENTS` names; `run_turn` puts the turn's file there.
- A turn with no event after `BEGIN_SECONDS` whose screen shows Codex's review of hooks or of the folder
  (`codex.held`, an optional part of the adapter contract) fails as an executor error saying what waits and where
  to answer it. Nothing in the orchestra writes to Codex before its prompt goes.
- Removed, from the review rounds: the trust preflight (`hooks_trust`, `_Briefly`) and its record
  (`tmp/orchestration/hook-trust.json`, left by the workers that ran it; nothing reads it now).
- The demo's Codex home is its own, its skills linked to the host's; the fake Codex draws the review, before its
  prompt, as Codex does.

## Verification

- **Red:** `tests.agents.test_adapters.CodexHooks` — the definition changed per turn and went through `notify`;
  `tests.agents.test_terminal.Hook` — no `TURN_EVENTS`; with `codex.held` taken away (`red_no_held.py`), a start
  Codex held at its review waited out the turn's limit (`RoleTimeout`).
- **The reviewer's BLOCKERs:** the count rule answered *Trust all* with another's hook waiting (red, the staged gate
  swapped in, `red_old_gate.py`); the two-start rule left a hook new between its starts to be trusted (the
  reviewer's interleaving, by reading). Neither path exists now: the tests hold that whatever waits — the
  orchestra's own on a new host, a repository's new since — nothing is trusted unless typed into the role's
  terminal (`Turns.test_a_codex_start_held_at_its_review_of_hooks_is_never_answered_here_and_fails_saying_so`), and
  that the operator's *Trust all* typed there lets the turn go on and the next ask nothing
  (`Turns.test_the_operator_trusts_codexs_hooks_at_its_review_in_the_roles_terminal`, against the fake).
- **Green:** WSL — 63 classes, 338 tests, OK, among them the agents', the workflow's, the replay of every recorded
  history and the Workbench's; Windows — 21 classes, 118 tests, OK, the operator's *Trust all* typed into the
  role's terminal through ConPTY among them; `make demo` — DEMO PASSED, 119 checks.
- **Real Codex, through `run_turn`** (`real_turns.py`, throwaway, first version): a fresh turn ended in 17 s and its
  thread resumed in 11 s on Windows, 8 s and 8 s on WSL, each on `UserPromptSubmit` and `Stop`. On the operator's
  run, the workers restarted on it, Continue reran the assessment whose `notify` had outgrown the command line: it
  ended in 67 s, verdict PASS.
- **Real Codex, no model** (`real_held.py`, throwaway, each config unchanged): in a scratch repository whose
  `.codex/hooks.json` held a hook of its own, a turn's start, prompt given, held at *1 hook is new or changed* with
  no event, and `held` read it off the real screen, on both hosts. Not measured: that real Codex sends a held
  turn's prompt once its review is answered — that takes a model; the docs promise only that later turns ask
  nothing.
- **Found on WSL:** resuming a session on the Windows drive it mounts, Codex named the repository in lower case and
  asked to trust it again — a scratch folder's artifact, a run's worktree on WSL being WSL's own; `held` reads that
  question too.
