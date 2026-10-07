# Codex output parsing: a valid JSON array or scalar is noise, not an event

**Status:** PASS (implementation) 2026-10-07
**Scope:** the Codex adapter's two output parsers — `session()` and `final_message()` in
[codex.py](../app/agents/adapters/codex.py) — and their tests under [tests/agents/](../tests/agents/).
No production code changes.
**Stable documentation owner:** [tests/README.md](../tests/README.md) (its `| file | proves |` table owns
what each test file proves). The adapters' contract in
[adapters/\_\_init\_\_.py](../app/agents/adapters/__init__.py) already owns the `session`/`final_message`
signatures and needs no change.

## Contents

- [Goal](#goal) · [Authority register](#authority-register) · [Non-goals](#non-goals)
- [Verified evidence](#verified-evidence) · [Current architecture](#current-architecture-and-source-of-truth)
- [Problem](#problem-and-root-cause) · [Decision](#decision) · [Invariants](#required-invariants)
- [Tasks](#implementation-tasks) · [Verification](#test-first-and-verification-plan)
- [Documentation](#documentation-plan) · [Completion](#completion-criteria) · [Review record](#review-record)

## Goal

A valid JSON line that is an array or a scalar, appearing in a Codex turn's output before the real
`thread.started`, is treated as noise: the turn's real session and real final message are still
extracted, no session id is harvested from the noise, and neither parser raises. That this holds is
proven by a test that has been shown able to fail.

## Authority register

### Operator decisions

- **D1** Audit the Codex adapter's output-parser tests for one concrete gap — valid JSON lines that are
  arrays or scalars before a valid `thread.started` event. If the adapter can crash, add a focused
  regression and make the smallest fix that preserves extraction of the real session and final message.
  - Effect: the fix half is conditional on a demonstrated crash. Evidence shows no crash is reachable
    (see [Verified evidence](#verified-evidence) F1–F4), so the conditional does not trigger and this
    change adds a test only.
  - Reason: a small Orchestra self-check for the operator to review.
  - Date/source: this task, 2026-09-30.
- **D2** Keep the change to this adapter and its tests; do not broaden the audit.
  - Effect: binds [Non-goals](#non-goals). Other kinds' parsers, other input classes and the
    pre-existing docstring wording are out of scope even where evidence notices them.
  - Reason: not stated.
  - Date/source: this task, 2026-09-30.
- **D3** Do not stage, commit, merge, push, or discard the worktree.
  - Effect: the change is left in the worktree for the architect; the controller commits, and only after
    a human approves. Binds the temporary mutation in [Red evidence](#red-evidence): it must be reverted
    inside the worktree, never stashed or committed.
  - Reason: the controller does that, and only after a human approves.
  - Date/source: this task, 2026-09-30.

### Operator gates

None. No question here changes the goal, the architecture, safety, or an irreversible outcome.

### Working assumptions

- **A1 [ACTIVE]:** the new test module stays out of the Windows list in `run-tests.ps1:11`. Both parsers
  are pure string and JSON handling with no host dependence, and [tests/README.md](../tests/README.md)
  describes that list as the files that exercise a host. WSL coverage therefore suffices.
- **A2 [ACTIVE]:** the new module gets a row in `tests/README.md`'s `| file | proves |` table, because 23
  of the 24 test files on disk have one and that table is the durable owner of what a test file proves.

## Non-goals

Each of these is excluded by D2, or by the evidence showing there is nothing to fix:

- Changing `codex.py`. The `startswith("{")` guard stays exactly as written.
- Adding an `isinstance(event, dict)` check to `session()`. It would duplicate the guarantee the guard
  already provides (F1, F4) and add a branch no input can reach.
- Auditing `claude_code`'s or any other kind's parsers, or raising this to a contract-level property
  tested across every shipped kind. F5 shows only Codex parses a JSON stream at all.
- A non-string `thread_id` (for example `{"type": "thread.started", "thread_id": {"a": 1}}`, which
  `session()` would return as a dict). A different input class from the one D1 names, and speculative.
- The docstring at `codex.py:118`, which says the events are "as `codex exec --json` prints them" while
  `command()` builds an interactive turn. Pre-existing wording.
- The missing `agents/test_adapters.py` row in `tests/README.md`'s table. A pre-existing gap.

## Verified evidence

### Verified facts

- **F1** `session()` ([codex.py:124-135](../app/agents/adapters/codex.py)) strips each line and skips
  anything not starting with `{` (its guard at lines 127-128) before `json.loads`. Its `except ValueError`
  at line 131 catches a malformed `{`-prefixed line. It holds no `isinstance` check, so that guard is the
  only thing between a non-object JSON line and `event.get("type")`.
- **F2** `final_message()` ([codex.py:145-156](../app/agents/adapters/codex.py)) applies the same `{`
  guard, and `message_of()` (lines 138-142) additionally checks `isinstance(event, dict)`. It is protected
  twice; `session()` once.
- **F3** Runtime probe at HEAD (`d9fa616`), calling both parsers directly on one stream of `[1, 2]`, `3`,
  `"hi"`, `true`, `null`, `{not json}`, an indented array wrapping a plausible
  `{"type": "thread.started", "thread_id": "spoof"}`, and plain prose, followed by real
  `thread.started` / `item.completed` / `turn.completed` events: `session()` returned the real thread id
  and `final_message()` the real message. On the noise alone: `None` and `""`. **No crash is reachable,
  so D1's fix half does not trigger.**
- **F4** Mutation probe, on a copy of the module outside the repository with only the two guard lines
  removed from `session()`: the same stream raised `AttributeError: 'list' object has no attribute 'get'`,
  which `except ValueError` does not catch. The mutant's `final_message()` still returned the real
  message, confirming F2. The guard is load-bearing, and load-bearing in `session()` alone.
- **F5** `claude_code.session()` returns `minted` unread, `final_message()` returns `out` verbatim, and
  `message_of()` returns `None` ([claude_code.py:151-160](../app/agents/adapters/claude_code.py)). Parsing
  a JSON event stream is Codex's concern alone, not a shared contract property.
- **F6** Callers: `nodes.extract_session` ([nodes.py:101-108](../app/agents/nodes.py)) calls
  `session(out, minted)` and raises `TransportError("the agent's turn named no session")` when it is
  falsy — so the `None` return in F3 is a contract, not an accident. `nodes.parse_review` (nodes.py:146)
  applies its own `{` guard. `activities.py:322` and `nodes.py:177` reach `final_message`.
- **F7** No existing test feeds a valid non-object JSON line to either parser.
  `tests/agents/test_adapters.py` covers the loader only (its classes are `Loading` and `Finding`).
  `tests/orchestration/test_workflow.py:352` feeds `codex_first_out("")`, `codex_first_out(" \n")` and
  `"no events at all\n"`; line 193 feeds plain prose. A grep of `tests/` for array or scalar inputs to
  either parser returns nothing. **This is the gap.**
- **F8** `tests/agents/test_terminal.py:297` already calls `session(out, None)` directly, so a parser
  called straight from a test in `tests/agents/` is established practice. That module is PTY- and
  subprocess-heavy and runs on both hosts.
- **F9** `run-tests.ps1:11` lists `tests.agents.test_adapters` among the Windows-host modules. A new
  module is not in that list.
- **F10** `tests/README.md:59-83` keeps a `| file | proves |` table with 23 rows against 24 test files on
  disk; `agents/test_adapters.py` is the one with no row.
- **F11** `tests/test_architecture.py` enforces README routing over `app/` and scans unit tests for
  unguarded trust writes. Nothing in it enforces the tests table, and the planned test writes no file.

### Inferences

- The strip-then-`{` shape in both parsers, and `message_of`'s `isinstance` check, read as deliberate
  tolerance of whatever else a turn prints, not as an accident. F5 and the vendor's own experimental,
  unguaranteed `--json` event format make that tolerance worth pinning rather than narrowing.

### Assumptions / unverified areas

- Whether real Codex builds ever emit a top-level array or scalar line was not measured against an
  installed CLI. The test pins Orchestra's tolerance either way, which is what D1 asks about; it does not
  claim the vendor emits such a line.

### Refuted

- **"The adapter can crash on an array or scalar line before `thread.started`."** Refuted by F3: both
  parsers skip every such line before `json.loads` and extract the real session and message. The crash is
  one guard removal away (F4), not present.

## Current architecture and source of truth

A kind's module owns everything that differs between agents; every other module takes a kind as data and
asks its module ([adapters/\_\_init\_\_.py](../app/agents/adapters/__init__.py)). Reading a finished
turn's output is part of that contract: `session(out, minted)` names the session a new turn began, and
`final_message(out)` its answer. `nodes.extract_session` and `nodes.parse_review` consume them and own
the refusals (F6). Per [tests/README.md](../tests/README.md) the suite mirrors the packages, so these
tests belong under `tests/agents/`; the shared fixtures stay at the suite root in
[tests/fakes.py](../tests/fakes.py).

## Problem and root cause

There is no defect to fix (F3, and the Refuted entry). The gap is in the evidence: the `startswith("{")`
guard in `session()` is the single point of protection against a valid non-object JSON line (F1, F4), and
no test exercises that input class (F7). Nothing in the suite would notice the guard being dropped as a
tidy-up — and dropping it produces exactly the `AttributeError` D1 asks about, which would surface
through `extract_session` as an `internal` error instead of the intended `TransportError` refusal (F6).

## Decision

Add one test module, `tests/agents/test_output.py`, holding one class with two tests over
`app.agents.adapters.codex` called directly. Change no production code. Add the module's row to
`tests/README.md`'s table (A2).

### Premise / KISS gate

The owner is already there: `codex.py` owns the parsing and `tests/agents/` owns that package's tests.
This change adds **no** service, process, fixture, helper or abstraction — one test module and one
documentation row, and it reuses `tests/fakes.py:codex_first_out` for the real events so the test cannot
drift from the event shapes the rest of the suite uses. Nothing is deleted.

`tests/agents/test_output.py` is a new file rather than a class inside `tests/agents/test_adapters.py`
because that module's charter is the loader — kinds found rather than listed, each checked against the
contract on load — and its two classes are `Loading` and `Finding`. A Codex parser test there would
force its docstring open to hold an unrelated concern. The repository names test modules for the concern
(`test_trust.py`, `test_launch.py`, `test_terminal.py`), and `test_output.py` follows that. `test_terminal.py`
is rejected as a home despite F8: its charter is the live terminal and it pays PTY and subprocess cost on
both hosts for what is a pure function call.

Knowingly given up: the test does not run on Windows (A1, F9). The parsers touch no host, so the Windows
run would re-prove the same pure-Python result at the cost of a `run-tests.ps1` entry.

### Alternatives considered

- **Harden `session()` with an `isinstance(event, dict)` check.** Rejected: the guard already provides
  that guarantee (F1, F3), so the branch is unreachable, and a second mechanism for one property invites
  the next reader to remove the first. It would also make the mutation in [Red evidence](#red-evidence)
  stop discriminating, leaving the property with no test that can fail.
- **A class in `tests/agents/test_adapters.py`.** Rejected on charter (above). It would gain Windows
  coverage for free (F9) — coverage A1 judges to be worth nothing here.
- **Raise this to a contract-level test across every shipped kind.** Rejected by D2, and independently by
  F5: there is no shared behaviour to pin, since `claude_code` parses nothing.

## Required invariants

1. `session()` returns the real `thread_id` from the first `thread.started` event with a truthy
   `thread_id`, whatever valid JSON of any other shape precedes it.
2. No session id is ever taken from a line that is not a JSON object — including an array that wraps a
   well-formed `thread.started` object.
3. `final_message()` returns the last agent message, whatever else the stream holds.
4. On a stream with no real events, `session()` returns `None` and `final_message()` returns `""`, which
   is what `extract_session`'s `TransportError` refusal depends on (F6).
5. Neither parser raises on any input. A malformed `{`-prefixed line stays a skipped line.
6. `app/` is unchanged by this todo, and the worktree holds no other edit when it is done (D3).

## Implementation tasks

- [x] Add `tests/agents/test_output.py`: the module docstring states the concern it owns — what a kind
      reads out of a finished turn's output, and that for Codex only a `{`-prefixed line is an event — and
      the `HERE`/`PKG` `sys.path` preamble copied from its sibling modules in the folder.
- [x] Write the two tests below and observe each fail under the mutation in
      [Red evidence](#red-evidence) before anything else is touched.
- [x] Confirm `git diff -- app/` is empty: the mutation is reverted and no production code changed
      (invariant 6).
- [x] Add the module's row to `tests/README.md`'s `| file | proves |` table (A2), naming what it proves,
      not how.
- [x] Run the checks in [Green evidence](#green-evidence) and record what each said.
- [x] Re-read the final diff against this todo; leave the worktree as it is (D3).

## Test-first and verification plan

Both tests are **permanent regression guards** for machine-provable contracts (invariants 1-5). There is
no acceptance measurement to take, because the behaviour is already correct (F3): what is missing is a
guard that can fail.

One shared input, `NOISE`, one line each: `[1, 2]`, `3`, `"hi"`, `true`, `null`, an indented
`  [{"type": "thread.started", "thread_id": "spoof"}]  ` (the array carrying a plausible event — indented
so it also pins that the strip happens before the guard), a malformed `{"type": "thread.started"`, and the
prose line `thinking...`. The real events come from `tests/fakes.py:codex_first_out("the answer", "t-real")`
so the test borrows the suite's event shapes rather than inventing a parallel grammar.

| case | proves | wrong behaviour it captures |
|---|---|---|
| `test_valid_json_that_is_not_an_object_is_never_an_event` — `NOISE` then the real events: `session(out, None) == "t-real"` and `final_message(out) == "the answer"` | invariants 1-3, 5 | a parser that raises on a non-object line, or that harvests `"spoof"` from the array ahead of the real event |
| `test_noise_alone_names_no_session_and_no_answer` — `NOISE` only: `session(NOISE, None) is None` and `final_message(NOISE) == ""` | invariants 4, 5 | a parser that raises where `extract_session` expects a falsy return to refuse with `TransportError` |

### Red evidence

The known-bad control is a mutation, since there is no pre-existing defect to fail on: in
`app/agents/adapters/codex.py`, temporarily delete the two guard lines
(`if not line.startswith("{"):` / `continue`) from `session()` **only**, run both tests, and observe each
fail with `AttributeError: 'list' object has no attribute 'get'` — not with an assertion mismatch, which
would mean the test found the wrong thing. Then restore the file and prove it restored with
`git diff -- app/agents/adapters/codex.py` returning empty. Never stash or commit the mutation (D3).

This control is what makes the two tests evidence at all: against the current, safe code every arm passes,
so a test written without it would discriminate nothing. Observed: with the guard deleted, both tests
error at `codex.py:131` with that `AttributeError` — an error, not an assertion mismatch — and both pass
once it is back, with `git diff -- app/` empty.

Not claimed: the mutation is the one measured control. The `"spoof"` assertion additionally pins ordering
against a future parser made tolerant enough to search inside an array, but no control for that variant
has been run.

### Green evidence

The runner takes modules, classes and single tests, as unittest names them — never a package. A package
name holds no tests, so `runner.py:147` raises and `runner.py:78-80` prints it and returns 5. The concern's
modules are therefore named one by one, and on the host the change was made on, which is this worktree's
own (`run-tests.ps1`; the same names follow `bash run-tests.sh` on WSL):

- `run-tests.ps1 tests.agents.test_output` — the two new tests with the guard restored.
  **1 class, 2 tests, OK, exit 0.**
- `run-tests.ps1 tests.agents.test_terminal` — the concern's heaviest neighbour, run as its own module.
  **7 classes, 31 tests, OK, exit 0.**
- `run-tests.ps1 tests.agents.test_adapters tests.agents.test_trust tests.agents.test_launch
  tests.test_architecture` — the concern's remaining modules, since the new one sits beside them, and the
  repository's rules about its own source, which scan the suite for unguarded trust writes (F11).
  **20 classes, 82 tests, OK, exit 0** — among them `TrustStaysOffTheOperatorsHome`, which now reads the
  new module too, and `EveryConcernIsReachable`, which reads the edited `tests/README.md`.
- `git diff -- app/` empty, and `git diff --stat` one insertion in `tests/README.md`; the new test module
  and this todo are untracked. Nothing staged, committed, merged or pushed (D3).

Per [tests/README.md](../tests/README.md) the whole suite runs once when the change is otherwise done,
and on both hosts only when the change touches launching, terminals or worktrees — which this does not
(A1). Whether to spend the full two-host run on a test-only change is the architect's call.

## Documentation plan

- **Authoritative stable owner:** [tests/README.md](../tests/README.md) — its `| file | proves |` table
  owns what each test file proves (F10).
- **Router / TOC update:** none. The `| folder | covers |` table already routes `agents/` to
  [app/agents](../app/agents/README.md), and the new module adds no folder.
- **Content to add or change:** one table row for `agents/test_output.py`.
- **Duplication avoided:** the row says what the module proves and does not restate the guard's mechanism,
  which `codex.py` owns as code. `adapters/__init__.py` already owns the contract line for
  `session`/`final_message` and is left alone.
- No stable doc, comment, test or configuration file references this todo.

## Completion criteria

- `tests/agents/test_output.py` holds the two cases in the matrix above, and both were observed failing
  with `AttributeError` under the mutation and passing with the file restored.
- `git diff -- app/` is empty; `git diff --stat` shows only `tests/agents/test_output.py` and
  `tests/README.md`.
- The three commands in [Green evidence](#green-evidence) all passed, and the report states what each
  said rather than that they were run.
- Nothing staged, committed, merged, pushed or discarded; the worktree is left intact (D3).

## Review record

### 2026-09-30 — investigation

- **Trigger:** D1 — audit the Codex output parsers for one input class, arrays and scalars before a valid
  `thread.started`, and fix a crash if one exists.
- **Root cause:** none in production. The `startswith("{")` guard in `session()` already makes every such
  line noise (F1, F3). The real gap is that this guard is the single point of protection (F4) and no test
  exercises the input class (F7), so its removal would pass the suite while turning an intended
  `TransportError` refusal into an `internal` error (F6).
- **Fix:** no production change. One test module and one `tests/README.md` row.
- **Verification:** planned — see [Test-first and verification plan](#test-first-and-verification-plan).
  Established during investigation: the HEAD probe (F3) and the mutation probe on a module copy outside
  the repository (F4).
- **Authority:** D1, D2, D3 recorded; A1, A2 opened; no gate.

### 2026-09-30 — implementation, and the architect's first round

- **Trigger:** implement the approved todo; then two required findings — green evidence incomplete and
  unreported, and an adjacent `test_terminal` failure left unattributed.
- **Root cause of the first finding:** the verification plan named `tests.agents`, a package. The runner
  takes only modules, classes and single tests, so it printed `no tests in tests.agents` and ran nothing;
  a `| tail` in the invocation then hid its exit code, and the run was read as green. Both are corrected
  in [Green evidence](#green-evidence), which now names modules and records what each run said.
- **Attribution of the second finding:** not reproduced, and not a defect this change can reach.
  `test_it_ends_its_turn_on_its_own_signal_and_resumes_its_session`
  (`tests/agents/test_terminal.py:291`) failed once, actual `(1, None)` — the *resumed* turn exited
  rc=1 — inside a six-module parallel pool. It then passed four times: the class alone; the same pool
  with the new module removed; the whole `test_terminal` module alone (7 classes, 31 tests, OK); and
  within that module's own run. The turn is a real PTY turn against `fake_cli.py`, and the new module is
  two pure-function tests in a process of their own, so it cannot change that turn's logic. What is
  claimed: a load-sensitive failure that did not recur. What is **not** claimed: that a defect exists, or
  that the new module's presence in the pool tipped it — the pool without it passed, so there is no
  evidence either way. Left alone per D2; no fix folded in.
- **Fix:** no change to the tests or to `app/`. The todo's Green evidence was corrected and filled in.
- **Verification:** 28 classes and 115 tests across `tests/agents/` and `tests/test_architecture`, all
  OK at exit 0, in the three runs listed in [Green evidence](#green-evidence).
- **Authority:** none added; D1, D2, D3 unchanged; A1 and A2 still active.
