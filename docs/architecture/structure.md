# Structure

## Contents

- Purpose · Owns · Does not own · Composition
- Relationships and dependency direction
- Invariants
- Accepted decisions
- Risks and technical debt

## Purpose

Drive one change through `plan → assess → build → verify` with two agent roles, in a git worktree
of whichever repository the change is for, with the agents running on the operating system that
repository needs — stopping for a human whenever a verdict says it should, and merging the verified
change only when the operator says so.

## Owns

The workflow of a run and its durable state, routing between stages, the round budget, the stops
and their answers, where a run's roles execute, the run's worktree from creation to merge or
discard, and the commit and merge of an approved change. What each stage asks for is workflow
contract and lives in `app/foundation/stages.py`, which `app/agents/nodes.py` renders into a
vendor prompt; what a role is lives in configuration.

- **D1** **Temporal owns the workflow.** One workflow execution per run, its Workflow Id the run
  id; a start refuses an id that is open or still retained (`WorkflowIDConflictPolicy.FAIL`,
  `WorkflowIDReusePolicy.REJECT_DUPLICATE`), and the orchestration never reuses a run id on its
  own. The workflow code decides every transition from `routing.py` and nothing else, and its event
  history is the run's durable state: a process that exits at a stop loses nothing, and any later
  process answers it. The self-hosted server keeps its own PostgreSQL, and its `orchestration`
  namespace keeps closed runs for 90 days.
- **D5** **`max_rounds`** = architect attempts per phase, counting from 1
  including the first; `== max` stops for the human. Operator guidance
  re-enters the phase with the counter reset. No other budget class. **Nothing
  runs twice on its own:** a role-run and every git side effect are single-attempt
  activities, and a failure stops the run for the operator.
- **D8** **State stays compact and raw** (ids, refs, verdict, feedback —
  never transcripts/diffs/accumulated prompts); prompts reach CLIs as an argv
  argument and are kept in files we name; per-role-run logs and terminal
  records own the bulky evidence.

## Does not own

Judgement about the work: an engineer's blocker reaches a human only as an architect verdict. The
agents' own reasoning, which runs in their CLIs. The repository's history beyond one run's commit
and merge. The operator's decision to merge.

- **D9** **No browser automation of chat UIs on critical accounts.** ChatGPT
  is consulted manually by the operator: its account is not risked. A
  low-cost web chat whose account can be lost, such as DeepSeek, may be driven
  through a browser as a detached architect — deliberately, never as a silent
  addition.
- **D11** **Agents never stage, commit or push.** Terminal state of the
  agents' work is `READY_FOR_HUMAN`; only the controller commits and merges,
  and only after the operator's `merge` at that run's final gate (D24).

### Why there is no state machine here

A hand-rolled state machine drops reviewer feedback on routing edges, and a typed domain contract
of gates, grants and retry episodes is the machinery that exists to catch that and keeps missing
it. The workflow is ordinary code over one compact state, reading its routes from two pure
functions; Temporal records every step, so a restart resumes mid-loop rather than re-deriving
where the run was. Do not re-derive a `states/` layer here.

## Composition

