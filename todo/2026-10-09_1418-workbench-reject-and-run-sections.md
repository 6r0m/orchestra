# Workbench: Pause and Reject at the top of a run's page, and closed runs in scrolling sections

**Status:** REVIEW REQUIRED
**Scope:** how a run is ended from the page — one ending word in
[workflow.py](../app/orchestration/workflow.py), the shared client in
[client.py](../app/application/client.py), one route in
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

A run's controls sit at the top of its page. **Pause** interrupts the agent at work and puts the
keyboard in its terminal, so the operator types to it and it goes on. **Reject** ends the run and
removes everything it left in its repository, with one confirmation, and its history stays readable.
That run, and only a run rejected that way, is listed under **Rejected**. Closed and Rejected each
scroll inside themselves once they hold more than five runs, on any window.

## Authority register

### Operator decisions

All 2026-10-09, in the operator's words.

- **D1** A Reject button that cleans everything up automatically; the run's history is kept.
  - *"reject button that automatically cleanup all and proper section"*; *"all history should preserve
    but mess should be removed"*.
- **D2** Rejected lists only the runs rejected with that button. A stopped run is not rejected.
  - *"only that run which we explicitly press reject button, stop it's not reject!"*
- **D3** Closed and Rejected each become a scroll box, adaptively, once they hold more than five runs.
  - *"sections with scrollbars"*; *"ok let's simplify - adaptive scrollbox if over 5 runs"*; *"read
    about adaptive design please"*.
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

### Working assumptions

- **A1 [ACTIVE]:** Pause is the Esc a role's terminal already takes, sent for the operator: the run is
  not told, the turn's clock keeps running, and what the operator then types steers that turn
  (architecture D17).
- **A2 [ACTIVE]:** Reject is offered in every state that offers *Stop run*. At the final gate *Discard*
  stays the stop's own answer.
- **A3 [ACTIVE]:** "The top" is the header of the run's own page, not the Workbench's bar, and it is not
  pinned while the page scrolls. "Control-plane buttons" are the run's own controls and the removal of
  what a closed run kept; a stop's answers stay in its decision, beside their evidence.
- **A4 [ACTIVE]:** On a window too short for five rows in each box, a box shows fewer and still scrolls.
- **A5 [ACTIVE]:** The live Temporal server hands a cancellation's reason to the workflow as the test
  server does. Unverified on the live server.
- **A6 [ACTIVE]:** `make demo` can run against the candidate code before a merge. Unverified from inside
  a run's own worktree.

## Non-goals

- No paused state in the workflow, and nothing that resumes a stopped run (A1).
- Reject stays Temporal's cancellation: no new stop answer, activity, workflow type or command.
- No `--reject` on the command line, which has no removal either (architecture D31).
- A run stopped and later removed by hand is not listed as rejected (D2).
- Operator action and Working are not boxed, and a stop's answers do not move (A3).
- The labels of the controls that exist do not change.
- No change to how many closed runs a page holds, or to *Load older runs*.
- The New run form preselecting the first listed repository is a separate defect, not fixed here.

## Verified evidence

Read from the checkout at `a0846f7` on 2026-10-09. One probe was run; no test of the suite was.

**Verified facts**

- **A cancellation can say why, and the workflow can read it.** The pinned `temporalio` 1.33.0 has
  `WorkflowHandle.cancel(reason=…)` and `workflow.cancellation_reason()`, read in the installed package.
  Probed on the time-skipping test server the suite uses: a cancellation sent with the reason `reject`
  was read by the workflow as `reject`, and one sent with none as the empty string.
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
  host's worker, and runs once.
- **An interrupted turn goes on with what the operator types.** A role's terminal on the page sends each
  key over that role's socket while its agent is live (`term.onData` in
  [terminals.js](../app/interfaces/workbench/static/terminals.js)); on Windows a lone Esc is delivered
  as the key ([ptyhost.py](../app/agents/ptyhost.py)). An interrupt completes nothing, and the turn ends
  on the completion of a prompt typed after it (architecture D17;
  `test_esc_and_typing_reach_the_agent_and_an_interrupt_completes_nothing` in
  [test_terminal.py](../tests/agents/test_terminal.py)). The turn's own time limit keeps running
  meanwhile (`timeout_seconds`, an hour as shipped).
- **The run's controls sit far down its page:** `run-controls` and `run-kept` follow the decision and
  the whole change in [index.html](../app/interfaces/workbench/static/index.html), and the terminals
  come after those. That was chosen: the [workbench UX todo](done/2026-09-25_2334-workbench-ux.md) put a
  run's decision first in the page and in the tab order, and its own controls after it.
