# The Workbench: Orchestra's operator console

**Status:** DONE — reviews passed and the full suite green on both hosts (D19); awaiting the operator's merge
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
- **D14** A worker the Workbench stops takes its stages' secret-bearing settings with it, through the
  existing narrow owner: stop the worker, prove its process dead, `discard_stale_settings()` on that
  host, report it stopped. A restart is that stop and cleanup, then a start; the sweep at a worker's
  start stays, for crashes and kills. No generic temporary-file cleanup framework.
  - Effect: constrains task 8 — the stack owner's stop.
  - Reason: *"if the Workbench intentionally stops a worker and leaves it down, its Langfuse settings
    must not remain until a future start"*
  - Date/source: 2026-09-21, operator
- **D15** The Windows suite's unexplained exit hang is root-caused with a bounded exit watchdog that
  dumps every thread's stack, and the smallest real ownership or teardown defect is fixed — never
  hidden with `os._exit`, arbitrary sleeps or a bigger global timeout. At least three clean
  consecutive full Windows-suite exits follow.
  - Effect: a verification gate of this change.
  - Reason: *"A suite that passed all tests and then remained alive for 14 minutes is not clean
    verification."*
  - Date/source: 2026-09-21, operator
- **D16** Retiring `abort` settles the trace's semantics with it: a user Stop is not a verdict and
  makes no misleading quality evidence — the smallest semantically correct representation, reviewed by
  the independent architect, and no new lifecycle or status abstraction.
  - Effect: constrains task 11.
  - Reason: *"A user Stop is not an architect/reviewer verdict and should not accidentally manufacture
    misleading quality evidence."*
  - Date/source: 2026-09-21, operator
- **D17** What a stopped run kept is shown clearly and can be removed from the Workbench, deliberately
  and later, through the existing target-host git and worktree owner, keeping every deletion and
  refusal guard; no git lifecycle logic in the Workbench.
  - Effect: constrains task 12.
  - Reason: *"The operator must be able to Stop, inspect the retained work, then deliberately remove it
    later."*
  - Date/source: 2026-09-21, operator
- **D18 [SUPERSEDED IN PART by D19 — the full evidence set and the operator's validation after
  `wsl --shutdown` are no longer required; driving it autonomously through fresh architect and tester
  PASSes, with nothing staged, committed or pushed, still binds]** The todo is driven to its end autonomously: implement, test, inspect, fix, review
  independently, and repeat until a fresh architect and a fresh tester both PASS; then the full
  evidence set on the final code; then the operator's own validation — `wsl --shutdown`, the operator
  starts WSL, and the service, `127.0.0.1:8390`, the stack's control and the Windows worker's control
  are verified from the service's context. Nothing is staged, committed or pushed.
  - Effect: the completion criteria; the todo is not done before the operator's validation.
  - Reason: *"Do not declare the todo done before that final independent architect + tester + operator
    validation."*
  - Date/source: 2026-09-21, operator
- **D19** No `wsl --shutdown` validation: the final check is the full suite, and that is all.
  - Supersedes: D18 in part (its evidence set and its operator validation)
  - Effect: the completion criteria — the full suite on the final code, on both hosts, since the change
    touches launching, terminals and worktrees (`AGENTS.md`).
  - Reason: *"for our kiss goal"*
  - Date/source: 2026-09-23, operator

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
- **A6 [RESOLVED by evidence — implemented so, structure D32]:** The stack owner sits in `app/application`
  beside `client.py`; the process mechanics stay in `workers.sh` and `workers.ps1`, split per component;
  the Make targets call the command line, which calls the owner.
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
- [x] **3.** `make demo`: a real run on the live Temporal with the suite's fake CLIs, through both loops
      in live terminals, answering one stop by pressing its button in a headless browser — so the body
      the page sends is proven — and removing everything it made. It grows with each step to D12's
      journey. Isolated by its own policy, never by a mode in production code: a stack of its own — a
      workflow queue and target queue of its own, polled only by its own worker, the real one, started
      and stopped from its own Workbench through the stack's owner with the fake CLIs on its PATH — so
      no real run can reach a fake agent, nor the demo run a real one; a temporary repository; and a
      demo Workbench on a spare port. The fake turns take a few watchable seconds; every delay lives in
      the demo's own fakes.
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

