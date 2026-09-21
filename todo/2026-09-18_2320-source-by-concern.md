# Source organised by concern — D30

**Status:** the move is done and verified; four review findings on top of it are closed. What is
left is the operator's, plus one pre-existing flake.

## Goal

Make Orchestra's source readable by someone who did not watch it being built: one package per
concern under `app/`, each stating at its own level what it owns, what it does not, what it may
import and the invariants it keeps — with the direction between them enforced by a test rather
than by a convention.

## Authority register

- **D1** — Operator: supersede the standing flat-root decision. Complete the move into
  concern-owned packages under `app/` with recursive README ownership, replace the flat module
  manifest with package-boundary tests, give Orchestra's own paths a neutral owner, mirror the
  concerns under `tests/`, and do not implement a proposed dependency table mechanically.
  **Status: DONE.** Durable record: D30 in [structure.md](../docs/architecture/structure.md); the
  reasoning in [decisions.md](../docs/history/decisions.md).
- **D2** — Operator: a todo with no secrets, showing work in progress, is good for a public
  repository. **Status: DONE** — this directory, and [its rules](README.md).
- **D3** — Operator: every concern carries its own architecture address, with structure and
  diagrams, as black boxes reached by recursive routers. **Status: DONE** —
  `app/<concern>/docs/architecture/`, routed from [app/README.md](../app/README.md).

## What landed

- Seven packages: `foundation`, `orchestration`, `workspace`, `agents`, `observability`,
  `application`, `interfaces`. Each has `docs/architecture/structure.md` and a `diagrams/main.md`
  drawing its own parts.
- `foundation.paths` derives the checkout root once. Three packages stopped importing `workspace`
  to get it, so the graph narrowed by fixing ownership rather than by adding indirection.
- `foundation.stages` owns the stage contract — the stages, their roles, their asks, the verdicts.
  It used to sit in `agents/nodes.py`, justified by being "next to the workflow that depends on
  it", which stopped being true the moment the workflow moved.
- `foundation.policy.prompt_path` is the one resolver for a role's persona file. Validation and
  the host that runs the role each built the path themselves, so a policy outside the checkout was
  validated against its own directory and then read from the checkout — two files, one name.
- The architecture test enforces package boundaries, resolves relative imports, and proves the
  checkout root still lands on a checkout. Every check carries a control, and the boundary check
  was measured against violations injected into the real tree.

## Left for the operator

1. **The index and the commit.** `git mv` staged the renames; the new files are staged too.
   Nothing was committed, and neither the commit nor the branch is an agent's to make.
2. **One run is still open:** `acceptance-d45ab567`, running since before this work and holding
   its worktree and branch. A discard is the operator's (D24).

## Known, not caused here

3. **`tests/interfaces/test_workbench.py` fails intermittently.** The final-gate unconfirmed
   discard answers 502 instead of 422: `execute_update` against the time-skipping test server
   raises `RPCError('update answer:<run>:2 not found')`, which `client.answer` does not catch, so
   the page's generic handler answers 502. Measured 3/3 at the commit before this work in a clean
   clone, and it passes in a full suite run — pre-existing and intermittent. A fix would catch that
   error beside `WorkflowUpdateFailedError` and answer 409, but the flake should be understood
   before it is dressed up as a refusal.

## Optional

4. `app/agents/nodes.py` keeps a name that says nothing about what it owns — prompt rendering, the
   agent argv, session identity and verdict parsing. A rename was out of scope.

## Verification

Full WSL suite and the Windows host suite green; the recorded histories replay; live acceptance on
the real stack, including a server-and-workers restart and a worker killed mid-turn; the page
served and rendered in a browser with every asset and API call answering 200; `make public-check`
passing with its scanner control still rejecting a known-bad string.
