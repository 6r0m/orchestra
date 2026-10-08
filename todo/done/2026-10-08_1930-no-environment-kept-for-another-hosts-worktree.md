# The test runner keeps no environment for a worktree its host does not own

**Status:** DONE 2026-10-08 — the external reviewer accepted the design and named three closing details
(PATCH, no further review asked for); each is closed below.
**Scope:** where the WSL runner builds the environment its tests run in ([run-tests.sh](../../run-tests.sh)).
No change to how a run's worktree or its own host's environment is removed.
**Stable documentation owner:** D22 in [structure.md](../../docs/architecture/structure.md).

## Goal

Nothing a run's agents do with the documented test runner leaves an environment behind on a host that will
never remove it.

## Authority register

### Operator decisions

- **D1** The leftover is fixed where it arises, not cleaned up by hand after each run.
  - Date/source: 2026-10-08, operator: *"I guess it's need to fix side effect on global level?"*.

### Decided under D1 — the agent's

- **Prevention at the runner, not a sweep and not a call across hosts.** The host that removes a run's
  worktree removes the environment it built itself (D22); the other host's runner therefore keeps none. A
  sweep would have to tell a dead worktree's environment from another checkout's by its name alone, and a
  removal across hosts would have to spell the other host's path as its runner happened to.
- **What tells the two cases apart is whether this host's git reads the checkout** — the same fact the
  suite's line-endings rule turns on: a worktree names its git directory in the spelling of the host that
  made it.

## Verified evidence (2026-10-08, run `find-one-small-6625194f`)

- The run's host was Windows. Its engineer ran the WSL suite from the worktree, as its plan required, and
  WSL built an environment for that worktree under its own root. A merge or a discard removes a worktree's
  environment on the run's host only; nothing on WSL would ever have removed that one.
- Until the shell scripts were pinned to LF a Windows worktree's runner could not start on WSL at all, so
  the case did not arise before.

## What changed

- [run-tests.sh](../../run-tests.sh): in a checkout this host's git reads, nothing changes — the checkout's
  own environment, kept, and the tests take the shell's place as before. In one it does not read, the tests
  run in an environment of their own under a temporary folder, removed when they end; a signal sent to the
  shell is handed on to them and they are waited for, and their exit status is the runner's.
- D22 says which host keeps an environment; [tests/README.md](../../tests/README.md) routes to it and names
  what the harness's tests prove of the runner.

## Verification

- **Red first:** in a checkout whose `.git` names a git directory this host cannot spell, the environment the
  tests ran in was still there afterwards.
- **`tests.test_harness.TheRunnersEnvironment`**, with a stand-in for uv: a checkout this host's git reads
  keeps its environment under the root; one it does not read gets one that is gone afterwards, with none
  under the root, the tests' own exit status passed on; ended from outside, the tests are told, their
  environment is still theirs when they have ended, and it goes only then. Controls: on a runner that hands
  the signal on without waiting for them, and on one that does not hand it on, that test fails.
- **The real runner and the real uv**, in a worktree made by Git for Windows, from WSL: the tests ran, their
  failing status came through, WSL's environments were the same before and after, and no temporary folder
  was left.
- **Interrupted, the same way,** with a class running and a process that class had started: `TERM` to the
  script alone, `HUP` and `INT` to its process group, and `TERM` twice — each time uv, the run, the class
  and what it had started were gone when the script ended, its status the run's own 130, the temporary
  folder gone and WSL's environments unchanged. Control: without the line that hands the signal on, all
  four were still running after the script had ended and removed their environment.
- **The one environment that run had left on WSL** went by the application's own removal once the run had
  landed: the name that removal derives for the worktree was the leftover's, and WSL keeps its checkout's
  alone.
- **The whole suite, one host after the other, on the tree that holds this:** WSL: 141 classes, 696 tests,
  OK; Windows: 97 classes, 496 tests, OK.

## Review

- **External reviewer, 2026-10-08 — PATCH.** The design stands. (1) An interruption with the real uv was
  unproved, the suite's test using a stand-in that ends itself: proved above, and the runner needed no
  change. The same look showed the suite's test passing on a runner that did not wait for the tests' end;
  it fails there now. (2) The environment left on WSL, removed after the run's merge, and (3) the row in the
  tests' README, added once the run had landed — both above.

## Not done here

- `run-tests.ps1` is unchanged: a worktree WSL's git made sits on WSL's own disk, which no Windows runner
  is started in.
- Other entry points that build an environment — the `Makefile`'s targets, the workers' scripts — are not
  what a run's agents use to run tests, and keep their checkout's environment as before.
