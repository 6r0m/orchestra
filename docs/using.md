# Using Orchestra

The Workbench is the surface; everything it does is also reachable from the command line, which is
what the tests, any automation and the Makefile use.

## The Workbench

A systemd user service in WSL, installed once from this checkout. Windows programs the service starts
run with the token WSL was started with, and the Windows worker — with every agent it runs — is never
started as an administrator: from an elevated WSL, its start goes through your desktop's shell, which
starts it as you.

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

The top bar shows each part of the stack — Temporal, the WSL worker, which also runs the workflows, and
the Windows worker — as up, starting (running, not yet polling) or down; a worker reads as running while
Temporal cannot be asked, and unknown while its process cannot be read. Its chips open the stack's
controls: Start, Stop and Restart for each part and for the whole stack. The whole stack's Start shows
only while a part is down and every part can safely be started, and its Restart not while a part is
unknown, because both start every part. A part that is down raises a banner saying what it holds up,
with its Start when this side can start it; one whose state cannot be read says so and offers no Start.
Temporal starts before the workers and stops after them, and a part is reported up only once it is:
Temporal answering, a worker polling as its own process. Stopping a worker ends any agent at work on it
— its stage then waits for you to continue it — and removes at once what its stages left of their trace
settings; a merge or discard it is running may be cut off, and its run then waits at that step until the
step fails or times out — Force terminate ends it sooner. Stopping Temporal pauses every run; an agent
at work goes on, but if Temporal stays down longer than a role's heartbeat interval, its stage fails and
waits for you to continue it. Each stop asks first, in the page's own dialog, saying this. The same,
from a terminal:

```bash
make up         # start the stack, each part proven up
make check      # each part's state, and the Workbench's service
make down       # stop both workers, then Temporal; its data stays, and the Workbench keeps serving
make restart    # the whole stack; one part: orchestrate --stack restart temporal|wsl|windows
```

The stack runs from a start to a stop, like a service started by hand: it outlives the terminal that
started it, a part that fails comes back, and after WSL restarts it is down until started again — only
the Workbench comes back with WSL. Nothing is exposed beyond loopback.

## The page

The runs are listed down its side under Operator action, Working and Closed. Each row names its
repository, task and worktree branch, with what waits or is working and for how long. A run ready to
merge stays under Operator action until you answer its final gate; Closed also includes stopped and
discarded runs. Older closed runs are a page away, so nothing Temporal
still retains is out of reach, and the tab's title counts the runs that need you. Each run is a link:
the page's address names the run open, so a reload keeps it and a new tab opens it.

If a vendor dialog waits in a live terminal, that running run also appears under Operator action.
Open its terminal to answer or interrupt it. This is a terminal prompt, not a workflow stop; routine
agent questions are denied and real blockers reach the normal workflow stop. Only a Claude role
reports such a dialog, through its hooks, and in practice a Claude architect: a Claude engineer is
denied what it may not do rather than asked, and a Codex role never asks.

*New run* opens the form that starts one — and with no runs at all, the page opens on it: on a
repository named in `.orchestra/repos.json` or in the file named by `ORCHESTRA_REPOS` — its menu
reads the file again each time it is opened, and a name that
carries its owners, `work/platform/service`, is found under `work`, then `platform`, each opening in
view as you hover it — or on any other one given as its path as WSL sees it (`/mnt/e/...` for a Windows
drive); only the one chosen is sent. The task's first words name the run and its branch. It follows the
flow chosen in its Flow list, whose steps show under it: `engineer-code`, the default — `default_flow`
in `.orchestra/settings.json` — has the engineer plan from the code; `architect-research` has the architect research
first and its brief wait for your approval. With no `default_flow`, a run that names no flow takes the
order runs took before flows, and the list offers that first. Each flow is a file in
[flows/](../flows/README.md), read again each time the list is opened, so a flow you add or edit there
shows at once; one that breaks a rule is listed with the reason and cannot be chosen. The one already
chosen, or named the default, stays chosen when its file breaks a rule or is gone — marked refused or
missing — so Start answers with the reason rather than starting another flow. A run keeps the flow it
started with. *Skip approvals* skips every approval the flow schedules, never a blocker, an exhausted
budget, a failed stage or the final gate.

