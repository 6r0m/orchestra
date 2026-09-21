# The workbench as the one place the operator controls Orchestra from

**Status:** REVIEW REQUIRED
**Scope:** the operator's page (`app/interfaces/workbench`), the client both surfaces share
(`app/application/client.py`), and — only where a gate below allows — the workflow's answers
(`app/orchestration/workflow.py`) and the stack's lifecycle scripts (`workers.sh`, `workers.ps1`)
**Stable documentation owner:** [structure.md](../docs/architecture/structure.md) (D29, the page; D6,
the answers; D24, the final gate) and [docs/using.md](../docs/using.md) (the operator's procedures)

## Contents

- Goal · Authority register · Non-goals
- Verified evidence · Current architecture · Problem
- Decision (KISS gate, alternatives) · Required invariants
- Implementation tasks · Test-first and verification plan
- Documentation plan · Completion criteria · Review record

## Goal

The operator controls Orchestra from the page, with no terminal, for everything they do day to day
with runs and the stack — seeing whether the stack can move a run, answering and closing any run,
and stopping one — delivered in small steps, each proven before the next.

## Authority register

### Operator decisions

- **D1** Control everything over the workbench web UI.
  - Effect: every operator action on runs and on the stack is to be reachable from the page; the
    command line stays for tests and automation.
  - Reason: not stated
  - Date/source: 2026-09-21, operator: *"I want control all things over our web server ui"*
- **D2** Make a run's state fully understandable, including why it is stuck, and show its live
  sessions — provable with mock agents: the run's goal (a feature request, a bug fix) with its title,
  its worktree, and the engineer's and the reviewer's iteration loops, each stage watchable live as
  in a terminal. Much of it is taken to exist already.
  - Effect: scopes gap 1 (Problem) to the run view as a whole, not a stack-health panel alone, and
    requires a mock-agent demonstration of it.
  - Reason: not stated
  - Date/source: 2026-09-21, operator: *"implement fully understandable stucks — where showing active
    live sessions (test with mock)"*
- **D3** The design for gap 2 is decided through the `/architect` review: a global, best-pattern
  decoupling of the page from the workflow's answer set.
  - Effect: gap 2's design (task 4) is not settled by this todo alone.
  - Reason: not stated
  - Date/source: 2026-09-21, operator: *"need proper design decision with /architect something global
    and best pattern decoupling"*

### Operator gates

- **Q1 [OPEN - BLOCKING]:** May the page write anything other than a run start or an answer Update?
  Accepted decision D29 says every page write is one of those two, through `client.py`, "so the page
  can do nothing the workflow's own rules and validators do not allow". Terminating a run in
  Temporal, or starting and stopping processes, would cross it. - gates: tasks 6–8; default while
  open: A2.
- **Q2 [OPEN - BLOCKING]:** Should the page start and stop the stack itself? The page is served by
  the workbench that `make up` starts, so it can never start the stack from nothing; it could restart
  workers, or the workbench could become a service that runs without the stack. - gates: task 8.
- **Q3 [OPEN - BLOCKING]:** Should the final gate offer `abort` — close the run, keep its worktree
  and branch — beside `merge`, `revise` and `discard`? Today a run at its final gate can end only by
  merge or discard, and both need a worker on the run's target host and its repository. - gates:
  task 6.
- **Q4 [OPEN - NON-BLOCKING]:** Should the page stop a run while a stage is working, not only at a
  stop? - default while open: not in this change's first step (A3).
- **Q5 [OPEN - NON-BLOCKING]:** Should the page remove a closed run's leftover worktree? An aborted
  run keeps its worktree and branch today. - default while open: not in this change (A4).

### Working assumptions

- **A1 [ACTIVE]:** "All things" means the operator's actions on runs and on the stack's health. Test
  and acceptance tooling, `make public-check`, and editing `policy.json` or `repos.json` stay outside.
- **A2 [ACTIVE]:** Until Q1 is answered, D29 stands: new controls reach runs only as a start or an
  answer Update, and new reads are Temporal's or a worker's.
- **A3 [ACTIVE]:** Stopping a working run is a later step; Esc in a role's terminal remains how a
  working agent is interrupted.
- **A4 [ACTIVE]:** Leftover worktrees stay visible in *Worktrees* and are removed by hand.

## Non-goals

- Test, acceptance, public-check and release tooling on the page.
- Editing configuration from the page.
- Anything past loopback: the page's token, origin and host checks stay exactly as D29 states them.

## Verified evidence

**Verified facts**

- The page's API has seven routes, all in
  [server.py](../app/interfaces/workbench/server.py): the run list, one run's status, its change in
  parts, a repository's worktrees, the repositories, starting a run, and answering the run's stop.
- The command line's forms ([cli.py](../app/interfaces/cli.py) `parse_args`) — start, answer,
  continue, show, worktrees — each have a page equivalent. Its one extra, `--policy`, picks a policy
  per run; since `policy.load` reads `ORCH_POLICY` for every entry point, the page starts runs with
  the host's policy.
- The page's stop buttons come from its own table, `ANSWERS` in
  [app.js](../app/interfaces/workbench/static/app.js), keyed by stop reason. The workflow publishes
  each stop's actions itself (`ACTIONS` in [workflow.py](../app/orchestration/workflow.py), carried in
  `stop["actions"]`). The two agree today; a new action would reach the page only if both were edited.
