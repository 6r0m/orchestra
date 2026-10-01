# Workbench run evidence: the change by file, history as what each role received and produced

**Status:** IMPLEMENTED — awaiting the external review (D8). Q1–Q3 are closed by D5–D7.
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
the change since the previous review — with the operator's own answers between. The terminals stay the place for the
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
- **D8** Implement this todo, once the external reviewer's last wording correction is in.
  - Effect: the design is approved; implementation starts, test first.
  - Reason: not stated.
  - Date/source: 2026-10-01, operator: *"check reviewer and /implement-approved-change"*.

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
- **A3 [REJECTED by evidence]:** no workflow change, no change to the turn logs a host writes, no change to any
  prompt. — A prompt's parts must come from `compose_prompt` itself and still reach the page, which needs them
  recorded beside the prompt (external review, 2026-10-01). A6 replaces it.
- **A4 [ACTIVE]:** the viewer opens a file whole by default (D1), its unchanged runs folded to three lines around
  each change and each fold a click away; a file over a size bound opens with its changes only and says so.
- **A5 [REJECTED by evidence]:** the Change section carries "Open in VS Code": a link that opens the run's worktree in VS Code,
  whose Source Control view lists the uncommitted change with its own diff. A plain `vscode://` link the browser
  and VS Code each confirm; the server launches nothing. — D1 asks the page itself to show the diff; an editor
  hand-off is a follow-up, not this change (external review, 2026-10-01).
- **A6 [ACTIVE]:** no workflow change and no change to any prompt's bytes. Each attempt's record — a turn's first,
  and its retry in a fresh session, whose prompt is composed anew — gains one file beside that attempt's prompt:
  its parts as `compose_prompt` built them, named as `terminal.turn_files` and `RETRIED` name the attempt's other
  files. An attempt recorded before that shows its exact prompt, unsplit.
- **A7 [ACTIVE]:** a review's activity result carries the tree it judged as `judged_tree` whatever its verdict, so
  every round's change can be read back (fact 8). Still no workflow change: the workflow reads no new key, and
  recorded histories replay. A run recorded before has trees only on its passes — measured on the saved run: its
  PATCH verify has none — and the page says so for those rounds.

## Non-goals

