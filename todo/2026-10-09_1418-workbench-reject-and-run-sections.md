# Workbench: Pause and Reject pinned at the top of a run's page, and the run list in scrolling sections

**Status:** BUILT, OPEN — the external reviewer passed the plan on 2026-10-09 and it was built the same
day; the reviewer's PATCH on the build, two points, is worked in, and the build awaits its pass. One
criterion is still unmet: the WSL suite's one whole run (completion criterion 2), which runs after that
pass.
**Scope:** how a run is ended from the page — one ending word in
[workflow.py](../app/orchestration/workflow.py), the shared client in
[client.py](../app/application/client.py), one route and the list's rows in
[server.py](../app/interfaces/workbench/server.py) — and the page's own files under
[static/](../app/interfaces/workbench/static/). No new activity, workflow type, stop answer or
command-line form.
**Stable documentation owner:** architecture D31 and D29 in
[structure.md](../docs/architecture/structure.md) for the decision; [using.md](../docs/using.md) for how
the page is used.

## Contents

- Goal · Authority register · Non-goals
- Verified evidence · Current architecture · Problem
- Decision, with the KISS gate and the alternatives
- Required invariants · Implementation tasks
- Test-first and verification plan · Documentation plan · Completion criteria · Review record

## Goal

A run's controls sit at the top of its page and stay in view while the page scrolls. **Pause**
interrupts the agent at work and puts the keyboard in its terminal, so the operator types to it and it
goes on. **Reject** ends the run and removes everything it left in its repository, with one
confirmation; its history stays readable, and the page says how far the cleanup got. That run, and only
a run rejected that way, is listed under **Rejected**. Each section of the run list scrolls inside
itself once it holds more than five runs, on any window.

## Authority register

### Operator decisions

All 2026-10-09, in the operator's words.

- **D1** A Reject button that cleans everything up automatically; the run's history is kept.
  - *"reject button that automatically cleanup all and proper section"*; *"all history should preserve
    but mess should be removed"*.
- **D2** Rejected lists only the runs rejected with that button. A stopped run is not rejected.
  - *"only that run which we explicitly press reject button, stop it's not reject!"*
- **D3** Sections of the run list become scroll boxes, adaptively, once they hold more than five runs.
  - *"sections with scrollbars"*; *"ok let's simplify - adaptive scrollbox if over 5 runs"*; *"read
    about adaptive design please"*. Earlier that day, the one time sections were named: *"each sections
    closed, rejected should have scroll box if not compact in screens"*.
- **D4** A run's control-plane buttons sit at the top, placed by web-interface practice.
  - *"all control plane buttons should be in top think with web skills - so pause / or reject should be
    there"*.
- **D5** A Pause button that pauses the agent at work, after which the operator types to it in its
  terminal and it continues.
  - *"we need pause button that just pause current agent run and then operator could kiss to enter text
    to terminal to agent - it's for convinient control and not search windows but pause and then
    continue with prompt"*.
- **D6** Very KISS. — *"very KISS"*.
- **D7** What an engineer runs to check a change must not break the flow it works in.
  - In a run's task: *"ingeneer will work in the same flow - so his test don't need break this current
    flow with deploy"*.
  - Effect: this change's own verification never stops, restarts or redeploys the live stack or the
    Workbench's service.
- **D8** The page's behaviour is tested properly, in a real browser.
  - *"need to test properly - you could use drive browser skill"*.

### Decided with the external reviewer — the reviewer's and the agent's

Points the operator's words left open, settled by the reviewer's PATCH and PASS of 2026-10-09 where the
agent agrees.

- **Under D4, the controls stay in view while the run's page scrolls.** D4 says the top; a control that
  has to be scrolled back to is searched for again, which D5 names as the thing to end.
- **Under D3, all four lists are boxes.** One rule for every list is less than a rule with two
  exceptions. Operator action gives up no height, and the counts stay in the headings.
- **Under D1, a rejected run says where its cleanup stands** — removing, cleaned up, or cleanup
  required with the removal beside it — from facts that exist already.
- **Under D5 and D8, Pause is proven in a browser through to a typed follow-up.** A check on a real
  agent is the operator's own, after the reviewer's pass.
