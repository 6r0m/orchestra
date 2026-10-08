# An architect's PASS on a build means its plan's completion criteria were met

**Status:** IMPLEMENTED — awaiting the external reviewer's look (D1). The touched tests pass on both hosts; no
run with real agents has met the case yet, and the live workers hand the new words to runs started from now.
**Scope:** what `PASS` means at `verify` when the approved plan names a completion criterion the build did
not meet — [the architect's role](../roles/architect.md), and what [the engineer's](../roles/engineer.md)
reports and records. No workflow code, no new stage, no enforcement in the controller.
**Stable documentation owner:** the roles themselves, which are what a run's agents read; for the operator,
[using.md](../docs/using.md).

## Goal

A build that left one of its approved plan's completion criteria unmet does not reach the final gate as
passed, unless the operator was asked, set that criterion aside, and the todo records it.

## Authority register

### Operator decisions

- **D1** An architect does not return `PASS` with a mandatory criterion unmet, unless the operator
  explicitly approved an exception and it is documented. No new workflow engine, no complicated enforcement.
  - Date/source: 2026-10-08, the external reviewer's rule, relayed by the operator.
- **D2** What the rule leaves open is the agent's to settle by it, not put to the operator.
  - Date/source: 2026-10-08, operator: *"you already should understand the goal"*.

### Decided under D2 — the agent's

- **Every completion criterion of the approved plan is mandatory.** A plan marks none optional: what need
  not hold is not a completion criterion, and the assessment of the plan is where to say so.
- **Only the operator sets one aside.** Unmet and still meetable is the architect's `PATCH`. Unmet and not
  meetable within the change is a `BLOCKER` that names the criterion, the cause and the exception asked
  for — however unrelated the cause. Neither role amends an approved plan's criteria on its own.
- **The exception is written in the todo as the operator's decision**, by the engineer on the blocker's
  guidance, and kept in the record the closeout cuts the todo to — so the final gate shows it.

## Verified evidence (2026-10-08, run `add-one-row-to-bcfaeb28`)

- The approved plan's completion criteria named two test modules passing on WSL. Neither ran there, and
  on Windows one class of one failed. The engineer reported both, with the cause — the worktree's line
  endings, since pinned — and the evidence that the change could not have made it.
- The architect's `PASS` named the failure and called it unrelated. The judgement was right; the criterion
  was neither met nor amended, and the run reached its final gate as passed
  ([the record](done/2026-10-07_2000-reconcile-before-the-final-gate.md)).
- The architect's role said `PASS` means ready within what was reviewed, and nothing of the plan's own
  completion criteria. It already said how a human decision is asked for: a `BLOCKER`.
- A blocker at `verify` stops the run, and the operator's answer is guidance its next build turn receives
  ([the stops](../docs/architecture/diagrams/stops.md)). How a role acts is its persona's to say, carried
  by a run from its start (`app/agents/nodes.py`); nothing else in a run states what a `PASS` requires.

## What changed

- **The architect's role:** at `verify` the plan it passed is the measure — each completion criterion met
  and the evidence seen, or no `PASS`; `PATCH` for one still to be met, `BLOCKER` for one that cannot be,
  naming it; `PASS` again once the todo records the operator's exception.
- **The engineer's role:** each criterion reported as met or not, with its evidence; an unmet one neither
  dropped nor reworded; the operator's exception written into the todo before the build goes back; kept in
  the closeout's record.
- **[using.md](../docs/using.md):** what such a blocker is, and that only the operator's guidance answers it.

## Verification

- **Red first:** a test that the shipped personas carry the rule — a run's policy holding the architect's
  and the engineer's words for it — failed before the roles were changed.
- **Not provable here:** that a model, reading the words, returns `BLOCKER`. No test can hold that; the
  first run that meets the case shows it, and until then a criterion set aside by an architect is to be read
  for at the final gate.

## Completion criteria

- The external reviewer's PASS (D1).
- The touched tests on both hosts — in the review record.

## Review record

### 2026-10-08 — recorded from the external review, then built

- **Trigger:** the reviewer's follow-up to the acceptance run; first kept as an open question, then built on
  the operator's word that the goal was already given (D2).
- **Verification, the modules that read a persona, one host after the other:** WSL — settings, policy,
  activities, workflow, settings delivery, workbench, trace parity and architecture: 50 classes, 274 tests,
  OK. Windows — those of them its host suite holds: 30 classes, 158 tests, OK. `make public-check`: passed.
- **Not run:** the full suite — two role texts, one test, documents; a run with real agents.
