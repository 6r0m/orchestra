# Structure

## Purpose

Run one turn of one role as the vendor's own interactive CLI, in a terminal the operator
can watch and type into, contained so the worker's death is the agent's death — and read
the turn's explicit result back out.

## Owns

- `terminal` — each role's live terminal on this host: its record, its WebSocket — which also serves the feeds the worker hands it — a role turn run in it, and that turn's completion.
- `launch` — one agent process from an argv list, with its whole descendant tree contained; and `read`, a short read-only command that ends with the process that started it — on Windows even when that process is killed.
- `ptyhost` — the pseudo-terminal the agent draws in; launched by path, inside the containment.
- `turn_hook` — the vendors' own completion wiring, writing a turn's events into that turn's file; launched by path, by the vendor.
- `pi_events` — Pi's native lifecycle extension, recording settlement and model usage in that same turn file.
- `nodes` — the prompt a turn is given, built as labelled parts it is rendered from byte for byte, the agent argv, session identity, verdict parsing and the failure classes.
- `adapters` — each vendor CLI's arguments, skill invocation syntax, installed skill roots and other kind-specific mechanics behind one contract.
- `trust` — telling this host's agent CLIs that a run's repository is one the operator works in, so no turn stops at their trust dialog.

## Does not own

What a stage asks for — that is [foundation](../../../foundation/README.md)'s `stages`;
this package renders it and parses the reply. The agent's reasoning, which runs in its CLI,
and its durable conversation, which the vendor's own session store owns (D21). Which role
runs when, which is [orchestration](../../../orchestration/README.md). Any repository fact
— this package reads none, and must not start.

## Composition

| part | responsibility |
|---|---|
| `terminal.py` | the role's live terminal, its WebSocket, and a turn run in it |
| `launch.py` | one contained process tree per agent, and a read that never outlives its process |
| `ptyhost.py` | the pseudo-terminal the agent draws in — launched by path |
| `turn_hook.py` | the vendor's completion, written into the turn's events file — launched by path |
| `pi_events.mjs` | Pi's native input, settlement, exact-session validation and generation evidence |
| `nodes.py` | prompt rendering, agent argv, session identity, verdict parsing |
| `adapters/` | the vendor-specific kind contract, including skill invocation and roots |
| `trust.py` | this host's CLI trust records for a run's repository |

## Relationships

This package's relationships are drawn once, in [the main view](diagrams/main.md).

Through the vendor CLI's own argv and its session store: a turn is that CLI started again
with the role's session resumed by exact id and the prompt as its last argument. No shell
sits between, so no task text is ever parsed as shell syntax. A prompt past `nodes.PROMPT_BUDGET` has its
longest parts — never the skill or the stage's ask — attached as files in the run's folder, each named in its
place; a kind that reads outside the worktree only where it is told to is told that folder (`readable`) — Claude
by a rule allowing reads there, never as a working directory, which would keep its shell's `cd` into the folder
and move the turn out of its worktree. Every kind draws on its terminal's normal screen, so the session stays in
the terminal's scrollback: Codex is started with `--no-alt-screen`, since its default alternate screen keeps no
scrollback and takes every mouse event.

Through the run's settings snapshot: `nodes` appends an optional operator prompt addition for
each role after the normal budget when extended rounds remain, and at the final budgeted
iteration. The code-owned reflection and handoff instructions remain in force when an addition
is empty, and every role keeps its own instructions. After the normal budget, each role diagnoses
non-convergence, checks its own contribution, and continues ordinary work when no human decision is
needed. The final architect handoff names a cause with evidence and separates the engineer's
contribution, the architect's assessment, unresolved and disputed findings, and any operator
decision. The addition does not replace the stage ask or the role's verdict contract.

Through the adapter contract: Settings discovers skill names from the same roots a kind checks
when preparing a run; no vendor path crosses the Settings API. What holds a turn to the access it
runs with — the vendor's sandbox, or the vendor's own rules alone — is each kind's to state, and
Settings shows a role the words of the kind chosen for it.

The Pi adapter targets the native lifecycle API in Pi 1.0.4. Pi profiles select their provider, model
and thinking level. Their optional launcher names a managed
wrapper instead of the default executable; preparation checks the same program that will run. Credentials
stay with Pi's native authentication store or the worker's environment. Orchestra neither copies them nor
changes the host's active provider. Pi's regular TUI keeps scrollback; its invocation trusts this worktree
for this session. Read access allows only read, grep, find and ls and disables MCP. Write access excludes
the PowerShell tool so a managed installation's shell permission rules remain applicable. Installed
extensions still execute as the host user: these settings provide no operating-system sandbox.
Skill discovery includes native skill directories and registered local packages' declared skill globs.