- **`make demo` takes back the environment it builds on WSL for a worktree Windows made**, when it ends,
  through the guarded removal that exists — no sweep, and nothing left to remove by hand.

### Working assumptions

- **A1 [ACTIVE]:** Pause is the Esc a role's terminal already takes, sent for the operator: the run is
  not told, the turn's clock keeps running, and what the operator then types steers that turn
  (architecture D17).
- **A2 [ACTIVE]:** Reject is offered in every state that offers *Stop run*. At the final gate *Discard*
  stays the stop's own answer.
- **A3 [ACTIVE]:** "Control-plane buttons" are the run's own controls and the removal of what a closed
  run kept, on the run's own page. A stop's answers stay in its decision, beside their evidence.
- **A4 [ACTIVE]:** A list of five runs or fewer is always whole. On a window too short for all four
  boxes, only the lists past five give up height, down to one row; for what still does not fit, the
  lists scroll as a whole.
- **A5 [RESOLVED by evidence]:** The live Temporal server records a cancellation's reason as the API
  defines it — `make demo`'s rejected run ended `REJECTED` on it.
- **A6 [ACTIVE]:** `make demo` runs from inside a run's own worktree. Run in a stand-in of one, where it
  passed (see what was run and seen); never in a run's own.

## Non-goals

- No paused state in the workflow, and nothing that resumes a stopped run (A1).
- Reject stays Temporal's cancellation: no new stop answer, activity, workflow type or command.
- No state of its own for a cleanup that is pending or failed: two facts that exist say it.
- No `--reject` on the command line, which has no removal either (architecture D31).
- A run stopped and later removed by hand is not listed as rejected (D2).
- A stop's answers do not move (A3), and the labels of the controls that exist do not change.
- No change to how many closed runs a page holds, or to *Load older runs*.
- No check on a real agent as part of this change's build: it spends a real turn, and is the operator's.
- The New run form preselecting the first listed repository is a separate defect, not fixed here.
- No sweep of environments: the demo takes back the one it built, for its own checkout, and no other.

## Verified evidence

Read from the checkout at `a0846f7` on 2026-10-09. Two probes were run; no test of the suite was.

**Verified facts**

- **A cancellation can say why, and the workflow can read it.** The pinned `temporalio` 1.33.0 has
  `WorkflowHandle.cancel(reason=…)` and `workflow.cancellation_reason()`, read in the installed package.
  Probed on the time-skipping test server the suite uses: a cancellation sent with the reason `reject`
  was read by the workflow as `reject`, and one sent with none as the empty string.
- **The reason's path, link by link.** The client sends it in the cancel request; the API defines the
  cancel-requested event's `cause` as "User provided reason for requesting cancellation" (the pinned
  package's own stubs); the SDK handed that event's cause to the workflow in the probe above.
- **A Stop closes the run for good.** `stop` in client.py is Temporal's cancellation; the workflow ends
  the run `STOPPED`, runs no git and bounds its cleanup (`_stopped` in workflow.py,
  `STOP_CLEANUP_SECONDS` in [policy.py](../app/foundation/policy.py)). An answer, and `--continue`,
  reach only an open run waiting at a stop (`answer` in client.py). So a stopped run keeps its worktree
  and branch, and the run itself does not resume.
- **Three places name that ending:** `_stopped`, which sets it and hands `STOPPED` to its cleanup
  activity; `finish_trace` in [activities.py](../app/application/activities.py), which reads the status
  it is handed; `outcome` in [ui.js](../app/interfaces/workbench/static/ui.js), the page's label.
- **Removal:** `remove_worktree` in client.py refuses an open run, a run that kept nothing and a second
  removal, each in words that say why (`not_kept`); it needs the run's workflow worker and its target
  host's worker, and runs once. How a removal went is Temporal's own record of it (`removal`).
- **What a closed run still keeps is worked out for its page, not for its row.** `_run` in server.py
  asks `removal` and `not_kept`; `_run_page` does not, and keeps a closed run's row for good once read
  (`finished`).
