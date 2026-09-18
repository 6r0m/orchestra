# interfaces

What a human or a process manager starts. Nothing imports this package.

## Owns

| module | responsibility |
|---|---|
| `cli.py` | the command line over `application.client`: start, answer, continue, show, list, worktrees |
| `worker.py` | one Temporal worker per host, polling that host's queue |
| `workbench/server.py` · `workbench/static/` | the operator's page: every run, its stop and answers, its live terminals, its rounds and its change |

```bash
python -m app.interfaces.cli "fix X in Y"        # or: make feature TASK="fix X in Y"
python -m app.interfaces.worker wsl | windows | check
python -m app.interfaces.workbench.server
```

The lifecycle scripts `workers.sh` and `workers.ps1` start the worker and the page; they
run them as modules from the checkout, which is what puts `app` on the path.

## Does not own

Any behaviour worth testing without a process. Everything an interface does is
`application`'s or below; these modules parse arguments, print, serve and exit.

## Depends on

Everything below it, directly. There is no facade here: the CLI reads a repository
descriptor and the page reads a terminal record, and inserting an indirection to hide
that would buy nothing.

## Invariants

- **Nothing imports an entry point**, enforced by `tests/test_architecture.py`. That is what
  keeps argparse and console output out of the worker and the workbench.
- **The workbench holds no state (D29).** Every read is Temporal's or a worker's, and every
  write is a start or an answer Update through `application.client`.
- **Everything listens on `127.0.0.1`**, and the API and the terminal sockets accept only the
  page's token, from the page's own origin. The terminal sockets take that token in the
  handshake's own header, never in a URL.
