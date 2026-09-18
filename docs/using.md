# Using Orchestra

The page is the surface; everything below it is also reachable from the command line, which is what
the tests and any automation use.

## The stack

```bash
make up       # the Temporal stack, both workers and the workbench
make check    # which queues a worker polls, and the workbench's URL
make down     # stop the workbench, both workers and the stack; its data stays on its volume
```

Nothing is exposed beyond loopback. `make check` is also the quickest answer to "is anything
listening at all".

## The page

Open the URL `make check` prints. Runs are grouped by whether they need you, are running, or are
finished; older finished runs are a page away, so nothing Temporal still retains is out of reach.

A run shows its stop with that stop's answers as buttons, both roles' terminals, the rounds with
each verdict and its feedback, the change, and links to its Temporal and (if configured) Langfuse
pages. Each terminal is the vendor's own CLI: press Esc to interrupt a working agent, type to steer
it. A large change is read in parts, a press each.

*Worktrees* lists any repository's worktrees and which of them are still unmerged.

## The command line

```bash
# this checkout's own environment, on this host's disk
export UV_PROJECT_ENVIRONMENT="$(uv run --no-project --managed-python --python 3.13 python app/foundation/envpath.py "$PWD")"
O="uv run --locked python -m app.interfaces.cli"

$O "<task>"                        # a run on this repository
$O "<task>" --repo webapp          # a run on a repository named in repos.json
$O --resume <run-id> --answer yes  # answer the stop the run waits at
$O --continue <run-id>             # run a failed stage again, after you fixed its cause
$O --show <run-id>                 # the stage table and the architect's words
$O --worktrees --repo webapp       # every worktree, and whether its work is merged
```

Each stop prints what it asks and the answers it takes: `yes`, `revise <feedback>` or `abort` at the
plan's approval; your guidance or `abort` at a blocker or an exhausted budget; `continue` or `abort`
after a failed stage. At `READY_FOR_HUMAN` the run waits for `merge`, `revise engineer <feedback>`,
`revise architect <feedback>`, or `discard` with `--confirm`. Nothing is committed, merged or removed
before your `merge` or `discard`. A stopped run waits indefinitely, and any process may answer it.

## Where to look when something is wrong

| to answer | read |
|---|---|
| what a run is doing now, and what it did | the workbench; the lines the CLI prints as it follows a run; the Temporal web UI on `http://localhost:8080`, namespace `orchestration`; `--show <run-id>` |
| what an agent showed in its terminal, turn after turn | the run's terminals in the page; afterwards `tmp/orchestration/<run-id>/terminals/<role>.out`, replayed there |
| raw evidence of one stage | `tmp/orchestration/<run-id>/logs/<stage>-e<episode>-<attempt>.{prompt,out,err,events}` |
| what a role actually said and did, in full | that role's own session store, kept by the vendor CLI on the host it ran on |
| a run's history across rounds, and how runs go over time | Langfuse, when it is configured — see below |

## The optional trace

With `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` in `.env`, each run writes a work item: its
phases, every role turn with the verdict and feedback, each stop and answer, and the final diff.
Without them a run behaves identically and records nothing — the trace is never read back, and no
decision depends on it. What the rows promise is in
[architecture/trace-contract.md](architecture/trace-contract.md).

## The port

The workbench's port is `workbench_port` in `policy.json`. It has to be free on *both* sides on a
Windows + WSL machine: a Windows process listening on the same loopback port takes the connection
before WSL's forwarding does, and the page then never loads in a Windows browser. `netstat -ano |
findstr :<port>` on Windows names the holder. The default avoids the ports Unreal Editor uses, which
is the collision that prompted the rule.