- **An interrupted turn goes on with what the operator types.** A role's terminal on the page sends each
  key over that role's socket while its agent is live (`term.onData` in
  [terminals.js](../app/interfaces/workbench/static/terminals.js)) — the Esc key as the one byte Pause
  would send; on Windows a lone Esc is delivered as the key ([ptyhost.py](../app/agents/ptyhost.py)). An
  interrupt completes nothing, and the turn ends on the completion of a prompt typed after it
  (architecture D17; `test_esc_and_typing_reach_the_agent_and_an_interrupt_completes_nothing` in
  [test_terminal.py](../tests/agents/test_terminal.py)). The turn's own time limit keeps running
  meanwhile (`timeout_seconds`, an hour as shipped).
- **The run's controls sit far down its page:** `run-controls` and `run-kept` follow the decision and
  the whole change in [index.html](../app/interfaces/workbench/static/index.html), and the terminals
  come after those. That was chosen: the [workbench UX todo](done/2026-09-25_2334-workbench-ux.md) put a
  run's decision first in the page and in the tab order, and its own controls after it.
- **Pinning has a pattern here.** The Workbench's bar is pinned at the top and the page's scroll padding
  keeps what is scrolled to clear of it; the rail is pinned under it; Settings pins its apply bar at the
  bottom, with a scroll margin on its controls (`.top`, `html`, `.rail`, `.apply-bar` in
  [style.css](../app/interfaces/workbench/static/style.css)). Below 640 px the Workbench's bar may wrap
  and grow past the height the others are pinned under.
- **The rail:** three lists, every closed run in the third (`GROUPS` and `render` in
  [rail.js](../app/interfaces/workbench/static/rail.js)); one scroll area for all of it. Operator action
  and Working show a count in their headings, and the page's title the count that waits. Below 1000 px
  wide the rail sits above the page at its full height, so every closed run a page holds comes before
  the run's own page. A row's view already carries its `status` (`view` in client.py).
- **Tests:** each half of a reject is covered in
  [test_workbench.py](../tests/interfaces/test_workbench.py), class `Runs`; a Stop's endings in
  [test_stops.py](../tests/orchestration/test_stops.py), a Stop while an agent works among them
  (`test_a_run_whose_agent_works_ends_stopped_and_its_agent_with_it`). The suite never runs the page's
  scripts; its controls are pressed by `make demo`, by label, in headless Edge
  ([demo.py](../tools/demo.py), [demo_press.py](../tools/demo_press.py)). The demo's agents answer no
  Esc today; the suite's stand-in CLI does ([fake_cli.py](../tests/fake_cli.py), its `interrupt` word).
- **What `make demo` needs of the checkout it runs in.** Its own files, all tracked; a settings file, a
  repository, queues, ports, a Workbench and a worker of its own, made in a temporary folder
  (`setup` in demo.py); the live Temporal. Every git call it makes is on its own repository, and it stops
  only its own worker — a stack that is not the checkout's own manages its WSL worker alone (`managed`
  in [stack.py](../app/application/stack.py)). In a worktree Git for Windows made, the Makefile is
  checked out with CRLF: GNU Make 4.3 on WSL read a CRLF copy of it and printed the demo's recipe clean.
  The shell scripts are pinned to LF, and Python reads either.
- **What it leaves there.** Run on WSL from a worktree Windows made, the Makefile and
  [workers.sh](../workers.sh) build that worktree an environment on WSL, which nothing removes: a
  worktree's environment goes with it on its own host only. The test runner avoids this for such a
  worktree ([run-tests.sh](../run-tests.sh)); these two do not.
- **How the demo's driver reads a press.** It finds a control by its label anywhere in the run's view,
  and reads the status line nearest that control (`button`, `REGION` and `SAID` in demo_press.py); it
  takes the page as loaded once the `runs-finished` list holds an entry. It has no way to type into a
  terminal.
- **Web-interface practice**, from the checklist the `web-design-review` skill pins: a destructive
  action needs a confirmation; flex or grid over script measurement for layout; an inner scroll area
  contains its overscroll; nothing pinned may cover the focused element.

**Inferences**

- A run waiting at a stop closes within the Stop's cleanup bound even with its target host's worker
  gone, so a bounded wait can follow a Stop.
- The reason comes from the run's own history, so reading it is the same on every replay.

**Unverified at the investigation**

- A5 and A6 — for what the build then showed of each, see the register.

## Current architecture and source of truth

