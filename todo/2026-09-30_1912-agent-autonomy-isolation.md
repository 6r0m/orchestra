# Agent autonomy behind a real filesystem boundary

**Status:** OPEN — the goal is not met. Investigated on both hosts (2026-10-08): a Codex role is held by the
operating system; the default engineer, Claude Code, is not, on either host. No boundary is built here, and
none is to be. What holds each kind is measured, stated in the architecture and shown in Settings — which
tells the operator, and enforces nothing. What is left is the operator's to decide (Q1).
**Scope:** how each role's agent may act without asking — the Claude adapter's permission mode, each kind's
sandbox, reads outside the worktree — on WSL and on native Windows.
**Stable documentation owner:** [structure.md](../docs/architecture/structure.md), where the roles' modes
and the accepted limit (D28) are stated; for the operator, the Settings section of
[using.md](../docs/using.md).

## Goal

The agents do routine work without asking, and read what their skills reference outside the worktree,
while no role can write outside its own worktree — by an enforced boundary, not by a tripwire.

## Authority register

### Operator decisions

- **D1** Close the open todos by the architect's judgment and the project's own goals and standards: a very
  good page for the operator, and automation that is under control.
  - Effect: the investigation was made, and what those standards could settle was settled below. Whether
    the limit that remains is accepted is not among it (external review, 2026-10-09): it is Q1.
  - Date/source: 2026-10-08, operator: *"/implement-approved-change with /architect to fully close todos
    use our goals to very great ui ux and control auto things with our standarts"*.

### Operator gates

- **Q1 [OPEN]:** the default engineer is Claude Code, and on Windows — where this repository's runs are —
  nothing a vendor ships can hold its shell to the worktree. Either that is accepted as a standing,
  calculated risk, the goal is revised to "what holds each role is known, shown, and the operator's to
  choose", and this todo closes; or the goal stays as it is written and waits for a boundary a vendor
  provides. - default while open: the goal stays open, the modes the architecture states stand (D28), and
  nothing more is built.
  - The agent's recommendation: keep it open, with the next step named under [Next](#next) — the gap is
    real, a write outside the worktree is not shown at the final gate, and a native way to an enforced
    writing role exists.

### Decided under D1 — the agent's

- **The boundary is the vendor's own sandbox, never one built here.** Orchestra's containment bounds a
  turn's lifetime and its git checks are tripwires; a sandbox of its own is a non-goal the merge flow
  already recorded.
- **Claude Code's sandbox is not turned on.** It covers shell commands on Linux and WSL2 only, so one role
  would be held differently on each host and not at all on native Windows; in a linked worktree it leaves
  the repository's shared git directory writable; under `dontAsk` it refuses every network host not
  listed; Docker does not run in it; and each repository's tools would need their own allowances.
- **The operator is told what a choice holds.** Each kind states what holds a turn to each access it can
  run with, and Settings says it under the role's agent. This is visibility: it isolates nothing.
- **No further reads are granted.** Both real runs of 2026-10-08 — a Codex architect and a Claude engineer
  on Windows — read their skills' references outside the worktree and never waited on a dialog.

## Verified evidence

### 2026-10-08 — measured on both hosts

- **Codex's sandbox, with no model in it** (`codex sandbox`, 0.159.0 on Windows, 0.160.0 on WSL), in a
  throwaway repository's linked worktree, with the modes the adapter passes. Control, no sandbox: wrote in
  the worktree, wrote outside it, staged. Read-only: wrote nowhere, the temporary folder included.
  Workspace-write: wrote in the worktree and the temporary folder; did not write outside; could not stage —
  a linked worktree's index lies outside it.
- **This repository's test runner under that sandbox**, on WSL: it does not start — uv cannot write its
  cache, `Read-only file system`. Control: the same command without the sandbox passed. An enforced
  boundary and "the engineer runs the tests in its turn" do not go together today, under either vendor's
  sandbox: the test environment and the package cache live outside the worktree by design (D22).
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

## Done so far

- Each kind's module states `BOUNDARY` — what holds a turn to each access it can run with — and a kind that
  leaves one out is refused when it is loaded. Settings shows it under each role's agent.
- The architecture says what was measured, what the boundary costs, and why Claude Code's sandbox is not
  turned on; the root README says in its trust section that Orchestra sandboxes no agent.
- Proved: `tests.agents.test_adapters`, red first; the words read on the running Workbench after its
  restart; the full suites on both hosts — WSL, 141 classes, 698 tests; Windows, 97 classes, 498 tests.

## Review

- **External reviewer, 2026-10-09 — BLOCKER for the goal as written.** Accepted: telling the operator what
  holds a role is not holding it, the record said DONE with its goal unmet, and accepting that limit is the
  operator's to say, not the agent's. The record is open again and says so. Not as the review put it: the
  limit was not passed over in silence — the record and the report both named it as unmet, and the
  architecture already lists it among its accepted limits (D28).

## Next

- **If the goal stays:** the one native way to an enforced writing role on both hosts is a Codex engineer
  whose sandbox is given writable roots for what its work keeps outside the worktree — the test
  environment and the package cache — per repository. To be investigated as a change of its own, with
  `/investigate-change`, when the operator asks. A sandbox for Claude Code on native Windows would be the
  other; no vendor ships one today.
- **If the limit is accepted:** D28 stands as it is written, this goal is revised as Q1 says, and the todo
  closes.
