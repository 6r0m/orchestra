# Approve with a note

**Status:** BUILT 2026-11-06 — red, then green; the reviewer's PATCH for page and worker of different versions
taken. It awaits the full suite, the workers' restart, and the operator's word to close it.
**Scope:** an approval's answer ([workflow.py](../app/orchestration/workflow.py) `_loop`, `_approval`, `_stop`,
the answer's validator), the answer's one path for both surfaces ([client.py](../app/application/client.py)
`answer`), the command line's `yes` ([cli.py](../app/interfaces/cli.py) `parse_answer`, `answer_line`), the
stop's note and Approve on the page ([run.js](../app/interfaces/workbench/static/run.js)), and the recorded
history ([record_histories.py](../tests/record_histories.py)).
**Stable documentation owner:** D6 in the [architecture](../docs/architecture/structure.md) and its
[stops diagram](../docs/architecture/diagrams/stops.md); [using.md](../docs/using.md), the decision's paragraph
and the command line's answers.

## Goal

At an approval the operator can approve and add a note: the run goes on to the next step, and the note reaches the
agents who do it, with no round of the approved work first — and a note is never lost unsaid.

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
- **The stop says whether it takes one (`noted`), and nothing else does** (the reviewer's PATCH): a worker from
  before notes takes an approve with words and drops them, saying nothing, while the page — served from disk —
  already offers the note. So `noted` is set only where `workflow.patched("approve-with-a-note")` holds and the
  approval does not end the run; the validator refuses a note elsewhere, the answer's one path refuses it before
  sending — whatever worker holds the run — and the page and the command line offer the note only there. A run
  recorded before replays as it ran (D25); which stop takes a note is read from the stop, never from the run's age.
- **`yes` itself is no note:** the command line sends only the words after it.

## What changed

- The workflow: an approval's stop says `noted`, the patch's marker recorded as it is drawn; an approve's words,
  once on to the next stage, become its guidance; a note at a stop that does not say `noted` is refused, saying
  why; the trace records the answer as `approve: <note>`.
- The answer's path (`client.answer`): a note with an approve to a stop that does not say `noted` is refused before
  anything is sent.
- The command line: `yes <note>` approves with it where the stop takes one, is refused elsewhere, listing the
  answers the stop takes; `yes` alone carries no words.
- The page: where the stop takes a note, the note's label names both answers and Approve reads *Approve with note*
  while one is written; elsewhere Approve stays *Approve*, and a note written beside it is not sent — the page says
  why at the note.

## Verification

- **Red, first round** (the new tests against the staged code, `tmp/agent/approve-note/red.sh`, throwaway): the old
  command line could not send `yes <note>`; `yes` was sent as words.
- **Red, the reviewer's PATCH** (the changed tests against the first round's code): against
  `control_workflows.NoteDroppingRun` — an approval stop as a worker from before notes publishes it, recording
  every answer — the note was sent (`NotAccepted not raised`); no stop said `noted`; `yes <note>` was parsed at a
  stop that does not say it takes one.
- **Green:** `tests.orchestration.test_stops.NamedAnswers.test_a_note_never_reaches_a_worker_that_would_drop_it` —
  refused through the shared client and the command line, nothing sent, the approve alone taken;
  `tests.orchestration.test_workflow.Routing` — the note to the build and its verification, `noted` on the stop,
  none at the run's end, refused there by the workflow itself; `tests.interfaces.test_cli`.
- **The history:** `approval_with_a_note_stop` recorded again — 106 events, the `approve-with-a-note` marker as the
  approval is drawn, before its answer — and every recorded history replays.