- **Architecture D31** owns how a run is ended from outside: a Stop is Temporal's cancellation and runs
  no git, so a host whose worker is gone never holds it; what a closed run kept stays until the operator
  removes it, confirmed, never while the run is open.
- **Architecture D17** owns a turn: the operator may press Esc and type in a role's terminal at any
  time, and a prompt typed during a turn steers that turn.
- **Architecture D29** owns the page: every run listed by whether it waits, works or has closed; every
  write through client.py.
- **Architecture D6** — ending a run is no stop's answer. **Architecture D25** — what the workflow
  commands is held by the recorded histories.

## Problem

Capability gaps. To interrupt an agent the operator has to find its terminal far down the page, click
into it and press Esc. Throwing a run away takes two controls on two states of the page, both below the
decision and the change, where the operator did not find them. Nothing tells a run the operator rejected
from one that was merely stopped. And the run list is as long as the page holds, which on a narrow
window is all above the run's own page.

## Decision

**Pause is the page pressing Esc for the operator (D5, A1).** While a role works, **Pause** opens that
role's terminal and no other, sends it the one Esc its own keyboard would, and leaves the keyboard
there, so the next thing typed reaches the agent with no click. The words beside it say what it is and
what follows: it interrupts the agent, what is typed steers this turn, the run moves on when the agent
has answered it, and the turn's time limit keeps running. Nothing but the page changes.

**Reject is a Stop that carries its reason, and then the removal.** `reject` in client.py cancels the
run with a reason the workflow module names, waits until Temporal reports the run closed — for the
Stop's own cleanup bound and a margin, no longer — and then calls `remove_worktree`. A run still open
when that wait ends is answered as pending: still stopping, nothing removed, and not yet called
rejected. Where the removal cannot remove, its own refusal is what Reject says: the run kept nothing,
its host's worker is down, git refused. The server takes it at `POST /api/runs/<run-id>/reject`, confirmed as a
removal is.

**The run itself says how it ended.** In `_stopped`, a run whose cancellation carries that reason ends
`REJECTED`; any other Stop ends `STOPPED`, as now. Nothing else in the workflow changes: the same
cleanup activity, handed `STOPPED` as now, and no command added — so the histories recorded for a Stop
already hold every command a reject issues.

**A rejected run says where its cleanup stands.** That ending is the operator's act; whether the mess is
gone is a second fact, and both exist: the run's ending, and Temporal's record of its removal. From
them the run's page and its row say one of three things — stopping and then removing while they run;
rejected, cleaned up; rejected, cleanup required, with *Remove worktree and branch* beside it. A row is
kept for good only once its run is cleaned up.

**Rejected is that ending and nothing else (D2).** The rail routes a closed row whose status is
`REJECTED` to Rejected and every other closed row to Closed. A row whose status cannot be read stays in
Closed.

**The run's controls are a strip pinned at the top (D4).** The run's id, `run-controls` and `run-kept`
make one strip at the top of the run's page, pinned under the Workbench's bar while the page scrolls, as
the rail is; what is scrolled to or focused stays clear of it, as it does of the bar. The words that
explain the controls sit under it, in the run's heading, and scroll away. It comes first in the page and in the tab order: Pause while a role works, *Stop run*,
**Reject** (A2) with one confirmation that says it ends the run and deletes its worktree and branch with
any work in them, and *Force terminate* where it is offered today. They stay quiet, so the decision
remains the one raised element.

**The boxes are styles alone (D3).** Each of the four lists is as tall as its runs up to five rows and
scrolls inside itself beyond that; every row is one height, so five rows are five at any width. When
the four do not fit the window together, the lists past five give up height, down to one row, and
Operator action none (A4); below 1000 px, where the rail sits above the page, each keeps its five-row
limit. No script measures a row.

### Premise / KISS gate

