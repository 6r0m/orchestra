# Structure

## Contents

- [Purpose and ownership](#purpose)
- [Composition](#composition)
- [Relationships](#relationships)
- [Invariants](#invariants)
- [Updating running code](#updating-running-orchestra-code)
- [Accepted decisions](#accepted-decisions)
- [Risks](#risks-and-technical-debt)

## Purpose

Put the concerns together: carry out on a target host what the workflow commanded, and
give the operator's two surfaces one way to start, read, answer and end a run, and to read, start
and stop the stack.

## Owns

- `activities` — everything a run does on its target host: resolve the repository, make the worktree, record trust, run a role turn — its prompt's parts kept beside the prompt, and a review's judged tree returned whatever its verdict when the worktree did not move while it judged; a closeout held to the todo and documentation, the tree it left returned — look at the run's base and bring it in when it moved, reopen a change sent back, merge, discard, read the change for review, write the trace.
- `client` — the one client of runs: start, list, status, what a run is doing now and whom its stop's words go to, answer, stop, reject and force terminate, where a rejected run's cleanup stands, the change, what its Temporal history holds of its turns and accepted answers, the worktrees and the removal of what a closed run kept, shared by the page and the command line.
- `settings` — the one settings loader and writer, adapter-aware validation, and the run-policy snapshot built from the selected flow.
- `stack` — the stack's one reading and its one owner: whether Temporal answers and each host's worker runs and polls, and the start, stop, restart and worker reload, in order, each outcome proven — and, once a stopped worker is proven gone, the sweep of what its stages left. The process mechanics it orders are `workers.sh` and `workers.ps1`, at the checkout root.

## Does not own

Any decision the workflow makes — an activity is told what to do, and
[orchestration](../../../orchestration/README.md) decides it. Printing: nothing here writes
to a console, which is what keeps `client` usable by both the page and the CLI. Any
mechanism of its own: every concern this composes is owned by the package it came from.

## Composition

| part | responsibility |
|---|---|
| `activities.py` | what a run does on its target host, one activity at a time |
| `changes.py` | a run's change, live, for the page: its worktree on this host against the base its workflow says it stands on now, as a summary that writes nothing, read again only when the worktree moved; the worker hands it to its socket |
| `client.py` | the one client of runs; history owns completed turns, all role-attempt timings and recorded trace correlation for optional cost display |
| `settings.py` | adapter-aware settings validation, the sparse local patch and the policy snapshot for a new run |
| `stack.py` | the stack's one reading and its one owner, for the Makefile, the command line and the page |

## Relationships

This package's relationships are drawn once, in [the main view](diagrams/main.md).

Through an activity name and its payload: what the workflow commanded. Through Temporal's
client API: a start, an Update carrying an answer, a cancellation or a termination, the `status`
query, a run's description, and who polls each task queue. Through the lifecycle scripts, one
part of the stack at a time: a start, a stop, its process's state, and the sweep.

Settings composes the foundation's strict data validation with each selected kind's adapter,
then hands a checked snapshot to a new run. The Workbench reads, applies and starts runs from the
same settings source; individual activities do not reload mutable settings.

The role activity registers both the legacy entrypoint and the retained-operator-context entrypoint
named by orchestration. Both delegate to the same execution owner. History and timing read both types;
the distinct name makes an incompatible target fail before a model starts, rather than ignore input.

Composition belongs here rather than inside a concern. `telemetry.final_diff(client, state,
worktrees.review_diff)` is written that way on purpose: the trace records a change it is
handed, and never learns how git reads one.

## Invariants

- New named starts validate the operator's complete short name before creating a workflow. Legacy start
  callers remain compatible. Landing preview/discovery uses the target host through the existing read workflow;
  no server reads another host's Git. A client refuses destination/message edits when the workflow worker
  lacks the advertised protocol. Only the versioned Merge Update accepts those edits, through target-host
  validation before state promotion. Closeout reads a proposal solely from the native final assistant product;
  an unavailable proposal cannot invalidate independently valid closeout evidence or trigger a paid retry.

The setup reader asks the selected host for cached compatible destinations and native skill references
through the existing read workflow. Repository scope comes from the selected repository, not the Workbench
checkout. Existing runs use their recorded repository and currently selected engineer kind. A Merge
preference is validated before start and remains display input until the final approved landing choice.

Large retained operator context is resolved from accepted Update events in the exact Temporal execution
that scheduled the role. The worker uses its own connection, validates each reference's stop, action,
recipient and text hash, and restores the ordered original provenance for normal prompt composition and
file attachment. Missing, corrupt or unreadable evidence fails before any agent starts. The bounded read
heartbeats and cancels its pending request on Stop; it uses the existing activity executor and role lifecycle.
No new note store or vendor-session reader supplies operator intent.

The history reader associates checkpoint results with accepted operator actions by their recorded identity,
including explicit capture failures. Same-base milestone exports use the net change between retained trees,
never concatenated turn patches. Legacy missing samples and cross-base ranges are refused explicitly.
A current endpoint can be sampled during a role turn or an operator stop. The stage, stop, worktree and
base must remain unchanged across the read; setup and Git transitions are refused. The sampled tree is
frozen for all later file reads and patch chunks and conveys no approval. Whole-run live diff remains
available independently. Private checkpoint refs
survive ordinary worktree cleanup; the workspace owner defines their retention and release.

- **A role-run and every git side effect are single-attempt (D5).** A failure stops the run for the operator; there is no automatic retry and no retry ledger (D16).
- **Closeout preflights the saved todo paths against the verified tree.** Every policy requires
  the assigned active or configured finished name in that snapshot. A deletion policy permits the
  todo's later absence from the working tree, including when a partial closeout continues. A mismatch
  refuses before an agent starts, with the explicit
  verified-name recovery command. Adoption follows the
  [workflow's paused-update contract](../../../orchestration/docs/architecture/structure.md#invariants);
  the activity reads the host's Git evidence and never writes workflow state.
- **Every write to a run goes through the workflow's own start rules, Updates and validators, or Temporal's own lifecycle**, so the page can do nothing the workflow does not allow.
- **A part of the stack is up only when proven, and a worker stopped only once its process is gone (D32)**; one stack action at a time, and a stack under another policy never touches Temporal or the Windows worker.
- **An activity never waits for a human** (D6).
- **A persona file is resolved by `foundation.policy.prompt_path` and nowhere else**, on the host that runs the role and inside the step, so a policy that host cannot read, or a host copy that differs from the run's, fails the step before an agent starts.

## Updating running Orchestra code

Orchestra updates never require shutting down or terminating a WSL distribution. Replace only the
process that loads the changed code. Browser assets take effect on page refresh; CLI invocations and
agent CLIs start fresh. New runs read current settings and keep that snapshot; changing the selection
or turn limit does not require a worker reload. Changing deployment identities, queue names or ports
requires a separate migration of the old deployment, rather than treating it as a source-code reload.

For Python code hosted by workers, run from WSL:

```bash
make reload                                             # both managed workers, leaving Temporal alone
make reload-wsl                                         # only the WSL worker
make reload-windows                                     # only the Windows worker
make check
```

The Make targets select this checkout's managed environment and call the shared CLI. Reload requests
native Temporal shutdown, stops new activity polls and waits for current activities with their existing
deadlines. On WSL, workflow polling remains available
for queries and Stop until its activities have finished. Subsequent activities queue normally. The
controller proves the original process gone, cleans its scope and stale stage settings through the
existing host mechanics, starts fresh code and verifies the new process polls its assigned queues.
Cleanup uses the host scripts' idle-only path, which refuses to signal a worker or remove its record
if one appears meanwhile. It never automatically escalates to force stop. Unknown process state,
unsupported drain requests,
or an unelevated Windows launch that cannot be arranged refuse replacement and say why.

The reload caller waits and holds the stack lock, potentially for a long turn. Run it in a terminal
that can stay open. Interrupting the caller does not undo a drain already requested: the worker may
finish and exit. Run `make check`, then repeat reload or start the stopped worker to complete activation.
Other stack actions are refused as busy until the lock is released; Stop for an individual run remains Temporal's.
The reported `draining` state projects a PID-scoped drain request; the worker logs when native
shutdown begins. It must not be treated as proof that every in-flight poll has already stopped.

An already running worker from before drain support must be replaced once while idle using its
targeted `--stack restart wsl` or `--stack restart windows` control. Ordinary `restart` and `stop`
remain interrupting operations. Successful turns leave live CLIs behind; replacement ends those
processes, including any manually initiated conversation still running in them. Finish that manual
work first. Vendor sessions, run snapshots and the worktree persist for subsequent controller turns.

For Workbench server or interface Python changes, use `make workbench-restart`, then refresh the page.
Its separate systemd service does not own the workers, so they and their activities keep running.
Do this after any stack operation issued through that Workbench has completed; restarting the caller
would interrupt that operation. Workbench never manages its own service. No update command here
restarts Temporal, Docker, WSL, or unrelated workloads.

## Accepted decisions

An index. Each decision is written where the project's architecture states it, beside the
boundary or invariant it constrains: see
[the accepted decisions](../../../../docs/architecture/structure.md#accepted-decisions).
The invariants above name the ones that bind this package.

## Risks and technical debt

This package imports every other concern, which is what it is for, and also what makes it
the easiest place for a responsibility to settle that belongs somewhere else. A new
mechanism appearing here rather than a composition of existing ones is the signal to watch.