- `abort` is offered at the approval, blocker, exhausted and failed stops, never at the final gate
  (`ACTIONS`). An aborted run ends `ABORTED` through `_end`, which runs no git: its worktree and
  branch stay.
- A final-gate `discard` is an activity on the run's target queue. `client.answer` preflights the
  run's queues and refuses when no worker polls one, so the page shows that refusal instead of
  hanging.
- Measured today: an acceptance run from 2026-09-18 waited at its final gate on a queue only an
  acceptance polls, with its repository and worktree deleted. No answer could close it — discard
  was refused by the preflight — and it was closed by terminating it in Temporal, outside the page.
- The refusal tells the operator to run `make orchestration-up`, which no Makefile target is named:
  the target is `make up` (`START_WORKERS` in [client.py](../app/application/client.py); the
  [Makefile](../Makefile)).
- Whether each queue is polled is read by `worker.check` in [worker.py](../app/interfaces/worker.py)
  through `client.preflight`; `make check` prints it. The page shows none of it: a run whose host
  has no worker lists as running, and the operator learns why only when an answer is refused.
- A role turn already honours activity cancellation: the turn loop heartbeats and raises on cancel
  (`terminal.py`, around `activity.is_cancelled`), and `run_role` ends the agent on any failure.
  The workflow has no path that requests it.
- The installed SDK (temporalio 1.33) has both lifecycle operations on `WorkflowHandle`: `cancel()`,
  a request the workflow's own code receives and may clean up after, and `terminate()`, which closes
  the run with no workflow code run. An activity the workflow awaits is cancelled with it, by default
  `ActivityCancellationType.TRY_CANCEL`: the workflow goes on without waiting for the activity to stop.
- Every activity the workflow starts (`_activity`) carries a start-to-close timeout and nothing else,
  so one on a queue no worker polls waits for a poller indefinitely — the trace writes (`_trace`)
  included. The git activities (`create_worktree`, `merge`, `discard`) do not heartbeat, so a
  cancellation cannot reach one that is running.

**Inferences**

- A graceful Stop would hang in its own cleanup on a host with no worker unless every target-host
  activity it starts is bounded by a schedule-to-close timeout (or not awaited); and a Stop arriving
  during a merge would let the workflow end while the merge still lands, unless git side effects in
  flight are shielded from the cancellation.

**Refuted**

- That stopping a working run needs an Update of Orchestra's own. Temporal's workflow cancellation
  reaches the workflow's code whether or not a stop is pending, and reaches a heartbeating role turn
  through the cancellation `terminal.py` already honours; a custom Update would only re-implement it.

**Assumptions / unverified areas**

- A1–A4. Whether Temporal's time-skipping test server reports pollers for `describe_task_queue` is
  unverified; the page tests already replace the preflight for that reason (`tests/interfaces/test_workbench.py`).

## Current architecture and source of truth

D29 owns the page: it holds no state, every read is Temporal's or a worker's, and every write goes
through `client.py`. D6 owns the answers each stop takes, D24 the final gate, D16 manual recovery
(`continue`), D10 that every run is human-triggered. `client.py` is the one client for the page and
the command line; the workflow's validator decides which answers exist.

## Problem

Four capability gaps, with evidence above:

1. The page cannot say whether the stack can move a run: Temporal reachable, which queues a worker
   polls, and which runs are waiting on a host with no worker.
2. The page's answer buttons are a second copy of the workflow's answer set.
3. A run at its final gate whose target host or repository is gone cannot be closed from anywhere
   but Temporal itself.
4. A working run cannot be stopped from the page, and the stack cannot be started or stopped from it.

Gaps 3 and 4 are one gap: there is no way to end a run, from any state, that keeps its work and needs
nothing but Temporal to accept.

## Decision

Deliver in steps; each is reviewed and merged before the next begins.