Each part rests on something that already works. The terminal already takes an Esc and a typed prompt;
Temporal already records why a run was cancelled and hands it to the workflow, and lists each removal;
the run's status is already what every surface reads; client.py already owns the Stop and the removal,
refusals included; the stylesheet already pins a bar and keeps focus clear of it. Added: one ending word
and one read in the workflow, one client function, one route, the removal read for a rejected row, two
buttons, one list, a few style rules, two verbs in the demo's driver — a line typed after a press, and
a layout read at a window size — and the demo's one call to the guarded removal of an environment.
Removed: nothing — *Stop run* keeps a run's work on purpose. Given up knowingly: the run does not know it is paused, so its row still reads
as working and a pause longer than the turn's time limit fails the step; Reject does not finish in the
background — where the run has not closed in time or its host cannot remove now, it says so and the
removal that exists finishes it; the pinned strip takes a line of every run's page; and on a waiting run
the keyboard reaches *Stop run* and Reject before the decision's answers, the order the earlier design
had avoided.

### Alternatives considered

- **The workflow removing the worktree itself when it is rejected.** The client would shrink to one
  call and a reject would finish with the page closed. But a Stop would then run git, which
  architecture D31 rules out so that a host whose worker is gone never holds one; it adds a command to
  the workflow, and a second way a closing run's work is removed.
- **A paused state in the workflow.** It would stop the turn's clock and show the pause on every
  surface, at the price of a new state, a new answer and new commands, for what one key already does.
- **`REJECTED` only once the removal has succeeded.** The ending would then wait on a second host, and a
  run the operator rejected would read as merely stopped whenever its cleanup failed — the mix-up D2
  rules out.
- **Calling a run rejected when it is stopped and its work is gone.** It would list a run stopped and
  removed by hand as rejected (D2).
- **The reject's sequence in the page's script.** It ends with the tab that started it, and the suite
  runs no page script, so its failure paths would have no test.
- **A script that measures five rows.** What the pinned checklist advises against where styles can do it.

## Required invariants

1. Pause sends what the operator's own Esc sends, once a press, to the role at work and no other, and
   tells the run nothing (architecture D17).
2. Reject's Stop is the Stop as it is: no git, taken with no worker polling (architecture D31).
3. A removal runs only once the run is closed, once, through its target host's git, and is refused under
   a git side effect of the run still running (architecture D31).
4. The workflow commands nothing new, and every recorded history replays as written (D25).
5. A Stop that carries no reason ends `STOPPED`, exactly as now.
6. The server refuses an unconfirmed Reject, and nothing happens.
7. Reject never says more than happened, and retries nothing by itself. A rejected run that still keeps
   work says so on its page and in its row, and offers the removal.
8. A run is listed as rejected only by its own `REJECTED` ending (D2).
9. Every run a page holds stays reachable in its box. Operator action gives up no height, and the
   counts in the headings and in the page's title stay.
10. The pinned strip never covers what has the keyboard, or what a link scrolls to.
11. The labels `make demo` presses do not change, each control keeps a status line of its own nearest
    it, and Pause says what it did there, so the demo's driver reads every press as it does now.
12. D7 holds for every check below.

## Implementation tasks

- [x] Write the red cases below and see each fail for its own reason.
- [x] The workflow: the reason's name, and the `REJECTED` ending in `_stopped`.
- [x] `reject` in client.py — the Stop with its reason, the bounded wait, the removal.
- [x] The server: the `reject` route, confirmed, its call bounded as a removal's is; and where a
      rejected run's cleanup stands, in its row as in its page.
- [x] The page: the pinned strip with the controls and what a run kept; Pause; Reject, its confirmation,
      its result and its cleanup's standing; the *Rejected* list; the four boxes.
- [x] `make demo`: an agent that answers an Esc, a step that presses Pause and types on, a step that
      reads the layout at three window sizes, a step that presses Reject on a run at work, and the
      driver's two new verbs; its line about *Stop run* alone reworded; the environment it built for
      another host's worktree taken back when it ends.
- [x] The stable documents in the documentation plan.
- [x] The verification below, bar the suite's whole run, and the diff read against this todo.
- [ ] The WSL suite once, after the reviewer's pass on the build.

## Test-first and verification plan

### Red evidence

