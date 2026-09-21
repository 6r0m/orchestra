# Orchestra

**Local-first orchestration and operator workbench for coding agents.**

Temporal owns workflow state. Git owns code and merge state. Claude Code and Codex stay exactly what
they are — native CLI agents, running on your machine, in their own terminals. Orchestra adds the
part that is usually missing: a deterministic loop between them, live terminals you can watch and
type into, a review you can read, and gates only a human answers.

```
Engineer → Architect → Approval → Engineer → Architect → Merge
```

## The problem it solves

An agent that works alone produces changes nobody reviewed. An agent supervised by hand produces
one change at a time, and only while you watch. The usual answers — a chat window, a CI bot, a
framework that owns the model — either lose the review or take the agent away from you.

Orchestra keeps the agents native and puts a workflow around them:

- **Two roles, one loop.** An engineer plans, an architect assesses, you approve, the engineer
  builds, the architect verifies, you merge. Each role keeps one conversation across its two
  stages, so the reviewer of the plan is the verifier of the build.
- **Only a verdict routes.** The architect ends every turn with `PASS`, `PATCH`, `BLOCKER` or
  `UNVERIFIED`, and that verdict is the only thing the workflow reads. Rounds are budgeted; when a
  budget runs out the run stops for you instead of looping.
- **The work happens in a worktree, never on your branch.** Agents never stage, commit, merge or
  push. The controller does that, after your explicit *Merge*, and commits exactly the tree the
  architect verified.
- **Nothing is lost when something dies.** A worker killed mid-turn takes the agent's whole process
  tree with it and the run stops for you to continue; the workflow's state is Temporal's history,
  not a process's memory.

## Architecture

```
            ┌──────────────────────────────────────────────┐
  browser → │  workbench (localhost)                       │   runs, stops, rounds,
            │  every run · live terminals · diff · gates   │   the change, the answers
            └───────────────┬──────────────────────────────┘
                            │ start / status / answer          (one client, also used by the CLI)
            ┌───────────────▼──────────────────────────────┐
            │  Temporal  — owns the workflow                │  plan → assess → build → verify,
            │  one workflow execution per run               │  stops, routing, retries, replay
            └───────────────┬──────────────────────────────┘
                            │ activities on the run's target queue
        ┌───────────────────▼───────────────────┐   ┌───────────────────────────────┐
        │  worker (WSL / Linux)                  │   │  worker (Windows)             │
        │  git worktree · role turns · terminals │   │  same, with ConPTY + Job      │
        └───────────────────┬───────────────────┘   └──────────────┬────────────────┘
                            │ one contained process tree per turn  │
                    ┌───────▼────────┐                     ┌───────▼────────┐
                    │  claude (CLI)  │                     │  codex (CLI)   │
                    └────────────────┘                     └────────────────┘
```

Each host runs its own worker and polls its own task queue, so a repository that must build on
Windows gets Windows agents and a Linux-only repository gets WSL agents — from one checkout, on one
machine. A turn is the vendor's real interactive CLI in a real PTY (ConPTY on Windows), contained so
that the worker's death is the agent's death, including anything it started.

The source is organised the same way: one package per concern under [app/](app/README.md), whose
README routes to each, and each states at its own level what it owns, what it may import, and the
invariants it keeps.

Every durable document — running it, the architecture, how it came to be — is reached from
[docs/README.md](docs/README.md). Read [docs/architecture/structure.md](docs/architecture/structure.md) for what owns what, and
[docs/architecture/diagrams/main.md](docs/architecture/diagrams/main.md) for the parts and the
processes they run in.

## Quick start

