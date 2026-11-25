# Orchestration tests

## Contents

- [Run the suite](#run-the-suite)
- [Test agents and model usage](#no-test-runs-a-real-agent)
- [Choose the test by the claim](#choose-the-test-by-the-claim)
- [Test inputs](#one-source-for-every-value)
- [Package tests and shared harness](#how-the-suite-is-laid-out)

## Run the suite

Run the full suite from the checkout in WSL.

```bash
bash run-tests.sh
```

It syncs this checkout's uv-managed environment (`app/foundation/envpath.py`), discovers every
`test_*.py`, at any depth, and runs each test class in a process of its own, a few at a time — a whole
run takes about as long as its slowest class. On Windows, the files that exercise a host run in that
host's own environment, and the list of them lives in the script:

```
powershell -NoProfile -ExecutionPolicy Bypass -File run-tests.ps1
```

While working on a change, name what it touches — modules, classes or single tests, as unittest names
them — and only those run: `bash run-tests.sh tests.interfaces.test_cli`. The whole suite, on each host
the change touches, runs once, when the change is otherwise done. A run fails on anything short of every
class passing whole: a failure, an error, a module that does not load, a class that ran fewer tests than
it holds, a run that found none, or a class still running after ten minutes — its threads dumped, then
its processes ended. However a run ends, interrupted included, it leaves no class running. One run per
host at a time.

The two hosts' suites share one localhost and its test ports, so run them one after the other.

Inside a run's own worktree three classes fail for the environment, not the code — they fail at an
unmodified checkout too — so take each suite's baseline first. On WSL, a worktree made by Windows git
names its gitdir by a drive path WSL's git cannot resolve, which fails `test_worktrees`' `Create`; one
WSL made reads fine. For such a worktree `run-tests.sh` builds its environment anew each time and keeps
none ([structure D22](../docs/architecture/structure.md)). On Windows, a role's git environment refuses every transport
([the Git transport invariant](../docs/architecture/structure.md#invariants)) and the suite's own processes inherit it, which
fails `test_worktrees`' `Remote` and `Guard` — cleared from the environment, both pass.

## No test runs a real agent

These tests are of Orchestra, not of agents. Nothing in this folder starts a vendor's agent or calls a
model, so no run of it — the whole suite on both hosts included — spends quota or needs a login. `claude`
and `codex` are played by a stand-in program (`fake_cli.py`) where a terminal is driven, and by scripted
turns (`fakes.FakeAgent`) everywhere else: what an agent "answers" is data the test wrote, so the agent's
scripted responses are repeatable. What is real is everything around the agent — the processes, the
worktrees, the PTY and Temporal's own test server — so a run can still fail on timing or on the host, as
any test of real processes can.

| what | a real agent or model | started |
|---|---|---|
| the suite — `run-tests.sh`, `run-tests.ps1` | never | by you: what a change touches while working, the whole of it once when the change is done |
| the live acceptance — `acceptance_restart.py` | never: real Temporal and real workers, fake agents | by you, by hand |
| a real agent run | yes: a vendor's CLI, on your account | by you, by hand, and by nothing here |

A changed value — a default model, an effort, a budget — is a deterministic rule, proven by the classes
that read that value, with scripted turns. Whether a vendor takes the model's name, and what the agent
then does, is a claim about the agent: only a real run answers it
([which to use](#choose-the-test-by-the-claim)).

## Choose the test by the claim

| What needs proving | Use |
|---|---|
| Orchestra's deterministic rules: settings and policy loading, run snapshots, flow and round routing, prompts and argv assembled from configuration, gates, recovery, cleanup and terminal wiring | Scripted agents at the role-turn seam. For a setting or policy that crosses components, add a smoke through its real entry point, client, Temporal workflow and activities; assert the recorded role turns and resulting state. Keep exact limits and failure cases in focused regression tests. |
| What the agent or its vendor CLI actually does: work quality, speed, understanding a prompt, loading and following a skill, or vendor-specific session and terminal behavior | A real agent run on the relevant host with a bounded task and observable outcome. Measure the property claimed; fake output cannot establish it. |

A live run can confirm an integration path, but it is not the regression guard for a deterministic
policy rule. A scripted run can prove which prompt and options Orchestra sends; only a real agent
can show how it responds. Use both when a claim spans both sides of that boundary.

Scripted agents are the default: a claim goes to a real agent only when no scripted turn can establish it.
Before any real run, ask the vendor's own CLI what it answers with no model called — the efforts its
`--help` names, the models its catalog lists (`codex debug models`). Where a change does need a real run,
it comes last, after every scripted check is green. A real run spends quota on your account, so a person
starts it, knowingly, and nothing in this repository does
([D10](../docs/architecture/structure.md#invariants)).

## One source for every value

A value the system is configured with — a profile's model and effort, the profile a role runs, a stage's
skill, a budget, the default flow — is written once, in
[the shared settings file](../.orchestra/settings.json). Read it from there, as the code does, and never
repeat it in a test or a fixture.

| A test needs | It reads |
|---|---|
| the shipped settings | `S.load()` — the suite names the shared settings alone (`tests/__init__.py`), never the operator's local patch |
| a scenario's settings | `cast.settings()`, `cast.policy()`, or `cast.file()` for an entry point that loads its own — the shipped settings, each role run by the profile the scenario names |
| what a scripted run was started on | `temporal_env.SETTINGS` and `temporal_env.POLICY`, made from that cast |
| what the page shows or a run received | the API's own answer, or the role turn the fake agent recorded |

Take the value a test expects from that reading. A literal that repeats what the file says fails the day
the file is edited, with nothing wrong. A fixture holds none of it either: the trace's kept rows carry no
agent profile, and `trace_rows.expected` gives each role's row the one its run's policy held.

Three things are a test's own, and stay in it:

- **Who plays its scenario.** Scripted turns speak one kind's contract, so a scenario says which profile
  runs each role — by the profile's name, never by a model or an effort. `cast.py` holds the cast every
  scenario starts with, a Claude engineer and a Codex architect, and a test that is about another names
  it: `cast.policy(engineer="codex-engineer")`. What that profile is — its kind, its model, its effort —
  stays the settings' to say, so a scenario that needs a kind of agent the settings do not define gets
  a profile added there, not a model written here.
- **An example it invents to exercise a rule** — a model token no vendor has, a settings file written
  into a temporary checkout, the policy a run started earlier carried. That is its input, not a copy: it
  names no real model, and it does not follow today's settings either. What an earlier run held is that
  run's own, and its test holds that it reaches the agent unchanged.
- **A value something outside the settings depends on**, pinned with its reason beside it — the workflow
  queue: runs started on it would be polled by no worker after a rename.

## How the suite is laid out

One folder per package under [app/](../app/README.md), named after it, holding that concern's tests.
The shared harness — the fakes, the controls, the fixtures and the recorded histories — stays at this
root, because it belongs to no single concern.

| folder | covers |
|---|---|
| [foundation/](foundation/) | [app/foundation](../app/foundation/README.md): the persona-file resolver and the flows, on either host |
| [orchestration/](orchestration/) | [app/orchestration](../app/orchestration/README.md): the workflow, its routes, its stops and replay |
| [application/](application/) | [app/application](../app/application/README.md): settings, target-host activities and the stack's one owner |
| [workspace/](workspace/) | [app/workspace](../app/workspace/README.md): repository descriptors and the worktree lifecycle |
| [agents/](agents/) | [app/agents](../app/agents/README.md): containment, live terminals, turn completion, trust records |
| [observability/](observability/) | [app/observability](../app/observability/README.md): the trace and its parity with the contract |
| [interfaces/](interfaces/) | [app/interfaces](../app/interfaces/README.md): the workbench's API over real runs, and how the command line types a stop's answers |

The client of runs is proven through its consumers and focused application contracts. Foundation path
derivation is checked by `test_architecture.py`, which owns what is true of the packages themselves.
Add a folder when a concern gains tests that are its own rather than its consumers'.

### Shared checks and fixtures

| What you need | Owner |
|---|---|
| Package boundaries, paths and documentation routing | [test_architecture.py](test_architecture.py) |
| Test isolation, timeout and process cleanup | [test_harness.py](test_harness.py) |
| Public scanning and known-bad controls | [test_public_check.py](test_public_check.py) |
| Test discovery and execution by class | [runner.py](runner.py) |
| Test Temporal server and worker setup | [temporal_env.py](temporal_env.py) |
| Scripted role replies and worktree seams | [fakes.py](fakes.py) |
| Interactive stand-ins for the vendor CLIs | [fake_cli.py](fake_cli.py) |
| Roles and settings for scripted scenarios | [cast.py](cast.py) |
| Recorded Temporal histories for replay | [histories/](histories/) |
| Record a new replay case | [record_histories.py](record_histories.py) |
| Live acceptance with real worker and server restarts | [acceptance_restart.py](acceptance_restart.py) |
| Remove and verify cleanup of a live test's exact runs | [temporal_cleanup.py](temporal_cleanup.py) |

See the [orchestration replay rules](../app/orchestration/docs/architecture/structure.md#invariants)
before recording a history. The [real-browser demo](../tools/README.md) covers the operator's
interactive workflow with scripted agents.
