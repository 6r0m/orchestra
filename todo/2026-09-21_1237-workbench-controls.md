# The Workbench: Orchestra's operator console

**Status:** REVIEW REQUIRED
**Scope:** the Workbench (`app/interfaces/workbench`); the shared application control API — the run
client (`app/application/client.py`) and one stack lifecycle owner beside it; the workflow's handling
of a Stop (`app/orchestration/workflow.py`); the stack's process scripts (`workers.sh`,
`workers.ps1`) and the `Makefile`
**Stable documentation owner:** [structure.md](../docs/architecture/structure.md) — structure D29
(the Workbench), structure D6 and D24 (a stop's decisions, the final gate), a new decision for Stop
and force terminate — and [docs/using.md](../docs/using.md) (operating Orchestra)

## Contents

- Goal · Authority register · Non-goals
- Verified evidence · Current architecture · Problem
- Decision (KISS gate, alternatives) · Required invariants
- Implementation tasks, by step · Test-first and verification plan
- Documentation plan · Completion criteria · Review record

## Goal

The Workbench is Orchestra's operator console. From it alone the operator starts, watches, steers,
stops and finishes every run, and starts, stops and restarts the stack that runs them — seeing at any
moment what each run is doing and, when it is not moving, why.

```
Operator -> Workbench -> shared application control API -> Temporal / workers / Git
```

## Authority register

`D<n>` here are this todo's own. The project's architecture decisions are cited as *structure D<n>*,
from [structure.md](../docs/architecture/structure.md).

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
- **D4** The Workbench is Orchestra's primary operator control plane. There is one operator, on
  loopback, inside the Workbench's security boundary, so no operation is kept out of the UI for being
  lifecycle, Temporal, stack or administrative: a normal operation needed to operate Orchestra belongs
  in the Workbench. The command line stays for tests, automation and emergency fallback.
  - Effect: supersedes structure D29's limit that every Workbench write is a start or an answer
    Update; the architecture is Operator → Workbench → shared application control API → Temporal,
    workers, Git.
  - Reason: *"ofcourse ui could cancel or etc since int only operator flow"*
  - Date/source: 2026-09-21, operator
- **D5** The Workbench controls every run's lifecycle: start; approve, revise, guide, continue, merge,
  discard; **Stop** from any open state, through Temporal's workflow cancellation; **force terminate**,
  through Temporal's termination, when a graceful Stop cannot finish — behind an explicit danger
  confirmation that says what may be left, and mirrored on the command line as the break glass;
  watching and typing into the live agent terminals; inspecting a run, its worktree, change, history
  and status. No lifecycle operation is command-line-only.
  - Effect: closes Q1 and Q4; Stop and force terminate are Workbench operations.
  - Reason: not stated
  - Date/source: 2026-09-21, operator
- **D6** The Workbench controls the Orchestra stack: the health of Temporal, the workers and every
  required component; starting, stopping and restarting the managed stack and each component; exactly
  what is down and why a run cannot progress. Where the Workbench can perform an operation, telling
  the operator to run `make up` is not the answer. The Workbench's own process is outside the stack it
  controls and stays up while the workers and Temporal are stopped — stopping Orchestra never stops the
  console. The Workbench is the bootstrap boundary: it does not manage its own process, a simple login
  or autostart mechanism makes it available, and no orchestration framework is built for that.
  - Effect: closes Q2.
  - Reason: *"q2 ui should contorl all such it's operator"*
  - Date/source: 2026-09-21, operator
- **D7** One global **Stop run** for every open run — an agent working, a wait for approval or
  guidance, a failed stage, the final gate, a target worker unavailable. Stop keeps the worktree and
  branch and mutates no git. `abort` is legacy duplication and retires once Stop is proven, with
  Temporal history compatibility kept.
  - Effect: closes Q3 and Q4; replaces the final-gate `abort` and any Stop Update.
  - Reason: not stated
  - Date/source: 2026-09-21, operator
- **D8** A Stop's correctness never depends on cleanup. Cleanup after a Stop is best-effort and
  bounded, and a dead target worker never makes a Stop hang. A git side effect already in flight is a
  critical section: the Stop shows as requested, the run is not reported stopped while a merge or a
  discard can still land, and the real outcome decides how the run ends. No generic shielding or
  cancellation subsystem.
  - Effect: constrains task 6.
  - Reason: not stated
  - Date/source: 2026-09-21, operator
- **D9** One narrow application-level owner of the stack's lifecycle — status, start, stop, restart —
  called alike by the Workbench, the Make targets and the command line, reusing the existing scripts
  and process mechanisms underneath; that logic is never duplicated in JavaScript or in server
  handlers.
  - Effect: constrains tasks 1, 8 and 10.
  - Reason: not stated
  - Date/source: 2026-09-21, operator
- **D10** For every run the Workbench shows at once: its goal and title; repository, worktree and
  host; current stage and role, and how long it has been there; the live engineer and reviewer
  terminals; the stop or question it waits at; its failure; the missing or down component when it is
  blocked; and the operator actions available right now — derived from the workflow's state and the
  stack's health, with no separate stuck detector.
  - Effect: extends D2; constrains task 2.
  - Reason: not stated
  - Date/source: 2026-09-21, operator
- **D11** Task 4's answer design stands: the workflow publishes action IDs and validates their
  meaning; the UI owns labels, layout and confirmation dialogs; the command line owns typing
  shortcuts; no server-driven form or schema protocol.
  - Effect: task 4 is not reopened.
  - Reason: not stated
  - Date/source: 2026-09-21, operator
- **D12** Acceptance demonstrates the product, with fake agents over the real Temporal workflow, the
  real Workbench and the real live-terminal path. From the Workbench: start a run; watch the engineer
  and the reviewer iterate; answer a stop; Stop a working run; Stop a waiting or final run; force
  terminate a deliberately stuck run; see a worker go down and why a run cannot progress; restart that
  worker or the stack; carry on without opening a terminal.
  - Effect: task 3's demonstration grows to this journey by the end of step 3.
  - Reason: not stated
  - Date/source: 2026-09-21, operator
- **D13** The operator starts WSL; Orchestra neither starts WSL nor starts at Windows logon. The
  lifetime boundary is: the operator starts WSL → WSL's systemd starts the Workbench → the Workbench
  controls Orchestra. One ordinary enabled systemd service inside WSL runs the Workbench: it starts
  whenever this WSL distro starts, restarts on failure, and dies when WSL shuts down. No Windows Task
  Scheduler, no Windows logon hooks, no arbitrary startup delays, no other supervisor, no Workbench
  logic that starts WSL. Startup is dependency-based and does not wait for an external network; a
  Windows-interop readiness problem, if one is measured, is gated on that dependency with a bounded
  check. `make up` and `make down` control Orchestra's components only; `make workbench-start`,
  `workbench-stop` and `workbench-status` may wrap `systemctl` for maintenance, outside the normal
  operator flow.
  - Effect: settles D6's start mechanism; closes Q6; A5 not adopted; constrains task 9.
  - Reason: *"you own Windows/WSL lifetime; systemd owns Workbench lifetime; Workbench owns Orchestra
    operation"*
  - Date/source: 2026-09-21, operator

### Operator gates

- **Q1 [CLOSED by D4, D5]:** May the page write anything other than a run start or an answer Update?
- **Q2 [CLOSED by D6]:** Should the page start and stop the stack itself?
- **Q3 [CLOSED by D7]:** Should the final gate offer `abort` — close the run, keep its worktree and
  branch — beside `merge`, `revise` and `discard`?
- **Q4 [CLOSED by D5, D7]:** Should the page stop a run while a stage is working, not only at a stop?
- **Q5 [CLOSED by D4]:** Should the page remove a closed run's leftover worktree? — it is a normal
  operation: task 12.
- **Q6 [CLOSED by D13]:** Which login mechanism makes the Workbench available?

### Working assumptions

- **A1 [RESOLVED by D4]:** "All things" means the operator's actions on runs and on the stack's health.
  Test and acceptance tooling, `make public-check`, and editing `policy.json` or `repos.json` stay outside.
- **A2 [RESOLVED by D4]:** Until Q1 is answered, D29 stands: new controls reach runs only as a start or
  an answer Update, and new reads are Temporal's or a worker's.
- **A3 [RESOLVED by D7]:** Stopping a working run is a later step; Esc in a role's terminal remains how a
  working agent is interrupted.
- **A4 [RESOLVED by D4]:** Leftover worktrees stay visible in *Worktrees* and are removed by hand.
- **A5 [RESOLVED by D13 — not adopted]:** The Workbench starts at Windows logon from a hidden Task
  Scheduler entry that runs it in WSL — where the stack's controls already run — installed and removed
  by one Make target. A WSL systemd user unit was not chosen: nothing starts WSL at logon to run it.
- **A6 [ACTIVE]:** The stack owner sits in `app/application` beside `client.py`; the process mechanics
  stay in `workers.sh` and `workers.ps1`, split per component; the Make targets call the command line,
  which calls the owner.
- **A7 [ACTIVE]:** D13's service is a *user* unit of the WSL user's systemd manager
  (`WantedBy=default.target`), not a system unit with `User=`. Agents are contained through
  `systemd-run --user` (`launch.py`), which needs that user's manager and bus, and a system unit's
  processes are outside the user's session. The user manager starts when the distro boots because
  lingering is enabled for this user (measured: `loginctl show-user` reports `Linger=yes`, PID 1 is
  systemd, `systemctl --user is-system-running` answers `running`). The repository ships the unit as a
  template; installing renders it with this checkout's path and environment (`envpath.py`), neither of
  which is committed.

## Non-goals

- A supervisor or orchestration framework for the Workbench's own process (D6); a Windows logon task,
  logon hook or startup delay (D13).
- A stuck detector, a server-driven form protocol, a generic cancellation or shielding subsystem
  (D8, D10, D11).
- A JavaScript test harness: the page's own requests are proven by the demonstration pressing its
  buttons (D12).
- Anything past loopback: the Workbench's token, origin and host checks stay as they are.
- Test, public-check and release tooling in the Workbench.

## Verified evidence

**Verified facts**

- The Workbench's API has seven routes, all in [server.py](../app/interfaces/workbench/server.py): the
  run list, one run's status, its change in parts, a repository's worktrees, the repositories,
  starting a run, and answering its stop. Every command-line form ([cli.py](../app/interfaces/cli.py))
  has a Workbench equivalent.
- A stop publishes its action IDs and the page and the command line render them (task 4, D11).
- `abort` is offered at the approval, blocker, exhausted and failed stops, never at the final gate; an
  aborted run ends `ABORTED` with no git run (`_end`), keeping its worktree and branch.
- A final-gate discard needs a worker on the run's target host; `client.answer` refuses when no worker
  polls the run's queues. On 2026-09-21 a run at its final gate, on a queue only an acceptance polls and
  with its repository deleted, could be closed only by terminating it by hand in Temporal.
- `workers.sh up` starts Temporal (`docker compose`), the WSL worker, the Windows worker
  (`workers.ps1`, through WMI, hidden) and the Workbench, and `down` stops the Workbench first, then the
  workers, then Temporal: stopping the stack stops the console. Each component already has start and
  stop code of its own in the script.
- The refusal when no worker polls names `make orchestration-up` (`START_WORKERS` in
  [client.py](../app/application/client.py)); the [Makefile](../Makefile) target is `make up`.
- Whether each queue is polled is read by `worker.check` ([worker.py](../app/interfaces/worker.py))
  through `client.preflight`, and printed by `make check`; the Workbench shows none of it.
- The installed SDK (temporalio 1.33) has `WorkflowHandle.cancel()` — a request the workflow's own code
  receives and may clean up after — and `WorkflowHandle.terminate()`, which closes the run with no
  workflow code run. An activity the workflow awaits is cancelled with it, by default `TRY_CANCEL`: the
  workflow goes on without waiting for the activity to stop.
- Every activity the workflow starts (`_activity`) carries only a start-to-close timeout, so one on a
  queue no worker polls waits indefinitely — the trace writes (`_trace`) included. The git activities
  (`create_worktree`, `merge`, `discard`) do not heartbeat, so a cancellation cannot reach one running.
- A role turn honours activity cancellation — the turn loop heartbeats and raises on cancel
  (`terminal.py`) — and `run_role` ends the agent on any failure.

**Inferences**

- A graceful Stop's cleanup must be bounded, and a git side effect in flight must be awaited for its
  real outcome, or D8 does not hold (see the two facts above).

**Refuted**

- That stopping a working run needs an Update of Orchestra's own: Temporal's cancellation reaches the
  workflow whether or not a stop is pending, and a heartbeating role turn through the cancellation
  `terminal.py` already honours.

**Assumptions / unverified areas**

- A5, A6. Whether Temporal's time-skipping test server reports pollers (the page tests replace the
  preflight for that reason). Whether a terminated run's working role turn ends its agent at its next
  heartbeat — verified in task 7, not assumed.

