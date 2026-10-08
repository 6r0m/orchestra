# One owner in the suite for the port another process will bind

**Status:** PASSED 2026-10-08 — the architect passed the build on the base it will land on; closed out
the same day.
**Scope:** the test suite's shared harness — `tests/ports.py`, its three consumers, and
[tests/README.md](../../tests/README.md): the harness routing table, and what a run inside its own
worktree cannot prove. Widened once, for one item: the skip condition on `ShellScriptsStayLf` in
`tests/test_architecture.py` and its control. No production code, and one test's behaviour changed —
that skip, and nothing else.

This record cites code by name rather than by line. Four review rounds were spent on line numbers the
change itself had moved; a name stays true while the file around it shifts.

## What was decided, and why

`port_for_another_process` was defined three times inside the suite — byte-identical in
`tests/application/test_stack.py`, `tests/observability/test_stale_settings.py` and
`tests/acceptance_restart.py`. The copies had already drifted once and had to be unified by hand
(commit `d294692`), which is the demonstrated consistency need the engineering policy requires before
extracting anything. [tests/README.md](../../tests/README.md) already named the owner: the shared
harness lives at the test root because it belongs to no single concern, and the three consumers span
`application/`, `observability/` and the root.

So the helper moved to a new root-owned `tests/ports.py` and the three copies became imports. Rejected
alternatives: `tests/temporal_env.py`, because importing it would pull `temporalio.testing` and the
worker machinery into a module that deliberately has no Temporal at all; `tests/folders.py`, which owns
temporary folders; and a shared `TestCase`, mixin or fixture, because the consumers share no lifecycle
and one of them is an executable script, not a test case.

### Operator decisions

- **D1** Find exactly one small, worthwhile cleanup in this repository's tests — a duplication, or a
  piece in the wrong place for the suite's own structure — and make it, confined to the tests and
  their README: no production code, no behaviour change, every test that passed still passing.
  - Reason: a small Orchestra self-check for the operator to review.
  - Date/source: 2026-10-08, the operator's request.
- **D2** The paragraph on what a run inside its own worktree cannot prove belongs in the build, where
  the architect verifies it — carrying only what was measured in this worktree, saying on what
  evidence, no longer than its two facts need. At a later closeout, nothing is added to a document the
  architect has not seen.
  - Reason: the first closeout added it after verification, so nobody had reviewed it.
  - Date/source: 2026-10-08, the operator's guidance on reopening the change.
- **D3** `ShellScriptsStayLf` is fixed rather than documented: it skips unless
  `git -C <checkout> rev-parse --git-dir` succeeds, through a helper beside `scripts_not_lf` replacing
  a condition that only looked for a `.git` entry, with a control over no repository, a real one, and a
  `.git` file naming a gitdir that is not on this host. It then comes out of the README paragraph,
  leaving `test_worktrees`' `Create` for the WSL case.
  - Effect: widens the scope to `tests/test_architecture.py`, and to nothing else; it is the sole
    exception to this change carrying no behaviour change.
  - Reason: not stated beyond the preference for fixing the test over documenting its failure.
  - Date/source: 2026-10-08, the operator's guidance on reopening the change a second time.

## What was done

- `tests/ports.py` added as the suite's one owner, the helper's name, signature, docstring and body
  byte-identical to the copies removed.
- The three local definitions replaced by imports; `import socket` dropped from the two consumers that
  no longer named it, kept in `test_stack.py`, which opens a real socket of its own.
- The `Ports` control retargeted to `mock.patch.object(ports, "socket", system)` — the repository's own
  idiom for replacing a name in a module — with its simulated port sequence and all three assertions
  unchanged.
- `tests/observability/test_stale_settings.py` gained the one `sys.path` line it had never had, for the
  suite root alone, since it imports nothing of `app/`.
- `git_reads` added beside `scripts_not_lf` and made `ShellScriptsStayLf`'s skip condition, with
  `test_it_tells_a_repository_this_hosts_git_reads_from_one_it_does_not` in `TheCheckersCanFail`
  covering its three cases; `sys.platform` picks the fixture so each host exercises the other's
  spelling of an absolute path (D3).
- [tests/README.md](../../tests/README.md) gained a row for `ports.py`, and a paragraph on what a run
  inside its own worktree cannot prove — three classes, the cause on each host, and the evidence for
  each (D2, D3). The git guard itself stays owned by the root README and is cited there, not restated;
  what the paragraph adds is that guard's consequence for running the suite, which no document owned.

A fourth, byte-identical copy remains in `tools/demo.py`, outside D1's scope: the suite has one owner,
the repository has two. `tools/demo.py` already puts the test root on its path, so collapsing it needs
scope rather than mechanism — the one question this todo leaves open.

## The evidence it passed on

