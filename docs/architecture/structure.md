# Structure

## Contents

- Purpose · Owns · Does not own · Composition
- Relationships and dependency direction
- Invariants
- Accepted decisions
- Risks and technical debt

## Purpose

Drive one change through the stages its flow gives — `plan → assess → build → verify` unless the
operator picks another order — with two agent roles, in a git worktree
of whichever repository the change is for, with the agents running on the operating system that
repository needs — stopping for a human whenever a verdict says it should, and merging the verified
change only when the operator says so.

## Owns

The workflow of a run and its durable state, routing between stages, the round budget, the stops
and their answers, where a run's roles execute, the run's worktree from creation to merge or
discard, and the commit and merge of an approved change. What each stage asks for is workflow
contract and lives in `app/foundation/stages.py`, which `app/agents/nodes.py` renders into a
vendor prompt; what a role is lives in configuration, and so does the order a run takes its stages
in — its flow, one file in `flows/`.

- **D1** **Temporal owns the workflow.** One workflow execution per run, its Workflow Id the run
  id; a start refuses an id that is open or still retained (`WorkflowIDConflictPolicy.FAIL`,
  `WorkflowIDReusePolicy.REJECT_DUPLICATE`), and the orchestration never reuses a run id on its
  own. The workflow code decides every transition from `routing.py` and nothing else, and its event
  history is the run's durable state: a process that exits at a stop loses nothing, and any later
  process answers it. The self-hosted server keeps its own PostgreSQL, and its `orchestration`
  namespace keeps closed runs for 90 days.
- **D5** **`max_rounds`** = architect attempts per phase — the plan's or the
  build's, the work a review judges; research, which none judges, has none —
  counting from 1 including the first; `== max` stops for the human. Operator guidance
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
where the run was. A run's flow does not bring one back: it is a list the loop walks, one work stage
and the review that judges it at a time, and feedback and guidance still live in the run's state.
Do not re-derive a `states/` layer here.

## Composition

| part | responsibility |
|---|---|
| [app/](../../app/README.md) | the production source, one package per concern; each package's README is its contract |
| [app/orchestration/](../../app/orchestration/README.md) — [workflow.py](../../app/orchestration/workflow.py) | the run: stages, verdict routes, stops and their named answers, the final gate, the `status` query |
| [routing.py](../../app/orchestration/routing.py) | which stop a verdict asks for and where it sends the run — no dependencies |
| [app/application/](../../app/application/README.md) — [activities.py](../../app/application/activities.py) | everything a run does on its target host: resolve, worktree, role-run, merge, discard, the change for review, trace writes |
| [client.py](../../app/application/client.py) | the one client of runs — start, list, status, answer, stop, force terminate, the change, the worktrees and the removal of what a closed run kept — shared by the page and the CLI |
| [stack.py](../../app/application/stack.py) | the stack's one reading and its one owner: Temporal and each host's worker, started, stopped and restarted for the Makefile, the command line and the page |
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
| [app/interfaces/](../../app/interfaces/README.md) — [workbench/](../../app/interfaces/workbench/server.py) | the operator's page: the stack, every run, its stop and answers, its live terminals, its rounds and its change — a systemd user service in WSL, outside the stack it controls |
| [cli.py](../../app/interfaces/cli.py) | the command line over the same client and the stack's owner: start, answer, continue, stop, force terminate, show, list, the stack — for tests, automation and the Makefile |
| [worker.py](../../app/interfaces/worker.py) · [workers.sh](../../workers.sh) · [workers.ps1](../../workers.ps1) | one Temporal worker per host, and each part of the stack's process mechanics: start, stop, status and the sweep of what a dead worker's stages left |
| [temporal/](../../temporal/compose.yaml) | the Temporal service: server, its PostgreSQL, the web UI, the namespace |
| [roles/](../../roles/) | two persona files, sent at session start |
| [flows/](../../flows/README.md) · [flows.py](../../app/foundation/flows.py) | the order of a run's stages, one file per flow, and the rules a flow keeps |
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
  (read-only — researches where a flow begins with it, assesses the plan, then
  verifies the build; one session, so the judge of the plan is the verifier of
  its execution). Five stages — `research`, `plan`, `assess`, `build`, `verify`
  — in the order the run's flow gives them, one workflow; `engineer-code`,
  `plan → assess → build → verify`, is the default.
