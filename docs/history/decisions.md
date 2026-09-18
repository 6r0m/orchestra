# What changed the design, and why

The architecture in [structure.md](../architecture/structure.md) is the current truth. This is the
shorter story of how it got there: the things that were believed, then measured, then changed. Every
item below cost a defect, a review round, or a measurement that contradicted an assumption.

## The workflow engine was not the first answer

A hand-rolled state machine came first, and it lost reviewer feedback on routing edges — the
feedback lived on the edge rather than in the state, so a run that came back from a reviewer had
forgotten what it was told. The answer was not a better state machine but a workflow engine that
already owns durable state: the loop became ordinary code over one compact state, and a restart
resumes mid-loop instead of re-deriving where the run was. There is deliberately no `states/` layer
to rediscover.

## A terminal is the vendor's own CLI, not a transcript

The first design ran agents headlessly and rendered their output. That loses everything the CLIs do
well — their own permission prompts, their own resume, their own interruption — and it made the
system the owner of a conversation it should not own.

A terminal multiplexer was evaluated as the host for real terminals and rejected on the first
measured criterion: its web client sends `x-frame-options: DENY`, so it cannot be embedded. What
replaced it is a thin PTY bridge — POSIX `pty`, ConPTY on Windows — with the vendor's real binary
inside it, its bytes recorded and served to the page. A turn ends on the vendor's *own* completion
event, never on screen matching:

- Claude's `Stop` for the prompt id its `UserPromptSubmit` reported, and not while a background task
  it started is still running;
- Codex's `agent-turn-complete` whose inputs include this turn's prompt — its title turn runs in a
  thread of its own and must not be mistaken for the answer.

An interrupt completes nothing; a prompt typed after one steers the same turn, which ends when that
steering completes.

## Terminals stay live and writable to the end

An earlier rule froze a role's terminal between turns, on the theory that a writable idle terminal
lets work happen outside the workflow. That was rejected as over-engineering by the person who uses
it: while a feature is unfinished, all of its terminals stay live.

The invariant that actually matters was then restated without restricting anyone: a verdict must
describe what the architect really read. Both review stages snapshot the tree they judge and fail
the step if it changes under them; a plan changed between `PASS` and *Approve* goes back for
assessment before a build starts; a merge commits exactly the verified tree or refuses. Typing into
an idle terminal is therefore always allowed and never silently promoted into work the workflow
believes was reviewed.

## Measurements that overturned an assumption

- **A payload has a limit.** Reading a change for review through the workflow failed on a 3.6 MB
  diff with `PayloadsTooLarge`. Changes are now read in bounded parts, each carrying the identity of
  the change it came from — an edit of exactly the same size is otherwise indistinguishable by
  length, and two revisions would be shown as one.
- **A part must not end inside a character.** The first bounded read cut UTF-8 mid-character, which
  inflated the next part past the bound and lost bytes.
- **Permission modes are not trust.** Running with permissions bypassed does not suppress a vendor's
  trust dialog: a fresh directory still asks. Trust is recorded per repository, in the CLIs' own
  stores, and an explicit `untrusted` decision is never overridden.
- **A trust record can be taken back.** A CLI that was running when a record was written rewrites
  its own file on exit from the copy it started with. A run therefore records again before every
  turn rather than once at its start.
- **A config file is not free to append to.** Appending a second table for a key a TOML file already
  holds is invalid TOML and breaks the CLI that reads it. Detection is the parser's job, never a
  regular expression over the text.
- **Windows creates a process before it can contain it.** A worker that died in that window left a
  suspended agent behind. The agent is now created *inside* its Job Object atomically.
- **A UNC path is not a working directory.** A native Windows process given one silently runs in
  `C:\Windows`. This is why a repository on the Linux filesystem cannot be a Windows target — and
  why this checkout lives on a Windows drive.

## Gates are the point, and they are explicit

Every stop is a named question with named answers, validated by the workflow itself: an answer it
does not offer is rejected before it reaches history, and an answer names the stop it is for, so it
is applied at most once and never to a later stop. The final gate is the only path to a commit, and
the merge that follows it commits the verified tree, moves the plan to its done folder, merges with
an explicit merge commit, and removes the worktree and its branch — or hands a conflict back to the
run's own agents rather than resolving it.

## What observability is not

The trace records a run; nothing reads it back. No routing, no gate and no guard depends on it, and
a run without credentials behaves identically. That boundary is checked by a test, not just stated.
