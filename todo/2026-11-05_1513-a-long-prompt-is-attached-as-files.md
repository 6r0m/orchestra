# A long prompt is attached as files

**Status:** BUILT 2026-11-05 — red, then green on both hosts. It awaits the external reviewer's PASS and the
operator's word to close it; the Windows worker runs it once restarted.
**Scope:** how a role turn's prompt reaches the agent's CLI ([nodes.py](../app/agents/nodes.py) `attach`,
[activities.py](../app/application/activities.py) `run_role`, the Claude adapter's `readable`).
**Stable documentation owner:** D17 in the [architecture](../docs/architecture/structure.md) and the agents'
[structure](../app/agents/docs/architecture/structure.md).

## Goal

A turn starts whatever the operator gives it: a part of its prompt too long for a command line is attached as a
file the agent reads, and a step stopped on such a prompt goes on with Continue.

## Authority register

### Operator decisions

- **D1** A prompt past what the command line takes is attached as files, automatically; the operator's text is
  not shortened.
  - 2026-11-05, operator: *"yes I input large prompt but then need attach it like files if prompt exceed! so no
    need to fix and give me opportunity to continue with prompt that auto scale to files"*

## Verified evidence

- **What failed.** A run's plan turn stopped at *A step failed*: `[Errno 206] CreateProcessW failed` for the
  worker's Python. Its prompt was 47,012 bytes — the operator's guidance, an audit pasted whole, 37,498
  characters of it — and Windows takes a whole command line of 32,767 characters. Continue reran it the same
  way. Linux takes one argument of 128 KiB: a longer note fails there too.
- **The seam.** A turn's prompt is the CLI's last argument (D17), composed from labelled parts
  (`compose_parts`) and recorded beside the turn. Claude reads outside its worktree only where it is told
  (`--add-dir`, as for the skills folder); Codex's sandbox bounds writes, not reads.

## What changed

- `nodes.attach`: while the rendered prompt is past `PROMPT_BUDGET` (24,000, as either host counts it — Windows'
  UTF-16 units once quoted, or UTF-8 bytes), its longest part, never the skill or the stage's ask, is written
  whole to `<run>/attachments/<turn>-<part>.md`, and in its place the prompt names that file under the part's
  own heading — in ASCII alone. A prompt that fits is given whole.
- `run_role` attaches as it composes, records the parts as sent, and has the kind make the folder readable —
  `readable(argv, folders)`, optional in the adapter contract, Claude's an `--add-dir`.
- D17's sentence, in the architecture and the agents' structure.

## Verification

- **Red:** the new tests before the code — `tests.agents.test_prompt_size`: no `attach`, `cost`, `readable`;
  `tests.application.test_activities.LongPrompt`: no `cost`.
- **Green:** on WSL `tests.agents.test_prompt_size`, `tests.application.test_activities`,
  `tests.agents.test_adapters`, `tests.orchestration.test_workflow.PromptParts`, `tests.test_architecture` —
  19 classes, 74 tests, OK; and `tests.agents.test_terminal.Turns` with the size tests on each host — 4
  classes, 21 tests, OK on both.
- **The real launch, on Windows:** the whole prompt, as a process's last argument through the launch every
  agent takes, refused with errno 206 — the operator's failure, as the control; with its long part attached,
  launched. On WSL a whole turn with the attached prompt completes; on Windows the test's fake CLI runs through
  a `.cmd` shim, which cannot carry a newline, so that half is WSL's (as the suite already skips it there).
- **Not run:** a real agent reading an attachment — Claude through its `--add-dir`, Codex through its sandbox
  on Windows; the operator's run, continued once the Windows worker is restarted, is that check.
