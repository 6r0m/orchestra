# Agent autonomy behind a real filesystem boundary

**Status:** DONE 2026-10-08 — investigated on both hosts and decided: no new enforcement is built. What holds
each kind of agent is measured, stated in the architecture, and said beside the role where the operator
chooses its agent. A Codex role is held by the operating system; a Claude Code writing role is not, and that
stays a stated limit. Closed on the operator's word.
**Scope:** how each role's agent may act without asking — the Claude adapter's permission mode, each kind's
sandbox, reads outside the worktree — on WSL and on native Windows.
**Stable documentation owner:** [structure.md](../../docs/architecture/structure.md), where the roles' modes
are stated; for the operator, the Settings section of [using.md](../../docs/using.md).

## Goal

The agents do routine work without asking, and read what their skills reference outside the worktree,
while no role can write outside its own worktree — by an enforced boundary, not by a tripwire.

## Authority register

### Operator decisions

- **D1** This question is closed now, by the architect's judgment and the project's own goals and
  standards: a very good page for the operator, and automation that is under control.
  - Date/source: 2026-10-08, operator: *"/implement-approved-change with /architect to fully close todos
    use our goals to very great ui ux and control auto things with our standarts"*.

### Decided under D1 — the agent's

- **The boundary is the vendor's own sandbox, never one built here.** Orchestra's containment bounds a
  turn's lifetime and its git checks are tripwires; a sandbox of its own is a non-goal the merge flow
  already recorded.
- **Claude Code's sandbox is not turned on.** It covers shell commands on Linux and WSL2 only, so one role
  would be held differently on each host and not at all on native Windows, where this repository's own runs
  are; in a linked worktree it leaves the repository's shared git directory writable; under `dontAsk` it
  refuses every network host not listed; Docker does not run in it; and each repository's tools would
  need their own allowances — a new surface of configuration nothing asks for today.
- **An enforced boundary and "the engineer runs the tests in its turn" do not go together here, under
  either vendor's sandbox:** the test environment and the package cache live outside the worktree by
  design (D22), and a role held to its worktree cannot write them. Having both would take writable roots
  for those folders, per kind and per repository. Not built: it is what a later change would start from.
- **The operator chooses, and is told what the choice holds.** Each kind states what holds a turn to each
  access it can run with, and Settings says it under the role's agent. An operator who wants the writing
  role enforced picks the Codex engineer, and reads there what that costs.
- **No further reads are granted.** Both of the day's real runs — a Codex architect and a Claude engineer
  on Windows — read their skills' references outside the worktree and never waited on a dialog.

## Verified evidence

### 2026-10-08 — measured on both hosts

- **Codex's sandbox, with no model in it** (`codex sandbox`, 0.159.0 on Windows, 0.160.0 on WSL), in a
  throwaway repository's linked worktree, with the modes the adapter passes. Control, no sandbox: wrote in
  the worktree, wrote outside it, staged. Read-only: wrote nowhere, the temporary folder included.
  Workspace-write: wrote in the worktree and the temporary folder; did not write outside; could not stage —
  a linked worktree's index lies outside it.
- **This repository's test runner under that sandbox**, on WSL: it does not start — uv cannot write its
  cache, `Read-only file system`. Control: the same command without the sandbox passed.
- **Claude Code on WSL** (2.1.286), started as the adapter starts a writing role, one short turn of the
  smallest model, judged by what was on disk: its file tool was refused outside the worktree; a command its
  shell ran wrote there.
- **Claude Code on Windows** (2.1.294): not measured. Started from the agent's own shell its commands never
  completed, the one inside the worktree included, so the instrument said nothing. The vendor's
  documentation for that version: on native Windows it runs commands unsandboxed.
- **Claude Code's sandbox**, from its documentation for the installed versions: Linux, WSL2 and macOS;
  shell commands and what they start, not its file tools, hooks or MCP servers; its prerequisites,
  bubblewrap and socat, are on this WSL.

### 2026-09-30, Claude Code 2.1.285 on both hosts — still so

- The Claude engineer runs in `dontAsk` with `Edit(./**)`: Claude denies what is not pre-approved, and
  checks its file tools, shell redirections, `tee` targets and protected paths against the worktree. It
  does not bound a program the shell runs: each host's own Claude settings allow every shell command, and
  Anthropic states that a Bash rule is not a security boundary.
- `bypassPermissions` skips the protected-path and working-directory checks too; Anthropic scopes it to
  isolated containers or VMs. It was tried for the engineer and withdrawn.
- Orchestra's containment — a systemd user scope, a Windows job object — bounds process lifetime, not
  writes (`app/agents/launch.py`). The controller's git checks and the host's guards are tripwires.
- The live walkthrough's paused turns were the architect's: a read outside the worktree, then a plan-exit
  dialog. A Claude `--add-dir` of every repository would open edits there for a writing role.

## What changed

- Each kind's module states `BOUNDARY` — what holds a turn to each access it can run with — and a kind that
  leaves one out is refused when it is loaded, like any other part of the contract.
- Settings shows it under each role's agent, after what the role may do, and follows the agent chosen.
- The architecture says what was measured, what the boundary costs, and why Claude Code's sandbox is not
  turned on.

## Verification

- **Red first:** the shipped kinds stated no boundary; a kind that left it out was not refused; what the
  page reads of a kind carried none.
- **`tests.agents.test_adapters`:** a kind stating no boundary, or none for an access it runs with, is
  refused saying so; the shipped kinds state one for each; the kinds' capabilities carry it.
- **In a browser,** on the acceptance's own Workbench, which runs this checkout's code: the engineer's
  agent reads Claude Code's words and the architect's Codex's; at 1280 and 390 px nothing overflows.
- **The touched modules, one host after the other:** WSL: 54 classes, 296 tests, OK; Windows: 34 classes,
  180 tests, OK.

## Not done here

- No enforced boundary for a Claude Code writing role, on either host: the limit the architecture states
  (D28). On Windows none exists to turn on.
- No writable roots that would let a role held to its worktree build a test environment outside it.
- The Workbench has to be restarted to say the new words; until then Settings shows what the role may do
  alone, as before.