| case | kind | wrong today |
|---|---|---|
| a Stop carrying the reason ends the run `REJECTED`; one carrying none ends it `STOPPED` | regression guard, `test_stops.py` | every Stop ends `STOPPED` |
| Reject confirmed at an approval: the run closes `REJECTED`, its host's git discards once, it keeps nothing | acceptance, `test_workbench.py` | the route answers 404 |
| Reject while a role works: its agent ends with the run, which closes `REJECTED`, and its host's git discards once | acceptance | 404 |
| after a Reject, the run's history and each of its turns still read | acceptance (D1) | 404 |
| Reject unconfirmed: refused, the run still open, no git | regression guard | 404 |
| a removal that cannot run: at git's refusal Reject says the removal's own words; for a run not closed within the bound it answers pending, and nothing calls the run rejected yet; either way nothing is tried again, and the run's row and page say cleanup required until a removal succeeds, then cleaned up | regression guard | 404; a row says nothing of what it keeps |
| `make demo` ending with an environment it could not take back: it fails, naming it — one that is not there fails nothing, and a checkout this host's git reads keeps its own | regression guard, `test_demo.py` | it passes, having printed what it left |
| Reject of a closed run: refused as a Stop of one is | regression guard | 404 |
| the page, by `make demo`: Pause on a working run opens that role's terminal and not the other's, the agent shows it was interrupted, and `continue`, typed with no click, reaches it and the turn ends | acceptance (D5, D8) | no such control |
| the page, by `make demo`: Reject on a run at work, its question, its result, the run ending `REJECTED` with its worktree gone and its history still shown | acceptance (D8) | no such control |
| the page, in a headless browser at a wide, a narrow and a short window, at the top of a run's page and scrolled to its history: the controls in view and nothing that has the keyboard under them; a rejected run under Rejected and a stopped one under Closed; each of the four sections without a scrollbar at five runs or fewer and scrolling inside itself at more | acceptance (D8) | one list, one scroll, controls below the change |
| the `web-design-review` checklist over the changed page files finds nothing this change brought | reviewer-checked | — |

The removal's other refusals are already held by the cases beside which these go, in class `Runs`.

### Green evidence

- While working, on WSL: `bash run-tests.sh tests.orchestration.test_stops tests.orchestration.test_replay
  tests.interfaces.test_workbench tests.test_architecture`.
- Once, when done: `bash run-tests.sh` on WSL. The change touches no launching, terminal or worktree
  code, so one host is what [AGENTS.md](../AGENTS.md) asks for.
- `make demo`, with the stack up: a stack of its own beside the live one, so D7 holds. It is also where
  A5 is proven, on the live Temporal server.
- The headless-browser row, against a Workbench serving the candidate code that is not the operator's
  own — the demo's.
- Not part of this change: `tests/acceptance_restart.py`, which restarts the live stack (D7). The
  Workbench's service shows the change only once restarted, which is the operator's step after a merge.
- The operator's own, after the reviewer's pass, and no criterion of the build: Pause and a typed
  `continue` on one real turn of each kind of agent a role is bound to.

### What was run and seen — 2026-10-09

- **Baseline**, before any change, on WSL: the four modules — 32 classes, 180 tests, OK.
- **Red.** The four new cases of class `Runs` failed on the route that was not there: `404` where `200`
  or `400` was expected. The Stop's case passed when first run, the ending's line having been written
  before it; with that line put back to `STOPPED` it failed —
  `('STOPPED', 'STOPPED') != ('REJECTED', 'REJECTED')`. The table of a cleanup's standing, in class
  `Kept`, was written with its function and not seen failing.
- **Green**, on WSL: the four modules — 32 classes, 186 tests, OK.
- **Two controls**, each failing the refused-removal case and then put back: a rejected row whose
  removal cannot be read taken for cleaned up — `('REJECTED', None) != ('REJECTED', 'unknown')`; and a
  rejected row kept for good while it still keeps work —
  `('REJECTED', 'required') != ('REJECTED', 'unknown')`.
