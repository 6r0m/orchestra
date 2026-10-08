# Agent autonomy behind a real filesystem boundary

**Status:** OPEN — not investigated as a change yet; recorded on the external review of the Workbench
UX todo's D8, 2026-09-30. Nothing here gates [the Workbench UX change](2026-09-25_2334-workbench-ux.md).
**Scope:** how each role's agent may act without asking — the Claude adapter's permission mode, each kind's
sandbox, reads outside the worktree — on WSL and on native Windows.
**Stable documentation owner:** [structure.md](../docs/architecture/structure.md), where the roles' modes
are stated.

## Goal

The agents do routine work without asking, and read what their skills reference outside the worktree,
while no role can write outside its own worktree — by an enforced boundary, not by a tripwire.

## Verified evidence (2026-09-30, Claude Code 2.1.285 on both hosts)

- The Claude engineer runs in `dontAsk` with `Edit(./**)`: Claude denies what is not pre-approved, and
  checks its file tools, shell redirections, `tee` targets and protected paths against the worktree. It
  does not bound a program the shell runs: each host's own Claude settings allow every shell command, and
  Anthropic states that a Bash rule is not a security boundary.
- `bypassPermissions` skips the protected-path and working-directory checks too; Anthropic scopes it to
  isolated containers or VMs. It was tried for the engineer and withdrawn.
- Orchestra's containment — a systemd user scope, a Windows job object — bounds process lifetime, not
  writes (`app/agents/launch.py`). The controller's git checks and the host's guards are tripwires.
- Claude's sandbox bounds shell commands' writes and network at the OS level on Linux and WSL2, not on
  native Windows; it is off on both hosts. Codex's own sandbox is on for both of its roles, on both hosts.
- The live walkthrough's paused turns were the architect's: a read outside the worktree, then a plan-exit
  dialog. A Claude `--add-dir` of every repository would open edits there for a writing role.

## Open questions

- Is the Claude sandbox, enabled for the engineer's turns on WSL, the boundary sought there — and what
  holds on a Windows host, where it does not run: Codex for the writing role, WSL only, or the tool policy
  as today?
- Which outside reads do roles need — the host's skills folder is already added — and how is each granted
  read-only, per kind?

## Next

Investigate with `/investigate-change` when the operator asks, against the installed CLIs on both hosts,
then decide. Until then the modes stated in the architecture stand.
