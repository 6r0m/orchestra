# Using Orchestra

The Workbench is the surface; everything it does is also reachable from the command line, which is
what the tests, any automation and the Makefile use.

## The Workbench

A systemd user service in WSL, installed once from this checkout. Start WSL from a normal terminal,
not an administrator's: Windows programs the service starts run with the token WSL was started with,
and the Windows worker — with every agent it runs — is never started as an administrator.

```bash
make workbench-install    # render it for this checkout and its environment, enable it, start it
```

From then on it starts whenever WSL does, comes back if it fails, and keeps serving
`http://127.0.0.1:8390` while the stack is down. It keeps running after your last WSL terminal closes
only while lingering is on for your WSL user — `loginctl show-user "$USER" -p Linger` says `yes`;
`sudo loginctl enable-linger "$USER"` turns it on, and the install warns while it is off.
`make workbench-start`, `workbench-stop`, `workbench-status` and `workbench-uninstall` are for its own
maintenance; everything else is done from the page.

## The stack

The panel at the top shows each part of the stack — Temporal, the WSL worker, which also runs the
workflows, and the Windows worker — as up, starting (running, not yet polling) or down, with Start,
Stop and Restart for each part and for the whole stack; a worker reads as running while Temporal
cannot be asked, and unknown while its process cannot be read. Temporal starts before the workers
and stops after them, and a part is reported up only once it is: Temporal answering, a worker polling
as its own process. Stopping a worker ends any agent at work on it — its stage then waits for you to
continue it — and removes at once what its stages left of their trace settings; a merge or discard it
is running may be cut off, and its run then waits at that step until the step fails or times out —
Force terminate ends it sooner. Stopping
Temporal pauses every run; an agent at work goes on, but if Temporal stays down longer than a role's
heartbeat interval, its stage fails and waits for you to continue it. Each stop asks first, saying
this. The same, from a terminal:

```bash
make up         # start the stack, each part proven up
make check      # each part's state, and the Workbench's service
make down       # stop both workers, then Temporal; its data stays, and the Workbench keeps serving
make restart    # the whole stack; one part: orchestrate --stack restart temporal|wsl|windows
```

Nothing is exposed beyond loopback.

## The page

Runs are grouped by whether they need you, are running, or are finished; older finished runs are a
page away, so nothing Temporal still retains is out of reach.

Each run says what it is doing now and for how long — the stage and the agent at work, the question
it waits on, the failure it stopped on — and, when a host's worker it needs is down, that it is
blocked by it, with that worker's Start beside it. A run whose worker is down is still shown.

A run shows its stop with that stop's answers as buttons, both roles' terminals, the rounds with
each verdict and its feedback, the change, and links to its Temporal and (if configured) Langfuse
pages. Each terminal is the vendor's own CLI: press Esc to interrupt a working agent, type to steer
it. A large change is read in parts, a press each.

*Stop run* ends a run from whatever it is doing — an agent at work, a stop waiting, a failed stage,
the final gate, a host whose worker is down — and keeps its worktree and branch as they are. A
merge or discard already running is let finish first, and decides how the run ends. *Force
terminate* is for a run a Stop cannot finish: it closes the run at once with no cleanup, but cannot
stop what the run's host is already doing — a worktree's creation, a merge or a discard already
running goes on and may still change the repository — and its confirmation says so.

A run that closed keeping its worktree and branch — stopped, force-terminated, or closed any other
way short of a merge or a discard — says so; look at its change, then *Remove worktree and branch*,
confirmed, deletes them through its host's own git as a discard would. It is refused while a merge
or discard of that run still runs on its host, and when git itself refuses, the page says why.
*Worktrees* lists any repository's worktrees, which of them are still unmerged and which run each is,
and removes a closed run's from there too.

## The command line

```bash
# this checkout's own environment, on this host's disk
export UV_PROJECT_ENVIRONMENT="$(uv run --no-project --managed-python --python 3.13 python app/foundation/envpath.py "$PWD")"
O="uv run --locked python -m app.interfaces.cli"

$O "<task>"                        # a run on this repository
$O "<task>" --repo webapp          # a run on a repository named in repos.json
$O --resume <run-id> --answer yes  # answer the stop the run waits at
$O --continue <run-id>             # run a failed stage again, after you fixed its cause
$O --stop <run-id>                 # end a run from whatever it is doing, keeping its worktree and branch
$O --force-terminate <run-id>      # close a run a stop cannot finish, at once; git already running goes on
$O --show <run-id>                 # the stage table and the architect's words
$O --worktrees --repo webapp       # every worktree, and whether its work is merged
```

Each stop prints what it asks and the answers it takes: `yes` or `revise <feedback>` at the plan's
approval; your guidance at a blocker or an exhausted budget; `continue` after a failed stage. At
`READY_FOR_HUMAN` the run waits for `merge`, `revise engineer <feedback>`, `revise architect
<feedback>`, or `discard` with `--confirm`. `--stop` ends a run at any of them. Nothing is committed,
merged or removed before your `merge` or `discard`. A run waiting at a stop waits indefinitely, and
any process may answer it.

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
