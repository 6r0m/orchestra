# A run's change, live, as the main block of its page

**Status:** BUILT 2026-11-05 — red, then green in its tests and in `make demo`. It awaits the external
reviewer's PASS and the operator's word to close it; the live workers serve the change once restarted.
**Scope:** the run's page — its one *Change* section, moved up and kept current — and the read behind it.
**Stable documentation owner:** [using.md](../docs/using.md) for what the operator sees; the interfaces' and
agents' structure documents for whichever read is chosen.

## Goal

The run's change is its result, so it is the page's main block: right under what the run is doing now, the
files its worktree has changed, kept current while it works, each opening into its diff — what an agent is
doing reads from its work, not only from its terminal. One section, never two views of one change.

## Authority register

### Operator decisions

- **D1** A block on the run's page, near its worktree, shows the files the run is changing, live.
  - 2026-11-05, operator: *"I need some how see live changes files in some properly ui/ux block to this task,
    so I need understand what's going on, maybe better give it some spoiler below worktree, think about
    observability and user experience"*
  - 2026-11-05, operator, on where: *"for me on top it's should be as result main focus"* — the change is
    the run's result, the main block near the top, not a spoiler.
- **D2** The top block is the run's whole change, summarised; each turn's own change stays in the history,
  as it is.
  - 2026-11-05, operator: *"we could keep per role changes as we do already but we need common changes on top
    to summarize, agreed?"* — agreed.

### Decided by the agent, by the direction set

- **B, pushed by the run's worker.** A mechanism, settled by D1 and D2: live without a Temporal execution per
  look, as a terminal's bytes already reach the page.

### Ownership — unchanged by this

- **Git** owns the files, in the run's worktree. **The workflow** owns the run's result: its base, the tree
  each review judged, what merges — already in its history. **The run's host's worker** only reads that host's
  git, as every change read already does; it keeps nothing. **The page** shows it. A live list is a view of
  work in progress, never a result: it is not recorded in Temporal.

## Verified evidence

- **What there is.** The run's *Change* section reads one snapshot of the worktree — its files, each opening
  into its diff, and the patch — on demand (*Read the change*), and on its own only at a stop that judges a
  change. It sits after the history while the run works, so it is out of sight, and it is never live.
- **What a read costs.** Each read is a `ReviewDiff` workflow on the run's own queue, executed on its host:
  one Temporal execution per read, kept as long as Temporal keeps any. The read writes a tree from a private
  copy of the worktree's index — exact, and what a review must see, but heavy to repeat every few seconds on
  a large worktree.
- **What the page already reaches.** Each host's worker serves the run's terminals over its own WebSocket,
  which the page connects to with its token; nothing else is served there.

## How the page learns of a change — transport only

Both read the same git, through the same worker; they differ only in how the news reaches the page.

| | A — poll the existing read | B — pushed on the connection the page already has to the worker (recommended) |
|---|---|---|
| How | While a role works and the run's page is open, the page reads the change every ~10 s through `ReviewDiff` | The worker the page already connects to serves `/<run>/changes`: while someone watches, it reads the worktree's changed files against the run's base every ~2 s, and sends only when they change |
| Live | every ~10 s | within ~2 s |
| Cost | a Temporal execution per read — hundreds on a long run, listed in Temporal's UI; a tree written each time | no Temporal record; one cheap git read per ~2 s on the host, and only while watched |
| New machinery | none | one channel beside the terminals; the worker finds the run's worktree from its own record, never from the page |
| A file's diff | the snapshot already read | opened by the existing read, once, on click |

## Proposed page

- **One Change section, moved up:** right under the line saying what the run does now, above its terminals
  and history, headed **Change — 3 files · +120 −8 · updated 4 s ago**. Nothing about it is a spoiler.
- **While the run works,** its file list — status, path, `+/−` — kept current, the file changed last first
  and marked a moment when it changes; a click opens its diff in place, read as one snapshot.
- **At a decision that judges a change,** the decision comes first and the section is the snapshot judged,
  as now; a live list never stands in for what the architect judged.
- **Once closed,** the run's last change: merged, or what its worktree still holds.
- Said plainly when there is nothing yet (*no change yet*), and when its host's worker is down (*the Windows
  worker is down: the change cannot be read*).

## Open question for the operator

- **Go ahead with B?** Pushed by the worker the page already connects to: current within ~2 s, nothing
  recorded in Temporal, cheap on a large worktree. A — the page asking the existing read every ~10 s — is
  smaller to build, but each ask is a Temporal execution and a full tree written on the host.

## Build

- **workspace** — `change_fingerprint(path)`: the worktree's `git status` (no optional locks, so the index is
  never written), HEAD, and each listed file's size and time — cheap, and changed whenever the change is.
