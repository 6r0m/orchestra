# A refused start says so in a window

**Status:** BUILT 2026-11-05 — red, then green in `make demo`. It awaits the external reviewer's PASS and
the operator's word to close it.
**Scope:** what the Workbench page shows when a run it started is refused
([start.js](../app/interfaces/workbench/static/start.js), [ui.js](../app/interfaces/workbench/static/ui.js),
[index.html](../app/interfaces/workbench/static/index.html), [style.css](../app/interfaces/workbench/static/style.css),
[app.js](../app/interfaces/workbench/static/app.js)), and its scripted proof in `make demo`
([demo.py](../tools/demo.py), [demo_press.py](../tools/demo_press.py)). The workflow, the client and the
server do not change.
**Stable documentation owner:** [using.md](../docs/using.md) for what the operator sees;
[tools/README.md](../tools/README.md) for the demo's row.

## Goal

A run started from the page that is refused opens a window saying why, and the window stays until the
operator closes it.

## Authority register

### Operator decisions

- **D1** A refused start is said in a window that stays until it is explicitly closed.
  - 2026-11-05, operator: *"we need clear error window shown up until we explicitly close it, because now
    it's silently acts"*

## Verified evidence

- **What happened.** A run was started on a repository entry whose folder is no git repository. The start
  was accepted, and the run's `prepare` refused it on its host before any work — as D26 requires. The page
  navigated to the run, and the run went straight to Closed as `Refused`, its reason one line on its own
  page. Nothing else said so: the operator read it as the run silently closing.
- **Where refusals come from.** `REFUSED` is set only at a run's start
  ([workflow.py](../app/orchestration/workflow.py)): a flow it cannot follow, or `prepare` refusing — an
  agent's program, the repository or a stage's skill missing on the target host. A start can also be
  refused by the server before any run exists; the form says that only in its alert line.
- **What the page has.** The run list's rows carry `status`, not the refusal's words; the run's own read
  carries them as `state.refusal`. The page already has one modal `<dialog>`, the confirmation, which
  closes when the page moves to another view.

## What changed

- **The window.** One `<dialog>` of the page's own, opened modal: a title, what was refused, and the
  refusal's words whole. Only its Close (or Escape) closes it; the page moving to another view does not.
  A refusal arriving while one is shown waits behind it.
- **Which refusals.** The runs started from this page are watched, in memory as unsent notes are, until
  the list reads them closed: one closed `REFUSED` opens the window with its reason, read from the run.
  A start the server refuses opens it too, beside the form's alert; a start the server never answered
  says it is not confirmed, since whether a run was made is not known there.
- **Proof.** `make demo` starts a run on a listed folder that is no git repository, as the operator does,
  and reads the window: it says the refusal, stays open through the page's own reads and a move to another
  view, and closes on its Close. The demo first checks that folder is in no repository's tree, where its
  git would find that repository and the run would start on it.
- **Docs.** The operator's side in [using.md](../docs/using.md); the demo's and its driver's rows in
  [tools/README.md](../tools/README.md).

## Considered and not taken

- **Keeping the watch across a reload** in the browser's session storage. The page keeps no state of its
  own beyond what is typed and unsent; a run refused while its tab reloads still shows as refused, with its
  reason, in the list and on its page.
- **The refusal's words in every row of the run list.** The run's own read carries them, and the window
  reads them once, for one run.

## Verification

- **Red:** `make demo` with the new check and the page as it was: the start was accepted (`started
  refuse-me-at-my-…`), then *gave up waiting for the page's window saying why the run was refused*.
- **Green:** with the window, DEMO PASSED, 106 checks — the window said *The run was refused*, that nothing
  was made, the host's own words (*… is not a git repository*) and the repository and run; it stayed
  through the page's reads and a move to Worktrees and closed on its Close; the run ended `REFUSED` with no
  worktree; every other run of the demo as before.
- **Not run:** the whole suite, which runs no page script — after the external reviewer's final pass; the
  server's own refusal of a start, which the demo does not drive.