- [x] **8.** `workers.sh` and `workers.ps1` split per component — Temporal, the WSL worker, the Windows
      worker — each with start, stop and status; the stack owner orders them (Temporal before the
      workers on start, after them on stop) and restarts one. `make up`, `make down` and `make check`
      call the command line, which calls the owner.
- [x] **9.** The Workbench leaves the stack as `orchestra-workbench.service`, a systemd user unit
      (D13, A7): `Restart=on-failure`, `RestartSec=2`, `WantedBy=default.target`, and no network
      ordering — a user manager has no network target, and a loopback Workbench waits for none; started
      with this checkout's own environment, whose absolute paths the one Make target renders when it
      installs and enables the unit; `workbench-start|stop|status` wrap `systemctl --user` for
      maintenance. `make up` and `make down` no longer touch the Workbench, and its pid file goes —
      systemd owns its process. Live acceptance, once: after `wsl --shutdown` and the operator starting
      WSL, the service is active, `:8390` answers, and the Windows worker's status and control path
      runs from the service's own context — interop measured there, not assumed from a shell; only a
      concrete readiness dependency it exposes is fixed, and never with a delay.
- [x] **10.** The Workbench controls the stack: start, stop and restart it all or one component; what is
      down, and the start that brings it back, shown in the health panel and on every run it blocks.

Step 4: [x] **11.** `abort` leaves the published actions — a change to what a stop publishes, not to any
command, so replay proves it needs no `workflow.patched` — its handling kept for the runs that took it; structure D6 and D24 and `docs/using.md` updated. The trace's
`final_verify_pass` records 0 for an aborted run and nothing for a stopped one — a run stopped at its
final gate keeps the 1 it scored there — so what a stopped run scores is decided here, with the
trace contract.

Step 5: [x] **12.** A stopped run's worktree and branch removed from the Workbench's *Worktrees*, through
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
D12's in full by the end of step 3; `make public-check`. `make demo` runs the workflow code this
checkout holds, in its own worker; the live workers run what they loaded when they last started, so a
change to the workflow restarts them (`make restart`, or Restart in the Workbench) before the live
acceptance counts for it.

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
journey passes from the Workbench on the live stack with fake agents and no terminal opened, and
D18's surviving gate and D19's have passed: a fresh architect's and a fresh tester's PASS, and the full
suite on the final code, on both hosts.

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

### 2026-09-21 — steps 3 to 5, and the two cleanups before them

- **D14 — a stopped worker's stages' settings go with its stop.** The stack owner stops a worker, looks
  at it again, and only once its process is proven gone runs on that host the sweep a worker runs as
  it starts — naming the worker it proved gone, whose pid Windows may already have given to another
  process. A status that could not be read never counts as gone. A restart is that stop, then a start;
  the sweep at a start stays. The Windows worker is created with TEMP and TMP set to the folder its
  sweep reads, and prints where its stages' settings go. Guards: `test_stack` over stand-in mechanics
  (the order; nothing swept for a worker not proven gone, or whose state cannot be read) and over real
  processes on both hosts; `make demo` stops its worker mid-stage with a stage's settings in place and
  finds them gone at once; from the service's context, a folder planted for the live Windows worker's
  pid went with its stop.
- **D15 — the exit hang: not reproduced, and the suite now names such a thread itself.** Step 2's hang
  left the main thread waiting and one thread asleep (`ExecutionDelay`, 16 ms of CPU); no stack was
  taken then. Fourteen full runs of the Windows host suite on that code — ten under an in-process exit
  watch recording every thread's origin, its stack and the shutdown's phases, four run as the operator
  runs them, with a watchdog outside ready to dump Python and native stacks — all exited within a
  second of their summary; at exit only daemon threads and idle executor threads were left, and every
  atexit handler returned at once. What holds an exit that way is a thread still running when the
  interpreter joins its threads: `concurrent.futures` joins every executor thread, a daemon one too,
  before any atexit handler — before the suite's Temporal workers stop. No test was found leaving one,
  so nothing was changed on a guess. The suite's runner is `python -m tests` on both hosts
  (`tests/__main__.py`): 60 s after the summary it prints every thread's stack and leaves the process
  as it is, so a recurrence names its thread and what it waits on; nothing is hidden. Found on the way
  and fixed: the Windows suite left every git-backed temporary folder it made — git's read-only objects
  defeat `rmtree(ignore_errors=True)` — about two thousand in TEMP; `tests/folders.py` removes them.