| part | responsibility |
|---|---|
| [app/](../../app/README.md) | the production source, one package per concern; each package's README is its contract |
| [app/orchestration/](../../app/orchestration/README.md) — [workflow.py](../../app/orchestration/workflow.py) | the run: stages, verdict routes, stops and their named answers, the final gate, the `status` query |
| [routing.py](../../app/orchestration/routing.py) | which stop a verdict asks for and where it sends the run — no dependencies |
| [app/application/](../../app/application/README.md) — [activities.py](../../app/application/activities.py) | everything a run does on its target host: resolve, worktree, role-run, merge, discard, the change for review, trace writes |
| [client.py](../../app/application/client.py) | the one client of runs — start, list, status, answer, the change, the worktrees — shared by the page and the CLI |
| [app/agents/](../../app/agents/README.md) — [nodes.py](../../app/agents/nodes.py) | prompt composition, the agent argv, session identity, verdict parsing, failure classes |
| [terminal.py](../../app/agents/terminal.py) · [ptyhost.py](../../app/agents/ptyhost.py) · [turn_hook.py](../../app/agents/turn_hook.py) | each role's live terminal on its host — its record, its WebSocket, a role turn run in it and that turn's completion |
| [launch.py](../../app/agents/launch.py) | one agent process from an argv list, with its whole descendant tree contained |
| [trust.py](../../app/agents/trust.py) | telling this host's agent CLIs that a run's repository is one the operator works in, so no turn stops at their trust dialog |
| [app/workspace/](../../app/workspace/README.md) — [worktrees.py](../../app/workspace/worktrees.py) | the run's worktree through the target's own git: create, guard, merge, discard, the view |
| [repos.py](../../app/workspace/repos.py) · [repos.json](../../repos.example.json) | which repository, target, base branch and worktree root a run uses |
| [app/foundation/](../../app/foundation/README.md) — [paths.py](../../app/foundation/paths.py) | the one derivation of this checkout's root, the runtime root a run writes under, and the secrets directory |
| [policy.json](../../policy.json) · [policy.py](../../app/foundation/policy.py) | roles, brains, budgets, access, target hosts — and strict validation of them |
| [envpath.py](../../app/foundation/envpath.py) | where each checkout's environment lives on each host, and its guarded removal |
| [app/observability/](../../app/observability/README.md) — [telemetry.py](../../app/observability/telemetry.py) | the optional trace of a run — its work item, phases, role steps, stops, final diff and scores, written to the [trace contract](trace-contract.md) — and the per-run settings that let each agent's tracing plugin nest its turns there |
| [app/interfaces/](../../app/interfaces/README.md) — [workbench/](../../app/interfaces/workbench/server.py) | the operator's page: every run, its stop and answers, its live terminals, its rounds and its change |
| [cli.py](../../app/interfaces/cli.py) | the command line over the same client: start, answer, continue, show, list — for tests and automation |
| [worker.py](../../app/interfaces/worker.py) · [workers.sh](../../workers.sh) · [workers.ps1](../../workers.ps1) | one Temporal worker per host, and their start, check and stop |
| [temporal/](../../temporal/compose.yaml) | the Temporal service: server, its PostgreSQL, the web UI, the namespace |
| [roles/](../../roles/) | two persona files, sent at session start |
| [tests/](../../tests/README.md) | what is proven, and how to run it |

- **D30** **Source is organised by concern, not by a flat root.** Each concern owns a
  package under `app/` — `foundation`, `orchestration`, `workspace`, `agents`,
  `observability`, `application`, `interfaces` — and each carries a README stating what it
  owns, what it does not, what it may import and the invariants it keeps. The folder is the
  structural source of truth: `tests/test_architecture.py` enforces the direction between
  packages, so a new module inside a package needs no entry anywhere, and a new *package*
  does. This supersedes the standing decision to keep every module at the repository root,
  which held while the orchestration lived inside another repository and was reversed when
  Orchestra became a repository of its own; the reasoning is in
  [decisions.md](../history/decisions.md). Three files are still launched by path and
  therefore import nothing of ours — `app/foundation/envpath.py`, `app/agents/ptyhost.py`
  and `app/agents/turn_hook.py`.
- **D2** **Two roles**: **engineer** (write access — plans the
  change, then builds it; one session, full context arc) and **architect**
  (read-only — assesses the plan, then verifies the build; one session, so
  the judge of the plan is the verifier of its execution). Four stages, one
  workflow: `plan → assess → build → verify`.
- **D13** **Config vs code:** which brain, model and reasoning effort a role
  uses, budgets, access, target hosts, repository descriptors and role
  personalities (`roles/engineer.md`, `roles/architect.md` — sent at session
  start) are configuration; the set of brains that can be bound is code,
  because each CLI has its own flags for session identity, turn completion
  and read-only mode, and none of that is derivable from configuration. Stage
  asks (which artifact a stage produces or judges) and any new *stage* are
  code. There is no JSON workflow DSL.
- **D22** **Environments are part of the toolchain.** Every orchestration
  process runs on a uv-managed CPython 3.13 from one `uv.lock`, pinned to one uv
  release by `required-version`; system Pythons are never used. WSL and Windows
  share one checkout on a Windows drive, so each host keeps each checkout's
  environment on its own disk, in a directory named by a hash of the checkout's
  path (`envpath.py`): a run worktree of this repository gets its own
  environment, and its tests never re-sync the one the live workers import.
  A run worktree's environment is removed with the worktree, on its target host,
  only when the derived path lies under that host's environment root, crosses
  no link or reparse point, and holds `pyvenv.cfg`.