A run shows what it is — its repository, host, flow, run and branch, worktree, its plan once it has
one, when it started, and links to its Temporal and (if configured) Langfuse pages — its flow drawn
step by step with the one it is at, and what it is doing now and for how long: the agent at work and
its stage, or the answer it waits for. When a host's worker it needs is down it says it is blocked by
it, with that worker's Start beside it. A run whose worker is down is still shown.

When a run waits for you, its decision comes first, with what to judge it by: the brief at a research's
approval, the architect's assessment and the plan at a plan's, the architect's verification and the
change at the final gate, the blocker or the last finding, or the failure, whole, to copy. At the
final gate the change is the one the engineer's closeout left — the todo cut to its record and in the
repository's done folder — and it is exactly what Merge commits. The architect did not judge the
closeout, which may touch only the todo and documentation: its turn in the history opens what it
changed since the architect's verification. A revise undoes it before its role's turn. Its
answers are the stop's own, as buttons. The note is labelled with the answers it is sent with, and a
note typed for a stop stays while you look at other runs; an answer the workflow refuses is said
beside what it concerns, and a merge or a discard asks first.

The change is read as one snapshot of the worktree — its last commit and the tree its files make — and
listed file by file, each by its whole path: a rename as its old path and its new one, a binary file
said so; a very long list comes a part at a time, *List more files* reading the rest of the same snapshot. Open a file to see its diff as an editor shows one: both line numbers, added lines green,
removed red, long unchanged runs folded a click away. A file too large to show whole shows its changes
alone, and says so. The patch sits below in a small box; *Copy patch* copies all of it, however large,
from the same snapshot, and *Read it again* reads a new one.

Both roles' terminals follow, the one at work open and an idle one closed until you open it. Each is the
vendor's own CLI: press Esc to interrupt a working agent, type to steer it. What you read in one is
never drawn again under you: after its worker restarts it keeps its record until its role's next turn,
which it then adds to. A terminal holds the whole session, including whatever you typed during a turn.

The history is the run as a transcript, phase by phase: each completed turn a row — its role, stage,
round, verdict, how long it ran from when a worker took it, and when — and your answers rows of their own
between them, in the phase of the step they answered, with your words and when the run took them. Open a turn to see what it received and what it produced. *Received*
is the turn's own new prompt — the vendor keeps the conversation before it in its session — in the parts
it was built from: the stage's skill, the task and the role's persona as the run started on a session's
first turn, the stage's instructions, and what it was handed, such as the research brief to check, the
findings to address or your guidance; the exact prompt is beside them, to copy. A turn whose parts were
not recorded shows its exact prompt alone. *Produced* is its answer as the run kept it — the brief, the
plan's account, the verdict and findings — said once: what the decision above shows is pointed to, not
repeated, and said again in the turn once the decision moves on. An engineer's turn adds *Change since the previous review*: the files between the tree the
review before it judged, or the worktree's last commit, and the tree the review after it judged, each
opening in the same viewer. The worktree is live, so that is what the review judged, not proof of who
wrote each line. After a PATCH, a turn's change is only what that turn changed in answer to it. A review
records its tree only when the worktree did not move while it judged; where one between two engineer turns
recorded none, the two cannot be told apart, so their change is shown once, on the later turn, which says
so, and the earlier one points to it; a tree git has since pruned is said gone. A turn
retried in a fresh session, its first one lost, shows each attempt; a failed attempt's retry from before
you pressed Continue stays in the local logs but is not shown as the new turn's. A local record that has
been removed is reported as unavailable.

*Stop run* comes after the decision. While a run waits for you nothing runs on its host, so it is the
one control offered there, quiet, saying it ends the run without merging and keeps its worktree and
branch. While a run works, *Force terminate* follows it — a run whose status cannot be read is shown
working — and while a run is stopping only *Force terminate* is offered. *Stop run* ends a run from
whatever it is doing — an agent at work, a stop
waiting, a failed stage, the final gate, a host whose worker is down — and keeps its worktree and branch
as they are. A merge or discard already running is let finish first, and decides how the run ends.
*Force terminate* is for a run a Stop cannot finish: it closes the run at once with no cleanup, but
cannot stop what the run's host is already doing — a worktree's creation, a merge or a discard already
running goes on and may still change the repository — and its confirmation says so.