- **Step 3 (tasks 8–10).** `app/application/stack.py` is the stack's one reading and one owner, and
  `workers.sh` and `workers.ps1` its mechanics, one part at a time; `make up|down|check|restart`, the
  command line's `--stack` and the Workbench's stack panel all call it. A part is up only when proven:
  Temporal answering; a worker's process — known by its pid file and its command line — polling each
  of its queues as `<pid>@<host>`. Each policy names its own workflow queue (`workflow_queue`,
  required), so the demo's and the acceptance's stacks are stacks of their own, and only the checkout's
  policy manages Temporal and the Windows worker. The Workbench is `orchestra-workbench.service`, a
  systemd user unit that `make workbench-install` renders; it has no pid file, and `make down` never
  touches it. The page shows each part's state and offers its start, stop and restart, and the whole
  stack's; a run blocked by a worker offers that worker's start.
- **Step 4 (task 11).** `abort` is no longer published at any stop, and is refused; its handling stays
  for the runs that took it — two histories recorded with the code before replay on this one — and
  needed no `workflow.patched`: a stop's published actions are state, not commands, and validators do
  not run on replay. A Stop writes no score (D16): `final_verify_pass` is 1 when a build reaches
  READY_FOR_HUMAN and 0 only for the retired abort, and the trace contract says the trace records
  whether a build was verified, not how a run ended, which is Temporal's; the architect reviewed the
  choice and agreed. The dashboard's tile is *Builds verified*. The unreachable `abort` branch after the
  final gate is gone.
- **Step 5 (task 12).** A closed run that kept its worktree and branch says so on its page, with Remove;
  *Worktrees* lists each run's worktree with its run, and Remove where it can go. A removal is
  `client.remove_worktree` → a `RemoveWorktree` workflow → the run's target host's own `discard`,
  once. One rule, `client.not_kept`, says what can be removed — never an open run, a merged or discarded
  one, one that never made a worktree, or one removed already — and a host refuses a removal while a
  git side effect of that run still runs there, as a terminated run's merge does. A removal git refuses
  says why, and runs again only when asked.
- **Found live: from the service, Windows programs run elevated.** WSL runs a Windows program with the
  token of whatever started WSL, and from the Workbench's service that is the process that booted the
  distro — here an elevated one, so a Windows worker the service started ran as an administrator.
  `workers.ps1` refuses such a start and says to start WSL from a normal terminal; the reading marks
  that worker as one this side cannot start; a restart leaves it running. Whether a WSL started
  normally gives the service a normal token is measured at the operator's validation (D18).
- **Reviews.** Step 3's design: PATCH — every policy's stack stopped the shared Temporal; readiness
  taken from a timestamp; the Windows worker known by its name alone; a sweep proof that could not
  fail — all taken. The fresh architect on the implementation: PATCH — a removal racing a terminated
  run's merge; a restart leaving an elevated Windows worker down; the kept rule decided in three
  places; the trace contract saying a run's end is in its scores; a stale README line — all taken, with
  its optional points: the removal's bounded wait, `make workbench-restart`, the main diagram's label,
  the dead branch. The fresh tester: PATCH — the removal's failure paths; a failed status read as not
  running; the Windows worker's temporary folder unverified; nothing checking control from the
  service; nothing proving a run's own workflow queue — all taken, with the optional guards it named:
  the policy's `workflow_queue` validated, a second worker leaving the first's record, a second
  removal refused, the removal's record gone from Temporal after the demo, the installed unit read by
  `systemd-analyze`. Each new guard was shown to fail with its fix taken out. The demo now also starts
  every run by typing its task into the page's own form.
- **A flaky test, root-caused.** The stack reading's tests took the time once, at import; the whole
  suite reaches them more than 90 s later, past the reading's polling window, so a live worker read as
  `starting` (three failures in a full run, none alone). Each test takes the time as it runs; run 95 s
  after import, they pass.

### 2026-09-22 — the second independent review: architect PATCH, tester PATCH, all taken