Main moved into this worktree while the change was in review, bringing a `run-tests.sh` that keeps no
environment for a worktree its host's git cannot read, and a `TheRunnersEnvironment` class. Every
reading below was taken again on that base.

- **The duplication**: three byte-identical copies, proven by `diff` of the ranges extracted from
  `git show`; the moved body byte-identical to the removed one by the same means. An AST pass over
  `tests/` read 3 definitions and 0 importers before, 1 definition and 3 importers after.
- **The extraction's control**: with the `Ports` patch left on its old target, the test fails
  `AssertionError: 47767 != 40002` — a real ephemeral port instead of the simulated sequence — so the
  retarget is what makes it pass.
- **D3's red, reproduced on the merged base**: with this change absent, `ShellScriptsStayLf` errors
  rather than fails — `CalledProcessError: git ls-files -z -- *.sh returned non-zero exit status 128` —
  because its condition asked only whether a `.git` entry exists, which a worktree satisfies while
  this host's git reads no repository. The predicate was checked before it was relied on:
  `rev-parse --git-dir` exits 128 here on WSL and 0 on Windows.
- **D3's green, and that the fix hides nothing**: `tests.test_architecture` reads 8 classes, 42 tests,
  `OK` on both hosts; and on Windows, with a tracked script made to hold a carriage return, the class
  still fails — so the rule is enforced where git can answer. The script was restored byte-identical.
- **The targeted matrix on the merged tree**: the two changed modules with `tests.test_architecture`
  beside them read 17 classes, 81 tests, `OK` on each host — the two modules' 9 and 39, plus the
  architecture module's 8 and 42.
- **The full matrix, each host against its own baseline on the merged base, in this worktree and under
  the same agent environment**:

  | run | classes / tests | failing |
  |---|---|---|
  | WSL, this change absent | 141 / 688 | `test_worktrees.Create`, `ShellScriptsStayLf` |
  | WSL, merged tree | 141 / 689 | `test_worktrees.Create` |
  | Windows, this change absent | 97 / 488 | `test_worktrees.Remote`, `Guard` |
  | Windows, merged tree | 97 / 489 | `test_worktrees.Remote`, `Guard` |

  Each host gains exactly one test, D3's control. No class moves from passing to failing, and
  `ShellScriptsStayLf` moves the other way. The three that remain are the two environmental limits the
  README paragraph records — the worktree gitdir on WSL, the inherited agent git guard on Windows.
- **The acceptance** was not run — it needs the live stack and the Workbench's service. Its one changed
  line was proven instead: the module compiles, its path setup precedes the `ports` import, and that
  import resolves to `tests/ports.py`.
- `tests.test_harness.Parallel` failed in one of several full Windows runs and passed in the others and
  in isolation. It cannot observe this change: it imports only the standard library and `tests.runner`,
  and drives its sub-runs over synthetic trees, never the real `tests/` tree. Left as an unrelated
  load-dependent instability; its diagnostic text was lost to a truncated capture and it did not recur.

No completion criterion was set aside.

## How this sits with what main brought

`run-tests.sh` now turns on the same `rev-parse --git-dir` probe that D3 uses, which corroborates the
predicate rather than duplicating the fix: that one decides where the uv environment lives, D3's decides
whether the line-endings rule can ask git anything. With this change absent from the merged base, the
class still errors. Ownership divides the same way —
[structure.md](../../docs/architecture/structure.md) owns where an environment is kept, and
[tests/README.md](../../tests/README.md) owns which classes cannot pass inside a run's own worktree.
That README still owes one row to the change main brought, which its own todo deferred until this one
landed.

## Corrected under review

- **The first wording of `tests/ports.py` and of its README row claimed isolation it does not have** —
  that no consumer could meet the live stack's ports or another test's. False, and it contradicted the
  helper's own docstring: the probe socket is closed before the child binds, so the port is free for
  anything to take in between. The `used` set makes the numbers within one policy distinct, and nothing
  more. Both now describe only what holds — a port free at that moment, never one the caller has
  already taken, released again.
- **The Windows baseline was argued by attribution before it was measured**, and both baselines were
  later taken again when main moved the base under the run.
- **The README paragraph was added by a closeout, after verification.** Under D2 it was written again
  as part of the build: only measured facts, with the evidence in the text, and shorter than before.
- **The todo lagged its own diff four times**, and one refutation of such a finding was itself wrong:
  the reviewer judgement, the documentation plan, criterion 7, the verification plan's "not a defect"
  and "no guard added", eleven line citations, and finally the whole measured matrix after the merge all
  described a tree that no longer existed. Two sweeps now exist for that class of defect — one over
  `path:line` citations, one over prose line references — and this record cites names instead.
- **One measurement was taken twice and only the clean one is recorded.** A probe ran on WSL while that
  host's baseline was still running, which this repository allows no more than one of at a time. The
  baseline was taken again alone; both readings agreed.
