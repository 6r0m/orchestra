# A Merge at the final gate lands what the gate showed, on the base as it is — or lands nothing

**Status:** IMPLEMENTED and passed by the external reviewer; the public check as this repository's pre-push
hook is built, the reviewer's two points on it answered — awaiting its re-review (D1). The full suite on both
hosts, a restart and a run with real agents are not done; the hook is installed in no clone; the live stack
still runs the code from before this.
**Scope:** how a run meets a base that moved, and where it lands: the look at the base, its coming into the
worktree and the landing ([worktrees.py](../app/workspace/worktrees.py)); the remote a base may live on
([repos.py](../app/workspace/repos.py)); the workflow's path around the final gate
([workflow.py](../app/orchestration/workflow.py)); the change the gate and the history read
([client.py](../app/application/client.py), the Workbench's change view).
**Stable documentation owner:** architecture D24, with D25 for how recorded runs keep replaying, in
[structure.md](../docs/architecture/structure.md); the stops in
[stops.md](../docs/architecture/diagrams/stops.md).

## Goal

At the final gate the operator reads what the run adds to the base as it is now, judged on that base; Merge
lands exactly that tree where the repository's base lives — or, the base having moved since, lands nothing
and says so.

## Authority register

### Operator decisions

- **D1** The external reviewer's feedback is evaluated against the code and applied where it holds; a point
  that is wrong is refuted, not applied.
  - Date/source: 2026-10-07, operator, relaying each review of the merge flow.
- **D2** A base that moved is reconciled before the final gate, and a Merge either lands or changes nothing.
  - Date/source: 2026-10-07, operator, on the flow as it was put to him: *"yes seems very cool flow"*.
- **D3** Where a repository's base lives on a remote, a run merges there: the remote is the repository's
  source of truth, and the local branch no destination. Agents still reach no remote; the controller alone
  fetches and pushes, the base branch only, on the operator's Merge, rewriting nothing there.
  - Date/source: 2026-10-07, operator: *"also need proper remote merge"*, with the reviewer's rules for it.
  - Effect: replaces what D24 held until now, that nothing a run does leaves the machine.
- **D4** Questions of mechanism are settled by the direction above and by what the industry does, not put
  to the operator.
  - Date/source: 2026-10-07, operator: *"we have vector, if not undersatnd check best industrial web way"*.

### Decided under D4 — the reviewer's and the agent's

- **A base that moved without a conflict is judged by the architect alone**; the engineer takes a turn only
  on a conflict, or on the architect's `PATCH`. What a merge queue does: it tests the merged result on the
  latest base before it lands, and again when the base moves (the "not rocket science" rule; bors; GitHub's
  and GitLab's queues).
- **Every run lands as the same two commits**: the change, one commit on the base tip it was judged on, and
  the merge commit named for the plan, its first parent that tip and its tree the final tree.
- **The base tip a run stands on is what a git step answered**, kept in the run's state; the workflow never
  asks git. A run that recorded none began before this and keeps its path (D25's second way).
- **A commit is judged by the main checkout's script and scanner configuration**, never by its own: a run
  cannot loosen what judges it, and a change to either that landed on the remote counts once the checkout
  holds it.
- **The hook is installed only where git proves it will run it**: one that reads no hook from its
  configuration is left with none, and CI stays behind every push.

### Working assumptions

- **A1 [ACTIVE]** Reconciling is the controller's step, not a role's stage: no flow file changes, and a run
  is told the base came in by the words of its next turn.
- **A2 [ACTIVE]** The base is looked at twice only — after a verify's `PASS` and at the Merge — never watched.
- **A3 [ACTIVE] — the agent's, to confirm:** a remote is the repository entry's to name (`remote`), never
  assumed from the repository having one. Reaching a remote is outward; a branch its remote protects takes no
  push; and a local repository must go on working. Unnamed, a run lands on the local branch as before.
- **A4 [ACTIVE]** The commits a run's branch holds from the base's coming in are the controller's own and
  never land, so no hook judges them; the one commit that lands is made with the repository's hooks.

## Non-goals

- Pull requests, a merge queue of its own, an integration service; pushing anything but the base branch; a
  push that rewrites anything on the remote.
- A sandbox for the roles: the remote's destination is pinned (F12), and a role still runs as the operator.
- Moving the operator's local branch after a remote landing: it is theirs to pull.
- Putting the todo of a run started before closeouts back at its path during a conflict (F9): those runs end.
- A row in the history for the base's coming in; the run's lines say it.

## Verified evidence

- **F1** `merge` committed the run's tree on its branch, then merged that into the local base as git merges:
  where the base had moved and git found no conflict, the base gained a tree no stage judged and no gate
  showed.
- **F2** A conflict was met only at the operator's Merge: aborted on the base, the base merged into the run's
  worktree, and a second Merge asked after the round that resolved it.
- **F3** Measured on the live stack, 2026-10-07, a run fourteen base commits behind: after its first Merge
  its worktree held 70 staged files and 1 unmerged — exactly the 71 the base had changed — and differed from
  the base by 3 files, +382 lines.
- **F4** The gate read its change from the worktree's own commit: 71 files, none of them the run's.
- **F5** The history after that conflict: the plan's row showed 3 files, +16 −96, where the plan was 1 file,
  +302; the row of the build that resolved the conflict, 72 files, +11255 −537 — the base's commits. A run
  recorded no commit it started from.
- **F6** A reconciliation commit's first parent is the run's commit and its second the base's tip: a base
  fast-forwarded to it has its first-parent history run through the run's branch, and `_adopted_merge`,
  which keeps a retried merge from landing twice, looks for the run's tip as a second parent on that line.
- **F7** Tried in throwaway repositories with a bare one as the remote, git 2.55: after `git add -A`,
  `git merge --quit` and `git reset --soft <tip>`, one `git commit` makes a commit whose only parent is the
  tip and whose tree is the worktree's files, the repository's pre-commit hook having run; `commit-tree` makes
  the merge on it; a plain push of that commit is taken while the remote is at the tip and refused once it
  moved, nothing changed; `git merge --ff-only` lands it on a checked-out branch, keeps an edit of the
  operator's elsewhere, and refuses — nothing changed — when the branch moved or the edit is in its way.
- **F8** A run's stages judge only its own base: two runs that pass alone and break together were caught by
  nothing before the base held both.
- **F9** Every role's ask names the todo by its first path; the controller's finish of a run started before
  closeouts moves it at the first Merge, so in the conflict's turns it is not there — seen live.
- **F10** This repository's rule is `make public-check` before a push, run by hand; it has no pre-push hook.
- **F11** A plain push lands on a remote's branch that was rewound to an ancestor of the commit pushed from:
  tried against a bare repository, git 2.55 and 2.54. The same push leased on that commit is refused there,
  as on a branch that moved on, and taken on one that stands.
- **F12** The role guard watches HEAD, the run's branch and what is staged. `git config remote.origin.url`,
  its `pushurl`, and a `url.<x>.insteadOf` or `pushInsteadOf` change none of them, and each turns where
  `origin` leads; `git remote get-url --all`, with and without `--push`, answers what they resolve to.
- **F13** `resolve` asked for a local branch of the base before it read `remote`, and found an unnamed base
  among the local ones.
- **F14** A base rewound to an ancestor of the commit a run stands on is, to git, merged into that run's
  worktree already: `reconcile` answered that it had come in, with nothing in conflict, and the run would have
  landed again what the base had dropped. One rewritten to another history was merged in beside the old.
- **F15** A remote may hold several push URLs, and one `git push` to it writes to each in turn.
- **F16** Git hands a pre-push hook one line a ref on stdin — the local name, its commit, the remote name,
  what the remote holds — and for the controller's push the first two are the merge commit itself; a deleted
  ref comes as `(delete)`, a push that carries nothing as no line. From a linked worktree the hook runs with
  that worktree's `GIT_DIR`. A hook's own stdout is the push's stdout under git 2.54, so what the controller
  relays — the push's stderr — held none of it.
- **F17** WSL mounts this machine's repository drive without file modes: no file there is executable, `chmod`
  succeeds and changes nothing, and WSL's git passes a `hooks/pre-push` file by with a hint and pushes —
  measured with the hook installed as a file, three pushes it should have refused landing. A hook stated in
  git's configuration (`hook.<name>.event`, `hook.<name>.command`) is run by git 2.54 on WSL and 2.55 on
  Windows alike, from a checkout and from a linked worktree, handed the same stdin; `git hook list` names it.
- **F18** The Docker that runs the scanner is WSL's; under Git for Windows' shell the check as it was failed
  every scan for want of one — while calling its control rejected, any failure of Docker reading as that.
- **F19** The hook `make hooks` states lives in the clone's `.git/config`, which every worktree of the clone
  shares and no guard of a role's turn watches: with its command changed to one that passes, the controller's
  push went past it and landed — the test's red. A hook's file is as open: its bytes, and `core.hooksPath`.
- **F20** The hand-over to WSL was made in the script's own checkout already — the script changes into it
  before it reads where it is — and the stated command finds that script through the clone's git directory:
  run by Git for Windows' own shell from a linked worktree holding a copy that passes anything, the unchanged
  script answered from WSL as the main checkout's.

### Refuted

- **"The 71-file change at the gate is cosmetic."** The agent's own earlier reading, and wrong (F4).
- **"Finalize by fast-forwarding the base to the run's reconciliation commit."** F6. The reviewer withdrew
  it for the two commits above, which make no reconciliation commit at all.
- **"The gate shows the current base tip → the final tree."** The tip the run was reconciled with: against
  one that moved again the change would show that later work undone. They are the same tip whenever a Merge
  may land.
- **"The engineer, then the architect, on every base move."** The reviewer's first diagram, withdrawn for the
  architect alone: with nothing in conflict there is nothing for the engineer to change.

## Decision

A run stands on one commit of its base — its remote's, where its entry names one. After a verify's `PASS` and
before the build is made final the base is looked at; one that moved is merged into the worktree,
uncommitted, and judged — by the architect alone where git merged it cleanly, by the engineer first where it
did not — until a `PASS` meets a base that stood still. The gate reads the change against that commit. Merge
lands the final tree on it as two commits, and the base takes them only while it is exactly at that commit:
a remote by a push leased on it (F11), a checked-out branch by `--ff-only`, a branch checked out nowhere by a
compare-and-swap. A base that moved again takes nothing; the change is reopened and reconciled again. A
remote is reached only where it led at the run's setup (F12), and its base branch is named, never found, and
needs no local branch (F13).

### Premise / KISS gate

Git's own primitives throughout, and its own refusal as the lock: a non-fast-forward is what a remote, a
checkout and a ref each refuse by themselves. One new git step, one new descriptor key, no flow change, no
service. Knowingly given up: an architect's turn each time the base moved under a run; and the base is not
watched between the two looks, so a Merge can still be answered with "it moved" — and then lands nothing.

## Required invariants

1. Nothing lands on the base that a stage did not judge on that base and the gate did not show.
2. A Merge lands only while the base's tip is the one the run recorded; otherwise nothing is committed,
   merged or pushed.
3. The base's first-parent history is its own; a run adds the same two commits whatever the base did
   meanwhile, and nothing kept of the base's coming in is reachable from it. A base that no longer holds the
   commit a run stands on is brought into nothing: the run stops for the operator.
4. A conflict never resolves on the base, in the controller or at the operator's Merge.
5. Every recorded history replays as it was written (D25); a run that recorded no base tip takes no new step.
6. Agents reach no remote. The controller reaches one only where the repository's entry names it, only where
   that remote led when the run was set up, and only while it leads to one place to fetch from and one to
   push to: it fetches the base branch, and pushes it only on the
   operator's Merge, as a compare-and-swap on the commit the change was judged on — never a rewrite. Its
   push runs the repository's own pre-push hook, or does not happen: a hook git would pass by refuses it,
   and so does anything git would run before a push that is not what it was when the run was set up.
7. A retried merge adopts the one it made; the operator's staged content and their edits in a checked-out
   base are never written over; a look at the base that could not be made is no answer.
8. This repository's public check, as its pre-push hook, judges the commits a push carries and nothing of
   the checkout, by the main checkout's own script and scanner configuration — no run judges its own landing.

## Implementation tasks

- [x] 1. The gate's change read against the base, not the worktree's own commit (F4).
- [x] 2. The recorded base tip; `reconcile`; its place after a `PASS` and at a Merge that found the base moved.
- [x] 3. The landing: two commits, fast-forward only; local, or the remote's by a push.
- [x] 4. The descriptor's `remote`; the page's words for the step and for a merge that leaves the machine.
- [x] 5. The history's rows (F5).
- [x] 6. A recording of a run that stands on a tip; D24, the stops' view, `using.md`, the tests' index.
- [x] 7. The public check as this repository's pre-push hook, judging the pushed commit (`make hooks`).

## Test-first and verification plan

| case | where |
|---|---|
| a conflict met before any gate, resolved, landed as the two commits | `test_worktrees.Landing`; `test_stops.Reconciling` |
| a base that moved cleanly: nothing lands until it is brought in and judged, by the architect alone | `test_worktrees.Landing`; `test_stops.Reconciling` |
| a Merge after the base moved again: nothing committed, merged or pushed; back through | `test_worktrees.Landing`, `Remote`; `test_stops.Reconciling` |
| the base's tree after a landing is the final tree; its first-parent line its own | `test_worktrees.Landing`, `Remote` |
| a retried merge adopted; the operator's staged content and edits kept; a hook-refused commit continued | `test_worktrees.Landing` |
| a remote's base: begun from it, landed by a push, the local branch untouched and not needed, a refusal landing nothing, an unreachable remote no answer | `test_worktrees.Remote`; `test_repos` for the entry's keys |
| a remote rewound between the look and the push takes nothing | `test_worktrees.Remote`, red first: a plain push landed on it |
| a remote turned elsewhere since the run began is neither fetched from nor pushed to | `test_worktrees.Remote`, four ways of turning it; `test_stops.Reconciling`: the fingerprint taken at setup and handed to every step |
| a base rewound or rewritten under a run is brought into nothing, the run not going on | `test_worktrees.Landing`, `Remote` — past the refused push, into the look that follows it |
| a remote with more than one URL either way is refused before a run begins | `test_worktrees.Remote` |
| the repository's own pre-push hook is handed the commit being landed; its refusal lands nothing, in its words | `test_worktrees.Remote` — control: the push made with `--no-verify` |
| a pre-push hook git would pass by unrun refuses the landing | `test_worktrees.Remote`, red first: the push went past it and landed |
| a pre-push gate changed since the run began — stated or a file — lands nothing | `test_worktrees.Remote`, four ways, red first: the push went past it; `test_stops.Reconciling`: taken at setup, handed to the merge, and not taken where nothing is pushed |
| no worktree's copy of the public check judges a push, on WSL or under Git for Windows | `test_public_check.InstalledHook`; `HandedToWsl` on the Windows host — control: the hand-over made where git stood |
| as the hook, the public check judges each pushed commit — files, what is tracked, history — and not the checkout | `test_public_check.PushedCommits`; `InstalledHook`, by real pushes from a clone and a worktree of it |
| the gate's change is the run's files | `test_worktrees.Merge`, `Landing`; `test_workbench.Runs` |
| the history's rows | `test_workbench.HistoryRead` |
| a run recorded before this replays, and takes no new step | `test_replay`; `test_stops.Reconciling`'s control |

The results, the controls and what was not run are in the [review record](#review-record).

Not proven here: a push to a real remote, its credentials and its protections — the remote in these tests is
a bare repository on disk. That is a live run's to show. The hook's hand-over from Git for Windows' shell to
WSL is tested on the Windows host as far as the gate's first answer, which needs no scanner; with the scanner
behind it, it is proven by the real pushes in the review record.

## Documentation plan

- **Owner:** D24.
- **Updated:** [stops.md](../docs/architecture/diagrams/stops.md), [using.md](../docs/using.md), the
  [README](../README.md), [tests/README.md](../tests/README.md), the workspace's and the application's
  structure notes, [the example descriptors](../.orchestra/repos.example.json).

## Completion criteria

- The external reviewer's PASS on the hook (D1); then the full suite once on both hosts.
- `make hooks` in this clone, its entry naming `remote` and `base_branch`, a restart, and a live run: landed
  on the remote by one Merge, the remote's branch shown to hold it.

## Review record

### 2026-10-07 — investigation, and the gate's change

- **Trigger:** the operator's questions at a gate after a conflict; the external reviewer's `PATCH` on the
  merge flow.
- **Applied:** the gate's change after a conflict read against the base brought in (F4): on the live run's
  worktree, 3 files where the running page showed 71.
- **Reviewer:** `PASS` on that fix; on the plan, the three decisions above and two requirements — the base
  tip recorded only from a git step's answer, and the retry and working-copy guards kept (invariant 7).

### 2026-10-07 — the flow built, and the remote landing (D2, D3)

- **Built:** tasks 2–6.
- **Verification, the modules the change touches, one host after the other:** Windows — worktrees, repos,
  workflow, stops, replay, trace parity, activities, flows, architecture and the history's reading: 53 classes,
  295 tests, OK. WSL — those and round boundaries, settings, workbench, settings delivery, cli, observability
  and the public check's own tests: 96 classes, 484 tests, OK.
- **Controls, one guard out at a time, each put back and the tree byte for byte as before:** a moved base
  unnoticed before the landing commit; the base taking git's own merge again; the change committed on the
  run's own branch, the base's coming in with it; a remote asked where it stands unfetched; the base never
  looked at by the workflow — the new recording stops replaying too; a base that came in cleanly sent to the
  engineer; the history blind to the base. Each failed the tests named for it.
- **`make demo`**, a stack of its own beside the live one: passed on this code — real workflow, worker, git
  and Workbench, its run looked at against its base and landed by the two commits. The git steps of F7 gave
  the same answers under git 2.54 on WSL. **`make public-check`:** passed.
- **Not run:** the full suite; a restart; a run with real agents; a push to a real remote.
- **To settle before a repository names its remote:** one whose pushes must pass a check first needs that
  check as its pre-push hook, which the controller's push runs. This repository has none (F10): until it has,
  its own entry should name no remote.

### 2026-10-07 — the reviewer's three findings on the remote landing

- **Reviewer:** `PASS` on the reconciliation and the history; a blocker on turning the remote landing on.
- **Applied, each red first:** the push is leased on the commit the change was judged on (F11) — the wording
  "forces nothing" is gone with it: the lease is a compare-and-swap, and the commit pushed is that commit's
  own descendant, asserted before the push; the remote's destination is fingerprinted at setup and held to at
  every fetch and push (F12); a remote's base is named with it and needs no local branch, the worktree view
  reading against it too (F13).
- **Refuted:** nothing.
- **Verification, the modules the change touches, one host after the other:** Windows — worktrees, repos,
  workflow, stops, replay, trace parity, activities, flows, architecture and the history's reading: 53 classes,
  299 tests, OK. WSL — those and round boundaries, settings, workbench, settings delivery, cli, observability
  and the public check's own tests: 96 classes, 488 tests, OK — after a test's own stand-in for the worktree
  view, and the fixture tool's for the worktree's creation, took the arguments those steps now take.
- **Controls, one guard out at a time, each put back and the tree byte for byte as before:** the push
  unleased — the rewound remote takes it; where the remote leads unchecked — the redirected one is reached;
  a remote's base looked for among the local branches. Each failed the tests named for it.
- **`make demo`** and **`make public-check`:** passed on this code.
- **Not run:** the full suite; a restart; a run with real agents; a push to a real remote.
- **Still to do before this repository names its remote**, as the reviewer and the agent both hold: its
  public check as a pre-push hook.

### 2026-10-07 — the reviewer's two edge cases of the remote

- **Reviewer:** `PASS` on the three fixes; a blocker still on turning the remote landing on.
- **Applied, each red first:** a base that no longer holds the commit the run stands on is refused by the
  look that would bring it in (F14) — after the refused push, not only at it; a remote with more than one URL
  to fetch from or to push to is refused, at setup and at every fetch and push (F15).
- **Refuted:** nothing. The agent had held the first to be enough said at the gate, where the dropped content
  would have shown as the run's own change; a base rewritten on purpose is the operator's to answer, not a
  diff's to reveal.
- **Verification, the modules the change touches, one host after the other:** Windows — 53 classes, 302
  tests, OK. WSL — 96 classes, 491 tests, OK.
- **Controls, one guard out at a time, each put back and the tree byte for byte as before:** a base that
  no longer holds the run's commit brought in like any other; a remote taken with any number of URLs. Each
  failed the tests named for it.
- **`make demo`** and **`make public-check`:** passed on this code.
- **Not run:** the full suite; a restart; a run with real agents; a push to a real remote.
- **For the pre-push hook this repository needs before it names its remote** (the reviewer's note): it must
  judge the commit being pushed, not the checkout — a remote landing leaves the local branch and its files as
  they were, and today's public check reads the index and the working tree.

### 2026-10-08 — the public check as the pre-push hook

- **Reviewer:** `PASS` on the merge and the reconciliation, no more design changes; next the hook that
  judges the commit being pushed, a review of it, and only then the full suites.
- **Built, each red first:** the public check judges a commit — `--pushed` as git's hook, `--commit` by hand
  — its tree read into an index of its own, so what is tracked, its bytes and the history it descends from
  are the commit's and the checkout's index is neither read nor written (F16); `make hooks` states the hook
  in git's configuration and asks git whether it will run it (F17); under Git for Windows the check is
  handed to WSL (F18).
- **Changed on the way, the agent's:** the hook as first built — a file under `hooks/` — did not run for the
  controller on this machine: three pushes it should have refused landed in a throwaway repository (F17).
  Hence the configuration; and in the controller, a pre-push hook whose file git would pass by now refuses a
  remote landing before anything is committed, and a refused push no longer says the remote refused what the
  repository's own hook did.
- **Refuted:** nothing.
- **Verification, the modules the change touches, one host after the other:** WSL — the public check's own
  tests, worktrees and architecture: 21 classes, 124 tests, OK. Windows — worktrees; the public check's
  tests are WSL's: 14 classes, 86 tests, OK.
- **Controls, one guard out at a time, each put back and the tree byte for byte as before:** the
  controller's push made with `--no-verify`; a hook's file that git would pass by not looked for; the
  checkout's index judged for a commit; every ref's history judged for it; a deleted ref judged; only the
  first ref of a push judged; git not asked whether it runs the hook. Each failed the tests named for it.
- **Real pushes through the installed hook, the real scanner, a bare repository on this machine's drive,
  under WSL's git 2.54 and Git for Windows 2.55 alike:** a clean commit pushed; one holding the scanner's
  control refused, the checkout clean of it; a clean one whose history holds it refused; a merge commit no
  branch holds, leased on the base as the controller pushes, landed while the checkout staged the control —
  which the check by hand then refused. This repository's own head, judged as a push of it: passed, 12 s.
- **`make demo`** and **`make public-check`:** passed on this code.
- **Not run:** the full suite; a restart; a run with real agents; a push to a real remote.
- **Not done:** `make hooks` in this clone — it changes what the operator's own pushes do, and waits for the
  review; this repository's entry names no remote.
- **Put to the reviewer, and accepted:** whose scanner configuration judges a commit, and what an older git
  is left with — both now among the decisions under D4.

### 2026-10-08 — the reviewer's two points on the hook

- **Reviewer:** `PATCH` — the hook itself good; pin what the hook's configuration says as the remote's URL
  is pinned; hand over to WSL in the main checkout, not where git stood, and test that from a linked worktree
  on Windows. The skipped-file guard and the refusal's wording accepted.
- **Applied, red first:** what git runs before a push — every hook its configuration states, and the bytes
  of its pre-push hook's file — is fingerprinted at the run's setup beside the remote, and the push held to
  it as the last thing before it is made (F19). The file's mode is left out: a hook that is not executable is
  refused as that, and made executable it is the same hook.
- **Refuted, with the evidence:** that the hand-over could run a worktree's copy. It could not (F20): the new
  Windows test passed on the script as it stood. The line now names the checkout outright, and the test and a
  control hold it there.
- **Verification, the modules the change touches or that use its stand-ins, one host after the other:** WSL
  — worktrees, repos, workflow, stops, replay, round boundaries, trace parity, activities, flows, policy,
  terminal, trust, workbench, settings delivery, cli, observability, architecture and the public check's own:
  111 classes, 554 tests, OK. Windows — those of them its host suite holds, the public check's now among
  them: 74 classes, 391 tests, OK.
- **Controls, one guard out at a time, each put back and the tree byte for byte as before:** the push not
  held to the gate; the file's bytes left out of it; what the configuration states left out of it; the gate
  not handed to the merge; the hand-over made where git stood (Windows); the stated command finding the
  script in the worktree pushed from. Each failed the tests named for it.
- **Real pushes, the real scanner, both gits, a sixth case:** from a linked worktree whose own copy of the
  check passes anything, a commit holding the control — refused by the main checkout's, nothing pushed.
- **`make demo`** and **`make public-check`:** passed on this code.
- **Not run:** the full suite; a restart; a run with real agents; a push to a real remote.
- **Not done:** `make hooks` in this clone; this repository's entry names no remote.
- **Not covered, for the reviewer to weigh:** the fingerprint holds what git is told to run, not the bytes of
  the program that command runs — here the main checkout's own script and scanner configuration, files a
  role's turn could write as it could any of the operator's. That is the hook's own to guard, if anyone's,
  not the controller's, which knows a repository's hook only as git does.
