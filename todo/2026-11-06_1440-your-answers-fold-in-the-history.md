# Your answers fold in the history

**Status:** BUILT 2026-11-06 — seen on the operator's run's history. It awaits the external reviewer and the
operator's word to close it.
**Scope:** how the run's history draws the operator's answers ([run.js](../app/interfaces/workbench/static/run.js)
`answerRow`, [style.css](../app/interfaces/workbench/static/style.css)).
**Stable documentation owner:** [using.md](../docs/using.md), the history's paragraph.

## Goal

An answer of the operator's in the history folds as a turn does, so a long note is one click from read, never a
page to scroll past.

## Authority register

### Operator decisions

- **D1** The operator's answers in the history fold, as the agents' turns do.
  - 2026-11-06, operator: *"where you in history I can't hide it like arhcitect and egineer by spoiler , so it's
    very huge scrolling instead one click to hide if I don't need to read it"*

## Verified evidence

- **What there was.** A turn is a `details` folded to its head and its answer's first line; an answer was a plain
  row with every word of the note under it — on the operator's run, an audit pasted whole, twice.

## What changed

- An answer with words is a `details`, folded to its head and its words' first line, kept as written; it stays open
  once opened across the page's reads, keyed as a turn is. An answer with no words — an approval — stays a row.

## Verification

- **On the operator's run** (`tmp/agent/terminal-scroll/answers.py`, throwaway): its six answers with words folded
  to 50 px each, the two without words rows of 30 px; one opened to 191 px on a click and stayed open after the
  page's reads.
- **`make demo`:** DEMO PASSED, 117 checks, none failed — its history checks read an answer's head, which folding
  leaves in sight; the folding itself is not among them.
