# Every button says what it does

**Status:** DONE 2026-11-05 — the goal met: reviewer PASS; checked on the live Workbench's views and a run's
page and, in `make demo`, at a run's approval; green in the full suite on both hosts; closed on the
operator's word.
**Scope:** the Workbench page's buttons ([index.html](../../app/interfaces/workbench/static/index.html) and the
scripts that make buttons), and their check ([demo_press.py](../../tools/demo_press.py) `hints`).
**Stable documentation owner:** [using.md](../../docs/using.md), where a button's name is used.

## Goal

A button whose name does not say what follows says it when the pointer rests on it.

## Authority register

### Operator decisions

- **D1** Buttons whose names are unclear get hints.
  - 2026-11-05, operator: *"what is read it again button? could you add intuitive hints to such strange buttons?"*

## What changed

- Every button and button-styled link shown outside a dialog has a `title`: what it does, and — where it is not
  plain — what follows (a Stop keeps the worktree, Reject deletes it, Apply reaches only runs started after it).
  A dialog's own buttons are left as they are: the dialog says what it asks.
- The change's *Read it again* is now **Refresh**, saying that what is listed is the change as it was when read;
  a failed read's *Read again* is **Try again**.
- `demo_press.py hints` lists every button shown without one, on New run, Settings, the stack's panel and a run's
  page; `make demo` runs it at a run's approval, where its answers show.

## Review record

- **External reviewer, 2026-11-05 — PASS**, with the live change's final review.

## Verification

- **On the live Workbench:** before the last fix, `hints` named the top bar's *New run* on both views; after it,
  *32 buttons shown across #new, #settings: each says what it does on hover*; at the close, with the operator's
  run at work, *39 buttons shown across #new, #settings, #run=…*, each with its hint.
- **`make demo`, at a run's approval:** *36 buttons shown across #new, #settings, #run=…: each says what it does
  on hover*; DEMO PASSED, 115 checks.
- **The full suite, after the final PASS:** on WSL 150 classes, 744 tests, OK; on Windows 102 classes, 517
  tests, OK.