- **The rail:** three lists, every closed run in the third (`GROUPS` and `render` in
  [rail.js](../app/interfaces/workbench/static/rail.js)); one scroll area for all of it (`.rail` in
  [style.css](../app/interfaces/workbench/static/style.css)). Below 1000 px wide the rail sits above the
  page at its full height, so every closed run a page holds comes before the run's own page. A row's
  view already carries its `status` (`view` in client.py).
- **Tests:** each half of a reject is covered in
  [test_workbench.py](../tests/interfaces/test_workbench.py), class `Runs`; a Stop's endings in
  [test_stops.py](../tests/orchestration/test_stops.py). The suite never runs the page's scripts; its
  controls are pressed by `make demo`, by label, in headless Edge
  ([demo.py](../tools/demo.py), [demo_press.py](../tools/demo_press.py)). The demo's agents answer no
  Esc today; the suite's stand-in CLI does ([fake_cli.py](../tests/fake_cli.py), its `interrupt` word).
- **Web-interface practice**, from the checklist the `web-design-review` skill pins: a destructive
  action needs a confirmation; flex or grid over script measurement for layout; an inner scroll area
  contains its overscroll; nothing pinned may cover the focused element.

**Inferences**

- A run waiting at a stop closes within the Stop's cleanup bound even with its target host's worker
  gone, so a bounded wait can follow a Stop.
- The reason comes from the run's own history, so reading it is the same on every replay.

**Unverified**

- A5 and A6.

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
from one that was merely stopped. And the Closed list is as long as the page holds, which on a narrow
window is all above the run's own page.

## Decision

**Pause is the page pressing Esc for the operator (D5, A1).** While a role works, **Pause** in the
run's header opens that role's terminal, sends it the one Esc its own keyboard would, and leaves the
keyboard there. The words beside it say what follows: what is typed steers this turn, the run moves on
when the agent has answered it, and the turn's time limit keeps running. Nothing but the page changes.

**Reject is a Stop that carries its reason, and then the removal.** `reject` in client.py cancels the
run with a reason the workflow module names, waits until Temporal reports the run closed — for the
Stop's own cleanup bound and a margin, no longer — and then calls `remove_worktree`. Where that cannot
remove, its own refusal is what Reject says: the run is not closed yet, it kept nothing, its host's
worker is down, git refused. The server takes it at `POST /api/runs/<run-id>/reject`, confirmed as a
removal is.

**The run itself says how it ended.** In `_stopped`, a run whose cancellation carries that reason ends
`REJECTED`; any other Stop ends `STOPPED`, as now. Nothing else in the workflow changes: the same
cleanup activity, handed `STOPPED` as now, and no command added — so the histories recorded for a Stop
already hold every command a reject issues.

**Rejected is that ending and nothing else (D2).** The rail routes a closed row whose status is
`REJECTED` to Rejected and every other closed row to Closed; its label reads *Rejected*. A row whose
status cannot be read stays in Closed.

**The run's controls move to its header (D4).** `run-controls` and `run-kept` sit at the top of the
run's page, beside its title, in that order in the page and in the tab order: Pause while a role works,
*Stop run*, **Reject** (A2) with one confirmation that says it ends the run and deletes its worktree and
branch with any work in them, and *Force terminate* where it is offered today. They stay quiet, so the
decision remains the one raised element.

**The boxes are styles alone (D3).** Closed and Rejected each show at most five rows and scroll inside
themselves beyond that; rows in those two lists share one height, so five is five at any width; the
limit gives way on a short window (A4); and the same boxes hold below 1000 px, where the rail sits above
the page. No script measures a row.

### Premise / KISS gate

Each part rests on something that already works. The terminal already takes an Esc and a typed prompt;
Temporal already records why a run was cancelled and hands it to the workflow; the run's status is
already what every surface reads; client.py already owns the Stop and the removal, refusals included.
Added: one ending word and one read in the workflow, one client function, one route, two buttons, one
list, a few style rules. Removed: nothing — *Stop run* keeps a run's work on purpose. Given up
knowingly: the run does not know it is paused, so its row still reads as working and a pause longer than
the turn's time limit fails the step; Reject does not finish in the background — where the run has not
closed in time or its host cannot remove now, it says so and the removal that exists finishes it; and
on a waiting run the keyboard now reaches *Stop run* and Reject before the decision's answers, the order
the earlier design had avoided.

### Alternatives considered

- **The workflow removing the worktree itself when it is rejected.** The client would shrink to one
  call and a reject would finish with the page closed. But a Stop would then run git, which
  architecture D31 rules out so that a host whose worker is gone never holds one; it adds a command to
  the workflow, and a second way a closing run's work is removed.
- **A paused state in the workflow.** It would stop the turn's clock and show the pause on every
  surface, at the price of a new state, a new answer and new commands, for what one key already does.
