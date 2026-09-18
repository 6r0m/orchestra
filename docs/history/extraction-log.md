# What the extraction had to prove

An extraction is only believable if the system still does what it claimed, from the new repository,
on both hosts it supports. This is what was run and what it showed. Every number here comes from
this repository, not from the one it left.

## The suites

| where | result |
|---|---|
| WSL / Linux, everything | `Ran 226 tests … OK (skipped=1)` |
| Windows, the files that exercise a host | `Ran 163 tests … OK (skipped=8)` |

The Windows list is the one in [tests/README.md](../../tests/README.md); the rest is either
platform-independent or needs a facility that host does not have.

## The live acceptance

`python tests/acceptance_restart.py`, against real Temporal and real workers with fake agent CLIs —
no model is called and nothing of it stays on the host:

```
PASS prepare already recorded this repository for claude, codex
PASS the run is back at approval, not building
PASS no build turn ran: assess-e1-1.out, assess-e2-1.out, plan-e1-1.out
PASS after the restart the workers poll again
PASS the change was larger than one payload and came through Temporal in 2 parts
PASS every part named the same change
PASS the parts joined are that patch, byte for byte (792568 bytes)
PASS killing the worker ended the grandchild within 5 s, before any timeout
PASS the first run merged … the merged worktree is gone … and so is its branch
PASS no trust record of its repository is left with either CLI
ACCEPTANCE PASSED
```

## The page

A run was parked at its final gate with a change larger than one payload, and the change was read to
the end in the browser, against a patch produced independently by `git`:

| | characters | checksum |
|---|---|---|
| what the page showed | 792,524 | 4048044673 |
| what `git` printed | 792,524 | 4048044673 |

The *read the next part* control then disappeared, and the terminals of a run whose worker had
restarted said *recorded*, not *live*. The run was discarded afterwards and its harness reported
nothing left behind.

## The public gate

`make public-check` passes, and it is not taking the scanner's word for it: every run feeds Gitleaks
a credential-shaped control from a temporary directory and fails if the scanner does *not* reject
it. Two of its rules were written by being wrong first — the tool allowlists its vendor's own
documented example key and obvious placeholder strings, so a control made of those proves nothing.

The scan covers the files a push would carry and the whole history, not the checkout: an ignored
`.env` holds real credentials by design, and that it is untracked is checked separately. That
distinction was also found by being wrong: the first version scanned the directory and correctly
reported the real keys in `.env`.

The one allowlisted path is `workbench/vendor/xterm/`, where a minified identifier in unmodified
upstream code matches a generic high-entropy rule. It is backed by evidence rather than trust: those
three files compare byte for byte against the published 5.5.0 tarball, whose sha512 is recorded
beside them.

## What the extraction itself broke, and how it was caught

- **A stage's skill became a binding, and the acceptance's fake agent stopped recognising its build
  stage** — it keyed on the skill invocation that the shipped policy no longer contains. The live
  acceptance failed on it: a change of one part where two were expected. The fake now reads the
  stage's own ask.
- **A new Makefile expanded task text.** The private repository's `feature` target passed a task
  through `$(value …)` for a reason; a fresh Makefile that used `$$TASK` let Make evaluate
  `$(shell …)` inside a task description. The test that exists for exactly that failed, and the
  guard came back.
- **Tests that encoded the old repository's facts**: the credentials file's location, a release
  derived from two paths inside a monorepo, descriptors that named the operator's repositories, and
  a page scenario that relied on the checkout's own path being a WSL target. Each now states what
  this repository is, not what the other one was.
- **Recorded histories carried the recording machine** — its hostname in every event's identity, and
  its paths inside base64 payloads that no text search would have found. The recorder now replaces
  both, and the replay guard still passes against the regenerated files.