## Current architecture and source of truth

Structure D29 owns the Workbench, and its write-path limit is superseded by D4; D6, D24, D16 and D10
of the structure own a stop's decisions, the final gate, manual recovery and human-triggered runs.
`client.py` is the one client of runs for every surface. `workers.sh` and `workers.ps1` own how each
host's processes start and stop; the `Makefile` fronts them.

## Problem

1. The Workbench cannot say why a run is not moving: the stack's health, a run's stage and how long it
   has been there, the component it waits on.
2. A run cannot be stopped from any state: not while an agent works, not at the final gate when its
   host or repository is gone.
3. Force terminate exists only by hand in Temporal.
4. The stack is controlled only from a terminal, and stopping it stops the Workbench.
5. `abort` duplicates what Stop will do.
6. A stopped run's worktree and branch are removed only by hand.

## Decision

The shared application control API is `client.py` for runs — start, answer, stop, force terminate,
and the run's view — and one stack owner beside it for components — status, start, stop, restart. The
Workbench's server and the command line are thin callers of both; the Make targets call the command
line. Temporal's own lifecycle carries a run's end: Stop is `cancel()`, force terminate is
`terminate()`. The workflow answers a cancellation by ending `STOPPED` after a bounded, best-effort
cleanup — or, when a git side effect is in flight, by awaiting its outcome and ending as it decides.
The Workbench leaves the stack it controls and runs as a systemd user service in WSL, so it is there
whenever WSL is (D13).