- **Calling a run rejected when it is stopped and its work is gone.** It would list a run stopped and
  removed by hand as rejected (D2), cost one more Temporal read per closed row, and leave a cached row
  stale when a run is removed later.
- **The reject's sequence in the page's script.** It ends with the tab that started it, and the suite
  runs no page script, so its failure paths would have no test.
- **A script that measures five rows, or a header pinned while the page scrolls.** The first is what the
  pinned checklist advises against where styles can do it; the second can cover what has focus on a
  small window, for controls that are one scroll away.

## Required invariants

1. Pause sends what the operator's own Esc sends, once a press, to the role at work, and tells the run
   nothing (architecture D17).
2. Reject's Stop is the Stop as it is: no git, taken with no worker polling (architecture D31).
3. A removal runs only once the run is closed, once, through its target host's git, and is refused under
   a git side effect of the run still running (architecture D31).
4. The workflow commands nothing new, and every recorded history replays as written (D25).
5. A Stop that carries no reason ends `STOPPED`, exactly as now.
6. The server refuses an unconfirmed Reject, and nothing happens.
7. Reject never says more than happened, and retries nothing by itself.
8. A run is listed as rejected only by its own `REJECTED` ending (D2).
9. A run that waits or works is never boxed or hidden (architecture D29), and every closed run a page
   holds stays reachable in its box.
10. The labels `make demo` presses do not change.
11. D7 holds for every check below.

## Implementation tasks

- [ ] Write the red cases below and see each fail for its own reason.
- [ ] The workflow: the reason's name, and the `REJECTED` ending in `_stopped`.
- [ ] `reject` in client.py — the Stop with its reason, the bounded wait, the removal.
- [ ] The server's `reject` route, confirmed, its call bounded as a removal's is.
- [ ] The page: the controls and what a run kept in the run's header; Pause; Reject, its confirmation
      and its result; the *Rejected* label and list; the two boxes.
- [ ] `make demo`: a step that presses Pause and one that presses Reject, with an agent that answers an
      Esc; its line about *Stop run* alone reworded.
- [ ] The stable documents in the documentation plan.
- [ ] The verification below, then the diff read against this todo.

## Test-first and verification plan

### Red evidence

| case | kind | wrong today |
|---|---|---|
| a Stop carrying the reason ends the run `REJECTED`; one carrying none ends it `STOPPED` | regression guard, `test_stops.py` | every Stop ends `STOPPED` |
| Reject confirmed at an approval: the run closes `REJECTED`, its host's git discards once, it keeps nothing | acceptance, `test_workbench.py` | the route answers 404 |
| Reject unconfirmed: refused, the run still open, no git | regression guard | 404 |
| a removal that cannot run — git's refusal, and a run not closed within the bound: Reject says the removal's own words, and nothing is tried again | regression guard | 404 |
| Reject of a closed run: refused as a Stop of one is | regression guard | 404 |
| the page, by `make demo`: Pause in the header of a working run opens its role's terminal, the agent shows it was interrupted, a typed line reaches it and the turn ends | acceptance (D8) | no such control |
| the page, by `make demo`: Reject in the header, its question, its result, the run ending `REJECTED` with its worktree gone | acceptance (D8) | no such control |
| the page, in a headless browser at a wide, a narrow and a short window: the controls at the top of the run's page; a rejected run under Rejected and a stopped one under Closed; a section of five runs or fewer without a scrollbar, one of more scrolling inside itself; Operator action and Working whole | acceptance (D8) | one list, one scroll, controls below the change |
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

## Documentation plan

- **Authoritative stable owner:** architecture D31 — a Stop may carry the operator's reason, and Reject
  is that Stop and then the removal; architecture D29 — the four groups, the boxes, where a run's
  controls sit, and Pause as the page's own key press.
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
- **Routers:** the rows of [tests/README.md](../tests/README.md) for the two test files, and the
  `demo.py` row of [tools/README.md](../tools/README.md).
- No stable document names this todo.

## Completion criteria

1. Every case of the red matrix that the suite can hold passes, having been seen failing first.
2. The four modules above pass whole on WSL, and the WSL suite passes once.
3. `make demo` passes with its Pause and Reject steps, on the live Temporal server (A5, A6).
4. The headless-browser row passes at the three window sizes, and what was pressed and seen is recorded
   here.
5. The checklist review is recorded here, with each finding fixed or answered.
6. The documents in the documentation plan say what the code does.
7. The diff holds this change alone: `activities.py`, `cli.py`, `terminal.py` and every recorded history
   are untouched.

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
  issues a Stop's commands; the demo's driver needs no new verb for the lists, which the headless row
  reads.
- **Authority:** D1–D8 as they stand; no gate open.
