# Approve with a note

**Status:** BUILT 2026-11-06 — red, then green on WSL; a history recorded with its marker. It awaits the external
reviewer and the operator's word to close it.
**Scope:** an approval's answer ([workflow.py](../app/orchestration/workflow.py) `_loop`, `_approval`, `_stop`,
the answer's validator), the command line's `yes` ([cli.py](../app/interfaces/cli.py) `parse_answer`,
`answer_line`), the stop's note and Approve on the page ([run.js](../app/interfaces/workbench/static/run.js)), and
the recorded history ([record_histories.py](../tests/record_histories.py)).
**Stable documentation owner:** D6 in the [architecture](../docs/architecture/structure.md) and its
[stops diagram](../docs/architecture/diagrams/stops.md); [using.md](../docs/using.md), the decision's paragraph
and the command line's answers.

## Goal

At an approval the operator can approve and add a note: the run goes on to the next step, and the note reaches the
agents who do it, with no round of the approved work first.

## Authority register

### Operator decisions

- **D1** Approve with notes: the stage switches, and the note instructs the next stage — not a revise.
  - 2026-11-06, operator: *"I want approve but append some notes … I don't need revise, pass but with notes, for
    switch stage but instruct architect to instruct engineer atuomatically on the next stage or globally instruct
    previous stage to switch to the next stage with some hints"*

### Decided by the agent, by the direction set

- **The note is guidance to the stage approved into:** the run's existing guidance, which the next work turn's
  prompt carries and the review after it too, until that review's verdict clears it — so the engineer building
  an approved plan reads it, and the architect verifying that build judges with it. No new prompt part, no
  architect turn to relay it: both read the operator's words themselves. It says what it is: *The plan was
  approved, with this note for the work after it.*
- **Behind `workflow.patched("approve-with-a-note")`** (D25): the page sent a note typed before Approve already,
  and the command line sent `yes` itself as words, both dropped; a run recorded so replays as it ran.
- **`yes` itself is no note:** the command line sends only the words after it.
- **An approval that ends the run takes no note:** no stage would read it, so the workflow refuses one there,
  saying so (`stop.ends`), and the page and the command line offer none.

## What changed

- The workflow: an approve's words, once on to the next stage, become its guidance; a stop that ends the run says
  `ends`, and its validator refuses a note there; the trace records the answer as `approve: <note>`.
- The command line: `yes <note>` approves with it; `yes` alone carries no words; the answers listed say
  `yes [<note for the next stage>]`.
- The page: the note's label names both answers it goes with, Approve reads *Approve with note* while one is
  written, and its hover says where the note goes.

## Verification

- **Red** (the new tests against the staged code, `tmp/agent/approve-note/red.sh`, throwaway):
  `test_workflow.Routing.test_a_note_given_with_an_approval_is_guidance_to_the_stage_approved_into` — the old
  command line could not send `yes <note>`; `…test_an_approval_that_ends_the_run_takes_no_note` — no `ends`;
  `test_cli` — `yes` sent as words, no note listed. `…test_yes_alone_approves_with_no_note` passed on both, as it
  should.
- **Green:** WSL — 63 classes, 338 tests, OK, the workflow's, the command line's, the Workbench's and the replay
  of every recorded history among them.
- **The history:** `approval_with_a_note_stop` recorded — 106 events, the `approve-with-a-note` marker among them,
  the build's and the verify's inputs carrying the note — and it replays.
- **Windows:** `tests.orchestration.test_workflow`, `tests.orchestration.test_replay` among 118 tests, OK.
- **`make demo`:** DEMO PASSED, 119 checks, none failed — its merged run's plan approved from the page with a note
  typed beside it, *Approve with note* pressed by that name, and the note in the build's and the verification's
  prompts. A run before it stopped once short of its build, waiting for an approved run to reach it (300 s): not
  seen again, its cause unread — the demo now prints the run's own lines when such a wait runs out.
- **Not yet:** the workers do not run it, so the operator's run still drops a note given with Approve.
