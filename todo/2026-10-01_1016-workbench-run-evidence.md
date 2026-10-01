# Workbench run evidence: the change by file, history as what each role received and produced

**Status:** REVIEW REQUIRED — investigation only; nothing implemented. Q1–Q3 are closed by D5–D7.
**Scope:** the Workbench run page's Change, History and run controls ([static/](../app/interfaces/workbench/static/),
[server.py](../app/interfaces/workbench/server.py)); the change read on the run's host
([worktrees.py](../app/workspace/worktrees.py) `review_diff`, the `ReviewDiff` workflow and activity); Temporal
reads in [client.py](../app/application/client.py); prompt parts beside their composer
([nodes.py](../app/agents/nodes.py)); the browser acceptance ([demo.py](../tools/demo.py),
[demo_press.py](../tools/demo_press.py)) and the documents that describe the page.
**Stable documentation owner:** [docs/using.md](../docs/using.md) (the page as the operator uses it); the
interfaces' [structure.md](../app/interfaces/docs/architecture/structure.md) (the page's composition and what it
reads); architecture D29 in [structure.md](../docs/architecture/structure.md) (the plain page and its vendored
dependencies).

## Contents

- [Goal](#goal) · [Authority register](#authority-register) · [Non-goals](#non-goals)
- [Verified evidence](#verified-evidence) · [Current architecture](#current-architecture-and-source-of-truth)
- [Problem](#problem-and-root-cause) · [Decision](#decision) · [Invariants](#required-invariants)
- [Tasks](#implementation-tasks) · [Verification](#test-first-and-verification-plan)
- [Documentation](#documentation-plan) · [Completion](#completion-criteria) · [Review record](#review-record)

## Goal

On a run's page the operator understands the run quickly: which files its change touches, each readable as a
proper diff; and, turn by turn, what each role was given and what it gave back — its conclusion, its verdict and
the files it changed that round — with the operator's own answers between. The terminals stay the place for the
full live session.

## Authority register

### Operator decisions

- **D1** The change shows each changed file by its exact path; clicking one shows that file's diff the way an
  editor does — the whole file viewable, added lines green, removed red. Prefer a proven tool over writing one;
  installing one is acceptable.
  - Effect: a file list and a per-file diff viewer replace the stat and the single patch block; a vendored
    library is in scope, subject to the page's constraints (Q1).
  - Reason: not stated.
  - Date/source: 2026-10-01, operator: *"with change I need to see exact files path and click them to see nice
    diff - some out of box like vscode do, if need some install into our system we could consider it or do it
    kiss from scratch but if better not reinvent the wheel - install some best. so goal I could click on each
    changed file and see nicely full file with green added and red deleted as usual diff do."*
- **D2** The raw patch stays available for copying, but small, with a Copy button.
  - Effect: the patch block shrinks to a bounded box with Copy; reading happens in the viewer (D1).
  - Reason: *"it need in fact only copy paste if needed"*.
  - Date/source: 2026-10-01, operator: *"also window for copy paste is good but very huge - it need in fact only
    copy paste if needed so smaller and copy button."*
- **D3** History is for quick understanding: for each stage and iteration, what each role received and what it
  produced (the diff, its conclusions); the terminals are for detailed debugging. Research how such runs are best
  observed and propose the structure.
  - Effect: History is restructured around turns, each with what it received and what it produced
    ([Decision](#history)).
  - Reason: the operator could not tell what "The research brief" was, and the turn record repeated it.
  - Date/source: 2026-10-01, operator: *"explain history, eg research brief? what is it - human input??? … goal
    see input data to model and output data … I think that I need just see full process like now with turns but
    each role detailed with specific info … need to search web how to better observable and propose best
    sturucture … terminal views for detail debug, but history it's like quick understanding what exactly in each
    stage receive each role and what output was after it (diff, conlcusions)"*.
- **D4** No new run, and the saved run is not changed.
  - Effect: evidence comes from code, fixtures, the suite's fake agents and reads of existing runs; the saved
    run `audit-the-codex-834fe5b3` and its worktree are read only.
  - Reason: not stated.
  - Date/source: 2026-10-01, operator: *"bro don't do new run or change previous"*.
- **D5** Q2 is answered by the best UX solution, found with the UX skill.
  - Effect: Q2 closed; the controls at a stop follow [Run controls at a stop](#run-controls-at-a-stop), reached
    with `web-design-review` and established tools' practice.
  - Reason: not stated.
  - Date/source: 2026-10-01, operator: *"q2 - need to best ux solution - use skill ux"*.
- **D6** History may read the trees the reviews judged from the run's Temporal history; what it serves is
  rechecking the last few worktrees.
  - Effect: Q3 closed and A2 resolved; a round's changed files come from the judged trees, and a tree `git gc` has
    pruned from an older worktree is said to be gone, not rebuilt.
  - Reason: *"it's needed just recheck few last worktrees"*.
  - Date/source: 2026-10-01, operator: *"q3 - I guess ok if you understand our goals, it's needed just recheck few
    last worktrees"*.
- **D7** Q1 is answered by searching the web for the best way to meet the goal: cleanly see the modified files,
  click one, and see its added and removed lines in colour.
  - Effect: a second, goal-led search; [Change view](#change-view) records its result.
  - Reason: not stated.
  - Date/source: 2026-10-01, operator: *"q1 - search web for best solutions as for our goal cleanly see files
    modifeid click on it and see + - with colors"*.

### Operator gates

- **Q1 [CLOSED by D7]:** the diff viewer. diff2html (recommended) builds its HTML from the diff's text with
  `innerHTML`, after escaping it; the page today puts run text in the DOM only as text (invariant 2). Accept
  diff2html with that exception confined to the viewer — or keep the invariant whole and render diffs with the
  page's own code, without syntax colours? - gates: task 4.
- **Q2 [CLOSED by D5]:** while a run waits for you, may its own controls be Stop run alone — said as "end
  the run here; its worktree and branch stay" — with Force terminate shown only while the run works or is
  stopping? - default while open: A1.
- **Q3 [CLOSED by D6]:** may History read the trees the reviews judged back from the run's own Temporal
  history, so each engineer turn shows the files it changed that round? - default while open: A2.

### Working assumptions

- **A1 [RESOLVED by D5]:** Q2 as asked. Every capability stays reachable: a Stop that cannot finish makes the run
  stopping, which offers Force terminate; a run whose status cannot be read is shown working, with both.
- **A2 [RESOLVED by D6]:** Q3 as asked: no new state and no new record; a pruned tree is said to be gone.
- **A3 [ACTIVE]:** no workflow change, no change to the turn logs a host writes, no change to any prompt.
- **A4 [ACTIVE]:** the viewer opens a file whole by default (D1), its unchanged runs folded to three lines around
  each change and each fold a click away; a file over a size bound opens with its changes only and says so.
- **A5 [ACTIVE]:** the Change section carries "Open in VS Code": a link that opens the run's worktree in VS Code,
  whose Source Control view lists the uncommitted change with its own diff. A plain `vscode://` link the browser
  and VS Code each confirm; the server launches nothing.

## Non-goals

- No change to the workflow, what a stop offers, the turn logs, or the prompts (A3); no new run (D4).
- No server-side cache, history store or push channel.
- No review features beyond reading: no comments, staging or editing; no token or cost figures, which no record
  holds today.

## Verified evidence

### Verified facts

1. **The file list is git's stat, paths shortened.** `review_diff` returns `git diff --cached --stat` and the
   whole patch in 512 KiB parts (`review_diff`, `PATCH_CHUNK` in [worktrees.py](../app/workspace/worktrees.py));
   the stat cuts a long path with `...` — the saved run shows `...-09-30_1627-audit_the_codex_adapter_s_output.md`.
   The page prints the stat as text and the patch as one block of marked lines
   ([change.js](../app/interfaces/workbench/static/change.js) `drawPatch`). No file can be opened on its own.
2. **The change is read on the run's own host.** `client.review_diff` runs the `ReviewDiff` workflow on the run's
   workflow queue; its activity reads the worktree with that host's git through a private index
   ([client.py](../app/application/client.py), [workflow.py](../app/orchestration/workflow.py),
   [activities.py](../app/application/activities.py) `review_diff`).
3. **The page builds no markup from run text.** Every node comes from `el()` and `textContent`; no `innerHTML` in
   `static/*.js` (searched). The CSP is `default-src 'self'; … style-src 'self' 'unsafe-inline'`
   ([server.py](../app/interfaces/workbench/server.py)): same-origin scripts, no `eval`. xterm.js 5.5.0 is the one
   vendored dependency, pinned with its licence and source (`static/vendor/xterm/VERSION`).
4. **"The research brief" is the architect's output, not the operator's input.** A work stage's final message is
   its product: the workflow keeps it as the run's `brief` and in the timeline entry (`_stage` in
   [workflow.py](../app/orchestration/workflow.py)), shows it at the research approval, and hands it to the plan's
   prompt (`compose_prompt`, "# The architect's research brief").
5. **Why the turn record repeated it.** A history entry shows the timeline's `brief` or `feedback` as "The
   research brief" / "The review findings", then "Recorded input and output", whose first field is the turn's
   final message — the same text — with the prompt one disclosure deeper
   ([run.js](../app/interfaces/workbench/static/run.js) `historyEntry`, `loadTurn`).
6. **A turn's prompt has a known shape** (`compose_prompt` in [nodes.py](../app/agents/nodes.py)): the stage's
   skill invocation on its first turn; `# Task`, the task and the role's persona on a session's first turn; the
   stage's instructions (`stages.STAGE_ASK`); then the material carried in, each under its own heading — `# The
   architect's research brief …`, `# Your previous brief`, `# Your prior findings …` or `# Architect findings to
   address`, `# Operator guidance`, `# Convergence reflection`, `# Final budget handoff` and the operator's
   additions. A later turn in a stage carries only its delta. The persona has no heading; its exact text is in the
   run's start (`policy.roles[role].persona`), which the turn route already reads (`client.started`).
7. **The operator's answers are not timeline entries.** A review entry records the gate it stopped at
   (`entry.gate`); a revise's or guide's words become the state's `guidance` and reach the next turn's prompt as
   `# Operator guidance` (`_stop`, `_run`); approve carries no words. A round after an answer starts a new episode.
8. **Each review records the tree it judged.** An assess or verify computes the worktree's tree before the
   architect reads it (`worktrees.work_tree`: `git add -A` into a private index, `git write-tree`) and returns it
   as `assessed_tree` / `verified_tree` (`run_role` in [activities.py](../app/application/activities.py)). The
   workflow keeps only the latest; every activity's input and result is in the run's Temporal history.
9. **The run's controls at a stop.** While a run waits or failed, the page shows its answers, then Stop run and
   Force terminate (`renderControls`; the [UX todo](2026-09-25_2334-workbench-ux.md)'s A3). "Stopping" is the
   workflow's own `STOPPING` status (`view` in [client.py](../app/application/client.py)); a run whose status
   cannot be read shows as working. At a stop nothing runs on a host, so a Stop ends the run when its workflow
   worker reads it, keeping the worktree and branch (`client.stop`).
10. **`make demo`** presses Stop run on waiting and working runs, Force terminate only on a run already stopping,
    and checks a merged run offers neither ([demo.py](../tools/demo.py)).

### Research (2026-10-01, primary sources; not yet measured here)

**Diff viewers** for a page with no build step under `default-src 'self'`:

| | fits this page | what it takes | notes |
|---|---|---|---|
| [diff2html](https://github.com/rtfpessoa/diff2html) 3.4.56, MIT | yes: prebuilt bundles load as a plain script (`Diff2HtmlUI`) | the unified patch the server already makes | line-by-line and side-by-side, word-level marks, highlight.js colours; `diff2html-ui-slim.min.js` 302 KB + `diff2html.min.css` 17 KB + highlight.js themes ~3 KB; inserts HTML with `innerHTML` (escaped); no eval, workers or fonts; whole file only as git's context gives it; no collapse of unchanged runs |
| [Monaco](https://github.com/microsoft/monaco-editor) 0.57.0 diff editor | no: its script build is unsupported since 0.53; the ESM build needs a bundler; injects inline styles ([#4927](https://github.com/microsoft/monaco-editor/issues/4927)) | two whole texts | VS Code's own, ~3 MB with a worker and a font |
| [@codemirror/merge](https://github.com/codemirror/merge) 6.12.2 | no: ESM by package name, needs a bundler; writes `<style>`, so a nonce | two whole texts | collapses unchanged runs; repository archived and moved 2026-04 |
| [@git-diff-view](https://github.com/MrWangJustToDo/git-diff-view) 0.1.7 | no: renders only through React, Vue, Solid or Svelte | — | — |
| [jsdiff](https://github.com/kpdecker/jsdiff) 9.0.0 + the page's own rendering | yes, 37 KB — not needed, the server already diffs | — | everything visual is ours to build |
| [@pierre/diffs](https://diffs.com/) 1.5.1, Apache-2.0 | no: its ESM imports `shiki` by name, so a bundle; Shiki's default engine needs `'wasm-unsafe-eval'` | two whole texts, for folding | closest to VS Code; shadow DOM with `adoptedStyleSheets`; builds HTML strings |
| VS Code itself | a `vscode://file/<path>` link opens a file or folder, never a diff; each link confirmed since [1.84](https://code.visualstudio.com/updates/v1_84) | the worktree | `code --diff <a> <b>` is its diff, from a command line only ([CLI](https://code.visualstudio.com/docs/configure/command-line)) |
| delta or difftastic in xterm.js | a binary on every host | git's diff | colours and side by side; fixed width, no fold |

D7's second search, led by the goal: none of these meets all three of this page's needs — no build step, a whole
file with its unchanged runs folded, file text kept out of `innerHTML`. git already makes a whole-file diff of one
file (`--unified` at least its length), which is the input folding needs.

**Observing an agent run** — the common shape of [Langfuse](https://langfuse.com/docs/observability/data-model),
[LangSmith](https://docs.langchain.com/langsmith/view-traces), [OpenAI Agents
tracing](https://openai.github.io/openai-agents-python/tracing/), [Phoenix](https://arize.com/docs/phoenix/tracing/how-to-tracing/setup-tracing/setup-sessions),
[Laminar](https://laminar.sh/docs/platform/viewing-traces), [Weave](https://docs.coreweave.com/weave/guides/tracking/trace-tree)
and the [OpenTelemetry GenAI agent spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md):
a session holds turns; each step is one collapsed row with who, type, duration and status, opening to its input
then its output; instructions kept apart from the new input (`gen_ai.system_instructions` vs
`gen_ai.input.messages`); long prompts collapsed with a preview; a human decision as its own record or
annotation; bodies loaded on demand, with raw and copy. Laminar opens on a transcript; LangSmith shows one turn
at a time. None diffs a turn's input against the one before.

### Inferences

- A per-file read is cheap for git: `git diff --numstat -z` gives exact, unquoted paths and counts; `git diff
  -U<n> -- <path>` gives one file whole.
- An engineer turn's change is the difference between the tree the review before it judged (or the worktree's
  base) and the tree the review after it judged — both already recorded (fact 8).
- Judged trees are unreferenced git objects; `git gc` may prune them after its expiry (two weeks by default), so
  an old round's diff can become unreadable, and must say so.

### Assumptions / unverified areas

- diff2html's escaping and CSP behaviour, and highlight.js's, are verified on this page when vendored (task 4).
- Reading a long run's history for its judged trees is cheap enough on demand: measured in task 6.

### Refuted

- *"The research brief" is human input.* Refuted by fact 4: it is the architect's research output.

## Current architecture and source of truth

- The page is architecture D29's: plain HTML, CSS and native modules over the Workbench API, holding no run state.
- A run's change belongs to its worktree on its host, read through `ReviewDiff` (fact 2).
- A run's timeline is the workflow's status query; a turn's exact prompt and final output are its host's turn
  logs, attributed by the run's start (the UX todo's D7); the run's Temporal history records every activity's
  input and result (fact 8).
- A prompt's shape is `compose_prompt`'s alone (fact 6).

## Problem and root cause

- **Change (D1, D2):** the page has no per-file model of the change — git's human stat and one paged patch block —
  so no file opens on its own, a long path cannot be read whole, and the copy box is the reading surface.
- **History (D3):** it is organised by the timeline's stored texts, not by turns. Each entry shows its product
  twice and its input deepest; the operator's answers do not appear; an engineer turn shows no change.
- **Controls (D5):** at a stop, Force terminate offers the remedy for a Stop that cannot finish before any Stop
  was tried; nothing runs on a host there.

## Decision

### Change view

- **Server:** `review_diff` also returns the files — exact path, old path on a rename, status, lines added and
  removed, binary — from `git diff --cached --numstat -z` and `--name-status -z` on the same private index. A
  read naming one path returns that file's diff whole (`-U<its length>`), or its changes only on request or past
  a size bound (A4). Both go through `ReviewDiff` as today, with optional arguments.
- **Page:** the file list replaces the stat — directory quiet, file name in ink, never cut, status and counts at
  the right. A click opens the file in the viewer, with Line by line / Side by side and Whole file / Changes
  only. The raw patch moves into a bounded box, about ten lines, with Copy (D2).
- **Viewer (D7):** the page's own, over git's whole-file diff of one file: the server sends that file with all
  its context (`--unified` at least its length), the page parses the ` `, `+`, `-` and `\` lines, numbers old and
  new lines, and builds every row with `textContent`. Added lines green, removed red; runs of unchanged lines
  folded to three either side of a change, each fold a button that opens in place (A4); Line by line or Side by
  side, where a run of removed lines pairs with the added lines after it. About 250 lines in one module, no
  dependency. Syntax colours are the one gap — VS Code, a click away (A5), has them.
- **Why not a library (D7's search):** no ready-made viewer meets all three of this page's needs at once — loads
  with no build step, folds a whole file's unchanged runs, and keeps file text out of `innerHTML`. diff2html loads
  as a plain script but folds nothing and inserts escaped HTML; @pierre/diffs, the closest to VS Code, needs a
  bundle, Shiki and possibly WASM; Monaco and @codemirror/merge need a bundler; @git-diff-view renders only
  through React, Vue, Solid or Svelte ([Research](#research-2026-10-01-primary-sources-not-yet-measured-here)).
  diff2html's base bundle (~107 KB, no colours) stays the fallback, at the cost of an `innerHTML` exception and no
  folding.
- **Open in VS Code (A5):** `vscode://file/<worktree>` for a Windows worktree; for a WSL one, VS Code's remote form
  for the distribution and path, its exact spelling checked on the installed VS Code when built. VS Code asks
  before opening such a link (since 1.84), and Edge asks before handing it on.

### History

One transcript, in the run's order, by phase and round — the structure the tools above share, cut to this loop:

```
Plan
 ▌engineer  plan, round 1                               4 min   16:20
   Received  /investigate-change, the task, the engineer's persona, plan instructions      ▸
   Produced  "Wrote the plan to todo/2026-…-export.md: one job per tenant, …"           ▸
             1 file changed  todo/2026-09-30_1627-….md  +120                             ▸ opens the viewer
 ▌architect assess, round 1      PATCH                  2 min   16:24
   Received  plan review instructions                                                   ▸
   Produced  PATCH  "The plan does not name the test that proves it."                   ▸
 ▌engineer  plan, round 2                               1 min   16:25
   Received  the architect's findings to address                                        ▸
 ◆ you      approved the plan                                   16:31
```

- **A turn is one row** under a rule in its role's colour: role, stage, round, verdict, how long it took, when.
  Collapsed it shows two lines; nothing opens by default.
- **Received** is the turn's own new prompt — the vendor holds what came before — in labelled parts: the skill;
  the task and the persona, collapsed and marked "as the run started", on a session's first turn; the stage's
  instructions; and each part carried in under its heading's plain name (the research brief to check, findings to
  address, your guidance, a reflection or handoff). The exact prompt stays one click away, with Copy. The parts
  come from one function beside `compose_prompt`, which owns those headings, and the run's start for the task and
  persona; anything it cannot place shows as it is.
- **Produced** is the turn's final message, read by its kind: the brief, the plan's account, or the verdict and
  findings. An engineer turn adds the files it changed that round, from the trees the reviews before and after it
  judged (D6); a click opens them in the same viewer. A retry in a fresh session nests under its turn.
- **Your answers are rows**, in your colour, between the turns they separate: approved, revised or guided — with
  the words, read from the `# Operator guidance` part of the turn they fed — a Continue, a merge.
- **Said once.** The separate "The research brief" / "The review findings" disclosures and the nested "Recorded
  input and output" go; the decision above keeps the current evidence, and its turn below says "shown above".
- Bodies load on demand, as today; terminals stay the live, full view.

### Run controls at a stop

D5's answer. `web-design-review` on today's controls: Stop run's label does not say what it does at a stop, and no
consequence is beside either control while a run waits (`#run-controls-hint` is written only while stopping).
Established tools put a force action only where a normal stop may not finish: Jenkins offers "forcibly terminate
running steps" only after an abort has not finished in 30 s ([Jenkins: Aborting a
build](https://wiki.jenkins-ci.org/display/JENKINS/Aborting-a-build.html)); GitHub keeps force-cancel off its UI, for
a run that does not respond to cancel ([GitHub changelog, 2023-09-21](https://github.blog/changelog/2023-09-21-github-actions-force-cancel-workflows/)).
GitHub's "Close pull request" — close without merging, the branch kept — sits apart from the merge box, a quiet
action of its own ([GitHub Docs](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/closing-a-pull-request)).

- **While a run waits or failed:** the decision's answers lead; below the decision, Stop run alone, quiet, with
  its consequence beside it — "Ends the run here without merging; its worktree and branch stay." Its name stays
  Stop run, as the command line, the docs and the demo say it.
- **While it works:** Stop run, and Force terminate after it — a run whose status cannot be read shows as working,
  so a Stop its stopped worker never reads can still be forced.
- **While it is stopping:** Force terminate alone, as today, with its hint.
- The UX todo's A3 is updated to match.

### Premise / KISS gate

- **Owners:** the run's host's git owns the change and every tree; `compose_prompt` owns a prompt's shape;
  Temporal owns what each turn was given and returned; the page only shows them.
- **Adds:** a file list and a per-file read on the existing `ReviewDiff` path; one diff-rendering module; one
  prompt-parts function; one read of judged trees from history; one link (A5). No dependency.
- **Removes:** the stat block, the full-height patch as the reading surface, the duplicated History texts and the
  nested turn record; Force terminate at a stop.
- **Given up, knowingly:** turn tokens and cost (no record holds them); a judged tree pruned by `git gc` (said, not
  rebuilt); a timeline or graph view — a fixed loop reads best as a transcript.

### Alternatives considered

- **diff2html (the fallback).** A proven tool, as D1 prefers, and quickest to ship: file list, side by side, word
  marks and colours. Not chosen because it folds nothing — a whole file opens as one long page — and inserts its
  escaped HTML with `innerHTML`, an exception to invariant 2.
- **@pierre/diffs, Monaco, @codemirror/merge.** The closest to VS Code, but each needs a bundler or build step,
  against architecture D29's no-build page; @pierre/diffs also builds HTML strings and may need WASM.
- **A terminal diff (delta, difftastic) shown in xterm.js.** A binary to install on every host; fixed width;
  nothing folds.
- **The server launching VS Code (`code --diff`, `git difftool --tool=vscode`).** VS Code's own diff of one file,
  but the Workbench would start processes on the operator's desktop from a page request, and from WSL for a
  Windows worktree. The link (A5) gives the same window with the browser's and VS Code's own consent.
- **Recording each turn's parts, trees and answers as new state or logs.** Duplicates what Temporal and the turn
  logs already hold, and would not cover the saved run (D4). Rejected (A3).
- **Langfuse as the history.** It is optional observability (architecture's rule); the page must stand alone.

## Required invariants

1. Architecture D29 holds: the page reads the Workbench API and holds no run state; reads stay reads.
2. Run text reaches the DOM only as text, in the diff viewer too.
3. A run's change and every tree are read by the run's own host's git, as today.
4. Every capability stays reachable: each answer, Stop run, Force terminate (working or stopping), the whole patch
   and its copy, every turn's exact prompt and output.
5. Nothing is attributed to the wrong turn or kind: the run's start names each role's kind; a retry older than its
   turn's prompt is not the turn's; an answer's words belong to the turn they fed.
6. The saved run and its worktree are not changed (D4); every check uses fixtures, the suite's fake agents or the
   demo's own runs.

## Implementation tasks

1. [ ] Red evidence first ([below](#red-evidence)).
2. [ ] **Change, server:** the file list and the one-file read in `review_diff`, through `ReviewDiff`'s optional
   arguments; the file list replaces the stat in the API's answer.
3. [ ] **Run controls** ([Decision](#run-controls-at-a-stop), D5).
4. [ ] **Change, page:** the file list, the viewer module (D7, A4) and the compact patch with Copy; the "Open in
   VS Code" link (A5); the new module in `STATIC`.
5. [ ] **Prompt parts:** the function beside `compose_prompt`, proven against prompts `compose_prompt` makes; the
   turn route returns the parts with the exact prompt.
6. [ ] **Round changes (D6):** read each review's judged tree from the run's history in
   [client.py](../app/application/client.py); a route lists an engineer turn's files and reads one of them through
   `ReviewDiff` with the two trees; a pruned tree is said.
7. [ ] **History:** turns as rows, Received and Produced, your answers as rows, retries nested, duplicates removed
   ([Decision](#history)).
8. [ ] **Acceptance:** `make demo` opens a changed file in the viewer and reads a known line, and a build turn's
   changed file; consumers updated for any changed label.
9. [ ] **Docs** ([plan](#documentation-plan)); `web-design-review` on every changed page file; the
   `frontend-design` critique on fixture captures at 1600, 1280, 900 and 390 px.
10. [ ] The verification matrix, the agents' round, the external review, the full suites — the operator's order.

## Test-first and verification plan

### Red evidence

| case | kind | today |
|---|---|---|
| the API lists each changed file by its exact path — a long one, one with a space, a rename | permanent guard, `test_worktrees` on a real repository | only the stat, its long path cut |
| a one-file read returns that file whole and nothing else | permanent guard, `test_worktrees` | no such read |
| prompt parts: each prompt `compose_prompt` makes (first turn, later turn, research, review, with guidance) splits into its parts and joins back to the same bytes | permanent guard, beside `compose_prompt`'s own tests in `test_workflow` | no parts |
| a round's engineer turn lists the files between the judged trees around it, through the real workflow's history | permanent guard, `test_workbench` on the time-skipping server | no round changes |
| a judged tree that is gone is said gone | permanent guard, `test_worktrees` | — |
| a file whose text is markup (`<img src=x onerror=…>`) shows as text in the viewer, every line numbered and its unchanged runs folded | acceptance, fixture page; `make demo` reads a known line of a changed file | no viewer |
| a waiting run offers no Force terminate; a stopping one does | acceptance, `make demo` | both shown while waiting |
| History shows each fact once, its answers as rows, at the four widths | reviewer-checked, fixture captures | duplicates (fact 5) |

### Green evidence

- The guards above, each red first; `make demo` whole with its new checks; fixture probes at the four widths;
  `web-design-review` clean; `git diff --check`; `make public-check`; then the operator's order.

## Documentation plan

- **[docs/using.md](../docs/using.md):** the change by file and its viewer; History as turns received and
  produced, with your answers; the run's controls at a stop.
- **Interfaces [structure.md](../app/interfaces/docs/architecture/structure.md):** what the page reads for a file,
  a round's change and a turn's parts.
- **[tests/README.md](../tests/README.md), [tools/README.md](../tools/README.md):** rows for the new checks.
- Stable docs, code, tests and configuration do not reference this todo.

## Completion criteria

- Tasks 1–10 done; every red case seen red, then green.
- `make demo` passes whole; the History and Change captures reviewed at four widths; `web-design-review` clean.
- No change to the workflow, the turn logs, the prompts or the saved run.

## Review record

### 2026-10-01 — opened from the operator's manual check of the saved run

- **Trigger:** the operator's three points on the saved run's page (D1–D3), with D4.
- **Evidence:** the code paths above; web research on diff viewers and agent-observability practice; no run
  started, the saved run only read.
- **Authority:** D1–D4 added; Q1–Q3 opened; A1–A4 added.

### 2026-10-01 — the operator's answers to Q1–Q3

- **Trigger:** *"q1 - search web for best solutions … q2 - need to best ux solution - use skill ux … q3 - I guess
  ok"* (D5–D7).
- **Q1:** a second search, led by the goal, found no ready-made viewer that loads without a build step, folds a
  whole file and keeps file text as text; the page's own renderer is chosen, diff2html kept as the fallback, and
  an "Open in VS Code" link added (A5).
- **Q2:** `web-design-review` on today's controls, and Jenkins', GitHub's force actions and GitHub's close without
  merging; the result is [Run controls at a stop](#run-controls-at-a-stop).
- **Authority:** D5–D7 added; Q1–Q3 closed; A1, A2 resolved; A5 added.