- **`make demo`**, beside the live stack, on the live Temporal server: DEMO PASSED, seven runs, the live
  stack up before and after.
  - *Pause*, pressed on a run whose engineer worked: the page said `paused the engineer: type to it in
    its terminal, and it goes on`; the keyboard was in the engineer's terminal, the only one opened;
    `continue`, typed with no click, came back on its screen as `heard: continue`; the turn's record holds
    its `Interrupted`, and the turn ended on what was typed.
  - *The layout*, with the run building, at 1600×1000, 600×900 and 1280×520: Pause, Stop run, Reject and
    Force terminate seen whole, nothing over them, at the top of the run's page and with the page
    scrolled to its history (872, 2337 and 1292 px); what then took the keyboard lay 187, 251 and 164 px
    below the strip. The lists held 1, 1, 10 and 0 runs, and only Closed scrolled. Wide: the four beside
    the run with no scroll of their own as a whole, Closed showing 3.4 rows. Narrow: above the run.
    Short: Closed down to one row, and the lists scrolling as a whole.
  - *Reject*, pressed while the engineer built: asked `Reject this run? Reject ends the run and deletes
    its worktree and its branch, with any work in them. Its history stays.`; said `rejected: its worktree
    and branch are removed`; the run ended `REJECTED`, Temporal's own word `CANCELED`, nothing left to
    clean up; its worktree and branch gone by its host's git, its agent ended; its history still read
    `you approved the plan`; and it was listed under Rejected, the run that was only stopped under Closed.
- **The same demo from a stand-in of a worktree Windows made** — this change's files as Git for Windows
  checks them out, the Makefile with CRLF, its `.git` a pointer WSL's git cannot follow: DEMO PASSED. It
  built that checkout an environment on WSL and removed it as its last act; the environments' root then
  held the main checkout's alone, and the live stack's workers were the same processes before and after.