A run that closed keeping its worktree and branch — stopped, force-terminated, ended `DONE` by a flow
with no build, or closed any other way short of a merge or a discard — says so; look at its change, then *Remove worktree and branch*,
confirmed, deletes them through its host's own git as a discard would. It is refused while a merge
or discard of that run still runs on its host, and when git itself refuses, the page says why.
*Worktrees*, at the top, lists any repository's worktrees, which of them are still unmerged and which
run each is, and removes a closed run's from there too.

### Settings

Settings shows the profiles bound to each role, each profile's model and effort, the one optional
methodology skill named for each stage, the plan and build review budgets, and the default flow. The
skill picker lists names found through each agent adapter; unbound installed skills remain available to
the vendor CLI. A run snapshots the effective settings when it starts.

Apply writes only changed values to `.orchestra/settings.local.json`, so a fresh Workbench read keeps
them and unrelated hand-written local members survive. Revert removes one override to reveal its shared
value. **Reset visible settings to defaults** stages Revert for every Settings page value; Apply is still
required. Model identifiers and available efforts are passed to their vendor CLI as configured.

Review budgets show the normal count plus the **After reflection** count as each phase's maximum (the
settings file calls the second value `extended`). After a non-`PASS` at the normal boundary, if the
second count is greater than zero, the engineer and architect each receive one code-owned convergence
reflection on their next turn; the loop then continues through the remaining budget. `BLOCKER` stops
immediately, and a non-`PASS` at the combined limit waits for operator guidance.

Advanced review guidance shows the code-owned instructions used at each boundary. It can add separate
instructions for each role after the normal budget and on the last budgeted iteration; these optional
additions follow the built-in guidance, which always applies. Additions are shared by Plan and Build and
limited to 4,096 combined UTF-8 bytes. At exhaustion, the engineer gives the architect a factual
handoff in its final message. The architect's final feedback separates both roles' contributions,
explains why the phase did not converge with evidence, lists unresolved or disputed findings, and
states any operator decision needed.

## The command line

```bash
# this checkout's own environment, on this host's disk
export UV_PROJECT_ENVIRONMENT="$(uv run --no-project --managed-python --python 3.13 python app/foundation/envpath.py "$PWD")"
O="uv run --locked python -m app.interfaces.cli"

$O "<task>"                        # a run on this repository
$O "<task>" --repo work/webapp     # a repository listed in .orchestra/repos.json or ORCHESTRA_REPOS
$O "<task>" --flow architect-research   # a run that follows another flow than the default
$O --resume <run-id> --answer yes  # answer the stop the run waits at
$O --continue <run-id>             # run a failed stage again, after you fixed its cause
$O --stop <run-id>                 # end a run from whatever it is doing, keeping its worktree and branch
$O --force-terminate <run-id>      # close a run a stop cannot finish, at once; git already running goes on
$O --show <run-id>                 # the stage table and the architect's words
$O --worktrees --repo work/webapp  # every worktree, and whether its work is merged
```

Each stop prints what it asks and the answers it takes: `yes` or `revise <feedback>` at an approval —
the plan's, with its summary, or the research's, with its brief; your guidance at a blocker or an
exhausted budget; `continue` after a failed stage. `--auto-proceed` skips the approvals, as the page's
*skip approvals* does. A run whose flow has no build ends `DONE`, keeping its worktree. At
`READY_FOR_HUMAN` — after the engineer's closeout, in a flow that has one — the run waits for `merge`,
`revise engineer <feedback>`, `revise architect <feedback>`, or `discard` with `--confirm`. `--stop` ends a run at any of them. Nothing is committed,
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

The workbench's port is `workbench_port` in `.orchestra/settings.json`. It has to be free on *both* sides on a
Windows + WSL machine: a Windows process listening on the same loopback port takes the connection
before WSL's forwarding does, and the page then never loads in a Windows browser. `netstat -ano |
findstr :<port>` on Windows names the holder. The default avoids the ports Unreal Editor uses, which
is the collision that prompted the rule.