You need Docker, [uv](https://docs.astral.sh/uv/), git, and whichever agent CLIs you intend to use
(`claude`, `codex`) installed and signed in as you normally use them.

```bash
git clone <this repository> orchestra && cd orchestra
cp .env.example .env          # nothing in it is required to start
make up                       # Temporal + its database, both workers, the workbench
make check                    # which queues are polled, and the page's URL
```

Open the page — `http://127.0.0.1:8390` by default — and start a run on this repository. To work on
your own repositories, copy `repos.example.json` to `repos.json` (ignored) and describe them there;
the page can also start a run on any path you type.

```bash
make feature TASK="fix the retry in the uploader"   # the same run, from the command line
make down                                           # stop everything; Temporal keeps its data
```

<!-- A screenshot or short GIF of the workbench belongs here: the run list, a live terminal
     mid-turn, and the final gate with a diff. Put it in docs/images/ and link it. -->

## Windows and WSL

One checkout serves both hosts, on a Windows drive (`/mnt/<drive>/…` from WSL) — a native Windows
process cannot use a `\\wsl.localhost\…` path as its working directory, so a checkout on the Linux
filesystem cannot run the Windows worker. Each host keeps its own Python environment on its own
disk, so the two never share a virtual environment.

Containment differs per host and both are real: a POSIX worker puts each turn in its own systemd
scope and reaps it; a Windows worker creates the agent **inside** a Job Object atomically, so a
worker that dies between spawn and assignment cannot leave an agent behind.

## Security and trust

- **Local-first.** Everything listens on loopback: the workbench, the terminal sockets, Temporal.
  Nothing is exposed to a network.
- **The page's own token.** The API and the terminal sockets accept only a token generated on first
  use, from the page's own origin, and the terminal sockets take it in the handshake's header rather
  than in a URL.
- **Agents cannot reach a remote.** A role's git environment refuses every transport, so a push
  fails even if an agent tries; the controller alone commits and merges, after your answer.
- **Only what a stage judged can proceed.** A plan changed after the architect passed it goes back
  for assessment before a build starts; a change made while the architect verifies fails that step;
  a merge commits exactly the verified tree or refuses.
- **Vendor trust dialogs are recorded, not bypassed.** Orchestra records a repository you start a
  run on with the CLIs' own trust stores, so an unattended turn does not sit at a dialog — and it
  never overrides an explicit `untrusted` decision of yours.
- **The private surface is one file.** `.env` holds credentials and machine-specific values;
  `.env.example` names its keys. Everything about how runs behave is public configuration in
  `policy.json`. Before publishing anything from a fork: `make public-check`.

## What is proven

The suite is the argument. It runs on both hosts and covers the things that are easy to claim and
hard to do: crash and restart, process-tree containment, exact turn completion for each vendor,
session loss and rehydration, merge and discard lifecycles, replay-safe workflow evolution, large
diffs through Temporal's payload limit, and the operator's page.

```bash
bash run-tests.sh                       # the whole suite, in this checkout's environment
python tests/acceptance_restart.py      # live acceptance: real Temporal and workers, fake agents
```

The live acceptance restarts the server and the workers mid-run, kills a worker while a role is
running, changes a plan between `PASS` and *Approve*, reads a change larger than one Temporal
payload in parts and compares it against a patch `git` prints itself, then merges one run and
discards another — and leaves nothing on the host. [tests/README.md](tests/README.md) says what each
file proves; [docs/history/](docs/history/) records how the system got here.

## Configuration

| what | where |
|---|---|
| roles, brains, budgets, timeouts, ports, target hosts | [`policy.json`](policy.json), validated strictly by [`policy.py`](app/foundation/policy.py) |
| how each role works | [`roles/engineer.md`](roles/engineer.md), [`roles/architect.md`](roles/architect.md) |
| the repositories runs may work on | `repos.json` — yours, ignored; copy [`repos.example.json`](repos.example.json) |
| credentials and machine-specific values | `.env` — see [`.env.example`](.env.example) |

Running it day to day — the page, the command line, and where to look when something is wrong — is
[docs/using.md](docs/using.md). What is being worked on right now is in [todo/](todo/README.md).

If you have your own engineering skills for your CLI, bind them per stage with `stage_skills` in a
policy of your own, named by `ORCH_POLICY`: the page, the command line and the workers all load the
policy it names, and the bound skill leads that stage's prompt. Orchestra ships none, and its role
files say enough to work without one. A policy inside the checkout needs nothing more. One outside it
is copied to each host, with that host's worker's `ORCH_POLICY` naming its copy; a copy that differs
from the policy a run started with is refused rather than used.

## License

MIT — see [LICENSE](LICENSE). The vendored `app/interfaces/workbench/static/vendor/xterm/` is
[@xterm/xterm](https://github.com/xtermjs/xterm.js) 5.5.0, MIT, unmodified.