Steps, each reviewed and merged before the next, each extending the demonstration (task 3):

1. **See** (tasks 1–5): the stack's health and each run's view in the Workbench, and the demonstration
   run. Reads only; no workflow command changes.
2. **Stop and force terminate** (tasks 6–7).
3. **Stack control** (tasks 8–10): per-component control through the stack owner, and the Workbench
   outside the stack as its own systemd user service.
4. **`abort` retires** (task 11).
5. **Leftovers** (task 12): a stopped run's worktree and branch removed from the Workbench.

### Premise / KISS gate

- **Owners.** Temporal owns a run's lifecycle; the workflow owns what a Stop means for a run;
  `client.py` owns every run operation for every surface; the stack owner owns each component's
  lifecycle; `workers.sh` and `workers.ps1` own the process mechanics on each host.
- **Removed.** `abort`, once Stop is proven; the Workbench's place inside the stack it controls; runs
  closed by hand in Temporal; the operator's need for a terminal.
- **Added.** Two calls to Temporal's lifecycle and the workflow's handling of one; one stack owner over
  the existing scripts; one run view assembled from facts that exist; one systemd user unit; a
  demonstration command.
- **Given up.** The Workbench restarting itself — it is the bootstrap boundary — and a Stop that cuts a
  git side effect off mid-write.