- **D15 — the exit hang, reproduced and fixed at its owner.** The architect's finding: at exit the
  interpreter joins every thread pool's threads — `concurrent.futures` does it in `threading._shutdown`,
  before any atexit handler — while the suite stopped its Temporal workers from atexit. An activity
  still running when a test process ended therefore held it for good: a heartbeating turn waits for a
  cancellation only its worker's shutdown sends. A test process that ends with a run's turn at work
  (`tests/test_harness.py`) reproduced it on both hosts — alive 120 s after its main thread ended, one
  thread asleep in its heartbeat loop and the main thread joining it: the signature step 2's hang left.
  `tests/temporal_env.py` now stops its workers and its test server as the interpreter begins to shut
  down, ahead of that join, and the same process exits within a second or two. The watchdog in
  `tests/__main__.py` stays, for anything else.
- **D16 — a stopped step is no failed stage.** The architect's other finding: a Stop of a working run
  closed its role step's row as ERROR, typed `internal` — a defect of this component, the misleading
  evidence D16 forbids. A step whose activity Temporal cancelled, or no longer knows — a Stop, a force
  terminate — now closes at DEFAULT, its output saying the run ended, with no error type; a worker's
  shutdown or a timeout is still the step's failure. Which of the two ended the run is Temporal's to
  say: a stopped run can close before its step next hears from Temporal. The contract's level table
  says so.
- **D8 — a Stop never waits for a worker.** The tester's first finding, a real defect: a merge answered
  just as its host's worker went away — the preflight still counts a worker dead for under 90 s as
  polling — waited on its queue without bound, and a Stop then waited at `STOPPING` until a worker came
  back, which would have run the merge after the run was stopped. A git step now waits for its host's
  worker to take it as long as a role's step may go unheard, the policy's heartbeat interval, and then
  fails never having run; it is behind `workflow.patched`, and every recorded history still replays. A
  Stop during a trace write, which nothing guarded, is guarded too.
- **Stack control from the service, whatever WSL's token.** The acceptance needs the Workbench's
  service and no longer falls back to the command line: it stops and starts the live stack through the
  Workbench's API, and where the service's side would start the Windows worker elevated — as now — it
  checks the refusal says so and starts that worker from its own side. Before the stop it leaves a
  stage's settings in each live worker's own temporary folder, named from the line the worker printed
  as it started, and requires the stop to have taken them: the Windows sweep's folder is checked
  against the worker's own, across the two contexts. Its host, workflow queue and ports are new each
  time.
- **The page's own questions and terminals.** `demo_press` records every question the page asks; the
  demo checks that the force terminate's says a running merge may still change the repository, and
  that Stop run, Remove and a worker's Stop ask first, and it reads the engineer's terminal as the page
  shows it, live from its host.
- **Tests at the mercy of the clock or the live stack.** `stack_as` in the Workbench's tests took its
  poll time once — the stack reading's defect again; every stack action in the tests now takes a lock of
  its own, never the live stack's.
- **Optional points taken:** Temporal's own up and down proofs; the kept rule's every branch; a
  connection kept across Temporal's stop; current-truth wording in D6 and the workflow's comment; the
  reading's states in `docs/using.md`; an unreadable part's own label on the page; the install's warning
  while lingering is off, and the guide's line on it; the investigation's leftovers in `tmp/`. **Left,**
  both reviewers' optional points: a stuck Windows read holds the page's reads for up to its 60 s bound;
  "kept" is read from the run's recorded state, so a run terminated during its worktree's creation can
  keep a worktree the page cannot remove, and one terminated during its merge reads as keeping what the
  merge then removed (its Remove finds nothing and succeeds); a worker stopped in the middle of a merge
  leaves its run at `merge` until the step's own timeout.
- Each new guard was shown to fail with its fix taken out — the exit test on both hosts.

### 2026-09-22 — the third independent review: architect PATCH, tester PATCH, all taken