**Step 1 — within D29, no workflow change (tasks 1–5).** The page shows the stack's health from the
same reading `make check` uses, moved into `client.py` so both surfaces share one owner; flags a run
whose queues no worker polls; renders each stop's buttons from the stop's own `actions`, keeping on
the page only how an action is presented; and the refusal names `make up`.

**Step 2 — Stop, gated by Q1 (tasks 6–7).** Ending a run is Temporal's lifecycle, not an answer: one
**Stop run** for every open run — an agent working, a stop waiting, a failure, the final gate, a host
with no worker — sent as Temporal's workflow cancellation through `client.py`. The workflow receives
it, ends `STOPPED` with its worktree and branch untouched, closes the run's terminals and finishes its
trace through target-host activities bounded so that a host with no worker cannot hold it, and lets a
git side effect already in flight finish rather than cutting it off — if that side effect lands, it
decides how the run ends. **Force terminate** is Temporal's termination, from the command line only:
the break-glass way out when the workflow itself cannot process a Stop, saying what it may leave
behind.

**Step 3 — `abort` retired (task 8).** Once Stop is proven from every state, `abort` leaves the
published actions behind `workflow.patched`, its handling kept for the recorded histories: a stop's
actions are then decisions only — approve, revise, guide, continue, merge, discard.

**Step 4 — gated by Q2 (task 9).** Only if Q2 asks for more than the health view of step 1.

### Premise / KISS gate

- **Owner.** Temporal and the workflow own every run; `client.py` owns how any surface talks to
  them; `worker.check`'s reading already owns "is the stack able to move a run". Step 1 moves that
  reading into `client.py` and adds one read route — no new process, port, protocol or credential.
- **Removed.** The page's own copy of the answer set, and a Makefile target name that does not exist.
- **Added.** One read route and its panel; for Stop, a call to the lifecycle operation Temporal
  already has, and the workflow's handling of it — no Update, answer or protocol of Orchestra's own.
- **Given up.** Terminating a run from the page — termination skips every cleanup, so it stays a
  command-line break glass — and starting the stack from the page (Q2).

### Alternatives considered

- **Stop as an Update, or a final-gate `abort`.** An answer of Orchestra's own that must also work
  when no stop is pending, and a second concept beside the one Temporal provides. Rejected by the
  review of 2026-09-21 in favour of cancellation.
- **Terminate from the page.** One call closes any run, including one whose workflow worker is gone,
  but ends it with no final state, no trace and live terminals left behind. Kept to the command line
  as the break glass.
- **The page drives `make up` and `make down`.** The page cannot start the stack it is served by, and
  `down` would stop the page mid-answer. Q2 decides between restarting workers only and an
  always-on workbench.

## Required invariants

1. D29's write path holds: every page write is a start or an answer Update through `client.py`;
   if Q1 is resolved as the review proposes, a Stop — Temporal's cancellation — is the third, and
   termination is never a page write.
2. The workflow's `ACTIONS` is the only owner of which answers a stop takes; the page decides only
   presentation.
3. No answer is ever read as another: the validator still rejects anything a stop does not offer (D6).
4. The recorded histories in `tests/histories/` still replay: any change to what the workflow
   commands goes behind `workflow.patched`.
5. A health read changes nothing; a run whose host has no worker is shown as such, never as moving.
6. The page's token, origin and loopback-host checks are unchanged.
7. A Stop runs no git: the worktree and branch stay as they are.
8. A Stop is accepted by Temporal without the target host's worker, and nothing the workflow does in
   response waits on that worker without a bound.
9. A git side effect in flight is never cut off by a Stop; one that lands decides how the run ends.
10. Force terminate exists only on the command line and says what it may have left behind.

## Implementation tasks

Step 1:

- [ ] **1.** Red: a page API test for a health route that reports Temporal reachable and each queue
      polled or not, and flags a run on an unpolled queue — 404 today.
- [ ] **2.** Move the queue reading `worker.check` does into `client.py`, one owner for both; `make
      check` prints exactly what it prints today.
- [ ] **3.** The health route and its panel; a run on an unpolled queue says which host's worker is
      missing.
- [x] **4.** (D3; design after the review of 2026-09-21.) A stop publishes its allowed action IDs
      (`stop["actions"]`), and a revise at the final gate is one ID per role — `revise:engineer`,
      `revise:architect` — so the role rule is derived from what the gate published, not written
      beside it. The page and the command line send "this action, with this note": the page renders
      the IDs and owns labels, colours and dialogs; the command line owns its shorthands and how an
      answer is typed; `client.py` turns a role-named ID into the answer the workflow has always
      taken. The workflow keeps the guards D6 and D24 name — a note for guide and revise, a
      confirmed discard — and describes no form.