- **application** — a change feed for this host: the run's worktree and the base it stands on now, from its
  workflow's own status (a reconcile moves the base); the fingerprint every few seconds; a summary that writes
  nothing — `change_summary(path, base)` — only when it moved; a file's diff read when its row is opened, through
  the existing reader. Its pace follows its cost: a slow read is asked less often. A run on another host, a
  worktree gone, or a status that cannot be read is said, never guessed.
- **agents** — the worker's socket serves a feed it is handed, by name, beside the terminals: same origin,
  same token; it knows nothing of git or Temporal (agents imports only foundation).
- **interfaces** — the worker hands its socket the feed; the page's one *Change* section moves up and listens
  while the run works.

## What changed

- [worktrees.py](../app/workspace/worktrees.py) `change_fingerprint`; [changes.py](../app/application/changes.py)
  `ChangeFeed`; [terminal.py](../app/agents/terminal.py) `serve(..., feeds=)`; [worker.py](../app/interfaces/worker.py)
  hands the feed over and binds it to its client.
- [worktrees.py](../app/workspace/worktrees.py) `change_summary`, which the feed sends; the page's
  [diff.js](../app/interfaces/workbench/static/diff.js) names no tree a list does not hold, and says a new file too
  large to count while the run works.
- [change.js](../app/interfaces/workbench/static/change.js): one section, first on the page; live while a role
  works on the run, a row kept while its file is unchanged; the snapshot judged under a decision that judges it;
  otherwise what was last seen, and its button. [run.js](../app/interfaces/workbench/static/run.js) decides which.
- The demo's held engineer of the run stopped at work drafts a file; the driver's `change:` mode reads it, its
  `change-rows` mode sends the page summaries in the worker's place, and its `change-idle` mode watches a waiting
  run's page.
- Docs: the agents', application's and interfaces' structure, the architecture's table and process diagram,
  using.md, tools/README.md.

## Review record

- **External reviewer, 2026-11-05 — PATCH, four findings, each taken, each verified against the code:**
  1. *An automatic snapshot writes objects:* `review_diff` builds its tree with `git add -A` and `write-tree` on a
     private index, so each look that found a change wrote blobs and a tree no ref holds until git prunes them.
     The live look is now `worktrees.change_summary` — `git diff` against the base, untracked files counted here,
     each file stamped with its size and time — which writes nothing; an exact snapshot is taken only when a file
     is opened, as the change is then.
  2. *An opened file was read again at every look:* the list was drawn anew and the open rows reopened, each
     reading its diff through Temporal. A row whose file the summary says nothing new of is now kept as it is;
     only a changed file's row is drawn anew, and read again only if it was open.
  3. *It watched while the run waited:* now only while the run is running with a role at work.
  4. *A look that read again stayed "not current":* a look that could not read now forgets its fingerprint, so the
     first that reads again sends what it reads.

## Verification

- **Red:** the new tests before the code — `tests.application.test_changes` could not import `changes`;
  `tests.agents.test_terminal.Socket`, `serve()` took no `feeds`; `tests.workspace.test_worktrees.Fingerprint`,
  no `change_fingerprint`.
- **Green:** those, with `tests.test_architecture`: 11 classes, 62 tests, OK.
- **The demo:** a first run reached the new check and failed in the driver's own print — the page's minus sign
  is not in the Windows console's code page — after the file was listed and its diff read; the driver now
  escapes what that console cannot show. The next run passed the new check and failed later, at the stack
  panel's Stop of the worker: the worker had ended — its scope then held no process, `Tasks: 0` — but systemd
  kept the empty scope active past the stop script's wait (WSL's systemd missing the cgroup's empty notice);
  that scope was stopped by hand. The run after that: DEMO PASSED, 112 checks — the change first on the run's
  page, *1 file changed · +1 −0 · read now*, listing `draft.txt` with nothing pressed, its diff opened showing
  `+ drafted while at work`; the stack panel's Stop of the worker passing as before.
- **A larger worktree, on Windows** (`tmp/agent/live-change/perf.py`, throwaway): 20,000 text files and ten
  20 MB binaries committed; five edits, one binary rewritten, three new text files and a new 30 MB binary. The
  fingerprint 0.23–0.27 s; the summary 0.54–0.65 s, objects loose and packed `(0, 20214)` before and after —
  none written; the exact snapshot, the control, 2.29 s and 15 loose objects written, the binaries among them.
  The pace now follows the whole look, the fingerprint included: a look takes at most a sixth of a watcher's
  time, between 2 and 60 seconds apart.
- **The touched modules on both hosts:** on WSL `tests.workspace.test_worktrees`, `tests.agents.test_terminal`,
  `tests.application.test_changes`, `tests.interfaces.test_workbench`, `tests.test_architecture` and
  `tests.test_demo` — 43 classes, 256 tests, OK; on Windows the first three — 21 classes, 129 tests, OK.
- **On the live Workbench:** the operator's run, waiting at its plan's approval, shows its change first on its
  page, as the snapshot that decision judges.
- **Not verified live:** the line a page says when its run's worker is up but sends no change — a worker
  started before this code — since no run of the live stack was at work to show it.
