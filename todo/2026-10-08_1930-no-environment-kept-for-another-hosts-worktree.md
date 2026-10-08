# The test runner keeps no environment for a worktree its host does not own

**Status:** IMPLEMENTED — awaiting the external reviewer's look (D1). The touched tests pass on both hosts.
One row of [tests/README.md](../tests/README.md) is still to add, once the run that found this has landed —
it changes that file too.
**Scope:** where the WSL runner builds the environment its tests run in ([run-tests.sh](../run-tests.sh)).
No change to how a run's worktree or its own host's environment is removed.
**Stable documentation owner:** D22 in [structure.md](../docs/architecture/structure.md).

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
  suite's line-endings rule now turns on: a worktree names its git directory in the spelling of the host
  that made it.

## Verified evidence (2026-10-08, run `find-one-small-6625194f`)

- The run's host was Windows. Its engineer ran the WSL suite from the worktree, as its plan required, and
  WSL built an environment for that worktree under its own root. A merge or a discard removes a worktree's
  environment on the run's host only; nothing on WSL would ever have removed that one.
- Until the shell scripts were pinned to LF a Windows worktree's runner could not start on WSL at all, so
  the case did not arise before.

## What changed

- [run-tests.sh](../run-tests.sh): in a checkout this host's git reads, nothing changes — the checkout's own
  environment, kept, and the tests take the shell's place as before. In one it does not read, the tests run
  in an environment of their own under a temporary folder, removed when they end; a signal sent to the
  shell is handed on to them and they are waited for, and their exit status is the runner's.
- D22 says which host keeps an environment.

## Verification

- **Red first:** in a checkout whose `.git` names a git directory this host cannot spell, the environment the
  tests ran in was still there afterwards.
- **`tests.test_harness.TheRunnersEnvironment`**, with a stand-in for uv: a checkout this host's git reads
  keeps its environment under the root; one it does not read gets one that is gone afterwards, with none
  under the root, the tests' own exit status passed on; ended from outside, the tests are told and the
  environment still goes.
- **The real runner and the real uv**, in a worktree made by Git for Windows, from WSL: the tests ran, their
  failing status came through, WSL's environments were the same before and after, and no temporary folder
  was left.
- **The touched modules, one host after the other:** the harness's and the architecture's — WSL: 11
  classes, 60 tests, OK; Windows: 11 classes, 60 tests, OK.

## Completion criteria

- The external reviewer's PASS (D1).
- The row for the runner's environment in [tests/README.md](../tests/README.md), after the run has landed.
- The one environment that run left on WSL removed, by the application's own removal, after its merge.

## Not done here

- `run-tests.ps1` is unchanged: a worktree WSL's git made sits on WSL's own disk, which no Windows runner
  is started in.
- Other entry points that build an environment — the `Makefile`'s targets, the workers' scripts — are not
  what a run's agents use to run tests, and keep their checkout's environment as before.
