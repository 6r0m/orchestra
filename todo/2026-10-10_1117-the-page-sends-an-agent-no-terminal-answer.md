# The page sends an agent no answer of its own terminal's

**Status:** BUILT 2026-10-10 — the one gap the external reviewer named is closed below. It awaits the
reviewer's PASS, and the operator's word to close it.
**Scope:** what a role's terminal on the page hands on to its agent
([terminals.js](../app/interfaces/workbench/static/terminals.js)), and the scripted proof of it in
`make demo` ([demo.py](../tools/demo.py)). Nothing on a host changes.
**Stable documentation owner:** the invariant in
[interfaces' structure](../app/interfaces/docs/architecture/structure.md); [using.md](../docs/using.md)
for what the operator gives up for it.

## Goal

What an agent reads in its prompt is what the operator typed and pressed — never something the page's own
terminal answered for itself.

## Authority register

### Operator decisions

- **D1** The reviewer's feedback is judged against the code, and what holds is fixed.
  - 2026-10-10, operator: *"Critically evaluate the reviewer's feedback against the actual code … Update
    the code/docs to fix issues affecting current functionality or future scalability."*

### Decided with the external reviewer — the reviewer's and the agent's

- **A clean prompt over three key chords.** A cursor's report from the top row and F3 held with Shift, Alt
  or Ctrl are the same bytes, so neither is sent.
- **Tracked here**, apart from the
  [Pause and Reject change](done/2026-10-09_1418-workbench-reject-and-run-sections.md), which stays closed.

## Verified evidence

- **Where it came from.** In that change's live check, with Codex at work, the page's terminal on
  connecting sent Codex its own answers to the questions Codex's CLI had asked its terminal as it started —
  the record is drawn again from its start on every connection — and they stood in Codex's prompt ahead of
  the operator's words. The page was then made to drop what is shaped as such an answer, except
  `ESC [ 1 ; 2…8 R`, kept as modified F3.
- **The reviewer's finding**, 2026-10-10: those bytes are also a cursor's report from row 1, columns 2 to
  8. The ambiguity is the protocol's own, so the stated invariant did not hold.
- **Reproduced in a browser before the fix:** a scripted agent that asks where its cursor is from row 1,
  column 2 was sent the report when the page's terminal connected.

## What changed

- [terminals.js](../app/interfaces/workbench/static/terminals.js): the exception for modified F3 is gone.
  What is shaped as a terminal's answer is not sent, those chords with it.
- [demo.py](../tools/demo.py): the scripted engineer asks, as it starts, where its cursor is from the top
  row's second column, beside the questions it already asked.
- The invariant with what is given up for it, in interfaces' structure; the operator's side of it in
  using.md; the demo's row in [tools/README.md](../tools/README.md).

## Considered and not taken

- **Telling a press from an answer by where it comes from.** xterm reports a key press apart from the data
  it then sends, so the chords could be kept. That leans on the order two of its events fire in, for chords
  neither vendor's CLI is known to use.

## Verification

- **Red:** `make demo` with the new question and the exception still there failed at `the page's terminal,
  connected, sent the engineer nothing`.
- **Green:** with the exception gone, DEMO PASSED — nothing sent on connecting, Pause's Esc interrupting
  the engineer, and `continue`, typed with no click, heard alone.
- **The page's rule, run from its own source:** fourteen kinds of answer dropped, the top row's cursor
  reports among them; nineteen keys and typed texts sent, the other function keys held with Shift among
  them; Shift+F3 and Ctrl+F3 dropped, as documented.
- **On WSL:** `tests.test_demo` and `tests.test_architecture` — 9 classes, 45 tests, OK.
- **Not run:** the whole suite, which runs no page script; a real agent, which this needs none of.
