# Add a row for the public check to `tools/README.md`

**Status:** PASS 2026-10-08 — the architect's PASS on the build
**Scope:** [tools/README.md](../../tools/README.md) — one table row. No code, no test, no other document.
**Stable documentation owner:** [tools/README.md](../../tools/README.md); its `| file | what it is for |`
table owns what each file in `tools/` is for, one row each. The row this change added *is* that
documentation, so nothing here outlived the change.

## What was decided, and why

`tools/` holds seven files beside its README, six of them documented across five rows — one row covers
both `demo_press` files — and [public_check.sh](../../tools/public_check.sh) had none. A reader of
`tools/` found no entry for the one tool [AGENTS.md](../../AGENTS.md) requires before every push, and
nothing of its four invocations without reading the script.

One row was added, drawn from the script's own header comment, carrying what the gate refuses and its
four invocations — `make public-check`, `--pushed`, `--commit`, and `--install` by way of `make hooks`.

- **The three categories, not the path list.** What it refuses is stated as the header's three numbered
  points, not as an enumeration of `.env`, `secrets/`, keys and descriptors. That enumeration already
  has two owners — the script itself and [AGENTS.md](../../AGENTS.md) — and a third hand-copy would
  drift from both.
- **First in the table, not appended.** Appending would have placed a tool that writes nothing to
  Langfuse directly above the table's "Both write to the real Langfuse" paragraph. The deciding reason
  is that this is the one tool here every contributor must run.
- **Nothing else changed**, by operator decision: no code, no test, no other document.

## What was done

One line added to [tools/README.md](../../tools/README.md), as the table's first body row.
`git diff --numstat` → `1  0  tools/README.md`.

## The evidence it passed on

- Every claim in the row traces to the header comment of
  [public_check.sh](../../tools/public_check.sh), and the row names all five of `make public-check`,
  `--pushed`, `--commit C`, `--install` and `make hooks`.
- Mentions of `public_check` in the file moved 0 → 1 and the table's body rows 5 → 6; its eight table
  lines each carry two columns; the row's link target resolves.
- `tests.test_architecture`, which owns the repository's document-routing checks, passed in full.
- `tests.test_public_check` passed but for `HandedToWsl`, which fails on a host condition this change
  neither created nor can reach: Git for Windows sets `core.autocrlf` at system scope and this
  repository pins no line endings, so `tools/public_check.sh` is checked out CRLF and WSL's bash
  rejects it. That file was unmodified, and the test never reads `tools/README.md`. Left alone, as
  [AGENTS.md](../../AGENTS.md) keeps an unrelated failing test out of a change. The same condition is
  why [run-tests.sh](../../run-tests.sh) could not run in this checkout and both modules were run by
  [run-tests.ps1](../../run-tests.ps1) on the Windows host; a Markdown row touches neither launching,
  terminals nor worktrees, so one host is what `AGENTS.md` asks for.

## Deliberately not acted on

`tools/README.md`'s opening line — "Nothing here runs as part of the workflow or the test suite" — is
imprecise about this one tool now that the table documents it: the controller's push fires the pre-push
hook, and the suite runs a copy of the script. It survives on the narrower reading that none of these
files is *collected* as a test, which the paragraph below the table suggests was the intent. Qualifying
it was outside this change, and the sentence stands exactly as it was. It wants an operator decision of
its own, not a closeout edit.
