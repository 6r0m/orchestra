# Copy all changes

**Status:** DONE 2026-11-09 — the goal met: used on the operator's run while it worked; reviewer PASS, its
finding on closed runs answered in the docs; `make demo` and the full suite green on both hosts; closed on the
operator's word.
**Scope:** the run's Change section ([change.js](../../app/interfaces/workbench/static/change.js),
[diff.js](../../app/interfaces/workbench/static/diff.js) `copyPatch`, [index.html](../../app/interfaces/workbench/static/index.html))
and its check ([demo_press.py](../../tools/demo_press.py) `change:`).
**Stable documentation owner:** [using.md](../../docs/using.md), the change's paragraph.

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

- *Copy all changes*, beside the heading, wherever the Change section is — the run at work, waiting, or closed
  keeping its worktree: the press reads the change as the worktree holds it then (`/api/runs/<id>/diff`, the exact
  snapshot a file's diff is read from) and copies every part. A run merged or discarded has no worktree and no
  Change section (`renderChange`, as before); its turns' changes stay in its history. A press racing the merge
  that removes the worktree says *Copy failed*, git's refusal on hover.
- Reviewer, 2026-11-06, PATCH: *the documentation promises the button after closure, and the read is refused once
  the worktree is gone*. The wording was loose — [using.md](../../docs/using.md) now says closed keeping its
  worktree — but no press reaches that refusal from the page; copying a merged run's last judged snapshot is a
  capability not asked for, and a merged change is in git.
- `copyPatch` takes the snapshot's first part or the read that will give it, so that read is part of the press.

## Verification

- **On the operator's run, the architect at work:** `demo_press.py change:` listed the run's todo live, opened its
  diff, then pressed *Copy all changes* — the clipboard stood in for — which copied a patch of 76,083 characters
  naming the file with its words.
- **`make demo`:** DEMO PASSED, 117 checks, none failed — its run stopped at work had *Copy all changes* copy the
  patch of the file its engineer drafted (146 characters, naming `draft.txt` with its words); the new button among
  the 39 that say on hover what they do. Run again after the review: DEMO PASSED, 117 checks, none failed, its
  merged run offering neither *Copy all changes* nor *Read the change*, its worktree gone with the merge (`absent:`).
