# How Orchestra was extracted

Orchestra grew inside a private repository, as one subsystem of a personal automation monorepo. This
is the record of moving it out into its own public repository: what was decided before anything was
copied, what changed on the way, and what deliberately stayed behind.

## Why it moved at all

The system had reached the point where its own documentation, tests and acceptance were the largest
part of it, and none of that could be read by anyone. A tool whose whole claim is *deterministic,
reviewable agent work* is worth little if the determinism cannot be inspected. So the subsystem
became the product, and the monorepo became one of its users.

Orchestra is now the single owner of the implementation. The private repository keeps no second copy.

## Decided before moving

**Where it lives.** The extraction was first proposed onto the Linux filesystem
(`\\wsl.localhost\Ubuntu\home\...`), which would have been faster for WSL. It cannot live there,
and this was measured rather than argued: a native Windows process given a WSL UNC path as its
working directory reports

```
CMD.EXE was started with the above path as the current directory.
UNC paths are not supported.  Defaulting to Windows directory.
native cwd: C:\Windows
```

Orchestra runs workers on *both* WSL and Windows from one checkout, so the checkout has to be on a
path both can use — a Windows drive, reached as `/mnt/<drive>/…` from WSL. `repos.py` already
refuses a Windows target on a Linux-only path for this exact reason; the checkout is subject to the
same rule.

**A clean history.** 41 commits touched the subsystem, and every historical version of `repos.json`
in them names private repositories and absolute operator paths. Rewriting 41 commits to be safe is
more risk than the history is worth, so Orchestra starts with its own history and the private
repository keeps the full one. Nothing is lost that matters: the architecture and its decisions are
written down in `docs/architecture/`, and the review history that produced them is summarised here.

**Flat modules, not a nested package.** The obvious public-repository instinct is
`orchestra/orchestra/*.py`. It was not done. Every module is imported by bare name, the worker and
the PTY host are launched as scripts by path, and the tests put the directory on `sys.path`; a
package layer would touch every import and every launch path to change nothing a user can see. The
repository root *is* the package directory.

*Superseded.* That held while the extraction was the only change in view. It stopped holding once
Orchestra had to be read by people who had not watched it being built, and the source now lives in
one package per concern under `app/`
([D30](../architecture/structure.md#composition)); what changed the decision is in
[decisions.md](decisions.md). The paragraph above is kept as the reasoning of the time, not as a
description of the repository today.

## What moved, and what changed on the way

| what | change |
|---|---|
| the implementation, tests, tools, roles, architecture docs, Temporal compose | moved as they were |
| the repository root | `ORCHESTRATION_REPO` was the monorepo, two levels above the code; it is now the Orchestra checkout, which is where `tmp/` and `secrets/` live |
| repository descriptors | `repos.json` held the operator's own repositories: it is now ignored, with `repos.example.json` committed, and a missing file means "no descriptors", not an error |
| the trace's release | was derived from two paths inside the monorepo; it is this repository's own commit |
| machine identity | host label, worktree roots and every path in documentation and tests are generic; nothing names the operator, their machine or their private repositories |
| the database password | the Temporal stack's PostgreSQL password comes from the environment with a development default, instead of being written into the compose file |
| the workbench port | already moved off 8090 before the extraction, because Unreal Editor listens there on Windows |

## What stayed in the private repository

- the operator's own `.env`, credentials and `secrets/`;
- their repository descriptors, which name private work;
- the monorepo's other subsystems, including the agent instruction set the engineer role reads from
  the host's own configuration directory;
- the task journal that produced this system, including the review rounds quoted in
  [decisions.md](decisions.md);
- the full git history.

## What the extraction had to prove before the first push

Not "it copied cleanly" — the same things the system always had to prove, from the new repository:
both hosts' full suites, the live acceptance against real Temporal and workers, the browser
acceptance, and the public-safety gate with a control that shows the scanner actually rejects
something. Those results are in [the extraction log](extraction-log.md).
