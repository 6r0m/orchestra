# Orchestra — rules for anyone working here, human or agent

## PUBLIC REPOSITORY

Everything committed here is assumed public, permanently.

**Never commit:**

- credentials, tokens, passwords, cookies or private keys;
- `.env` or any secret file;
- Claude or Codex authentication, provider session data or session ids;
- terminal or run transcripts, unless they are intentionally sanitized fixtures;
- generated logs, runtime or cache state (`tmp/`, `secrets/`);
- contents copied from a private repository;
- private host, user or machine information where a generic example would do.

Use placeholders in examples: `/path/to/repo`, `you`, `localhost`.

Secrets belong in `.env`, in a runtime secret store, or in the vendor's own authentication store.
Generated state belongs only in the ignored runtime directories.

**Never disable, bypass, suppress or broadly allowlist a public-safety or secret-scanning failure to
make a commit pass.** A suspected false positive is investigated and explained, never waved through.

Before pushing: `make public-check`. It also runs on every push here, and it is the only
automated check — the suite is not run by CI, because it drives real processes, real worktrees
and a PTY, so it must run on a real host. Run `make test` yourself on the host you changed, and
on both when the change touches launching, terminals or worktrees.

## What owns what

Read [docs/architecture/structure.md](docs/architecture/structure.md) before changing behaviour; it
carries the accepted decisions and the invariants that must not be weakened. In short:

- **Temporal owns the workflow.** Every transition is the workflow's, from `routing.py`; no agent
  and no best-effort event decides one. A change to what the workflow commands goes behind
  `workflow.patched(...)`, or the recorded histories in `tests/histories/` stop replaying.
- **Git owns code and merge state.** Agents never stage, commit, merge or push; the controller does,
  and only after a human answers the final gate.
- **Langfuse is observability only.** A run behaves identically without it.
- **The vendors own their own conversations.** A role's session lives in the CLI's own store; what a
  terminal shows is evidence, not workflow state.

## Working here

- The repository root is the package: modules are imported by bare name and the workers, the PTY
  host and the tools are launched by path. Keep it that way.
- Tests before behaviour: a defect gets a failing test that fails for the real reason first.
  `bash run-tests.sh` on WSL or Linux, and the host suite on Windows — both are in
  [tests/README.md](tests/README.md).
- Documentation has one owner per fact. `docs/architecture/` owns the architecture; a README routes
  to it rather than restating it.
- Prefer what the platform already provides over new machinery, and leave nothing behind that has no
  present need.
