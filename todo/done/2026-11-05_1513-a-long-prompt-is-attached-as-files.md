# A long prompt is attached as files

**Status:** DONE 2026-11-09 — the goal met: reopened once, when the operator's next engineer turn could write
nothing to its worktree because of how the attachment was made readable (*Defect found after closing*, below);
fixed red first, proven with a real Claude on both hosts, reviewer PASS; the full suite green on both hosts; live,
that run's build turn wrote its plugins into its worktree; closed on the operator's word.
**Scope:** how a role turn's prompt reaches the agent's CLI ([nodes.py](../../app/agents/nodes.py) `attach`,
[activities.py](../../app/application/activities.py) `run_role`, the Claude adapter's `readable`).
**Stable documentation owner:** D17 in the [architecture](../../docs/architecture/structure.md) and the agents'
[structure](../../app/agents/docs/architecture/structure.md).

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

- **Defect found after closing.** The run's next engineer turn, its guidance attached again, ran `cd` into the
  attachments folder to compare that guidance with the last. Claude keeps a `cd` that ends inside one of its
  working directories, and `--add-dir` had made the folder one: the shell stayed there for the rest of the
  turn. The operator's own edit guard judges a write by the shell's directory, so it then refused every edit
  of the worktree's todo — eight in a row; Claude's own edit rule, `Edit(./**)`, refuses it too once the
  shell has moved (measured, below). The engineer wrote its round to its scratch folder instead; the
  architect found the todo unchanged and raised a blocker. The next turn starts in the worktree again, but any
  turn that entered the folder would repeat it.

## What changed

- `nodes.attach`: while the rendered prompt is past `PROMPT_BUDGET` (24,000, as either host counts it — Windows'
  UTF-16 units once quoted, or UTF-8 bytes), its longest part, never the skill or the stage's ask, is written
  whole to `<run>/attachments/<turn>-<part>.md`, and in its place the prompt names that file under the part's
  own heading — in ASCII alone. A prompt that fits is given whole.
- `run_role` attaches as it composes, records the parts as sent, and has the kind make the folder readable —
  `readable(argv, folders)`, optional in the adapter contract, Claude's an `--add-dir`.
- D17's sentence, in the architecture and the agents' structure.
- **The defect's fix:** Claude is given the folder as a rule allowing reads under it — `--allowedTools
  "Read(//<folder>/**)"`, its path in the POSIX form Claude matches on Windows (`E:\x` as `/e/x`) — never as a
  working directory, so a `cd` into it is not kept. The agents' structure says so.

## Review record

- **External reviewer, 2026-11-05:** the implementation passed its tests; a real agent's reading of an attachment
  stays UNVERIFIED until the operator's blocked run is continued on a restarted Windows worker and its turn is
  seen to read the attached guidance and end normally.
- **External reviewer, 2026-11-06 — PASS** for the defect's fix: a rule allowing reads in place of `--add-dir`,
  on the real-Claude evidence of both hosts.

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
- **The full suite, after the review:** on WSL 150 classes, 744 tests, OK; on Windows 102 classes, 517 tests,
  OK.
- **The operator's run, continued on the restarted Windows worker:** the plan turn that had stopped at
  errno 206 launched — its prompt 9,742 bytes where it had been 47,012, the 37,498-character guidance written
  to its attachments and named under its own heading. Claude's own session shows the turn's first act was to
  read that file, whole — its 297 lines, nothing cut; the turn ended normally, its answer a plan that follows
  the guidance, and the run went on to the architect's assessment, whose prompt fits and attaches nothing.
- **The defect, red then green.** Tests first: `tests.agents.test_prompt_size.Readable` and
  `tests.application.test_activities.LongPrompt` failed — `--add-dir` given, no `read_rule`. Then a real Claude
  (haiku), launched with the adapter's own permission flags in a throwaway worktree, told to `cd` into the
  folder, run `pwd` in a separate command, read the attachment and write a file in the worktree: with
  `--add-dir`, `pwd` printed the folder and the write was refused; with the rule, Claude said *Shell cwd was
  reset to* the worktree, read the file and wrote; with neither — the control — the read was refused. On
  Windows, with Read and Write only (its shell hangs when started from an agent's own), the rule built by
  `read_rule` from the Windows path let the read through, and the control was refused. Green: on WSL
  `tests.agents.test_prompt_size`, `tests.application.test_activities`, `tests.agents.test_adapters`,
  `tests.test_architecture` — 74 tests, OK; on Windows the first three's long-prompt and adapter classes — 5
  classes, 14 tests, OK.
- **Left as is, for the reviewer:** the host's skills folder is still a working directory (`host`), so a `cd`
  into it would be kept the same way; its skills read their references through it, links included, so moving it
  to a rule is its own change.
- **Not seen live:** a Codex turn given an attachment. Its sandbox bounds writes, not reads (as measured
  without a model), so it reads the file as Claude does through `--add-dir`.
