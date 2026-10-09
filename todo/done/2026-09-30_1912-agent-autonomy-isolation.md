# Agent autonomy behind a real filesystem boundary

**Status:** DONE 2026-10-09 — by the operator's decision (D2): maximum autonomy for the agents, with guards
under the accident that destroys work, and no enforced boundary for the writing role. The goal is revised to
that. What holds each kind is measured, stated in the architecture and shown in Settings; the host's guards
are proved to stand under a role's turn.
**Scope:** how each role's agent may act without asking — the Claude adapter's permission mode, each kind's
sandbox, reads outside the worktree — on WSL and on native Windows.
**Stable documentation owner:** [structure.md](../../docs/architecture/structure.md), where the roles'
modes and the accepted limit (D28) are stated; for the operator, the Settings section of
[using.md](../../docs/using.md).

## Goal

As decided (D2): the agents do routine work without asking, and read what their skills reference outside
the worktree. What holds each kind of agent to its worktree is known and shown where the operator chooses
it, and the host's own guards refuse the accident that destroys work — a recursive delete, or an edit,
outside the working repository.

As first written, and not met: no role can write outside its own worktree — by an enforced boundary, not by
a tripwire. A Codex role is held so; a Claude Code writing role is not, on either host.

## Authority register

### Operator decisions

- **D1** Close the open todos by the architect's judgment and the project's own goals and standards: a very
  good page for the operator, and automation that is under control.
  - Effect: the investigation was made, and what those standards could settle was settled below. Whether
    the limit that remains is accepted was not among it (external review, 2026-10-09): D2 says.
  - Date/source: 2026-10-08, operator: *"/implement-approved-change with /architect to fully close todos
    use our goals to very great ui ux and control auto things with our standarts"*.
- **D2** Maximum agent autonomy, with guards against blindly removing files outside the repositories: the
  writing role without an operating-system boundary is accepted.
  - Effect: Q1 is closed; the goal is revised as above; nothing enforcing is built or waited for.
  - Reason: asked where the risk lay and what was to be decided, and shown the two answers.
  - Date/source: 2026-10-09, operator: *"yes it's good we enforce maximum agent autonomy and add some guards
    to protect blindless removing files outside repos - I guess it's good"*.

### Operator gates

- **Q1 [CLOSED by D2]:** whether a Claude Code writing role with nothing a vendor ships to hold its shell to
  the worktree is accepted as a standing, calculated risk, or the goal waits for a native boundary.

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
- **The guards are the host's, not Orchestra's.** They are hooks of the host's own Claude settings, so they
  hold every session there, a role's turn among them; Orchestra adds none and carries none.
- **No further reads are granted.** Both real runs of 2026-10-08 — a Codex architect and a Claude engineer
  on Windows — read their skills' references outside the worktree and never waited on a dialog.

## Verified evidence

### 2026-10-09 — the host's guards under a role's turn

- **Without a model, on both hosts:** the host's guard, handed what Claude Code hands it for a command,
  with the working folder spelled as a run's worktree. A recursive delete inside the worktree: let
  through. One of another run's worktree beside it, of the main checkout, of the home folder: refused. One
  file removed outside, not recursively: let through — the guard is for the recursive delete alone, by its
  own design. The host's own check of its guards passed on both.
- **With one, on WSL** (Claude Code 2.1.286): a turn started as the adapter starts a writing role, with
  hooks of its own given through `--settings` as the adapter gives them. A recursive delete inside its
  worktree ran; one in the main checkout was refused by the guard's hook, in the hook's own words. So the
  host's hooks run beside the ones a run gives a turn.
- **On Windows, with a model: not measured** — a turn started from the agent's own shell there does not
  complete a command. The guard's script and its registration are the same on both hosts.

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
- **Claude Code on Windows** (2.1.294): not measured, for the reason above. The vendor's documentation for
  that version: on native Windows it runs commands unsandboxed.
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
  leaves one out is refused when it is loaded. Settings shows it under each role's agent.
- The architecture says what was measured, what the boundary costs, why Claude Code's sandbox is not turned
  on, and that a host's own hooks hold a role's turn too; the root README says in its trust section that
  Orchestra sandboxes no agent, and where a net against an accident belongs.
- Proved: `tests.agents.test_adapters`, red first; the words read on the running Workbench after its
  restart; the full suites on both hosts — WSL, 141 classes, 698 tests; Windows, 97 classes, 498 tests.

## Review

- **External reviewer, 2026-10-09 — BLOCKER for the goal as written.** Accepted: telling the operator what
  holds a role is not holding it, the record had said DONE with its goal unmet, and accepting that limit
  was the operator's to say. It was put to the operator, who decided (D2). Not as the review put it: the
  limit was not passed over in silence — the record and the report both named it as unmet, and the
  architecture already lists it among its accepted limits (D28).

## Not done here

- No enforced boundary for a Claude Code writing role: accepted (D2). The guards under it are against an
  accident, not against a role that sets out to go round them, and only a recursive delete and an edit are
  guarded: a single file removed outside, or a file a program writes there, is not.
- If an enforced writing role is wanted later, the native way is a Codex engineer whose sandbox is given
  writable roots for what its work keeps outside the worktree — the test environment and the package
  cache. A change of its own.
