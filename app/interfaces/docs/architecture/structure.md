# Structure

## Purpose

Give a person and a process manager a way in — a command line, a worker per host, and one
page over every run — without any of them owning behaviour worth testing on its own.

## Owns

- `cli` — the command line over `application.client`: start, answer, continue, show, list, worktrees.
- `worker` — one Temporal worker per host, polling that host's queue and no other.
- `workbench/server` and `workbench/static` — the operator's page: every run, its stop and answers, its live terminals, its rounds and its change.

## Does not own

Any behaviour worth testing without a process. Everything an interface does belongs to
[application](../../../application/README.md) or below; these modules parse arguments,
print, serve and exit. The page holds no state of its own.

## Composition

| part | responsibility |
|---|---|
| `cli.py` | the command line over the shared client |
| `worker.py` | this host's Temporal worker and the queues it polls |
| `workbench/server.py` | the page's HTTP server and its small JSON API |
| `workbench/static/` | the page itself: HTML, CSS, JavaScript and a pinned xterm.js |

## Relationships

This package's relationships are drawn once, in [the main view](diagrams/main.md).

Through `application.client`: every start and every answer, so the page and the command
line can do nothing the workflow's own rules and validators do not allow.

Through the worker's WebSocket: the page attaches to a run's live terminals on whichever
host is running them.

There is no facade here: the CLI reads a repository descriptor and the page reads a
terminal record directly, and an indirection to hide that would buy nothing.

## Invariants

- **Nothing imports an entry point**, enforced by `tests/test_architecture.py`. That is what keeps argparse and console output out of the worker and the workbench.
- **The workbench holds no state (D29).** Every read is Temporal's or a worker's, and every write is a start or an answer Update.
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