- **D16 was not yet deterministic.** Both reviewers found it, from two sides. The architect: a real Stop
  usually reaches its step through the Stop's own cleanup, which closes the run's terminals on the
  host and so ends the agent, long before the next heartbeat (up to a minute away) could bring the
  cancellation — the step then failed as `agent_exit`. The tester: Temporal's "no longer known" comes
  both after a Stop or a force terminate and after the step timed out while its run goes on, so a real
  failure could be recorded as a Stop. Now the Stop's cleanup marks its run on that host before it
  ends the agents, and a step cut short reads DEFAULT "stopped" only for that mark or Temporal's
  cancellation; a step cut short any other way — its worker stopped under it, a force terminate, a
  heartbeat timeout — is ERROR with a type of its own, `lost`, which the contract states. One test for
  each order a Stop can take (the cleanup's with the shipped two-minute heartbeat), and one each for a
  force terminate, a heartbeat timeout and a worker taken away; the old classifier fails three of them.
- **"Nothing is lost" was not true.** The page's question before stopping Temporal and the guide said
  so; a stage at work longer than a role's heartbeat interval with Temporal down fails and waits for
  Continue. Both now say what happens, and a worker's stop says a merge or discard it runs may be cut
  off.
- **D14's named pid had no guard that could fail.** A test now sweeps a folder named after a live pid
  — the test's own, standing for one Windows gave away — which stays unnamed and goes once named.
- **D13's "comes back if it fails" was never exercised.** The acceptance now kills the Workbench's main
  process with SIGKILL — SIGTERM is a clean exit, which `on-failure` leaves alone — and requires it back
  by itself within 30 s.
- **Optional points taken:** after a Stop ended a run whose merge no worker took, a worker coming back
  runs nothing; without a Stop, that merge fails saying why and Continue merges once a worker is back;
  a stop whose sweep failed is reported so; the exit test measures from the moment the process's work
  is done; a history recorded under the git step's wait (`final_merge_no_worker_continue`: the merge
  no worker took, then continued), carrying its patch marker, so the replay guard covers runs started
  on this code. **Left:** pressing the whole-stack and Temporal buttons in a browser (their API is
  exercised live); the run list's handling of an unreadable closed run; the WSL worker as a transient
  systemd service instead of a scope with a pid file (it would revisit D9 and D32).

### 2026-09-22 — the fourth independent review: architect PATCH, tester PATCH, all taken; D15's cause

- **D15 — the hang's own mechanism, found.** A test that had timed out twice before in this work
  (`AnotherProcess`: a second process answers a stop and follows the run) hung again in a batch, and
  under full CPU load it hung every time: the child printed all it had to, then never exited. Its two
  threads were a native thread of the SDK's runtime in `pause()` and the main thread waiting on a lock
  (`/proc/<pid>/task/*/wchan`). CPython 3.13 parks, for good, any foreign thread that asks for the
  interpreter once it has begun to shut down — `pause()` on Linux, `SleepEx(INFINITE)` on Windows, which
  Windows shows as the `ExecutionDelay` step 2's hung suite had, beside a main thread waiting. The call
  answered that late was the command line's own history long poll in `cli.follow`: cancelled in Python
  when the follow returned, still in flight in the runtime, and answered by the run's last events as
  the process exited. The test processes follow runs in-process the same way and left such polls open,
  which the test server's shutdown answers. `cli.follow` now looks at the run every second and leaves no
  call in flight; a test holds it to that — control: the long poll, which the SDK answers after its
  caller stopped waiting — and the loaded batch that hung twice in two passed three times in three. With
  the harness's own order at exit (the previous entry), both ways a test process could hang at exit are
  closed. The watchdog in `tests/__main__.py` stays.
- **D14 — a sweep that cannot remove settings no longer reports a clean stop.** The tester's finding:
  the sweep ignored what it could not remove and always exited 0, so a file still held open on Windows
  kept the trace store's key under a stop reported done. It now names what it could not remove and
  fails, and the stack's stop with it; a test holds the file open on Windows and takes a folder's write
  permission elsewhere — control: the exit code before.
- **The list and the page's buttons with a workflow worker down.** The run list's bounded status read
  and its not keeping an unread closed run are now tested. An answer or a read of the change, pressed
  while no worker can read the run, is refused at once naming the worker, as a removal already was,
  instead of failing after two minutes.
- **The preflight's window.** A worker counts as polling only while its last poll is recent; a test
  feeds Temporal's own poller times — control: any poller Temporal still lists.
- **D16's classifier, signal by signal,** as a table of its own; the heartbeat-timeout test now waits
  for the failed stop instead of a fixed silence.
- **The architect's finding:** two durable files cited this todo's D16, which in `structure.md` is
  another decision; they cite structure D20 and the trace contract now. Its optional point on the WSL
  worker's stop wording is taken: a git step it cuts off stops its run there for the operator to
  continue.