- **`make public-check`:** passed.
- **After the reviewer's PATCH on the build**, on WSL:
  - *Red.* The three Reject cases failed on the answer's missing word — `pending` read `None` where
    `True` or `False` was expected. The demo's ending case failed with `0 == 0`: a demo whose removal
    was refused had printed what it left behind and passed.
  - *Green.* `tests.test_demo`, `tests.interfaces.test_workbench` and `tests.test_architecture` —
    22 classes, 126 tests, OK; and once the pending answer's words were last changed, the classes that
    read a Reject's answer, `Runs` and `Kept`, with `tests.test_demo` — 3 classes, 36 tests, OK.
  - *Control*, failing and then put back: the demo taking any checkout's environment, whether or not
    this host's git reads it — `the environment the live stack may be running from is never the demo's
    to remove`.
  - `make demo` was not run again. What the round changed of it is its last lines, which `test_demo.py`
    runs both ways; of the page, one branch a Reject that removes never reaches, in a script that still
    parses.
- **The checklist review** over the changed page files: three findings, each fixed — a row's focus ring
  was cut off by its list's box, and is drawn inside the row; the two groups of controls did not name
  the words that explain them, and do; a Pause that finds no agent under the terminal said nothing, and
  says so with what to do.
- **Not run:** the WSL suite whole, which waits for the reviewer's pass; a real agent, which is the
  operator's.

## Documentation plan

- **Authoritative stable owner:** architecture D31 — a Stop may carry the operator's reason, Reject is
  that Stop and then the removal, and a rejected run says where its cleanup stands; architecture D29 —
  the four groups and their boxes, the pinned strip, and Pause as the page's own key press.
- **Beside them:** the Stop invariant in
  [orchestration's structure](../app/orchestration/docs/architecture/structure.md) and the closing
  paragraph of [the stops view](../docs/architecture/diagrams/stops.md), which both name the ending a
  Stop gives.
- **Operator-facing:** [using.md](../docs/using.md), "The page": the sentence naming the lists, the
  paragraph on the terminals, and the paragraphs on *Stop run* and on removal, which place the controls
  after the decision.
- **Package level:** `client` under Owns in
  [application's structure](../app/application/docs/architecture/structure.md), and what goes through
  `application.client` in [interfaces' structure](../app/interfaces/docs/architecture/structure.md).
- **Routers:** the rows of [tests/README.md](../tests/README.md) for the three test files, and the rows of
  [tools/README.md](../tools/README.md) for the demo and its driver.
- No stable document names this todo.

## Completion criteria

1. Every case of the red matrix that the suite can hold passes, having been seen failing first.
2. The four modules above pass whole on WSL, and the WSL suite passes once.
3. `make demo` passes with its Pause and Reject steps, on the live Temporal server (A5, A6).
4. The headless-browser row passes at the three window sizes, scrolled and not, and what was pressed and
   seen is recorded here.
5. The checklist review is recorded here, with each finding fixed or answered.
6. The documents in the documentation plan say what the code does.
7. The diff holds this change alone: `activities.py`, `cli.py`, `terminal.py` and every recorded history
   are untouched.

**Standing, 2026-10-09:** 1 and 3–7 are met, and the modules' half of 2. Unmet: the WSL suite's one whole
run (2).

## Review record

### 2026-10-09 — investigation, and the operator's answers the same day

- **Trigger:** the operator, ending a run started on the wrong repository, found no single control that
  ends a run and removes its work, and did not find the controls there are.
- **First draft:** Reject as a Stop and a removal with no mark of its own; Rejected as every run that did
  not finish; boxes of five rows growing to ten.
- **The operator's answers** changed three things: only a run rejected with the button is listed as
  rejected (D2), which the run's own ending now carries; the boxes are adaptive and have no control (D3);
  the run's controls move to the top of its page (D4). D1 gained the kept history; D5 and D8 were added.
- **Rechecked for something simpler, at the operator's asking:** Reject no longer words its own
  outcomes — the removal's refusals are its words; no history is recorded for a rejected run, since it
  issues a Stop's commands.
- **`make demo` reasoned through, at the operator's asking:** nothing in it needs the checkout's own git
  or touches the live workers; the two links that were guesses — make reading a CRLF Makefile, and the
  API naming the event's cause as the user's reason — were checked. Found on the way: the environment it
  leaves on WSL for a worktree Windows made.

### 2026-10-09 — the external reviewer: PATCH

- **Worked in, as the reviewer's and the agent's:** the controls pinned while the page scrolls; all four
  lists boxed; a rejected run saying where its cleanup stands; the cases for a Reject at work and for
  the history after one; Pause proven in a browser through a typed `continue`, which gives the demo's
  driver one verb; the scrolled state in the browser row; a real-agent check left to the operator.
- **Not taken as stated:** that the pinned controls and the four boxes were explicit operator
  requirements changed into assumptions — the operator's words, quoted in D3 and D4, say "the top" and
  name Closed and Rejected, so both were open and are now settled on their merits; and that Pause rests
  on vendor behaviour of its own — it sends the byte the terminal sends today when the operator presses
  Esc, over the same socket.
- **Kept against the review's wording:** `REJECTED` is still the run's ending before the removal runs.
  It records what the operator did (D2); the cleanup's standing is shown beside it.
- **Authority:** D1–D8 as they stand; no gate open.

### 2026-10-09 — the external reviewer: PASS on the plan, and the build

- **The reviewer's one caution, taken:** the environment `make demo` builds on WSL for a worktree Windows
  made is taken back by the demo itself, through the guarded removal — the reviewer's and the agent's.
- **Where the build differs from the plan's wording, each keeping what was approved:**
  - the strip names the run by its id, and the run's title stays whole in its heading;
  - a list of five or fewer never gives up a row, and Operator action none at all (A4);
  - a rejected row whose removal cannot be read just now says `Rejected` alone, and is read again;
  - where a Reject finds nothing to remove, the page says so in the removal's own words and does not
    call the run rejected — a merge already running lands and ends the run merged;
  - the demo's driver gained two verbs, the typed line and the layout read.
- **Found in the browser and fixed before this record:** a list past five did not give up height, a flex
  item's automatic minimum being its whole content, so the lists scrolled as a whole and Rejected lay
  below the window's edge; the layout read now refuses that.
- **Open:** the WSL suite's whole run, after the reviewer's pass on the build; then the operator's check
  on a real agent.

### 2026-10-09 — the external reviewer: PATCH on the build

- **Both points taken, the reviewer's and the agent's; neither refuted.**
  - A Reject whose run had not closed in time was reported by the page as rejected, cleanup required,
    while Temporal still held the run open. Its answer now says `pending`, and the page says the run is
    still stopping. Its words had also read as if the removal would follow by itself; they now say the
    removal is the operator's once the run has closed, and do not say how it will end — a merge already
    running still decides that.
  - A demo whose environment could not be taken back printed that and passed. That environment is now
    something left behind like any other, and fails the demo.
- **Added beside the second:** the guard that keeps a checkout this host's git reads — it had no test.
- **Seen and left, as outside the two points:** a Reject whose run is force-terminated during its wait
  is still worded as rejected in the press's own line; the run's heading says how it ended.