- [ ] **5.** `START_WORKERS` names `make up`; `tests/acceptance_restart.py`'s docstring too.
- [ ] **5a.** (D2) The run view says what the run is doing now and why it is not moving: the stage
      and role at work and since when, the stop it waits at, its failure, or the host whose worker
      is missing.
- [ ] **5b.** (D2) A mock run to watch: a real run on the live stack whose agents are the suite's fake
      CLIs, working visibly in both terminals through both loops, started by one command and
      removed by it afterwards; no model is called. It answers one stop by pressing its button in a
      headless browser, so the body the page sends is proven, not only the API behind it.

Step 2 (Q1):

- [ ] **6.** Red first: a Stop ends the run `STOPPED` with its worktree and branch untouched from each
      state — an agent working (the agent ended, nothing of it left running), waiting at a stop, a
      failed stage, the final gate, and a target host with no worker (the Stop completes; the
      target-host cleanup is skipped within its bound); a Stop during a merge lets the merge finish
      and the run end `MERGED`. Then `client.stop`, the workflow's cancellation handling, the page's
      Stop button on every open run and the command line's `--stop`; a run whose Stop the workflow
      has not yet processed is shown as such.
- [ ] **7.** `--force-terminate <run>` on the command line only, through Temporal's termination with
      its reason, printing what may be left: the worktree, the branch, a live terminal until its
      worker next restarts. Verify, rather than assume, that a terminated run's working role turn
      ends its agent when its heartbeat finds the run gone.

Step 3: **8.** Retire `abort` from the published actions behind `workflow.patched`, keeping its
handling for the recorded histories; D6, D24 and `docs/using.md` updated.

Step 4 (Q2): **9.** Designed only if Q2 asks for more than step 1's health view.

## Test-first and verification plan

### Red evidence

| case | kind | wrong today |
|---|---|---|
| the page reports Temporal and every queue's pollers | permanent guard | no such route (404) |
| a run on a queue no worker polls is flagged on the page | permanent guard | listed as running |
| the refusal names a real make target | permanent guard | names `make orchestration-up` |
| buttons come from the stop's own actions; an unknown action still renders | reviewer-checked (plain JS, no build step), and a headless-browser render | a second table keyed by stop |
| (step 2) a Stop from each open state ends `STOPPED` and runs no git | permanent guard | no way to do it but a stop's `abort` |
| (step 2) a Stop with the target host's worker gone completes | permanent guard | its cleanup would wait forever |
| (step 2) a Stop during a merge lets it land and the run end `MERGED` | permanent guard | the merge would land after the run said it stopped |
| (step 2) force terminate closes any run and says what is left | acceptance (live stack) | only by hand in Temporal |

### Green evidence

The cases above; `bash run-tests.sh` (WSL) and `run-tests.ps1` (Windows host suite), one after the
other; the recorded histories replaying; the live acceptance with a Stop and a force terminate
for steps 2 and 3; the page rendered
headless against the live stack, every asset and API call answering 200; `make public-check`.

## Documentation plan

- **Authoritative stable owner:** `docs/architecture/structure.md` — D29 for what the page shows and
  writes, a decision beside D16 for Stop and force terminate, and D6 and D24 when `abort` retires.
- **Router / TOC update:** none; `docs/using.md` gains the page's health panel in *The page* and
  loses nothing else; the mock run's command goes in `tools/README.md`.
- **Duplication avoided:** the answer set lives in `ACTIONS` only; the docs name answers as D6 does.
- Stable docs, code, comments, tests and configuration never reference this todo.

## Completion criteria

Step 1 is complete when tasks 1–5 are green on both hosts, `make check` prints what it did, the page
shows the stack's health and flags an unpolled run against the live stack, and D29 and
`docs/using.md` describe it. Step 2 is complete when every Stop case above is green on both hosts,
the live acceptance stops one working run and force-terminates another, and D29 and the new decision
say what each does. Step 3 when no stop publishes `abort` and the recorded histories still replay.

## Review record

### 2026-09-21 — opened

- **Trigger:** the operator, *"I want control all things over our web server ui"*.
- **Findings:** the page covers every command-line form; four gaps remain (health, the duplicated
  answer set, closing a final-gate run whose host or repository is gone, stopping a working run and
  the stack); D29 bounds the page's writes.
- **Authority:** D1 recorded; Q1–Q5 opened; A1–A4 recorded.

### 2026-09-21 — the operator's first answers