- Each new guard was shown to fail with its fix taken out.

### 2026-09-22 — the fifth independent review: tester PATCH, taken; the architect's review cut off

- **A run blocked by its target host's worker alone.** Every blocked-run test had the WSL worker down,
  which also runs the workflows, so dropping the target host's queue from what a run needs passed them
  all. A view test now has the Windows worker down alone: a Windows run is blocked by it, a WSL run is
  not — control: the target's queue dropped, and every queue of the stack counted.
- **The operator's words from the page.** Nothing sent a revise or a guidance with its words the way the
  page does. An API test now sends a revise with a note and finds it in the engineer's next plan —
  control: the server dropping the words — and the demo presses Revise with a note typed into the
  page, and reads it in the plan's prompt.
- The demo's removal is checked to run on the demo's own workflow queue.
- The architect's review of this round ended on an API error before it returned a verdict, and is run
  again.

### 2026-09-22 — the sixth independent review: architect PASS, tester PATCH, taken

- **The architect: PASS.** It named, as optional, the command line's `--stop` and `--answer` asking for
  the run's status before any worker could answer it — with the WSL worker down, `--stop` waited
  without ever sending the Stop the page sends at once. Both now read the run only once a worker polls
  its workflow queue: `--stop` records the Stop first and, with none, says it is recorded and exits 2;
  `--answer` is refused at once, naming the worker. Also taken: a comment on what cancelling a timed-out
  Workbench call does, and the follow test counting every call.
- **The tester's findings.** Nothing guarded the page's Stop and force terminate with no worker to read
  the run — a status read added to them would have passed; now tested with the real preflight and a
  status that never answers. A failed sweep reached the stack only through the scripts' exit codes,
  which nothing guarded; a stop through `workers.sh` over a folder the sweep cannot empty is now reported
  not done, and on Windows `workers.ps1`'s sweep fails over a settings file held open and names it. The
  follow test's first look found the run already stopped, so it never reached the wait between looks;
  its first look now finds the run working. Two environment-bound tests: the Windows status is compared
  by its first line (an elevated shell adds one), and the exit test never waits on a child that prints
  nothing.
- Each new guard was shown to fail with its fix taken out.

### 2026-09-23 — the seventh independent review: architect PASS, tester PATCH, taken

- **The tester's finding.** The demo never pressed Revise with no note, and nothing read the question a
  Discard asks; both are now checked in the demo. Also taken: a failed stage's view, the git-step Stop
  test given a heartbeat long enough that its Stop always meets the merge still waiting, and the
  failing-sweep test's folder made writable again in a `finally`.
- **The architect's optional points, taken as inside this change's boundary.** A worker dead for less
  than the preflight's recency window counted as polling, so an answer could still wait on a status
  that never came: the status an action reads is now bounded and, when it does not come, refused
  naming the worker. The run's workflow queue is read from Temporal's own record rather than from the
  run's state. `--stack` given to the run commands is refused rather than taken for a start. The page's
  and the guide's words on a worker stopped mid-merge now say its run waits at that step until the
  step fails or times out, and that Force terminate ends it sooner.
- Each new guard was shown to fail with its fix taken out: the read unbounded, its failure not turned
  into a refusal, and the `--stack` refusal taken out.

### 2026-09-23 — the eighth independent review: architect PATCH, tester PATCH, one finding, taken

- **Both reviews' required finding.** The removal still read its run's status itself, unbounded, so the
  seventh round's bound held for an answer and a change read but not for Remove: pressed while a worker
  dead under a minute and a half still counted as polling, it waited for the page's eleven minutes. The
  removal now reads through the same bounded read, and a Workbench test of it failed first on the old
  code (a bare error for the page instead of the refusal naming the worker).
- **Taken from the optional points.** Temporal's own query, on a queue no worker polls, is now shown to
  end at its bound as the refusal — no stand-in — and the harness's use of CPython's thread-join hook
  names the interpreter it was proven on.
