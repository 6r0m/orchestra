# Trace contract

What the trace of a run promises the saved views, the dashboard and the scores built on it. The
trace is written by [`telemetry.py`](../../telemetry.py), which owns the exact names and fields;
this document owns what they mean, when each is written, and what the vendor plugins' rows do not
promise. Where the trace sits among the observability owners is `structure.md` D20.

## Contents

- Rows
- Levels and error types
- Scores
- Dimensions
- Masking
- What the vendor plugins own
- Dashboard and saved views

## Rows

A work item is one trace. Every row this component writes is one of six kinds, and its name says
which kind — never which run, round or verdict, because saved views, the dashboard and the agent
graph group rows by name. A run's own values are metadata.

| kind | parent | what it records |
|---|---|---|
| work item | none — the trace's only root | the request, the repository, the base branch and the OS the agents run on |
| phase | the work item | plan or build, and which roles act in it |
| role step | its phase | one role-run: what the role was asked, and its answer — the engineer's account, or the architect's verdict, feedback and reasoning |
| stop | its phase; the work item for the plan approval | why the run stopped for a person — the plan approval, with the plan's summary, a blocker or an exhausted budget; a failed stage and the final gate write no row |
| answer | where its stop is | what the person answered |
| final diff | the work item | the change as `gdiff -s` copies it, cut at a size cap |

The work item opens and closes at setup, before any process that resumes the run exists, so it has
no output: how the run ended is in the final diff and the scores. On a role step, the round, phase,
stage and role are metadata, and so are the logs, the brain, the model, the reasoning effort and
the provider's session id.

Under each role step, the agent's own tracing plugin nests its turns, model calls and tool calls.

## Levels and error types

| level | when |
|---|---|
| DEFAULT | the row recorded what happened |
| WARNING | the stage went on, degraded — `session_lost`: the session to resume did not exist, and a fresh one was given the whole task; `telemetry_degraded`: the architect's turns were not uploaded, so its step has none nested |
| ERROR | the stage failed and the run stopped with its exception; or git could not read the final diff, `git_error` |

The cause is the row's status message, and it is also written into the step's output, because the
step's detail view does not show a status message. In the trace view, *View Options* → *Min Level:
WARNING* leaves only these rows.

A failed stage's `error_type` is one of:

| error type | meaning | what to do |
|---|---|---|
| `timeout` | the role-run outlived its budget, and its whole process tree was ended | read the role's logs for what it was doing; raise the budget only if the work was progressing |
| `agent_exit` | the agent CLI exited non-zero — quota, authentication, network or a crash, which nothing measured tells apart | read the role's `.err` log, fix the cause, then `--continue` |
| `malformed_output` | the agent answered, but not in the shape its stage requires | read the role's `.out` log |
| `executor` | the agent could not be launched on its host | install or repair that agent on the run's target host, then `--continue` |
| `git_violation` | the role changed the worktree's HEAD, its branch or what is staged, which only the controller may | inspect the worktree, then `--continue` or `--resume <run-id> --answer abort` |
| `internal` | anything unclassified: a defect in this component | the status message and the traceback |

No row's level marks its parent. A tool call that failed is ERROR on its own row while its role
step stays DEFAULT, because a failed command is often part of an agent's investigation.

## Scores

Scores record judgements, never counts.

| score | type | attached to | written |
|---|---|---|---|
| `architect_verdict` | categorical: PASS, PATCH, BLOCKER, UNVERIFIED | the architect's role step | at every judgement |
| `plan_first_pass`, `build_first_pass` | boolean | the work item | at the phase's first judgement: 1 when it was PASS |
| `final_verify_pass` | boolean | the work item | when the run ends: 1 at `READY_FOR_HUMAN`, 0 when aborted |

A work-item score has one id per work item, so a stage or a process run again after a crash replaces
it instead of adding a second. A run stopped at a gate has not ended and has no `final_verify_pass`.
With *Show Scores* on, a verdict shows on its step in the trace tree.

## Dimensions

Every row carries the work item's session — its label: start time, request and run id — its trace
name, the version `observability-schema-v1`, and four tags: `workflow:feature`,
`repo:<the run's repository>`, `target:<the run's target, wsl or windows>` and `source:manual`. The
repository, its base branch and the target come from the run, never from the process writing the row.
Every row is written by an activity that runs once, so a replayed workflow or a retry never writes
one twice.

Environment and release are recorded by every emitter: this component's client, the Codex uploader,
and the Claude plugin inside each role-run.

| dimension | value | an explicitly set variable wins |
|---|---|---|
| environment | `dev`; `fixture` for the UI fixture | `LANGFUSE_TRACING_ENVIRONMENT` |
| release | the orchestrator's commit in 12 hex digits, with `-dirty` when the working tree differs from it | `LANGFUSE_RELEASE` |

Sampling is 100%: every run is recorded.

## Masking

This component's client masks the input, output and metadata of every row it writes, and redacts
status messages and the final diff itself: private keys, high-confidence token shapes, and the
values of the secret entries in `secrets/langfuse.env`. A final diff that held a secret is marked
`redacted`, because its copy is then not the exact change.

The mask does not reach the plugins' rows — the agents' prompts, tool inputs and tool outputs — which
their own processes export, and self-hosted Langfuse has no server-side masking. Those rows are
audited instead.

## What the vendor plugins own

The Claude and Codex plugins write the turns, model calls and tool calls nested under each role
step. None of this is configurable from here:

- **names** — `Conversational Turn`, `LLM Call` and `Tool: <name>` for Claude; `Codex Turn`, `LLM`
  and the tool's own name for Codex;
- **levels** — a model call is DEFAULT, so *Min Level* cannot hide model calls; a tool call is
  ERROR when it failed; a turn is WARNING when it was interrupted;
- **session, tags and version** — attached under a stage, neither plugin sets any, so their rows
  appear in the trace tree and the Log View but not among a session's observations;
- **input and output** — structured messages for Claude; Codex's model-call inputs carry tool
  results as JSON-encoded text;
- **attribution** — a model call carries no role, so cost is broken down by model, not by role or
  repository.

## Dashboard and saved views

The *Orchestration Health* dashboard is defined and applied by
[`tools/langfuse_dashboard.py`](../../tools/langfuse_dashboard.py). It cannot show an aggregate per
work item — wall time, rounds before PASS, cost per work item — or anything grouped by metadata such
as `error_type`: the dashboard API offers neither.

Four saved views on the observations table, made in the UI with *Save view*, since Langfuse has no
API for them:

| view | filter | sort |
|---|---|---|
| Work Items | name is `orchestration-run` | newest first |
| Needs Attention | level is WARNING or ERROR, and type is not TOOL | newest first |
| Agent Actions | type is TOOL | newest first |
| Model Calls | type is GENERATION | total cost, highest first |

*Needs Attention* leaves tool calls out because a failed command is usually part of an agent's work;
a failed tool call shows in *Agent Actions*.
