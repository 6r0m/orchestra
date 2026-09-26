# Structure

## Purpose

Give a person and a process manager a way in — a command line, a worker per host, and one
page over every run — without any of them owning behaviour worth testing on its own.

## Owns

- `cli` — the command line over `application.client` and `application.stack`: start, answer, continue, stop, force terminate, show, list, worktrees, and the stack, which the Makefile's `up`, `down` and `check` run.
- `worker` — one Temporal worker per host, polling that host's queue and no other, and the sweep of what dead workers' stages left on the host.
- `workbench/server` and `workbench/static` — the operator's page: the stack and its controls, every run, its stop and answers, its live terminals, its rounds, its change and what it kept; and `workbench/orchestra-workbench.service`, the systemd user unit that runs the page in WSL.

## Does not own

Any behaviour worth testing without a process. Everything an interface does belongs to
[application](../../../application/README.md) or below; these modules parse arguments,
print, serve and exit. The page holds no state of its own.

## Composition

| part | responsibility |
|---|---|
| `cli.py` | the command line over the shared client and the stack's owner |
| `worker.py` | this host's Temporal worker and the queues it polls |
| `workbench/server.py` | the page's HTTP server and its small JSON API |
| `workbench/static/` | the page itself: HTML, CSS, its JavaScript as native modules — the stack, the runs, a new run, the run open with its terminals and its change, the worktrees, and `app.js` their entry — and a pinned xterm.js |
| `workbench/orchestra-workbench.service` | the systemd user unit the page runs as, rendered for a checkout by `make workbench-install` |

## Relationships

This package's relationships are drawn once, in [the main view](diagrams/main.md).

Through `application.client`: every start, answer, Stop, force terminate and removal, so the
page and the command line can do nothing the workflow's own rules and validators, or Temporal's own
lifecycle, do not allow. Through `application.stack`: the stack's reading and every start, stop
and restart of it, so neither keeps a second copy of how the stack runs.

Through the worker's WebSocket: the page attaches to a run's live terminals on whichever
host is running them.

There is no facade here: the CLI reads a repository descriptor and the page reads a
terminal record directly, and an indirection to hide that would buy nothing.

## Invariants

- **Nothing imports an entry point**, enforced by `tests/test_architecture.py`. That is what keeps argparse and console output out of the worker and the workbench.
- **The workbench holds no state (D29).** Every read is Temporal's, a worker's or the stack owner's — the stack's reading shared by the requests of a few seconds, and a finished run's view kept once read — and every write goes through `client` or `stack`.
- **The workbench never manages its own process (D32).** Systemd runs it; it starts and stops the stack, and the stack never includes it.
- **A stop's answers are the ones it publishes (D6).** The page and the command line offer exactly the actions a stop publishes; the page owns their labels, colours and dialogs, the command line their shorthands and how each is typed, and neither keeps its own list.
- **Everything listens on `127.0.0.1`**, and the API and the terminal sockets accept only the page's token, from the page's own origin. The terminal sockets take that token in the handshake's own header, never in a URL.
- **Agent text reaches the page as terminal bytes or as text, never as markup.**

## Accepted decisions

An index. Each decision is written where the project's architecture states it, beside the
boundary or invariant it constrains: see
[the accepted decisions](../../../../docs/architecture/structure.md#accepted-decisions).
The invariants above name the ones that bind this package.

## Risks and technical debt

The page's token keeps other sites and other users out, not other processes of the same
user, which can read it (D28). The page is plain HTML, CSS and JavaScript with no build
step, which is deliberate; the cost is that its one vendored dependency is pinned by hand.