### Alternatives considered

- **Stop as an Update, or a final-gate `abort`.** An answer of Orchestra's own that must also work when
  no stop is pending, beside the primitive Temporal provides.
- **Stack control in the Workbench's handlers.** A second copy of what `make` does; D9 gives the Make
  targets, the command line and the Workbench one owner.
- **A supervisor for the whole stack, the Workbench included.** A framework to solve the bootstrap,
  which D6 settles by keeping the Workbench outside.
- **A Windows logon task.** Not needed: the operator starts WSL, and systemd inside it owns the
  Workbench's lifetime (D13).
- **A system unit with `User=`.** Loses the user's systemd manager that agent containment needs (A7).

## Required invariants

1. Every Workbench operation goes through the shared application control API — `client.py` and the
   stack owner. No run or stack logic lives in the Workbench's handlers or JavaScript.
2. The workflow's `ACTIONS` own which decisions a stop takes; clients own presentation (D11).
3. The validator still rejects anything a stop does not publish (structure D6).
4. The recorded histories in `tests/histories/` still replay; a change to what the workflow commands
   goes behind `workflow.patched`.
5. A Stop runs no git: the worktree and branch stay as they are.
6. Temporal accepts a Stop without the target host's worker, and nothing done in response waits on that
   worker without a bound.
7. A git side effect in flight is never cut off by a Stop; the run is not reported stopped while it can
   land, and its outcome decides how the run ends.
8. Force terminate asks for an explicit danger confirmation in the Workbench and says what may be left.
9. Stopping the stack never stops the Workbench, and the Workbench never manages its own process.
10. A health read changes nothing; a run blocked by a down component is shown as blocked by it.
11. The Workbench's token, origin and loopback-host checks are unchanged.

## Implementation tasks

Step 1 — see:

- [x] **1.** Red first: a Workbench API test for the stack's health — Temporal reachable, each queue
      polled, each managed component up — which is 404 today. Then the stack owner's `status`,
      carrying the reading `worker.check` does, so `make check` prints what it prints today, and the
      Workbench's health panel.
- [x] **2.** Red first: a Workbench API test that a run parked at a stop, one working, and one whose
      host's worker is down each report what D10 lists. Then the run's view in `client.py` — goal,
      repository, worktree, host, state (running, waiting, failed, stopping, closed), stage, role,
      since, the stop, the failure, the component it is blocked by, the actions available now —
      assembled from the status query, Temporal's description and the stack's health. The workflow
      records when its current stage began (`workflow.now()`, state only). The Workbench shows it at
      the head of every run. The *stopping* state comes with Stop, in task 6.
- [x] **3.** `make demo`: a real run on the live stack with the suite's fake CLIs, through both loops
      in live terminals, answering one stop by pressing its button in a headless browser — so the body
      the page sends is proven — and removing everything it made. It grows with each step to D12's
      journey. Isolated by its own policy, never by a mode in production code: a unique target queue,
      polled only by a demo activity worker that carries the fake CLIs — it registers no workflow, so
      the normal WSL worker runs the demo's workflow and no real run can reach a fake agent, nor the
      demo run a real one — a temporary repository, and a demo Workbench on a spare port. The fake
      turns take a few watchable seconds; every delay lives in the demo's own fakes.