## Relationships and dependency direction

Orchestra's parts and the participants outside it are drawn in
[the main view](diagrams/main.md); which process each runs in is
[the processes view](diagrams/processes.md), and every stop a run can reach is
[the stops view](diagrams/stops.md). Verdicts flow one way — architect to workflow — and
nothing else routes. Observability depends on the workflow and is never read back (D20). What
each verdict means is in [the architect's own file](../../roles/architect.md); a host that binds its
own methodology to a stage (`stage_skills`) owns it there instead.

The source itself is organised by concern (D30): one package per concern under `app/`, and the
folder is the ownership boundary. Each concern states its own boundaries, parts and invariants
at its own level, reached from [app/README.md](../../app/README.md); the direction they depend
in is drawn once, in [the main view](diagrams/main.md), and is not restated here.

That direction is not a convention: `tests/test_architecture.py` reads `app/`, resolves every
import — relative ones included — and fails on one that crosses a boundary the table does not
allow, with controls that prove each check can reject a violation. The table records the
imports that exist; no indirection exists here to satisfy it, and nothing imports an entry
point, which is what keeps argparse and console output out of the worker and the workbench.

Where a run may put files, where this checkout is, and which agent a turn is each have exactly one
owner for the same reason — a second definition is equal only until someone moves a module. The
checkout root is derived once, in `app/foundation/paths.py`, and the suite proves the derivation
still lands on a checkout.

- **D4** **Only architect verdicts route** — `PASS / PATCH / BLOCKER /
  UNVERIFIED`. Engineer output always goes to the architect; an engineer-side
  blocker or open question reaches the human only through the architect.
- **D7** **Sessions:** one persistent CLI session per `(run_id, role)`;
  resume by exact stored id (Claude `--session-id` minted by us, Codex the
  thread its first turn completed in), never `--last`. Session = disposable
  working memory; the workflow's state + worktree = truth, sufficient to
  rehydrate. Automatic fresh-rehydrate only on a definitive
  session-not-found *before* work begins.
- **D17** **The execution seam is a role turn in the role's live terminal on the target host, contained.**
  A role-run is an activity on its target host's task queue. Each role of a run has one
  terminal on that host's worker, from its first turn until the run's merge or discard begins
  or the run is aborted: every byte its agent draws is recorded under `tmp/orchestration/<run-id>/terminals/`
  and served on the worker's WebSocket, which takes keystrokes back, so the operator can
  watch, press Esc and type at any time. A turn ends the agent process under the terminal,
  if any, and starts the vendor's interactive CLI again from an argv list — no shell, so no
  task text is ever parsed as shell syntax — with the role's session resumed by exact id and
  the prompt as its last argument. It ends on the vendor's own completion, which the vendor's
  hook writes into the turn's own events file. The file and the process are the turn's, so a
  prompt the operator types into the running agent — after an Esc, say — steers this turn, and
  its completion ends it: Claude's `Stop` for the prompt id its `UserPromptSubmit` reported for
  that prompt or any submitted after it in the role's session, while no background task of it
  still runs; Codex's `agent-turn-complete` in the role's thread whose inputs, the thread's
  prompts so far, include the controller's. Codex's title turn runs in a thread of its own and
  never ends it; an interrupt completes nothing. `StopFailure`, any check of the result failing,
  the agent exiting first, or the timeout fails the step and ends the agent. A successful turn
  leaves the agent running, live. The verified tree is the worktree as the architect's verify
  turn began, and a change during that turn fails the step. The merge and the discard end the
  run's agents before git touches the worktree, and close the viewers attached to them, so
  nothing changes the worktree between the check of the verified tree and the commit, and a
  page attaches again to whatever terminal comes next.

  The agent runs in a pseudo-terminal under `ptyhost.py`, launched through `launch.py`, so its
  whole descendant tree is contained by a primitive native to the host: on POSIX a transient
  systemd user scope, a cgroup no descendant leaves whatever it does to its own session. A stub
  inside the scope reports in and starts the process only on the worker's answer, so an agent
  never runs outside a scope and never starts after the worker's death, and a launch no scope
  can hold is refused before the agent runs; a reaper process, started before any of it and
  holding a pipe from the worker, kills that scope when the worker dies. On Windows the
  process is created already inside a job object that kills every process in it when its last
  handle, the worker's, closes, and its ConPTY is created by that process, inside the same job.
  A turn's end, a timeout, a cancellation, the run's close and the worker's own death all end
  the tree. A Claude engineer runs in `dontAsk` mode with edits allowed inside its worktree and
  the host's skills directory added for reading, so a turn never waits on a permission prompt:
  what is not allowed is denied and the agent works on. A Codex role never asks either. The
  prompt follows `--`, so no option that takes several values can swallow it. On Windows a Codex role-run uses Codex's unelevated sandbox: the elevated one
  starts its helper through an administrator prompt, which a worker outside the interactive
  desktop can never show; the ConPTY asks its terminal for win32-input-mode, in which Codex
  ignores a bare ESC byte, so the terminal delivers Esc as a key event. An agent's environment
  never carries the markers of a Claude Code session the worker was started from: with them,
  Claude runs as that session's child and keeps no transcript to resume. The activity
  heartbeats while the turn runs, so a lost worker becomes a failed stop after the heartbeat
  timeout. The prompt, the final message, the turn's events and what the terminal showed during
  the turn stay under `tmp/orchestration/<run-id>/logs/` of the orchestration checkout on that
  host.
- **D18** **Model and reasoning effort are configuration**: optional per-role
  `model` and `reasoning_effort` strings are passed straight to each brain's
  native control — `--model` on both, `--effort` for Claude, the
  `model_reasoning_effort` config override for Codex. Absent means the
  provider default, which is whatever was last chosen interactively on this
  machine, so a role whose judgement must not drift pins both: the architect
  does. No model registry. Policy validation is **strict** — unknown
  top-level or role keys are rejected, so a typo cannot silently do nothing,
  and both values must be plain tokens.
- **D21** **A role's durable conversation is owned by its provider's own
  session store on the target host** — Claude under `~/.claude/projects/<cwd>/<session-id>.jsonl`,
  Codex under `~/.codex/sessions/<date>/rollout-*-<thread-id>.jsonl`, in that
  host's user profile — keyed by the worktree the role ran in, spanning every
  resumed stage of that role, and independent of the process that launched it.
  Our `logs/*.out` own the *parsed* evidence a stage was judged on; the session
  store owns the conversation. What a session store holds is every message and
  every tool call with its result. Reasoning differs by vendor. Codex writes a
  readable summary of its reasoning into the rollout only when summaries are on,
  so a Codex role's launch sets `model_reasoning_summary="detailed"` and the
  trace shows the architect's summaries beside its verdict; with summaries off,
  a reasoning record carries only `encrypted_content`. Claude persists its
  thinking as an empty `thinking` block plus a signature, so no stored surface
  holds the engineer's reasoning; what its interactive CLI draws while it thinks
  is visible in its live terminal and its record, and nowhere else. Do not add
  plumbing to chase it.
- **D20** **Observability has four owners, and no projection is ever authority.**
  Temporal owns what a run is doing and what it did: its event history, and the workflow's
  `status` query with one console line per stage transition and a timeline of every judgement —
  what `orchestrate` prints while it follows a run, what `--show <run-id>` prints afterwards, and
  what the Temporal web UI shows. The trace store — a self-hosted Langfuse, written by
  `telemetry.py` — owns the debugging history of a run: one work item per run, its session named
  by its start time and task, holding its plan and build phases; in each, every round's engineer
  and architect step, named for its kind of step with the round in its metadata and the
  architect's verdict scored on it; each stop for a human and the answer given to it, the approval
  carrying the plan's summary; each agent's own turns and tool calls, nested by that vendor's
  tracing plugin under the step that caused them; and the final diff as `gdiff -s` copies it, cut
  at a size cap and marked truncated when it exceeds one, redacted and marked when it held a secret.
  The names, levels, scores and dimensions that views and the dashboard select on are the
  [trace contract](trace-contract.md). The provider session store owns the full conversation
  (D21), and `logs/` with the terminal records the raw evidence. The workbench (D29) shows
  Temporal's view, the live terminals and the records; it owns none of them.

  The trace is observability only: nothing reads back from it, and its failure can neither break
  correctness nor reroute a run, nor block one beyond its own bounded timeout. It is optional — a
  run without keys records nothing and behaves identically. Only activities write it, each run
  once, so neither a replayed workflow task nor a retry can write a row twice; the only values that
  cross back into the workflow are the opaque ids of the work item and its phases, which no route,
  verdict, budget or stop reads. A failed stage is recorded as an error with its error type before
  its failure reaches the workflow.

  The trace store receives only what this component launches. No user-level configuration holds a
  working key — neither Claude's settings nor its credential store, whose secret outranks any a
  run supplies — so this component takes the keys from `secrets/langfuse.env`, the one file holding every
  Langfuse credential, and a traced Claude role-run receives them in its own settings file for as long as it
  runs. The setup, on both hosts, is in [tools/README.md](../../tools/README.md).
- **D23** **Each target host has its own task queue**, `target:<os>:<host>`,
  polled only by that host's worker, and every activity of a run goes to its
  target's queue. The WSL worker also runs the workflows on the `orchestration`
  queue. A run needs the workflow queue and its own target's queue polled, and
  nothing else: a WSL run never waits on the Windows worker.
- **D24** **The worktree lifecycle and the final gate.** A run's worktree is
  created by the target's own git at `<worktree root>/<run-id>` on branch
  `<run-id>` from the base branch, linked the way that repository's own git
  settings say. The run id reads as the task: its first words, lowercase and hyphenated, up
  to 16 characters, then eight random characters — 25 in all, because a Windows
  worktree folder plus a repository's deepest file must stay within Windows' path
  limits. A start whose id meets a run Temporal still retains draws a fresh one; a
  Windows worktree whose deepest file or folder would pass those limits, measured
  on that repository's base branch, is refused before it exists; and an existing
  branch of the run's name is adopted only while it still points at the base. At `READY_FOR_HUMAN` the run waits at its final gate for `merge`,
  `revise engineer|architect <feedback>` or a confirmed `discard`; a defect goes
  back into the run, to the role the operator names. `merge` commits only the
  tree the architect's last `PASS` verified: the plan moves to the repository's
  done folder with a finished status line — or, where the repository deletes a
  finished task (a null `todo_done_dir`), is deleted — the change lands as one commit whose
  message is the plan's name and a few words of the task, and the base branch
  gains an explicit `--no-ff` merge commit named for the plan — in the base's
  checkout when it is checked out there, which refuses staged changes that are
  the operator's, and otherwise without touching any checkout. A conflict never
  resolves in the controller: the base is merged into the run's worktree with its
  conflict markers, the engineer resolves the files, the architect verifies, the
  operator merges again, and the run branch gains one reconciliation merge commit.
  After a merge the worktree, its branch and its environment go; a discard removes
  them unmerged. Every git side effect reads what git already holds first, so an
  attempt whose worker died after git wrote is adopted when it runs again, never
  applied twice; a merge whose commit was refused after the plan was finished is put
  back to the verified plan and staged nothing, and merges when continued.

- **D29** **The workbench is the operator's surface.** One page on `http://127.0.0.1:<workbench_port>`
  lists every run Temporal holds, grouped by whether it waits for the operator, runs or has
  finished — every open run, however old, and the finished ones newest first a page at a time, so a
  run waiting for an answer is never off the list and everything Temporal still retains is reachable; a run shows its stop with that stop's answers as
  buttons, both roles' live terminals from their host's worker, its plan and build rounds with each
  verdict and its feedback, its change as its target host's git reads it, and links to its Temporal
  and Langfuse pages. It also shows any repository's worktrees and which of them are merged. It
  starts runs. It holds no state: every read is Temporal's or a worker's, and every write is a
  start or an answer Update through `client.py`, which the command line uses too, so the page can
  do nothing the workflow's own rules and validators do not allow. A change is read in bounded
  parts, because Temporal refuses a payload past its own limit and a review that cannot be read is
  worse than one read in two presses; each part carries the identity of the change it came from, so
  parts of two changes — the terminals stay writable at the gate — are never shown as one. Its API and the workers' terminal sockets accept only the
  page's token — a random value in `secrets/workbench.token`, made on first use — from the page's
  own origin, and the page only from its own loopback host name, so neither another site in the
  browser nor a rebound DNS name can use them; the terminal sockets take that token in the
  handshake's own header, never in a URL, which browsers print and proxies log. Everything listens
  on `127.0.0.1`. It is plain HTML, CSS and JavaScript with a pinned, vendored xterm.js and no
  build step; agent text reaches it only as terminal bytes or as text, never as markup.

## Invariants

- **D3** **The judge is never the builder:** the architect must not be the
  same model as the engineer. Independence is a property of the model that
  thinks, not of the CLI that launches it, so a role's judging identity is
  `(brain, model)` — one `claude` running Opus and another running Fable are
  two judges; two roles that both take the provider default are one. Rejected
  at policy load, enforced further by each CLI's own read-only mode, set by
  its flag. Different vendors remain
  the strongest form, because they share neither training nor blind spots; two
  models from one vendor share tooling and much of their training, so they are
  the weaker form and are chosen deliberately. The guard compares the names it
  is given and cannot resolve them: two different names that alias to the same
  weights pass it, so naming two genuinely different models is the operator's
  part of this invariant.
- **D6** **A stop waits in the workflow and nowhere else.** Its answer arrives as
  an Update carrying one of that stop's named actions — approve, revise or abort
  at the plan approval; guide or abort at a blocker or an exhausted budget;
  continue or abort after a failed stage; merge, revise or discard at the final
  gate — and a validator rejects anything else before it reaches history, so no
  unrecognised answer is ever read as abort or discard. The Update's id is
  `answer:<stop-id>`, so an answer sent twice is applied once. No activity ever
  waits for a human.
- **D10** **Account safety:** human-triggered only (no scheduler may start an
  agent run on subscription auth), strictly sequential, bounded, official
  CLI interfaces only. Scheduled/parallel execution, if ever wanted, moves
  to API-key auth first.
- **D14** **Mutual critique, both directions:** feedback is evidence, not
  authority. The engineer refutes wrong findings with evidence instead of
  applying them; the architect re-verifies refutations against code instead
  of defending positions.
- **D15** **Architect's wider horizon**: the architect may
  challenge the *task itself* (mismatched/harmful/wrong problem → BLOCKER
  with a better direction — the human gate decides), may propose
  refactor-first or a different tool/approach before any build, and is
  expected to check current practice on the live web (live web search is
  enabled for its brain). Bound by the evidence rule: every challenge cites something
  read or found, never taste; and by D4 — challenging routes through
  verdicts, it grants no new routing power.
- **D16** **Failure recovery is manual and explicit**: when a
  role-run fails for an external reason (quota, auth, network) or its worker is
  lost, the run stops with the failing stage and its error named and its logs
  pointed to. After fixing the cause the operator continues the same run with
  `orchestrate --continue <run-id>`, which runs that stage once more; every
  stage that completed stays completed. **No automatic retry, no retry ledger.**
- **D18b** **A rehydrated session is bootstrapped from zero**:
  any prompt built for a session being born carries task, persona, the
  **current stage ask**, and the latest findings/guidance — never a delta
  that references memory the new session never had. This is the executable
  form of the standing boundary that state plus the worktree must be
  sufficient to reconstruct a role. Healthy resumed sessions keep the
  cheap delta.
- **D19** **The skill owns how a role judges; the persona owns only what is
  orchestrator-specific**: the global `architect`,
  `investigate-change` and `implement-approved-change` skills own the stance,
  the evidence rules and the verdict vocabulary, through the shared contracts
  they read. A `roles/*.md` file states who the role is in this workflow, defers
  to its skill, and adds only what the skill cannot know — session persistence
  across its two stages, and that the verdict is what routes (D4). It never
  restates the stance, so the two cannot drift. Each stage invokes its skill
  as the prompt's first characters (the `stage_skills` policy key): the skills are
  model-invocable, but an unattended run must not depend on the model choosing
  correctly every episode, and a mid-prompt invocation is inert. This does not
  widen D13 — the persona files stay configuration, and which skill a stage
  invokes stays code.
- **D25** **The workflow is deterministic.** No clock, randomness, file,
  network or process call happens in workflow code outside Temporal's own APIs;
  every effect is an activity. A change to what the workflow commands goes
  behind `workflow.patched`, and the recorded histories under `tests/histories/`
  must keep replaying.
- **D26** **One authority per repository fact, refusing when there is none.** A
  run's repository, base branch, execution target, worktree root and todo
  convention come from its `repos.json` entry when configured, and are detected
  otherwise: a repository on a Windows drive runs on Windows unless its entry says
  WSL; the base branch is `develop`, else `dev`, else the remote's default; the
  worktree root is the target's root, then the folder matching the repository's
  category case-insensitively, then its name. A value neither configured nor
  detected refuses the run on its target host before any worktree exists, and a
  Windows target refuses a path Windows cannot use as a working directory, which
  it would otherwise silently replace with `C:\Windows`.
- **D27** **Only the controller changes a worktree's git state.** Around every
  role-run the controller compares a digest of HEAD, the run's branch,
  `MERGE_HEAD` and the staged content; a change fails the stage. An agent's git
  runs with every push URL rewritten to an unusable transport, every transport
  refused, and `GIT_ALLOW_PROTOCOL` naming a protocol that does not exist — which
  takes precedence over the transport configuration, so a deliberate
  `git -c protocol.allow=always` no longer lifts the refusal. Under the environment
  the controller supplies, a push an agent attempts reaches no remote, and the
  orchestration itself has no push operation; `git status`, `git diff`, `git log`, `git add` and
  `git commit` keep working. A Codex role-run is sealed further by the vendor's own
  sandbox, which has no network at all. What these guards are not is in
  [Risks and technical debt](#risks-and-technical-debt).

## Accepted decisions

An index. Each decision is written above, beside the boundary, relationship or invariant it
constrains.

| decision | where it lives |
|---|---|
| D1 Temporal owns the workflow, D5 round budget and single attempts, D8 compact state | [Owns](#owns) |
| D9 no chat-UI automation on critical accounts, D11 agents never stage, commit or push | [Does not own](#does-not-own) |
| D2 two roles and four stages, D13 config versus code, D22 environments, D30 source organised by concern | [Composition](#composition) |
| D4 verdict routing, D7 sessions, D17 execution seam, D18 model as configuration, D20 observability owners, D21 provider session stores, D23 a task queue per host, D24 worktree lifecycle and final gate, D29 the workbench | [Relationships and dependency direction](#relationships-and-dependency-direction) |
| D3, D6, D10, D14, D15, D16, D18b, D19, D25 determinism, D26 repository facts, D27 controller-only git | [Invariants](#invariants) |
| D28 containment, live-terminal and plugin-build limits | [Risks and technical debt](#risks-and-technical-debt) |

The superseded founding register — 77 decisions and the full reviewer journey — is in git history
at commit `a60f864`.

## Risks and technical debt

- **D28** **Accepted limits.** The agent's git guards are its environment, not a
  security boundary: a role that clears `GIT_ALLOW_PROTOCOL` and the `GIT_CONFIG_*`
  block from its own environment can reach a remote, and only the remote itself — a
  protected branch — prevents that. They hold against a role that pushes without
  meaning to, which is the failure they exist for. A POSIX host needs a reachable
  systemd user manager to run any role. The workbench's token keeps other sites and other
  users out, not other processes of the same user, which can read it. What the operator types
  into a live terminal between turns reaches only that agent and routes nothing; typed during
  a turn it steers that turn, whose final message — for the architect, its verdict — routes as
  any turn's does. A change to the worktree while the architect judges it fails that step, at
  either review stage, so a `PASS` always describes the tree that architect actually read; a plan
  the operator changed after that `PASS` goes back to the architect instead of being built, because
  the summary the operator approves from is the one the architect wrote about the plan it read; and
  a merge still commits only the tree its last `PASS` judged. What a Claude engineer
  may do beyond editing its worktree is what the host's own Claude settings allow and deny:
  those rules are part of its boundary. Both interactive CLIs stop at a trust dialog in a
  repository they have no record of, so a run records its repository for them on its target host
  before any agent starts — starting a run on a repository is that decision, whether it came from
  `repos.json` or as a path, and the record covers every later run of that repository
  ([tools/README.md](../../tools/README.md)). The record is best effort: one that
  could not be written leaves the dialog, and a turn left waiting there ends at its timeout. An architect's turns nest under their stage
  only with a Codex tracing plugin built with the parent-trace and
  turn-lifecycle changes that [tools/README.md](../../tools/README.md) names,
  kept under the orchestration's own directory on each host because Codex
  restores its own plugin cache; `telemetry.py` warns when the build it finds
  lacks them.