- **D13** **Config vs code:** which brain, model and reasoning effort a role
  uses, budgets, access, target hosts, repository descriptors and role
  personalities (`roles/engineer.md`, `roles/architect.md` — sent at session
  start) are configuration; the set of brains that can be bound is code,
  because each CLI has its own flags for session identity, turn completion
  and read-only mode, and none of that is derivable from configuration. Stage
  asks (which artifact a stage produces or judges), which role takes each,
  which work each review judges, the rules a flow keeps and any new *stage* are
  code (`stages.py`, `flows.py`). The order of a run's stages is configuration:
  its **flow**, one file in `flows/` holding `role:action` steps, read and
  checked when a run starts and handed to it whole — the workflow never reads a
  flow, a run keeps the one it started with, and a start that carries no flow
  at all, as none did before flows, follows `LEGACY_FLOW`, today's default
  order. A flow keeps these rules: from
  one to `MAX_FLOW_STEPS` steps, the bound that keeps a run the bounded work one
  workflow is for; each step's role the one its action is the stages'; every
  `plan` followed by its `assess` and every `build` by its `verify`, so an
  engineer's work always reaches a review (D4); an approval only after a review
  or a `research`; a `research` only before any `plan`, which starts from its
  brief; a `build` only after a `plan`; and a flow that builds ends with the
  merge, right after a `verify` (D24). A run is handed its flow as `{name, steps}`
  and takes it as given: one of another shape, or that breaks a rule, ends the
  run `REFUSED` before any step. A flow's name is its file's, by one grammar
  (`flows.is_name`) wherever a name is taken — a file, the policy's
  `default_flow`, a run's own flow. It is one list, with no states,
  transitions or conditions — Temporal's own pattern for a workflow defined as
  data, one interpreter given the definition as its input.
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
imports that exist — an allowed import nothing makes fails too — and the main view draws
exactly that table; no indirection exists here to satisfy it, and nothing imports an entry
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
  or the run otherwise ends: every byte its agent draws is recorded under `tmp/orchestration/<run-id>/terminals/`
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
  the tree. On Windows a termination only begins the end — a process still holds the directory
  it worked in, which Windows then refuses to remove, and the job drops it from its own list at
  once — so the end closes the job to newcomers, holds each process it lists, and after the
  termination waits until each has ended: a worktree is free to remove the moment its agents are
  ended, and an end it cannot prove — a process it lists but cannot open, or one not ended within
  the grace — fails the step, so no merge or discard goes on as though it were. A Claude engineer runs in `dontAsk` mode with edits allowed inside its worktree and
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
  by its start time and task, holding a phase for each work stage of its flow — research, plan,
  build; in each, every round's engineer and architect step, named for its kind of step with the
  round in its metadata and the architect's verdict scored on it; each stop for a human and the
  answer given to it, an approval carrying the plan's summary or the research brief; each agent's
  own turns and tool calls, nested by that vendor's
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
  verdict, budget or stop reads. A step a Stop cut short is no failure: its row says only that the run
  was stopped. One cut short any other way — its worker stopped, a force terminate, a heartbeat timeout
  — is recorded as lost. A failed stage is recorded as an error with its error type before
  its failure reaches the workflow.

  The trace store receives only what this component launches. No user-level configuration holds a
  working key — neither Claude's settings nor its credential store, whose secret outranks any a
  run supplies — so this component takes the keys from this checkout's `.env`, the one file holding every
  Langfuse credential, and a traced Claude role-run receives them in its own settings file for as long as it
  runs. One a stage left when its worker died first is removed as soon as the stack stops that worker
  and has proven it gone (D32), or else by the next worker to start on that host. The setup, on both hosts, is in [tools/README.md](../../tools/README.md).
- **D23** **Each target host has its own task queue**, `target:<os>:<host>`,
  polled only by that host's worker, and every activity of a run goes to its
  target's queue. The WSL worker also runs the workflows, on its policy's
  workflow queue (`workflow_queue`): `orchestration` for the deployment, where
  every run Temporal retains is queried, and one of their own for the demo's and
  the acceptance's policies, so each is a stack apart whose worker never takes
  another's workflow tasks. A run needs its workflow queue and its own target's
  queue polled, and nothing else: a WSL run never waits on the Windows worker.
