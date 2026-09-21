# Source organised by concern — D30

**Status:** the move is done; the second and third reviews (PATCH, PATCH) are answered in the
working tree, unstaged, and await review. What is left is the operator's.

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

## Second review — PATCH, answered

Each finding checked against the code; the fixes are unstaged, beside the staged move.

1. **Accepted — the resolver was not cross-host safe.** A policy carried its client's absolute
   path, and a target with no `ORCH_POLICY` of its own resolved it there. Measured across the two
   hosts: a policy loaded on WSL and decoded on Windows sent the staged resolver to a
   `roles/engineer.md` under a directory that does not exist. Fixed: a policy inside the checkout
   carries its origin relative to it, the target's own `ORCH_POLICY` decides over that, an origin
   only the other host can spell and a missing persona are refused, and the refusal happens
   inside the step, so it fails the step before an agent starts. The same crossing now resolves
   to the Windows checkout's own persona files. Four new tests fail against the staged resolver.
2. **Not accepted — a separate package for the stage contract.** `foundation` already owns
   domain rules through `policy` — the two roles, the independent judge, the git authority —
   and the policy is validated against the stages. A `contracts` package would sit below
   `policy`, add an edge, and split one contract across two owners. The real defect was
   `foundation`'s one-line description, which named only host facts; it is corrected wherever it
   appeared, and the reason is in `foundation`'s own structure document.
3. **Accepted — `from .. import sibling` passed the boundary check.** Every name taken by an
   import is now resolved against its module, so `from .. import high` and `from app import high`
   both read as `app.high`; the control now expects the violation.
4. **Accepted, and it found more than it said.** The guard checked files, not hops — and every
   scope, the project's included, skipped `docs/README.md` from its README. Every README now
   routes one level down, and the guard checks each hop as a link; a README skipping a level,
   injected into the real tree, fails it.
5. **Accepted.** The main view missed `application → foundation` and five `interfaces` edges. It
   now draws exactly the allowed imports, and the test compares the view with the table and the
   table with the imports that exist.
6. **Accepted, and understood.** The flake was the time-skipping server closing the run: awaiting
   a workflow's result — the page reading a change — lets its clock jump to the parked run's
   default ten-year run timeout. The history of a failing run ends in a timeout, and Temporal's test
   server answers an Update to a closed run with exactly the error seen. Behind it was a real
   defect: a closed run still answers its status query with the stop it closed at, so an answer
   to a run terminated at a gate came back as a failure of the page. Fixed red-first — that
   answer is now refused as not waiting — and the page's scenarios run in real time, which is how
   a gate is answered. Without the real-time change the module failed 1 in 30 runs; with it,
   none in 60.

## Third review — PATCH, answered

The reviewer accepted the refutation of point 2: `stages` stays in `foundation`, which stays
dependency-free and holds only small shared contracts and facts.

1. **Accepted — a resolved persona path still crossed hosts.** Validation stored each role's
   resolved `prompt_path` in the policy the client sends; the target ignored it, but the value was
   still there. Validation now only proves the persona exists, and the one resolved path is the
   target's, made inside the step.
2. **Accepted, and it was worse than stated.** A target's `ORCH_POLICY` lent only its directory,
   so a copy naming other personas would have been read silently. It is now a copy of the run's
   policy by contract: anything but where it was read must match, or the step fails before an
   agent starts. Checking that exposed a real defect: `load()` never read `ORCH_POLICY`, so a run
   started from the page, or from the command line without `--policy`, carried `policy.json` even
   where `ORCH_POLICY` bound its stage skills. `load()` now reads it, for every entry point.
3. **Accepted — the proof now sits at the activity boundary.** A client's policy, decoded as
   Temporal carries it, goes through `Activities.run_role` with the runner seam as the agent, on
   each host's suite: the prompt the agent receives carries that host's persona, and an unreadable
   origin or a differing copy starts no agent. Mutations — storing the path again, skipping the
   copy check — each fail two of the new tests.

## Left for the operator

1. **The index and the commit.** The move is staged; the second review's fixes are not. Nothing
   was committed, and neither the commit nor the branch is an agent's to make.
2. **One acceptance run from before this work is still open,** holding its worktree and branch. A
   discard is the operator's (D24).
3. **A WSL-to-Windows role turn with real agents,** if wanted: the activity boundary is proven on
   the Windows host suite with a fake agent, and the vendor CLIs' own transport by the terminal tests.

## Optional

4. `app/agents/nodes.py` keeps a name that says nothing about what it owns — prompt rendering, the
   agent argv, session identity and verdict parsing. A rename was out of scope.

## Verification

Of the second and third reviews' fixes, on the working tree: the full WSL suite (280 tests) and the Windows
host suite, `tests.foundation.test_policy` included, green; the recorded histories replay; the
workbench module 60 times in a row without a failure; each new guard failing on a violation
injected into the real tree — a README skipping a level, an arrow missing from the main view, a
bare relative climb into a sibling — and passing again once it was removed; the live acceptance on
the real stack, restart and killed worker included; a real server answering an Update to a closed
run with the `NOT_FOUND` the client now refuses as not waiting; the page rendered by a headless
browser against the live stack, with every asset and API call answering 200; `make public-check`
and `git diff --check` clean.