- **Left, with reasons.** The status query's own `workflow_queue` stays: it is `workflow.info()`'s, the
  same record the listing gives, and the demo reads it. `--show` reads a run unbounded as before this
  change and stays out of it. Two runs on different workflow queues are not told apart by a unit test;
  the demo proves the removal's queue live, and every action reads the queue from Temporal's record, not
  from a policy. Whether the Windows worker itself runs unelevated is not checked by the acceptance;
  `workers.ps1` refuses an elevated start, a
  refusal met live whenever the calling context is elevated, as this machine's service context was.

### 2026-09-23 — the ninth independent review: architect PASS, tester PASS; one optional point closed

- **Both PASS.** The tester named, as optional, the same wait one hop further: the removal's own git step
  had no bound on being taken, so with the target host's worker dead under a minute and a half it
  waited out the removal's ten minutes. Taken, as inside this change's boundary: a removal no worker of
  its host takes within a minute fails never having run, and the page names the worker to start. The
  removal workflow is new with this change and in no recorded history, so it needs no patch. Its test
  refuses within the bound and finds git never ran, even once a worker is back; controls: the removal
  unbounded, and the refusal not naming the host.
- Also taken: the shipped policy's workflow queue pinned as the one runs started before it was the
  policy's are on.
- Left: `restart` starts a part whose stop failed, and says both; the worker keeps the ids of the runs
  it saw stopped for its lifetime; the page's two worker-stop warnings differ by one word; the reading
  of parts another policy's stack does not manage has no reading test; the git step's patch marker is
  not itself failed by replay, its behaviour guarded by the two git-step tests.

### 2026-09-23 — the tenth independent review: architect PASS, tester PATCH, taken

- **The tester's finding.** The single run's page and the worktree view each read a run's status for
  five seconds at most, and no test would have failed with that bound gone: their stand-ins failed at
  once. Both stand-ins now wait out the bound they are given, and the tests assert it and the moment the
  page answers in; with the bound taken out, each hangs until the page's own limit and fails.
- **Left:** the architect's note that a removal's wait for a worker plus its step's limit can exceed
  the removal's own ten minutes — real removals take seconds — and that the removal workflow's input
  gains a version guard only when it next changes.

### 2026-09-23 — the eleventh independent review: architect PASS, tester PATCH, taken

- **The tester's finding.** The pid of a worker the owner proved gone was tested only at its two ends —
  the owner passing it, and the sweep honouring it — while every real sweep route used a pid already
  dead, which is swept named or not. A test now puts a stage's settings under a live pid — the test's
  own, as a reused one would be — where each host's sweep looks, and sweeps through the real script:
  unnamed they stay, named they go. Controls, on each host: `workers.sh` or `workers.ps1` dropping the
  pid, and the worker dropping it.
- **Left:** the worktree view reads its rows one after another, each bounded, where the run list reads
  them together — only a worker dead under a minute and a half with many kept runs meets it; the
  worktree view's own workflow has no execution timeout, as before this change, the page's limit ending
  it; an unlistable temporary folder reported as left has no test of its own; the Worktrees panel's
  Remove is not pressed by the demo, the run page's, which calls the same route, is.

### 2026-09-23 — the twelfth independent review: tester PATCH, taken

- Only the tester reviewed again: the eleventh round changed tests alone, and the architect had passed
  it.
- **The finding.** Each call to a host's script is bounded by its action's limit, and nothing would
  have failed with that bound gone: every test of the owner replaced the scripts. Unbounded, a
  PowerShell interop call that never returns would hold the stack's lock for good, and every later
  start, stop or reading would be refused as busy or fail. A test now runs a script that never
  returns: it is given up on at its limit, reported not done, and the lock is free after — control: the
  call unbounded, which waits it out.
- A test added for a policy without its workflow queue was found, in the next round, to repeat
  `test_the_workflow_queue_is_required_and_a_plain_token`, and was taken out again.

### 2026-09-23 — the thirteenth independent review: tester PASS

- Nothing material unguarded. Left, as optional: the whole stack's stop confirmed by the page alone, not
  the server, as its terminate and removal are not; the test cleanup's prefix match on change reads,
  which removes only change reads.

### 2026-09-23 — the final check (D19)

- The full suite on the final code: WSL 391 tests OK (4 skipped); Windows 277 OK (34 skipped), its
  process exiting two seconds after its summary. `make public-check` passed; `git diff --check` clean;
  nothing staged, committed or pushed.
- **Left:** a start of a worker already running counts its polls from a window back; a regression there
  slows a start, never misreads one.