Claude Code profiles may select DeepSeek as their API provider, following
[DeepSeek's Claude Code integration](https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code/).
The existing Claude adapter keeps ownership of its hooks, sessions, skills and access rules; changing the
model's provider does not introduce another kind of CLI. Only that process receives the provider endpoint,
model mappings and authentication from `DEEPSEEK_API_KEY` in its host worker's environment or the checkout's
private `.env`, read at each turn with the environment taking precedence. The provider overrides also enter
the private per-turn CLI settings, since Claude settings can replace inherited environment values. The
file is shared with hook and trace settings and removed at the end of the stage; a dead worker's sweep
removes what it left. No credential is passed on the command line. Missing
authentication refuses before launch, with no subscription fallback. The key is never a profile setting,
part of the run snapshot or trace metadata. Other profiles keep the CLI's existing configuration.

A role's session spans every turn of the role, so it can fill its context: a Claude turn's own settings turn
its auto-compact on, whatever the operator's, since a session that fills with it off stops at *Context limit
reached* and fires no hook (measured), and its turn would wait out its limit. Compaction can still stop — off
by the worker's environment, or given up when the context refills at once (documented) — so a begun turn gone
silent for two minutes, no new event and nothing drawn, has what it drew read (`halted`). What it drew is a
stream, not its screen as it stands, so silence is the evidence: a Claude at work keeps redrawing its spinner,
and one stopped draws nothing (measured). An exact stop of that kind, its working line nowhere after it and its
answer not ended, fails the step saying how to go on; never words a working agent or its tools may print.

The run's snapshotted `timeout_seconds` remains a finite wall-clock cap on each role turn, independent of
terminal output. A quiet build alone is not a failure, and a redrawing spinner alone cannot prove useful
progress. Known held-start and context stops, process exit, explicit completion, and operator Stop retain
their existing behavior under a longer cap. A timeout ends the contained process tree and leaves the worktree
and provider session available for the operator's Continue; there is no automatic retry or periodic restart.
The turn cap bounds elapsed time, not billed usage; it configures no provider balance or spending limit.

Through the vendor's own completion hook: a turn ends on Claude's `Stop` for its own
prompt id, or Codex's `Stop` for the turn its `UserPromptSubmit` began with our prompt, in its own thread —
never on a first event. Every hook is given its event on stdin: one carried on a command line grows with the
session and outgrows Windows' (Codex's `notify`, measured). Codex runs a hook only once it has trusted that exact
definition, so its hooks are one definition on every turn — the turn's events file named in the environment
(`ORCHESTRA_TURN_EVENTS`), which both vendors pass on to their hooks — so the operator trusts them once on a
host, at Codex's own review, which it draws before a turn's prompt goes in the role's terminal. Nothing here ever
answers that review: its *Trust all* trusts every hook waiting, whoever's, and Codex trusts no hook by name, so
no automatic answer could be kept to ours — not by a count of the hooks waiting, nor by a look a moment before,
which a hook new in between would pass. A start held there records no event: two minutes on, unless the operator
has answered it, the kind reads the review off the screen (`held`) and the step fails, saying what waits and where
to answer it when the run continues.
Pi uses its native `agent_settled` notification after the controller's input, not `agent_end`, which can
precede retries or compaction. Aborted settlement ends no turn; a later typed instruction can finish it.
Its assistant messages record each generation's native token buckets for the observability owner to
upload under the stage. A resumed session is an exact native session file: a missing file is session loss
before work; unreadable, malformed or mismatched identity is a refusal, never a new conversation.
Claude's notification and tool-finish hooks also record their events, keeping only the session and a
notification's kind — never what a dialog says or what a tool read or wrote. Every event is stamped with when
its hook recorded it (`_at`), so answers in two roles' records are ordered by when each came, never by when a
record last changed. The adapter reads a waiting
dialog from them for the Workbench (`waiting`), and a role's answer to words the operator typed into its
terminal after its turn (`reply`); they never decide a turn's result.

Through a host containment primitive: a transient systemd user scope on POSIX, a job object
on Windows. A launch no scope can hold is refused before the agent runs.

Through the worker's WebSocket: the terminal's record and its live bytes reach the page, and
keystrokes come back. The terminal's size is the worker's, one for every viewer: 160 columns, the width the agents
lay their screens out for, and 48 rows until a page's Maximize asks for as many as fill its window — 24 to 200 —
and its Restore for 48 again, as a console window's own resize does. The size travels to the PTY host in its stdin
as a sequence no key makes (`ESC _ orchestra-size;…`, refused in what a page types), holds for the role's next
turns until a Restore or the worker's restart, and is marked in the record where each size begins (`OSC 5379`), so
every page draws each part at the size it was drawn at. The marker is recorded and delivered before the resize
command can trigger the agent's redraw; a page asks only a worker that names its size. The same
socket serves each feed the worker hands it, by name, beside the terminals —
the run's change is one — with the same origin and token; what a feed reads is the worker's to compose, and
this package knows nothing of it.

## Invariants

- **The vendor is the run's decision.** A turn is driven as the brain the run chose, passed explicitly; an agent this host cannot wire is refused before the turn leaves anything behind.
- **A turn ends on the vendor's own completion of its own prompt (D17).** A completion from another session, an earlier prompt, a background task finishing later or Codex's title turn never ends it; neither does an interrupt.
- **An agent's whole descendant tree is contained.** A turn's end, a timeout, the run's close and the worker's own death all end the tree.
- **Sessions resume by exact id (D7)**, never `--last`.
- **A trust record that cannot be written costs a dialog, never the run.**

## Accepted decisions

An index. Each decision is written where the project's architecture states it, beside the
boundary or invariant it constrains: see
[the accepted decisions](../../../../docs/architecture/structure.md#accepted-decisions).
The invariants above name the ones that bind this package.

## Risks and technical debt

A POSIX host needs a reachable systemd user manager to run any role at all; without one
every launch is refused, which is the intended failure but a hard one. What a Claude
engineer may do beyond editing its worktree is what the host's own Claude settings allow
and deny: those rules are part of its boundary, and they are not this repository's (D28).
