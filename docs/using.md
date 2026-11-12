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

The runs are listed down its side under Operator action, Working, Closed and Rejected. Each row names its
repository, task and worktree branch, with what waits or is working and for how long. A run ready to
merge stays under Operator action until you answer its final gate; Closed also includes stopped and
discarded runs, and Rejected holds only the runs you ended with *Reject* — each saying whether its
worktree and branch are gone, or that its cleanup is still required. Each list shows up to five runs and
scrolls inside itself beyond that; on a window too short for all four, the lists past five give up height
and the shorter ones stay whole. Older closed
runs are a page away, so nothing Temporal
still retains is out of reach, and the tab's title counts the runs that need you. Each run is a link:
the page's address names the run open, so a reload keeps it and a new tab opens it.

If a vendor dialog waits in a live terminal, that running run also appears under Operator action.
Open its terminal to answer or interrupt it. This is a terminal prompt, not a workflow stop; routine
agent questions are denied and real blockers reach the normal workflow stop. Only a Claude role
reports such a dialog, through its hooks, and in practice a Claude architect: a Claude engineer is
denied what it may not do rather than asked, and a Codex role never asks.

Codex runs a hook only once you have trusted it, and the orchestra's own two hooks are how a Codex turn ends. So
the first Codex turn on a host — and the first after a Codex update that asks again — stops at Codex's *Hooks need
review* in the role's terminal, before its prompt goes. Answer it there: *Review hooks* shows each one; the
orchestra's run `turn_hook.py`. Trust them, and every turn after asks nothing. The same review
comes up for any other hook new on that host — yours, a plugin's or the repository's. The orchestra never answers
it for you: Codex's *Trust all* would trust whatever waits. Left unanswered for two minutes, the step fails and
says what waits; Continue, and answer it in the terminal then. *Continue without trusting* leaves the turn unable
to end.

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

A start that is refused says why in a window that stays until you close it: refused by the Workbench at
once, or by the run's host before any work — its repository no git repository there, say, or an agent's
program or a stage's skill missing — when the run is listed under Closed as refused, its reason on its
page. The window comes to the tab the run was started from, while that tab stays open. A start the
Workbench did not confirm — it failed or timed out itself, or never answered — is said as not confirmed,
never as refused: the run may have been made, so check the list of runs before starting it again.

A run shows what it is — its repository, host, flow, run and branch, worktree, its plan once it has
one, when it started, and links to its Temporal and (if configured) Langfuse pages — its flow drawn
step by step with the one it is at, and what it is doing now and for how long: the agent at work and
its stage, or the answer it waits for. When a host's worker it needs is down it says it is blocked by
it, with that worker's Start beside it. A run whose worker is down is still shown.

When a run waits for you, its decision comes first, with what to judge it by: the brief at a research's
approval, the architect's assessment and the plan at a plan's, the architect's verification and the
change at the final gate, the blocker or the last finding, or the failure, whole, to copy.