- **D32** **The stack has one owner, and the Workbench is outside it.** A stack is
  what one policy runs: Temporal, one service on the machine, and a worker per
  target host, the WSL one also running the policy's workflows.
  `app/application/stack.py` is its one reading and its one owner — the Makefile's
  `up`, `down` and `check`, the command line's `--stack` and the Workbench's stack
  panel all go through it, on WSL. It starts Temporal, then each worker once
  Temporal answers, and stops them in the reverse order. A part is up only when
  proven: Temporal answering, and a worker polling each of its queues as the
  process its pid file names — Temporal lists a dead worker's polls for minutes. A
  worker stopped on purpose counts as stopped only once its process is proven gone,
  and then what its stages left on that host is swept at once (D20). One action
  runs at a time, under a lock the kernel frees if its holder dies. A part runs from
  its start to its stop and nothing else starts it: Temporal's containers come back
  only when they fail, never with Docker at WSL's start. The checkout's
  own policy's stack manages all three parts; another policy's manages only its
  WSL worker, since Temporal is the deployment's and the Windows host runs only
  its own copy of a policy. The process mechanics are `workers.sh` and
  `workers.ps1`, one part at a time: the WSL worker starts in a systemd scope of its
  own, so a restart of the Workbench's service never takes it; the Windows worker
  is created through WMI, hidden, and known by its command line as well as its pid.
  WSL runs a Windows program with the token of whatever started WSL — from the
  Workbench's service, which systemd starts, that is the process that booted the
  distro — and the Windows worker and its agents never run as an administrator: a
  start from an elevated side is handed to the desktop's shell, which starts it with
  the user's own token (Microsoft's ExecInExplorer pattern). Only with no shell to
  hand it to is the start refused, saying so; the reading then shows the worker as one
  this side cannot start, and a restart leaves it running rather than stop it only to
  leave it down.
  The Workbench is a systemd user service in WSL, `orchestra-workbench.service`: it
  starts whenever the distro does and comes back if it fails, runs with the
  operator's login PATH, which the workers it starts inherit, and is installed,
  started and stopped only by the Makefile's `workbench-*` targets — never by
  itself, `make up` or `make down`.
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
  them unmerged. A run whose flow has no build never reaches the final gate: it
  ends `DONE` after its last stage, merging nothing, and keeps its worktree and
  branch for the operator, as a stopped run does (D31). Every git side effect reads what git already holds first, so an
  attempt whose worker died after git wrote is adopted when it runs again, never
  applied twice; a merge whose commit was refused after the plan was finished is put
  back to the verified plan and staged nothing, and merges when continued.