- **Trigger:** the operator's reply to the four gaps and three gates.
- **Authority:** D2 (gap 1) and D3 (gap 2, through `/architect`) added. Q1–Q3 were not understood as
  written and stay open, to be restated in plain terms; gaps 3 and 4 were questioned and are to be
  explained, not yet decided.

### 2026-09-21 — architect review of task 4 (D3): PATCH

- **Findings:** the answer set and each answer's requirements live in three places — the workflow
  (`ACTIONS` and the validator), the page (`ANSWERS`), the command line (`parse_answer`) — and the
  first task 4 would have kept the requirements in the page. Only the validator reads a stop's
  published `actions`; the page and the command line use their own copies.
- **Recommended design:** the owner publishes each stop's answers with their requirements, and the
  clients render them — the pattern where the server that enforces the rules also tells clients what
  is possible now. It keeps one owner, and a workbench running older code than the worker still shows
  what the worker's workflow actually accepts. Task 4 now carries it.
- **Not recommended:** a spec module the page server and the command line import — one owner too, but
  a workbench on other code than the worker would offer answers the workflow refuses.

### 2026-09-21 — review of the design: BLOCKER on the answer schema

- **Findings accepted:** the published answer schema bundled three concerns — a role is the
  controller's routing, a confirmation dialog is presentation, a note is input — and would have had
  the controller describe forms; version skew on one machine does not justify it. The stop's
  published action IDs already are the contract: clients send an action and a note.
- **Finding refuted:** that the controller should never care about a confirmation. D24 accepts
  "a confirmed discard" as the workflow's guard, so a client that skips its dialog is refused; the
  guard stays, unpublished, and only the dialog is the page's.
- **Proposed, awaiting the operator:** one lifecycle — **Stop** ends a run and keeps its worktree
  and branch, replaces Abort, is valid in every open state (working, waiting, failed, the final
  gate), and depends on no worker; **Discard** and **Merge** stay as they are; Esc interrupts only an
  agent's turn; a break-glass `force-terminate` belongs to the command line, never the page. For
  the gates the review proposes: Q1 — the page never goes around the workflow, the command line gets
  `force-terminate`; Q2 — (a) only, the page shows what is down and the command that brings it up;
  Q3 — no separate Close, Stop covers it. None of these binds until the operator confirms it.
- **Authority:** task 4 rewritten; Q1–Q3 unchanged, with the review's proposals recorded here.

### 2026-09-21 — task 4 implemented

- **Change:** the final gate publishes `revise:engineer` and `revise:architect`, and the validator
  reads the role rule from what a stop published; `client.py` turns a role-named action into the
  action and role the workflow's answer carries; the page renders `stop.actions` with its own
  labels, colours and dialogs and sends only words the operator wrote; the command line types any
  published action, with its shorthands, and lists a stop's answers from the stop. The page's and
  the command line's own answer tables are gone.
- **Red first:** eight new cases failed for the reason they exist — the gate published `revise`
  alone, the shared client's `revise:architect` was refused, a revise with a role was accepted at the
  plan approval, and the command line could not type an action it had no table entry for.
- **Found in the diff review and fixed:** the page sent an action's own name as its words when the
  note was empty, which would have passed the workflow's "needs your words" check; it now sends only
  what was written, and a page-shaped answer with no words is refused — a new page API case.
- **Verification:** the answer-related modules on WSL (133 tests); the full WSL suite (290), the
  Windows host suite (221) and the live acceptance, all passing; the recorded histories replay, so
  no `workflow.patched` was needed — the change is to what a stop publishes, not to any command.

### 2026-09-21 — review of the lifecycle design: PATCH (task 4 PASS)

- **Accepted:** Stop is Temporal's workflow cancellation and force terminate its termination —
  lifecycle beside Start, not an answer beside Approve; one Stop for every open run replaces the
  final-gate `abort` and the Stop Update, so Q3 and Q4 collapse into step 2; `abort` retires from the
  published actions afterwards; the review's test-gap note — the page's own request body — is covered
  by pressing a button in the mock run (task 5b), not by a JavaScript test harness.
- **Corrected against the code:** the review's "activities already fit this model" holds for the role
  turn, which heartbeats, and not for the git activities, which do not; and a graceful Stop's own
  cleanup runs on the target host with no bound. Invariants 8 and 9 and task 6 carry both.
- **Proposed, awaiting the operator:** Q1 — D29's write path gains the Stop (cancellation), and
  termination stays off the page; Q2 — (a); Q3 and Q4 — one Stop, step 2. None binds until confirmed.
- **Authority:** steps 2–4, tasks 6–9, invariants 1 and 7–10 rewritten; Q1–Q5 unchanged.