- No change to the workflow, what a stop offers, or a prompt's bytes (A6); no new run (D4).
- Not in this change, each waiting for a need shown in use: a side-by-side view, syntax colours, an "Open in VS
  Code" hand-off (A5).
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
8. **A review records the tree it judged — on a PASS only.** An assess or verify computes the worktree's tree
   before the architect reads it (`worktrees.work_tree`: `git add -A` into a private index, `git write-tree`) and
   returns it as `assessed_tree` / `verified_tree` only when it passes (`run_role` in
   [activities.py](../app/application/activities.py)); a PATCH, UNVERIFIED or BLOCKER review returns none. The
   workflow keeps only the latest; every activity's input and result is in the run's Temporal history. Found in
   implementation (the history test's PATCH review had no tree); A7 closes it.
9. **The run's controls at a stop.** While a run waits or failed, the page shows its answers, then Stop run and
   Force terminate (`renderControls`; the [UX todo](2026-09-25_2334-workbench-ux.md)'s A3). "Stopping" is the
   workflow's own `STOPPING` status (`view` in [client.py](../app/application/client.py)); a run whose status
   cannot be read shows as working. At a stop nothing runs on a host, so a Stop ends the run when its workflow
   worker reads it, keeping the worktree and branch (`client.stop`).
10. **`make demo`** presses Stop run on waiting and working runs, Force terminate only on a run already stopping,
    and checks a merged run offers neither ([demo.py](../tools/demo.py)).
11. **Every answer is a recorded Update.** `client.answer` sends it as the workflow's `answer` Update with the id
    `answer:<stop-id>`, carrying the stop, the action, the role a revise names, its words and any confirmation
    ([client.py](../app/application/client.py) `answer`, [workflow.py](../app/orchestration/workflow.py)
    `FeatureRun.answer` and its validator). An accepted Update's event keeps its request
    (`WorkflowExecutionUpdateAcceptedEventAttributes.accepted_request`, installed temporalio 1.33.0); one the
    validator refuses never enters the history.
12. **The patch's parts carry one identity.** `review_diff` returns a `snapshot` hash of the whole patch, and the
    page reads its parts again from the start rather than join parts of two changes (`loadDiff` in
    [change.js](../app/interfaces/workbench/static/change.js)). Its private index's tree (`git write-tree`, as
    `worktrees.work_tree` makes one) names the same change as an object git can read later.

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
  -U<n> -- <path>` gives one file whole. Read between the base commit and the snapshot's tree, every read names the
  same change whatever the live worktree does meanwhile.
- The change since the previous review is the difference between the tree the review before an engineer turn
  judged (or the run's base) and the tree the review after it judged — both already recorded (fact 8). The
  worktree is live — its terminals take typing, and anything on the host can write to it — so that difference is
  what the next review judged, not proof of who wrote each line.
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
- Who owns what this change shows: Temporal the workflow's sequence and state, its Updates and its activities'
  inputs and results; the host's turn logs a turn's exact prompt and vendor output; the vendor its conversation;
  git the code, every tree and the change.

## Problem and root cause

- **Change (D1, D2):** the page has no per-file model of the change — git's human stat and one paged patch block —
  so no file opens on its own, a long path cannot be read whole, and the copy box is the reading surface.
- **History (D3):** it is organised by the timeline's stored texts, not by turns. Each entry shows its product
  twice and its input deepest; the operator's answers do not appear; an engineer turn shows no change.
- **Controls (D5):** at a stop, Force terminate offers the remedy for a Stop that cannot finish before any Stop
  was tried; nothing runs on a host there.

## Decision

### Change view

- **One snapshot.** A change read makes the private index's tree (`git write-tree`) and returns it with the base
  commit as the change's identity; every later read names that pair and is read from it — the file list, one
  file, each part of the patch, and Copy. The live worktree moving meanwhile changes nothing already shown; Read it
  again makes a new snapshot.
- **One diff policy.** Every git diff this change reads — the file list, a file, the patch and its parts, a review's
  change — compares two trees (the base and the snapshot, or two judged trees) with the same explicit options:
  `--no-ext-diff --no-textconv --find-renames --no-color`. These pin the behaviours the page relies on: no
  external diff or text conversion runs, rename detection is on whatever `diff.renames` says, and the text is
  uncoloured whatever `color.ui` says. Git may still bound its exhaustive rename search (`diff.renameLimit`), and
  no `-l0` lifts that bound, which would risk quadratic work: a rename git detects shows as `old → new`, otherwise
  as a delete and an add. Paths come from the `-z` lists, never from a patch's headers, which follow `diff.noprefix`.
  A selected path must be one of that snapshot's files and is passed as a literal pathspec; object names are
  checked as object names.
- **Server:** `review_diff` returns the base, the tree and the files — exact path, old path on a rename, status,
  lines added and removed, binary — from `git diff --numstat -z` and `--name-status -z` between them, in place of
  the stat. A read naming one path returns that file's diff whole (`--unified` at least its length), or its changes
  only past a size bound, said so (A4). All of it goes through `ReviewDiff`, with optional arguments.
- **Page:** the file list replaces the stat — directory quiet, file name in ink, never cut, counts at the right.
  A rename reads `old/path → new/path`; a new or deleted file opens like any other; a binary file is listed with
  its status and says "Binary file — no text diff". A click opens the file in the viewer.
- **Viewer (D7):** the page's own, one unified diff of one file: the page parses the ` `, `+`, `-` and `\` lines,
  numbers old and new lines, and builds every row with `textContent`. Added lines green, removed red; runs of
  unchanged lines folded to three either side of a change, each fold a button that opens in place (A4). One module,
  no dependency.
- **Raw patch (D2):** a bounded box of about ten lines, with Copy patch, which copies the complete patch of the
  snapshot — every part, however many, read from the same tree.
- **Why not a library (D7's search):** no ready-made viewer meets all three of this page's needs at once — loads
  with no build step, folds a whole file's unchanged runs, and keeps file text out of `innerHTML`. diff2html loads
  as a plain script but folds nothing and inserts escaped HTML; @pierre/diffs, the closest to VS Code, needs a
  bundle, Shiki and possibly WASM; Monaco and @codemirror/merge need a bundler; @git-diff-view renders only
  through React, Vue, Solid or Svelte ([Research](#research-2026-10-01-primary-sources-not-yet-measured-here)).
  diff2html's base bundle (~107 KB, no colours) stays the fallback, at the cost of an `innerHTML` exception and no
  folding.

### History

One transcript, in the run's order, by phase and round — the structure the tools above share, cut to this loop:

```
Plan
 ▌engineer  plan, round 1                               4 min   16:20
   Received  /investigate-change, the task, the engineer's persona, plan instructions      ▸
   Produced  "Wrote the plan to todo/2026-…-export.md: one job per tenant, …"           ▸
             Change since the previous review  1 file  +120                               ▸ opens the viewer
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
  instructions; and each part carried in under a plain name (the research brief to check, findings to address,
  your guidance, a reflection or handoff). The exact prompt stays one click away, with Copy. `compose_prompt`
  builds the parts first and renders the prompt from them, byte for byte as today; the turn's record keeps the
  parts beside the prompt (A6), and the page shows parts only when they render to the recorded prompt — otherwise,
  and for a turn recorded before, the exact prompt unsplit.
- **Produced** is the turn's final message, read by its kind: the brief, the plan's account, or the verdict and
  findings. An engineer turn adds **Change since the previous review**: the files between the tree the review
  before it judged (or the run's base) and the tree the review after it judged (D6), each opening in the same
  viewer. It is said as that, never as the files the engineer wrote: the worktree is live, so the delta is what the
  next review judged. A retry in a fresh session nests under its turn, with its own Received.
- **Your answers are rows**, in your colour, at the time you gave them: each accepted `answer:<stop-id>` Update in
  the run's Temporal history (fact 11) — approve, revise (to which role) or guide with your words, continue, merge
  or discard. An answer no turn followed is a row all the same. The next turn's Received shows, on its own, how
  your words reached its role.
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

- **Owners:** Temporal the workflow's sequence and state, its Updates and its activities' inputs and results;
  the host's turn logs a turn's exact prompt and vendor output; the vendor its conversation; git the code, every
  tree and the change; `compose_prompt` a prompt's shape and parts. The page combines them and owns none.
- **Adds:** a change snapshot (base and tree) that every change read names; a file list and a one-file read on the
  existing `ReviewDiff` path; one diff-rendering module; prompt parts built by `compose_prompt` and recorded beside
  the prompt; a review's judged tree in its result whatever its verdict (A7); one read of the run's history for
  judged trees and answers. No dependency.
- **Removes:** the stat block, the full-height patch as the reading surface, the duplicated History texts and the
  nested turn record; Force terminate at a stop.
- **Given up, knowingly:** turn tokens and cost (no record holds them); a judged tree or a snapshot pruned by
  `git gc` (said, not rebuilt); prompt parts for turns recorded before this change; a side-by-side view and syntax
  colours until use shows the need; a timeline or graph view — a fixed loop reads best as a transcript.

### Alternatives considered

- **diff2html (the fallback).** A proven tool, as D1 prefers, and quickest to ship: file list, side by side, word
  marks and colours. Not chosen because it folds nothing — a whole file opens as one long page — and inserts its
  escaped HTML with `innerHTML`, an exception to invariant 2.
- **@pierre/diffs, Monaco, @codemirror/merge.** The closest to VS Code, but each needs a bundler or build step,
  against architecture D29's no-build page; @pierre/diffs also builds HTML strings and may need WASM.
- **A terminal diff (delta, difftastic) shown in xterm.js.** A binary to install on every host; fixed width;
  nothing folds.
- **Handing off to VS Code** — a `vscode://` link, `code --diff`, `git difftool --tool=vscode`. Its own diff and
  colours, but not what D1 asks — the page showing the change — and each form has a cross-host detail to own.
  Deferred (A5).
- **Parsing the recorded prompt into parts.** A second grammar beside `compose_prompt`'s headings, which would
  drift from it. Rejected: the composer builds the parts once (external review).
- **Reading an answer's words from the next prompt.** Indirect, and blind to approve, continue, merge, discard, an
  answer's time and an answer no turn followed. Rejected: the run's history holds each answer (fact 11).
- **Checking a later read against the list's snapshot and refusing.** Correct, but every click recomputes the
  whole diff and a live worktree turns clicks into refusals; reading from the snapshot's tree never mixes and never
  refuses.
- **Recording trees or answers as new workflow state.** Duplicates what Temporal and git already hold, and would
  not cover the saved run (D4).
- **Langfuse as the history.** It is optional observability (architecture's rule); the page must stand alone.

## Required invariants

1. Architecture D29 holds: the page reads the Workbench API and holds no run state; reads stay reads.
2. Run text reaches the DOM only as text, in the diff viewer too.
3. A run's change and every tree are read by the run's own host's git, as today.
4. One change, one snapshot, one diff policy: the file list, a file, every patch part and Copy patch name the same
   base and tree and read it with the same options; nothing joins two snapshots, and no repository setting turns
   on an external diff, text conversion or colour, or turns rename detection off.
5. A prompt's bytes are unchanged: the parts `compose_prompt` builds render to exactly the prompt it makes today.
6. Every capability stays reachable: each answer, Stop run, Force terminate (working or stopping), the whole patch
   and its copy, every turn's exact prompt and output.
7. Nothing is attributed to the wrong turn or kind: the run's start names each role's kind; a retry older than its
   turn's prompt is not the turn's; an answer is the Update the run accepted, at the time it accepted it.
8. The saved run and its worktree are not changed (D4); every check uses fixtures, the suite's fake agents or the
   demo's own runs.

## Implementation tasks

1. [x] Red evidence first; today's prompts captured into `tests/fixtures/prompts.json` before `compose_prompt`
   changed. Each guard seen red for its reason: no `compose_parts`; no `parts` on a turn; the diff route not
   passing the snapshot; no `tree`/`files`/`ChangeRefused`, `base` short; no history route — then, with the route,
   the PATCH review's tree missing (fact 8, A7).
2. [x] **Change, server:** `worktrees.review_diff` — snapshot, file list, one-file read, `DIFF`, literal paths,
   `ChangeRefused`; `ReviewDiff`'s arguments passed through unchanged; `client.review_diff` turns a refusal into
   the page's 400.
3. [x] **Run controls:** `renderControls`; the UX todo's A3 updated.
4. [x] **Change, page:** `static/diff.js` (file list, viewer, Copy patch), `change.js`, `#change` in
   `index.html`, `/diff.js` in `STATIC`.
5. [x] **Prompt parts:** `nodes.compose_parts`/`render`/`PARTS`; `terminal.record_parts` beside each attempt's
   prompt; the turn route's `parts` while they render to the prompt.
6. [x] **The run's history:** `client.history` and `/api/runs/<id>/history`; a round's change through
   `/diff?base=&tree=`; a review's `judged_tree` (A7). Measured on the saved run (read only): 0.07 s, 7 turns, 2
   answers, its PATCH verify without a tree.
7. [x] **History:** turns as rows with Received and Produced, answers as rows, retries as attempts, said once.
8. [x] **Acceptance:** `make demo` passed whole, 82 checks: a changed file read in the viewer, the build turn's
   change since the review before it, the approval as a history row, no Force terminate while waiting.
9. [x] **Docs**, `web-design-review` (five findings, fixed: a span's ignored label, rows not virtualised, an
   empty list drawn, a history read error with no retry, an unread history taken for "no review yet"), and
   fixture captures at 1600, 1280, 900 and 390 px (one fix: the History's part classes collided with the stack
   panel's).
10. [ ] The external review, then the full suites — the operator's order. No review agents (operator,
    2026-10-01: *"no need more activate tester and reviewer agents"*).

**Verification so far:** WSL `run-tests.sh` on test_worktrees, test_workflow, test_workbench,
test_observability, test_terminal, test_activities, test_architecture, test_replay — 301 tests OK; Windows
`run-tests.ps1` on test_worktrees, test_workflow, test_terminal, test_activities, test_architecture,
test_replay — 176 tests OK; `make demo` passed; `make public-check` passed; `git diff --check` clean.

## Test-first and verification plan

### Red evidence

| case | kind | today |
|---|---|---|
| the API lists each changed file by its exact path — a long one, one with a space, a rename, a binary | permanent guard, `test_worktrees` on a real repository | only the stat, its long path cut |
| a one-file read returns that file whole and nothing else | permanent guard, `test_worktrees` | no such read |
| the worktree changes after the list is read: the file read, the next patch part and the whole patch still come from the listed snapshot | permanent guard, `test_worktrees` | parts re-read from the start; no file read |
| a patch larger than `PATCH_CHUNK` read whole for Copy equals `git diff` of the snapshot, byte for byte | permanent guard, `test_worktrees` | only the parts read so far exist on the page |
| a path not in the snapshot, or one that is pathspec magic, is refused | permanent guard, `test_worktrees` | — |
| in a repository set to `diff.renames=false` and `color.ui=always`, with a `diff` driver configured, the list still shows a rename as one file `old → new` and the patch holds no escape codes; control: the same reads without the explicit options show the rename as a delete and an add | permanent guard, `test_worktrees` | `review_diff` passes no `--find-renames` or `--no-color` |
| prompt bytes: every prompt in a captured matrix of today's `compose_prompt` (first and later turns, research, plan, review, brief, findings, guidance, reflection, handoff) is reproduced byte for byte, and its parts render to it | permanent guard, beside `compose_prompt`'s tests in `test_workflow` | no parts |
| a turn's record holds its parts, and the route returns them; a turn without them returns its prompt unsplit | permanent guard, `test_workbench` | — |
| a lost session's retry records its own parts: each attempt's parts render byte for byte to that attempt's own prompt, the first's and the retry's | permanent guard, `test_workbench` through the real activity and the recording runner | — |
| each accepted answer — approve, revise with words to one role, continue, discard — is a row with its action, words and time, one no turn followed included; a refused answer is not | permanent guard, `test_workbench` on the time-skipping server | answers absent |
| an engineer turn's change since the previous review lists the files between the judged trees around it | permanent guard, `test_workbench` | no round changes |
| a judged tree that is gone is said gone | permanent guard, `test_worktrees` | — |
| a file whose text is markup (`<img src=x onerror=…>`) shows as text in the viewer, every line numbered and its unchanged runs folded; a rename and a binary said | acceptance, fixture page; `make demo` reads a known line of a changed file | no viewer |
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
- No change to the workflow, any prompt's bytes or the saved run; the turn logs gain only the parts file (A6),
  a review's result only its judged tree (A7).

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

### 2026-10-01 — external review of the design: PATCH

- **Accepted, each checked against the code:** answers read from the run's accepted `answer:<stop-id>` Updates
  (fact 11), not from the next prompt; prompt parts built by `compose_prompt` and rendered from, with a byte-equality
  guard, not parsed back; one snapshot for the list, each file, each patch part and Copy — read from the snapshot's
  tree, the reviewer's first option, rather than refusing; one unified view, side by side deferred; Open in VS Code
  dropped (A5); Copy patch copies the whole snapshot, with a guard past `PATCH_CHUNK`; renames and binaries said;
  ownership worded as the architecture states it.
- **Made explicit:** parts can reach the page only if recorded beside the prompt, so A3 gives way to A6; a turn
  recorded before shows its exact prompt unsplit — the saved run among them.
- **Authority:** A3 and A5 rejected by evidence; A6 added.

### 2026-10-01 — external review of the design, second pass: PATCH

- **Accepted:** prompt parts per attempt, a retry's beside its own prompt (A6 rewritten in place); a review's tree
  delta named "Change since the previous review", never the engineer's authorship; one explicit diff policy for
  every read, with a control against repository settings.
- **Added beyond the review:** `--no-color` in that policy — a repository or user set to `color.ui=always` would
  otherwise put escape codes into the patch and the file the page parses.

### 2026-10-01 — external review of the design, third pass: PATCH, then PASS

- **Accepted:** the diff policy's claim narrowed — `diff.renameLimit` still bounds rename detection (probed: at
  `1`, four renamed and edited files list as four deletes and four adds, with `git diff` and `diff-tree` alike);
  no `-l0`; invariant 4 says what the options pin.
- **Added beyond the review:** the same probe showed `git diff` follows `diff.noprefix` in a patch's headers, so
  paths are read only from the `-z` lists.
- **Authority:** D8 added; implementation starts.

### 2026-10-01 — implemented

- **Built** as decided, with A7 added on evidence (fact 8 corrected); tasks 1–9 done, evidence under
  [tasks](#implementation-tasks). Awaiting the external review.
