# Copy all changes

**Status:** BUILT 2026-11-06 — used on the operator's run while it worked; `make demo` passed. It awaits the
external reviewer and the operator's word to close it.
**Scope:** the run's Change section ([change.js](../app/interfaces/workbench/static/change.js),
[diff.js](../app/interfaces/workbench/static/diff.js) `copyPatch`, [index.html](../app/interfaces/workbench/static/index.html))
and its check ([demo_press.py](../tools/demo_press.py) `change:`).
**Stable documentation owner:** [using.md](../docs/using.md), the change's paragraph.

## Goal

One press copies the run's whole change — every file, however long — whenever the operator wants it.

## Authority register

### Operator decisions

- **D1** The Change section has a button that copies all the changes to the clipboard.
  - 2026-11-06, operator: *"also need button where change to copy all changes in buffer"*

## Verified evidence

- **What there was.** *Copy patch* copies a snapshot's whole patch, but sits under the snapshot *Read the change*
  draws — not on the live list a run at work shows, where nothing copied the change.
- **What it can reuse.** `copyPatch` reads every part of one snapshot and writes the clipboard as the click's own
  (a `ClipboardItem` whose text is a promise), so reads that take long still reach the clipboard.

## What changed

- *Copy all changes*, beside the heading, at any state of the run: the press reads the change as the worktree
  holds it then (`/api/runs/<id>/diff`, the exact snapshot a file's diff is read from) and copies every part.
- `copyPatch` takes the snapshot's first part or the read that will give it, so that read is part of the press.

## Verification

- **On the operator's run, the architect at work:** `demo_press.py change:` listed the run's todo live, opened its
  diff, then pressed *Copy all changes* — the clipboard stood in for — which copied a patch of 76,083 characters
  naming the file with its words.
- **`make demo`:** DEMO PASSED, 117 checks, none failed — its run stopped at work had *Copy all changes* copy the
  patch of the file its engineer drafted (146 characters, naming `draft.txt` with its words); the new button among
  the 39 that say on hover what they do.