- **D29** **The workbench is the operator's surface.** One page on `http://127.0.0.1:<workbench_port>`
  lists every run Temporal holds, grouped by whether it waits for the operator, runs or has
  finished — every open run, however old, and the finished ones newest first a page at a time, so a
  run waiting for an answer is never off the list and everything Temporal still retains is reachable. A
  run that waits shows its stop first, with that stop's answers as buttons and what to judge them by;
  then both roles' terminals from their host's worker, the one at work open and an idle one opened when
  the operator opens it; its flow with the step it is at, the rounds of each phase with each verdict and
  its feedback and a research step's brief, its change as its target host's git reads it, and links to
  its Temporal and Langfuse pages. The page's address names the run open, so a reload keeps it.
  Each run also says what it is doing now — the stage and role at work, or
  the stop it waits at or the failure it stopped on — since when, and which host's worker it is
  blocked by when one is down, with that worker's start beside it; a run whose workflow worker is
  down is still shown, from its listing. Above them the stack's chips show each part of the stack,
  the reading `make check` prints, and open its start, stop and restart of each part or of the whole
  stack (D32) — the whole stack's start and restart only while every part is in a state that is safe
  for them, since they act on every part — and a part that is down raises a banner, with its start
  where this side can start it. It
  also shows any repository's worktrees, which of them are merged and which run each is. It starts
  runs on the flow chosen from `flows/`, read again each time its list is opened, stops or
  force-terminates them (D31), and removes what a closed run kept. It holds no
  state: every read is Temporal's, a worker's or the stack owner's, and every write is a start, an
  answer Update, a Stop, a force terminate or a removal through `client.py`, which the command line
  uses too, or a stack action through the stack's owner — so the page can do nothing the workflow's
  own rules and validators, Temporal's own lifecycle or the stack's owner do not allow. A change is read in bounded
  parts, because Temporal refuses a payload past its own limit and a review that cannot be read is
  worse than one read in two presses; each part carries the identity of the change it came from, so
  parts of two changes — the terminals stay writable at the gate — are never shown as one. Its API and the workers' terminal sockets accept only the
  page's token — a random value in `secrets/workbench.token`, made on first use — from the page's
  own origin, and the page only from its own loopback host name, so neither another site in the
  browser nor a rebound DNS name can use them; the terminal sockets take that token in the
  handshake's own header, never in a URL, which browsers print and proxies log. Everything listens
  on `127.0.0.1`. It is plain HTML, CSS and JavaScript — native modules, one per concern — with a
  pinned, vendored xterm.js and no build step; agent text reaches it only as terminal bytes or as text, never as markup.

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
- **D6** **A stop waits in the workflow and nowhere else.** Each stop publishes
  the actions it takes — approve or revise at an approval the run's flow
  schedules, after a review or after research, whose brief it shows;
  guide at a blocker or an exhausted budget; continue after a failed stage; merge,
  `revise:engineer`, `revise:architect` or discard at the final gate, where a
  revise names the role it goes to — and the page and the command line offer
  exactly those, owning only how each is labelled and typed. Its answer arrives
  as an Update carrying one of them, and a validator rejects anything else before
  it reaches history, so no unrecognised answer is ever read as a discard; guide
  and revise carry the operator's words, and a discard must be confirmed. The
  Update's id is `answer:<stop-id>`, so an answer sent twice is applied once. No
  activity ever waits for a human. *Skip approvals* (`auto_proceed`) skips every
  approval a flow schedules and nothing else: a blocker, an exhausted budget, a
  failed stage and the final gate still stop. Ending a run is no stop's answer: a Stop ends
  it from any state (D31). No stop offers `abort`; a run that took one ended
  `ABORTED`, and the workflow keeps its handling so those runs still replay.
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
- **D31** **A run is ended from outside through Temporal's own lifecycle.** *Stop* is
  Temporal's cancellation of the run, valid in every open state — an agent working, a
  stop waiting, a failed stage, the final gate, a host whose worker is gone — and
  Temporal takes it with no worker polling. The workflow hears it wherever the run
  waits and ends it `STOPPED`, which Temporal records as cancelled: it runs no git, so
  the worktree and branch stay as they are, and its cleanup — the run's terminals and
  trace, closed on its target host — waits a minute at most, which a policy may only
  shorten (`stop_cleanup_seconds`), so a host whose worker is gone never holds a Stop.
  A working role's turn hears the Stop at its next heartbeat,
  and the terminals' close ends its agent sooner. A git side effect already running —
  the worktree's creation, a merge, a discard — is never cut off: the run shows
  `STOPPING`, waits for what git did, and a merge or discard that landed ends the run
  as it always does, while anything else ends it stopped. One that its host's worker
  has not taken within the policy's heartbeat interval fails, never having run, so a
  Stop never waits for a worker to come back, and nothing lands after it. *Force terminate* is
  Temporal's termination, for a run a Stop cannot finish: the run closes at once and
  none of its own cleanup runs, but termination cannot stop what the run's host is
  already doing. A working role's turn hears it at its next heartbeat and ends its
  agent; a git side effect already running — the worktree's creation, a merge, a
  discard — does not heartbeat, so it runs to its end and may change the repository
  after the run has closed. Nothing is promised of the worktree and branch, the run's
  terminals stay until its host's worker restarts, and nothing stops a git side effect
  mid-write. The workbench asks for force terminate to be confirmed and says all of
  this. Both are the workbench's and the command line's (`--stop`,
  `--force-terminate`), through `client.py`. What a run that closed this way kept —
  its worktree, its branch and the worktree's environment — stays until the operator
  removes it from the workbench, confirmed, through the run's target host's own git
  as a discard removes them; never while the run is open, never for a run that
  merged or was discarded, and never under a git side effect of the run still running
  on its host — a terminated run's merge goes on — which refuses it there until it
  has landed. A removal runs once, like every git side effect: when git refuses, the
  workbench says why, and only the operator's next removal tries again. One that its
  host's worker has not taken within a minute fails never having run, and the workbench
  names the worker to start.
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
  across its stages, and that the verdict is what routes (D4). It never
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
| D2 two roles and five stages, D13 config versus code and the flows, D22 environments, D30 source organised by concern | [Composition](#composition) |
| D4 verdict routing, D7 sessions, D17 execution seam, D18 model as configuration, D20 observability owners, D21 provider session stores, D23 a task queue per host, D32 the stack's one owner, D24 worktree lifecycle and final gate, D29 the workbench | [Relationships and dependency direction](#relationships-and-dependency-direction) |
| D3, D6, D10, D14, D15, D16, D31 Stop and force terminate, D18b, D19, D25 determinism, D26 repository facts, D27 controller-only git | [Invariants](#invariants) |
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