- [x] **4.** (D3; design after the review of 2026-09-21.) A stop publishes its allowed action IDs
      (`stop["actions"]`), and a revise at the final gate is one ID per role — `revise:engineer`,
      `revise:architect` — so the role rule is derived from what the gate published, not written
      beside it. The page and the command line send "this action, with this note": the page renders
      the IDs and owns labels, colours and dialogs; the command line owns its shorthands and how an
      answer is typed; `client.py` turns a role-named ID into the answer the workflow has always
      taken. The workflow keeps the guards D6 and D24 name — a note for guide and revise, a
      confirmed discard — and describes no form.
- [x] **5.** The refusal when a worker is missing names the host whose worker it is, and `make up`.
      The Workbench's own Start for a missing worker is task 10.

Step 2 — Stop and force terminate:

- [x] **6.** Red first: a Stop ends the run stopped, with its worktree and branch untouched, from each
      state — an agent working (its agent ended, nothing of it left running), a stop waiting, a failed
      stage, the final gate, and a target host with no worker (the Stop completes; the host's cleanup
      is skipped within its bound). A Stop during a merge shows as requested, lets the merge land, and
      the run ends merged. Then `client.stop` (Temporal's cancellation), the workflow's handling of it,
      **Stop run** on every open run in the Workbench, and `--stop` on the command line.
- [x] **7.** Force terminate: `client` through Temporal's termination with its reason; in the
      Workbench behind a danger confirmation naming what may be left — the worktree, the branch, a live
      terminal until its worker next restarts; `--force-terminate` on the command line. Verify, rather
      than assume, that a terminated run's working role turn ends its agent at its next heartbeat.

Step 3 — stack control:

- [ ] **8.** `workers.sh` and `workers.ps1` split per component — Temporal, the WSL worker, the Windows
      worker — each with start, stop and status; the stack owner orders them (Temporal before the
      workers on start, after them on stop) and restarts one. `make up`, `make down` and `make check`
      call the command line, which calls the owner.
- [ ] **9.** The Workbench leaves the stack as `orchestra-workbench.service`, a systemd user unit
      (D13, A7): `Restart=on-failure`, `RestartSec=2`, `WantedBy=default.target`, and no network
      ordering — a user manager has no network target, and a loopback Workbench waits for none; started
      with this checkout's own environment, whose absolute paths the one Make target renders when it
      installs and enables the unit; `workbench-start|stop|status` wrap `systemctl --user` for
      maintenance. `make up` and `make down` no longer touch the Workbench, and its pid file goes —
      systemd owns its process. Live acceptance, once: after `wsl --shutdown` and the operator starting
      WSL, the service is active, `:8390` answers, and the Windows worker's status and control path
      runs from the service's own context — interop measured there, not assumed from a shell; only a
      concrete readiness dependency it exposes is fixed, and never with a delay.
- [ ] **10.** The Workbench controls the stack: start, stop and restart it all or one component; what is
      down, and the start that brings it back, shown in the health panel and on every run it blocks.

Step 4: **11.** `abort` leaves the published actions behind `workflow.patched`, its handling kept for
the recorded histories; structure D6 and D24 and `docs/using.md` updated. The trace's
`final_verify_pass` records 0 for an aborted run and nothing for a stopped one — a run stopped at its
final gate keeps the 1 it scored there — so what a stopped run scores is decided here, with the
trace contract.

Step 5: **12.** A stopped run's worktree and branch removed from the Workbench's *Worktrees*, through
the target host's own git as a discard removes them.

## Test-first and verification plan

### Red evidence

| case | kind | wrong today |
|---|---|---|
| the Workbench reports Temporal, each queue and each component | permanent guard | no such route |
| a run's view: stage, role, since, stop, failure, blocking component, actions | permanent guard | only raw status |
| a Stop from each open state ends it stopped and runs no git | permanent guard | no Stop; `abort` only at some stops |
| a Stop with the target host's worker gone completes | permanent guard | its cleanup would wait forever |
| a Stop during a merge lets it land and the run end merged | permanent guard | a merge could land after "stopped" |
| force terminate closes any run and says what is left | acceptance (demonstration) | only by hand in Temporal |
| stopping the stack leaves the Workbench serving | acceptance (demonstration) | `down` stops it first |
| the Workbench comes back when WSL restarts, and after it is killed | acceptance (live, once) | started by `make up` only |
| the Windows worker's control path runs from the Workbench service's context | acceptance (live, once) | never run outside a shell |
| a component stopped and started again from the Workbench | acceptance (demonstration) | only `make` |
| the page's own request body when a button is pressed | acceptance (demonstration) | proven by inspection only |

### Green evidence

The cases above; `bash run-tests.sh` (WSL) and `run-tests.ps1` (Windows host suite), one after the
other; the recorded histories replaying; `make demo` passing its journey as it stands at each step,
D12's in full by the end of step 3; `make public-check`. `make demo` proves the workflow code the live
WSL worker loaded, and `make up` leaves a running worker as it is: a step that changes the workflow
restarts the workers onto it (`make down`, then `make up`) before the demo counts for that step.

## Documentation plan

- **Authoritative stable owner:** `docs/architecture/structure.md`. Structure D29 is rewritten for the
  Workbench as the console as each step lands — a stable document states what is true, so it changes
  with the code, not ahead of it. A new decision beside structure D16 carries Stop and force
  terminate (step 2); structure D6 and D24 change when `abort` retires (step 4).
- **Router / TOC update:** `docs/using.md` leads with the Workbench — its logon start, its health
  panel, Stop and force terminate — with the command line as the fallback; `tools/README.md` gains
  `make demo`.
- **Duplication avoided:** a stop's decisions live in `ACTIONS` only; the stack's components and their
  order live in the stack owner only.
- Stable docs, code, comments, tests and configuration never reference this todo.

## Completion criteria

Each step is complete when its tasks are green on both hosts, `make demo` passes its journey as it
stands, and the stable documents say what the step made true. The change is complete when D12's
journey passes from the Workbench on the live stack with fake agents and no terminal opened.

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

### 2026-09-21 — the operator's decisions: the Workbench is the console

- **Trigger:** the operator, on the gates: *"ofcourse ui could cancel or etc since int only operator
  flow"*, *"q2 ui should contorl all such it's operator"*, and instructions to rewrite the plan around
  the Workbench as the primary operator control plane.
- **Root cause of the loop:** the plan treated the Workbench as a restricted client of a
  command-line system, so every capability became a question of whether the UI was allowed it.
- **Authority:** D4–D12 added. Q1–Q5 closed by them; Q6 added (the logon mechanism), with A5 as its
  default. A1–A4 resolved; A5 and A6 added. Structure D29's write-path limit is superseded by D4; the
  stable document changes as each step lands, because it states what is true now.
- **Plan:** rewritten around the end state. Steps: see; Stop and force terminate; stack control with
  the Workbench outside the stack; `abort` retires; leftovers. Task 4 stands (D11).

### 2026-09-21 — the Workbench's lifetime: systemd inside WSL

- **Trigger:** the operator, *"drop Windows Task Scheduler entirely"* — the operator starts WSL, so
  the lifetime boundary is the WSL distro.
- **Checked against the machine:** systemd is PID 1 in WSL with lingering enabled for the user, so a
  user service starts with the distro; the review's sample unit was a system unit with `User=` and an
  `ExecStart` in the checkout's `.venv`. Agent containment needs the user's systemd manager
  (`systemd-run --user`), which a system unit's processes are outside of, and this checkout's
  environment lives outside it (`envpath.py`) — so the unit is a user unit, rendered at install
  (A7).
- **Authority:** D13 added; Q6 closed; A5 not adopted; A7 added; task 9 rewritten.

### 2026-09-21 — step 1, tasks 1, 2 and 5 implemented

- **Change:** `app/application/stack.py` owns the stack's health — Temporal answering, each queue
  and whether a worker polls it, each host's worker up or down — and `make check` prints it through
  that owner; the Workbench serves it at `/api/health` and shows it in its header, and says
  "down" rather than failing when Temporal is out of reach. `client.view` is the one reading of what
  a run is now: closed, failed, waiting or running; the stage and role at work or the stop it waits
  at, since when; its failure; the hosts whose worker it needs and is missing; the actions it takes.
  The run list and each run carry it, and the page shows it on every run. The workflow records what
  it is doing and since when (`state["current"]`, and each stop's `since`), from `workflow.now()`,
  with no new command. The refusal names the host whose worker is missing and `make up`; which host
  runs the workflows is one constant the worker and the client share.
- **Scope kept:** a host's worker reads as up while it polls its queues. The status of each managed
  process — Temporal's containers, each worker's process — joins the stack owner with its start and
  stop in step 3, where it is needed; task 5's "the Workbench offers to start it" is task 10.
- **Red first:** the health route answered 404, no run carried a view, the list had no state, and the
  refusal named `make orchestration-up`.
- **Found while verifying:** a test comparing two runs' final states skipped the fields that differ
  between runs; `current` carries a time, so it joined them.

### 2026-09-21 — review of step 1 and of the demo's design: PATCH

- **Accepted:** the demo is isolated by its own policy and queue — the acceptance's way of starting
  its worker, the normal entry point, would also register on the global workflow queue, so the demo
  runs only an activity worker on its unique queue; task 5 and task 2 no longer claim what task 10
  and task 6 own; the user unit drops `After=network.target`; task 9 gains one live acceptance of
  WSL-to-Windows interop from the service's own context.
- **Authority:** tasks 2, 3, 5 and 9 corrected; no decision changed.

### 2026-09-21 — step 1, task 3: `make demo`

- **Change:** `tools/demo.py` runs a demo stack beside the live one — an activity worker of its own on
  a unique target queue, carrying fake CLIs and registering no workflow; a Workbench of its own on a
  spare port; a throwaway repository named in a descriptor of its own — starts a run from that
  Workbench, and answers the approval and the merge by pressing the page's own buttons in headless
  Edge (`tools/demo_press.py`, run on Windows by `tools/demo_press.ps1`, because WSL cannot reach
  Windows' loopback here — measured). It fails at once, with the run's own lines, when the run
  fails or ends instead of reaching what it waits for, and removes everything it made.
- **Found while running it:** the demo's own worktree folder had to exist, and a repository given only
  by path infers its worktree folder from a layout a throwaway repository lacks — so the demo names
  its repository in a descriptor with an explicit worktree root, as the acceptance does.
- **Verification:** `make demo` passed on the live stack — the architect's PATCH then PASS, Approve and
  Merge pressed in headless Edge with the page reporting each answer, the run merged and its change on
  the base branch — with no window opened and focus never moved, as sampled throughout; afterwards
  no demo process, temporary folder, run folder, trust record or browser remained.

### 2026-09-21 — review of step 1: PATCH on the demo's cleanup

- **Accepted:** `make demo` left its run in Temporal — terminated when still open, never deleted —
  and the namespace keeps a closed run for 90 days (`temporal/setup.sh`), so each demo added a
  finished fake run to the Workbench's list. The demo now deletes that exact execution and proves it
  gone: the Workbench lists the finished run, Temporal holds it and deletes it, and then neither
  Temporal — the execution itself or its listing — nor the Workbench's list has it. Recorded beside
  it: `make demo` proves the workflow code the live WSL worker loaded, and `make up` leaves a running
  worker as it is (the demo's docstring and first check, `tools/README.md`, the green evidence above).
- **Found while proving it, and fixed:** at the final gate the page reads the run's change on its
  own, and each read is a `ReviewDiff` workflow named after the run, retained like the run — the demo
  deletes those too. A Ctrl-C reached the demo twice — `uv run`'s child gets a process group's SIGINT
  twice (measured) — and the second cut its cleanup short, leaving its worker, Workbench, folders and
  trust records; the first Ctrl-C now ends the demo, and the cleanup, which is bounded, ignores any
  further one. The cleanup stopped the demo's worker only after removing the run's folder, which a
  turn still running could write again; the worker now stops first. Whatever the cleanup cannot
  remove is named, and fails the demo.
- **Found, not in this patch, reported to the operator:** `tests/acceptance_restart.py` leaves its
  runs in Temporal the same way — they are all 16 runs the live Temporal holds, with 17 reads of
  their changes. Four `orch-claude-settings-*` folders from earlier runs remain in WSL's temporary
  folder, each with a stage's trace settings, which carry the trace store's key: `run_role` removes
  them when a stage ends, so a worker stopped mid-stage leaves them.
- **Verification:** `make demo` passed on the live stack with the removal step, and a separate read
  of Temporal found neither the run nor its change's read — by id, in the listing, or in the
  Workbench's run list — while an earlier demo run, the control, was found by all three. `make demo`
  interrupted as a terminal's Ctrl-C interrupts it, with the engineer's agent mid-turn: the run
  deleted from Temporal and nothing else left — no process, agent scope, temporary folder, run folder
  or trust record. The four runs earlier demo attempts left, and one read of a change, were listed by
  every demo marker and deleted. `make public-check` and the architecture tests pass.

### 2026-09-21 — step 2, tasks 6 and 7: Stop and force terminate

- **Change:** a Stop is Temporal's cancellation of the run (`client.stop`), heard wherever the run
  waits — the SDK delivers it as an `ActivityError` with a cancelled cause at an activity and as a
  `CancelledError` at a stop, so each handler that turned an activity's failure into a failed stop,
  a refusal or a skipped trace row now lets a cancellation through. The run ends `STOPPED`, which
  Temporal records as cancelled: no git runs, the stop it waited at is cleared, and `finish_trace`
  closes its terminals and trace on its host under a one-minute schedule-to-close bound. The three
  git side effects run shielded: a Stop during one shows `STOPPING` and waits for what git did; a
  merge or discard that landed ends the run as always, and after anything else the next thing the
  run would wait on raises the Stop. Force terminate is Temporal's termination
  (`client.force_terminate`). Both refuse a closed run up front, because Temporal's test server takes
  a cancellation of one. The Workbench has *Stop run* and *Force terminate* on every open run, the
  second behind a confirmation the server also requires; the command line has `--stop` and
  `--force-terminate`; the run view gains `stopping`. Structure D31 is new, and D29, `docs/using.md`,
  the stops diagram and the workflow's own architecture page say what changed.
- **Red first:** the seven workflow cases failed for the reason they exist — a Stop at a stop left the
  run cancelled with its status `RUNNING` and its stop still offered; at work it became a failed stage
  whose error read `Cancelled`; with no worker the run read `REFUSED`; during a merge nothing said
  `STOPPING`. Against the committed code, in a copy made by `git archive`, both new routes answered
  404, the view read `running`, and both command-line forms were refused.
- **Verified, not assumed (task 7):** a terminated run's working turn ends its agent at its next
  heartbeat, and the test's control shows the agent does not end by itself. Force terminate therefore
  leaves the worktree, the branch and the run's terminals until its host's worker restarts, but no
  agent past its next heartbeat — not "a live terminal", as task 7 assumed; the confirmation says so.
- **Found while building it:** the history recorder rewrote every history each time it ran, which
  would have replaced those older code wrote; it now records a history by its name, and two new ones
  — a Stop at the approval, a Stop during a merge that then lands — guard the Stop's path, because the
  Workbench queries closed runs and a query replays. A stopped run gets no trace score; task 11
  decides it.
- **Demonstration:** `make demo` grew to step 2's part of D12's journey, every control pressed in
  headless Edge — a run stopped while its engineer is held at work, which ends it and its agent; one
  stopped at its approval; one whose merge a git hook holds, whose Stop waits at `STOPPING` because
  it never cuts a merge off, force-terminated; each keeping its worktree and branch. The live stack
  was restarted onto this code first (`make down`, `make up`), as the green evidence requires.
- **Verification:** the WSL suite (308 tests) and the Windows host suite (231) pass; the five
  recorded histories replay and the control fails each; `make demo` passed on the restarted stack,
  with no window opened and focus unmoved as sampled throughout, and afterwards no demo process,
  agent scope, held git hook, temporary folder, run folder, trust record, browser or Temporal
  execution remained.

### 2026-09-21 — review of step 2: Stop PASS, force terminate PATCH, two cleanups before step 3

- **Accepted — force terminate promised too much.** Termination closes a run but cannot stop an
  activity already running, and the three git side effects do not heartbeat: a worktree's creation,
  a merge or a discard in flight goes on after a force terminate and may change the repository. The
  record above says force terminate leaves the worktree and branch; that is wrong. D31,
  `client.force_terminate`, the Workbench's confirmation, the command line's help and message,
  `docs/using.md` and the stops diagram now say what termination does, and a terminated run reads
  "terminated" in the Workbench rather than the status termination found it at. The guard:
  `ForceTerminate.test_a_git_side_effect_already_running_goes_on_after_a_force_terminate`, which
  passes on the code before this patch too — it pins Temporal's behaviour, and the worker logged the
  merge's late completion refused ("Completed workflow"). `make demo` now lets the held merge go after
  the force terminate, its worker still running, and proves the merge lands on the base branch and its
  own cleanup takes the worktree and branch. No primitive that stops git mid-write is built.
- **Accepted — a worker killed mid-stage leaves the stage's settings, with the trace store's key.**
  They are private already (a 0700 directory, the file created 0600 and exclusive). Each settings
  directory is now named after the process that made it, and a worker removes, as it starts, those
  whose process is gone — never one a stage still uses: sweeping every such directory would take the
  settings of a stage running in the demo's or the acceptance's worker on the same host. Red first:
  the worker's own entry point, started after a stage killed mid-run as a restart starts it, left that
  stage's settings (`test_stale_settings`, on both hosts). The seven such directories found — four on
  WSL, three days-old ones on Windows — were removed by hand.
- **Accepted — the acceptance's leftovers, and more than the review counted.** Beside its 16 runs and
  17 reads in Temporal it left 16 run folders and a pid file for every worker it killed. It now records
  each run as soon as its id is known — the second run's from the command line still following it,
  should the acceptance fail first — and afterwards deletes its runs and their reads from Temporal,
  proving them gone, removes their folders and its killed workers' pid files, and fails on anything
  left. `tests/temporal_cleanup.py` is the one helper it and `make demo` share. What earlier
  acceptances left was listed by the acceptance's own queue and repository and deleted: Temporal holds
  no test run now.
- **Accepted — `alive()`.** A `/proc/<pid>/stat` opened before its process is reaped raises
  `ProcessLookupError` when read (reproduced deterministically); both copies — the terminal tests' and
  the acceptance's — now take that as gone.
- **Simplified:** the review's "terminate if needed" before deleting — Temporal's deletion terminates
  an open execution itself.
- **Step 3's precondition:** a worker stopped or restarted from the Workbench now leaves no secret
  behind for long: the next worker to start on that host removes it.
- **Verification:** the WSL suite (311 tests) and the Windows host suite (234) pass. One earlier full
  Windows run passed every test, then hung at exit, with a thread asleep and the main thread waiting
  to join it; it was stopped, and the next full run and the two new modules alone exited normally —
  the cause is not found. `make demo` passed with the held merge landing after the force terminate,
  and the live acceptance passed, its last check that it left nothing on the host or in Temporal;
  afterwards Temporal held no run, and neither host a settings directory. `make public-check`.