At an approval your note goes with either answer. With *Revise*, it is what should change, for another round of
the same work. With *Approve* — the button then reads *Approve with note* — the run goes on, and the note goes
with it to the next step: the engineer building an approved plan reads it as your guidance, and so does the
architect verifying that build. Accepted notes remain available in later rounds and phases, together with
their original phase and recipient, so a reviewer summary cannot replace your requirements.
If a new note exceeds the [aggregate retained-note budget](../app/orchestration/docs/architecture/structure.md#invariants),
the answer is refused and the run stays at its stop. Shorten the new note or start a separate run;
earlier accepted notes are kept whole. The budget includes JSON escaping and provenance, so it is not
a character count. Older runs already over budget preserve their notes and still accept note-free answers.
An approval that ends the run has
no next step, so it takes no note; nor does one in a run started before approvals took notes. There Approve
stays *Approve*, and a note written beside it is not sent: the page says so, and you clear it or Revise with it.

When revising, distinguish your decisions from quoted review advice: for example, "Adopt these public
names; evaluate the quoted review against the remaining decisions." Each review must account for the
material requests and identify anything refuted or unresolved. A genuine decision conflict should return
to you as a blocker. A PASS does not prove that a model followed every instruction; inspect its evidence
before merging.

If guidance is refused because the workflow worker cannot preserve original notes, gracefully reload
the workers and reload the Workbench service to load its shared client, using the existing stack and
Workbench controls above. WSL itself stays running. The next accepted answer activates preservation for
that run, including earlier accepted notes recovered from Temporal history; it does not rerun old turns.
If a role step reports that `run_role_with_operator_context` is not registered, gracefully reload that
run's target worker and press Continue. That refusal starts no agent and spends no model quota.

A blocker, or rounds run out, comes from the architect's review of the engineer's work, and only you can say
whom your guidance is for, so it takes it either way. *Guide the engineer* sends your note to the engineer, whose
work goes on with it, and the architect then judges what it does with it. *Guide the architect* sends it to the
architect, which judges the work as it stands again with it — say, when it misread the work, or the engineer
has already changed it while you talked — and the engineer takes no turn first.

You may settle such a stop in a terminal first, with either agent. What the one you talked with last answered
you there is then shown on the stop, to be sent with one press, as your guidance, to either of them — *Send to
the engineer* or *Send to the architect*, the one you did not talk with first: the one you talked with keeps the
talk in its own session. Nothing moves until you press, and a press sends exactly the words shown.

At the
final gate the change is the one the engineer's closeout left — the todo cut to its record and in the
repository's done folder — and it is exactly what Merge commits. The architect did not judge the
closeout, which may touch only the todo and the documents the repository names (`closeout_docs` in
its entry in `.orchestra/repos.json`; the todo alone when it names none): its
turn in the history opens what it changed since the architect's verification. A revise undoes it
before its role's turn. If the base branch moved while the run built, it was brought into the worktree
and judged before this gate, so what you read is the change on the base as it is. Merge lands it on
that base: the repository's own branch, or — where its entry names the `remote` its base lives on —
that remote's, by a push that forces nothing, which the confirmation says. That push runs the
repository's own pre-push hook on the commit being landed, and what the hook refuses lands nothing: the
gate says why, in the hook's words. A hook changed or taken out since the run began lands nothing
either — put it back as it was, or stop the run and begin again. Should the base have moved again since
you were shown the gate, Merge lands your change on it as git merges the two — the same change, on the
base as it is, with no turn of a role and no second gate; the run's history says it was merged so. Git's
merge is no proof the two work together: nothing reads or tests the merged tree before it lands, as
with any merge git makes by itself. Where git finds a conflict, Merge lands nothing; the run brings the
base in, its engineer resolves the conflict, its architect judges the result, and it comes back to
you. A base that was rewound or rewritten under the run is never brought in: the run stops there and says so,
for you to continue once the base is as it was, or to stop the run and begin from the base as it is. Its
answers are the stop's own, as buttons. The note is labelled with the answers it is sent with, and a
note typed for a stop stays while you look at other runs; an answer the workflow refuses is said
beside what it concerns, and a merge or a discard asks first.

What an agent wrote reads as the Markdown it wrote — headings, lists, tables, code, emphasis — in a decision, in a
turn's history and in the parts of its prompt. A link opens only on the web, in a tab of its own; a path on the
agent's host stays its words, the path shown when you point at it; an image is its words, never loaded. Copy copies
the text as written, and a failure, the exact prompt and the raw record stay as written too.

The run's change is its result, so it comes first on its page, right under what the run is doing now —
under the decision, when a decision judges it. The Change disclosure starts collapsed with its file count
visible. Open the heading to review files, refresh or copy the patch. Updates and Refresh preserve your
open or closed choice; opening another run starts collapsed again. While a role works on the run it is live: its host's worker
looks at the worktree every few seconds — less often when a look is slow — and, when something moved, the page
shows how many files, lines added and removed and when it was read, with nothing to press. That look writes
nothing in git; a file's diff is read when you open it, as the file is then, and a file you opened stays open,
read again only when it changes. Each turn's own change stays in the history. When the change cannot be read
just now — its worker down, its status unanswered — the page says so and shows the last one as no longer
current. While the run waits at a blocker or a failed step, or once it is closed keeping its worktree, nothing
moves it: the page shows what was last seen, and *Read the change* reads what its worktree holds now.

Each read of it is one snapshot: the commit of its base the run stands on and the tree the
worktree's files make, so that it shows what the run adds to that base and nothing the base brought in —
and listed file by file, each by its whole path: a rename as its old path and its new one, a binary file
said so; a very long list comes a part at a time, *List more files* reading the rest of the same snapshot. Open a file to see its diff as an editor shows one: both line numbers, added lines green,
removed red, long unchanged runs folded a click away. A file too large to show whole shows its changes
alone, and says so. The patch sits below in a small box; *Copy patch* copies all of it, however large,
from the same snapshot, and *Refresh* reads a new one. *Copy all changes*, in the expanded block, copies the whole
change as the worktree holds it at that moment — every file, however long — whenever you press it, the run at
work, waiting, or closed keeping its worktree. A run merged or discarded has no worktree, and so no Change
section: a merged change is in git, and each turn's change stays in the history.

Both roles' terminals follow, the one at work open and an idle one closed until you open it. Each is the
vendor's own CLI: press Esc to interrupt a working agent — or *Pause*, at the top, which presses it for you —
and type to steer it. Its agent gets what you type and press and nothing of the page's own; the one thing
given up for that is F3 held with Shift, Alt or Ctrl, which a terminal spells exactly as one of its own
answers and the page therefore does not send. What you read in one is
never drawn again under you: after its worker restarts it keeps its record until its role's next turn,
which it then adds to. A terminal holds the whole session, including whatever you typed during a turn.

Large terminal histories show catch-up progress while replaying, then live output. Reconnecting keeps
the output already drawn. Navigating between open or waiting runs keeps a bounded cache of parsed screens;
returning shows the tail and reads only new bytes. Hidden cached screens have no live socket. Closing a run
or cache pressure releases its retained display; a full page reload replays the record. This browser cache
does not keep the agent's CLI initialized.

A worker marked *draining* is updating: its current work continues, and new
steps wait for its replacement. This is an update notice, not a down-worker warning. An agent command
that pipes its output through `tail` can still stay quiet until that command finishes.

If a role loses track of its instructions, Pause it and ask it to re-read the applicable `AGENTS.md`,
its current stage's skill and the approved todo, inspect the existing diff and verification evidence,
then continue the current stage while preserving completed work. The latest controller prompt is
available under that turn's *Received* history. Resuming a conversation retains history, but compaction
can summarize earlier details. Each new role invocation refreshes its current contract; Pi also keeps
that contract in a native system section during a long turn. These measures preserve context delivery,
not proof of model compliance. No WSL restart or new session is needed for this recovery.

If closeout reports that its saved todo path is missing after an approved rename, adopt the filename
already present in the architect's verified tree:

```bash
orchestrate --adopt-todo-name <run-id> concise-change.md
```

This updates the saved path while keeping the run paused. It does not move files or start an agent;
the old name must be absent from the verified tree and the selected active or finished name present. After checking the
updated Plan path, press **Continue** to run closeout again in the existing session. The usual model
usage applies to that continued turn. There is no need to repeat the build or verification.

A terminal is drawn to fit its box, all 160 columns of it, so in a narrow window its text is small. *Maximize*,
beside its name, fills the window with it, as a console window does: its text is drawn as large as the columns
allow across, and the agent's own terminal takes as many rows as fill the window down — on a portrait display,
about three times its usual 48. Every page watching it draws those rows too, and the role's next turns start at
them, until *Restore* puts back 48; Esc still reaches the agent. Scroll back through the session with the wheel or by dragging its scrollbar — Codex too,
which draws inline as Claude does, and shows its session's history again each time a turn resumes it. Select text
and press Ctrl+C to copy it, say into your guidance; with nothing selected, Ctrl+C goes to the agent, as in any
terminal.

Change also contains **Review milestones**. Each accepted approval, revision, guidance or Continue closes
an interval; copying or terminal typing creates none. Open an interval to copy that milestone, or choose an
earlier checkpoint under **Compare from** to copy a larger net range. The copied text identifies its snapshots
and then contains the full patch. **Copy all changes** exports the entire current run change while its worktree
is retained. After merge or discard removes it, historical milestones remain accessible under Change.
Current milestone exports are sampled at an operator stop and labelled unverified; while a role executes,
Copy all changes remains available. Missing historical captures and ranges crossing a base update are
explicitly unavailable. Existing runs acquire exact boundaries from future supported answers, not retroactively.
Snapshots survive ordinary worktree cleanup and use disk until explicitly released through the
[run-scoped retention procedure](../app/workspace/docs/architecture/structure.md#review-snapshot-retention).

The history is the run as a transcript, phase by phase: each completed turn a row — its role, stage,
round, verdict, how long it ran from when a worker took it, and when — and your answers rows of their own
between them, in the phase of the step they answered, with your words and when the run took them — an answer
with words folded to their first line, as a turn is, and opened with a click. Open a turn to see what it received
and what it produced. *Received*
is the turn's own new prompt — the vendor keeps the conversation before it in its session — in the parts
it was built from: the stage's skill, the task, the run's saved persona and current-stage instructions
on every invocation, and what it was handed, such as the research brief to check, the
findings to address or your guidance; the exact prompt is beside them, to copy. A turn whose parts were
not recorded shows its exact prompt alone. *Produced* is its answer as the run kept it — the brief, the
plan's account, the verdict and findings — said once: what the decision above shows is pointed to, not
repeated, and said again in the turn once the decision moves on. An engineer's turn adds *Change since the previous review*: the files between the tree the
review before it judged, or the worktree's last commit, and the tree the review after it judged, each
opening in the same viewer. The worktree is live, so that is what the review judged, not proof of who
wrote each line. After a PATCH, a turn's change is only what that turn changed in answer to it. A review
records its tree only when the worktree did not move while it judged; where one between two engineer turns
recorded none, the two cannot be told apart, so their change is shown once, on the later turn, which says
so, and the earlier one points to it; a tree git has since pruned is said gone. A run that has landed, or
whose worktree was discarded or removed, still shows what each turn changed: those trees are read from the
repository for as long as git keeps them. A turn
retried in a fresh session, its first one lost, shows each attempt; a failed attempt's retry from before
you pressed Continue stays in the local logs but is not shown as the new turn's. A local record that has
been removed is reported as unavailable.

A run's own controls are a strip at the top of its page, named by the run's id, and stay there while the
page scrolls. While a role works, *Pause* is first: it presses Esc in that role's terminal for you, opens
the terminal and leaves the keyboard in it, so you type and press Enter with no click. It is an interrupt,
not a freeze — what you type steers the turn, the run moves on once the agent has answered it, and the
turn's time limit keeps running — and the run itself is told nothing, so its row still says the role works.
*Stop run* and *Reject* follow, quiet while the run waits for you, where nothing runs on its host. *Stop
run* ends a run from whatever it is doing — an agent at work, a stop waiting, a failed stage, the final
gate, a host whose worker is down — and keeps its worktree and branch as they are; a stopped run does not
start again. *Reject* ends it the same way and then deletes its worktree and branch, asked once: the run
ends `REJECTED`, its history stays, and its page says how far the cleanup got. Where its host's worker is
down or git refuses, the run is rejected all the same and says its cleanup is required, with *Remove
worktree and branch* beside it. Where the run has not closed by the time Reject stops waiting for it — its
own worker down, or its host still busy — Reject says it is still stopping and that nothing was removed;
once it has closed as rejected, it says its cleanup is required. A merge or discard already running is let
finish first, and decides how the run ends — as *Force terminate* does, pressed while a Reject waits for its
run to close. The line a Reject leaves beside the buttons then names that ending, never "rejected", and still
says, apart from it, what came of the run's worktree and branch. While a run works, *Force terminate* is offered too — a run whose status cannot be read is shown
working — and while a run is stopping it is the only one. It is for a run a Stop cannot finish: it closes
the run at once with no cleanup, but cannot stop what the run's host is already doing — a worktree's
creation, a merge or a discard already running goes on and may still change the repository — and its
confirmation says so.

A run that closed keeping its worktree and branch — stopped, force-terminated, ended `DONE` by a flow
with no build, or closed any other way short of a merge or a discard — says so at the top of its page; look at
its change, then *Remove worktree and branch*, in the same strip,
confirmed, deletes them through its host's own git as a discard would. It is refused while a merge
or discard of that run still runs on its host, and when git itself refuses, the page says why.
*Worktrees*, at the top, lists any repository's worktrees, which of them are still unmerged and which
run each is, and removes a closed run's from there too.

### Settings

Settings shows the profiles bound to each role, each profile's model and effort, the one optional
methodology skill named for each stage, the plan and build review budgets, and the default flow. The
skill picker lists names found through each agent adapter; unbound installed skills remain available to
the vendor CLI. A run snapshots the effective settings when it starts. The page reads the settings files
each time it loads, so a default edited in `.orchestra/settings.json` shows at the next reload, with no
restart.

To switch a paused existing run to the current engineer profile and turn limit, run
`orchestrate --use-engineer-defaults <run-id>`. This is explicit: changing Settings alone still affects
new runs only. The command keeps the run paused, preserves its worktree and architect session, and
starts a fresh engineer conversation on the next turn if its profile changed. Its existing persona
stays with the run. The Workbench's run facts show the effective engineer and per-turn limit.
Then use the stop's normal answer, such as Continue for a failed step, when ready to resume.

Under each role's agent the page says what that role may do, and what holds the agent you chose to it.
Codex is held by its own sandbox, which the operating system enforces: a read-only role cannot write, and
a writing one cannot write outside its worktree — which also keeps a tool whose cache or environment lies
elsewhere, such as this repository's test runner, from running in its turn. Claude Code is held by its own
rules alone: its file edits stay in the worktree, and what a command it runs may reach is what that host's
Claude settings allow. Those settings' own permission rules and hooks hold a role's turn as they hold any
session of yours there, so a guard you keep in them — one that refuses a recursive delete outside the
working folder, say — stands under a run's engineer too.

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

Each stop prints what it asks and the answers it takes: `yes`, `yes <note for the next stage>` or
`revise <feedback>` at an approval — the plan's, with its summary, or the research's, with its brief; your guidance at a blocker or an
exhausted budget — for the engineer, or `guide architect <your guidance>` for the architect; `continue` after a
failed stage. A build that could not meet one of its plan's
completion criteria comes to you as such a blocker, naming the criterion: only your guidance sets one
aside, the engineer writes it into the todo as your decision, and the final gate shows it there. `--auto-proceed` skips the approvals, as the page's
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
Without them a run behaves identically and records nothing. The Workbench optionally reads recorded
costs for display; no workflow decision depends on them. What the rows promise is in
[architecture/trace-contract.md](architecture/trace-contract.md).

Under a run's title, **Run elapsed**, **Role time** and **Recorded USD** show its timing and recorded
spend. Expand **Time and cost by role & iteration** for every role attempt, including failures and
unknown starts. The browser tab also keeps the amount visible. `≈` means estimated; `partial` means
some recorded requests are unpriced, an upload reported degradation or the trace read is truncated.
`API-equivalent` identifies a Standard API reference valuation, including the Codex model's long-context
rate; it does not measure subscription charges. Billing coverage remains unknown
even when every observed request has a price: this is a recorded subtotal, not an invoice. Usage may
arrive after a turn ends; costs refresh separately, and a store outage leaves the last amount marked
stale while the run's controls continue to work.

A self-hosted Langfuse keeps its traces in ClickHouse, whose own system logs can grow far past them — on one
such stack 8 GB of them beside 38 MB of traces, and ClickHouse kept busy merging them. Langfuse reads none of
`trace_log`, `text_log`, `metric_log`, `asynchronous_metric_log`, `opentelemetry_span_log` or `latency_log`;
[its FAQ](https://langfuse.com/faq/all/reduce-clickhouse-disk-size) shows how to switch them off in ClickHouse's
`config.d`. Turning a log off leaves its old table: drop that once the setting is seen to hold.

## The port

The workbench's port is `workbench_port` in `.orchestra/settings.json`. It has to be free on *both* sides on a
Windows + WSL machine: a Windows process listening on the same loopback port takes the connection
before WSL's forwarding does, and the page then never loads in a Windows browser. `netstat -ano |
findstr :<port>` on Windows names the holder. The default avoids the ports Unreal Editor uses, which
is the collision that prompted the rule.
