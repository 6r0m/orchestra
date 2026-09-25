# Configurable flows: the order of a run's work, chosen per task

**Status:** IN PROGRESS — the external review passed; the final suite ran; the operator's live check
next
**Scope:** the order of a run's steps — a new `flows/` folder and its reader `app/foundation/flows.py`;
[workflow.py](../app/orchestration/workflow.py), [routing.py](../app/orchestration/routing.py),
[stages.py](../app/foundation/stages.py), [policy.py](../app/foundation/policy.py) and `policy.json`, the
role step in [activities.py](../app/application/activities.py), [nodes.py](../app/agents/nodes.py), the
run start in [client.py](../app/application/client.py), the Workbench's Start form and the CLI, the
trace's phases
**Stable documentation owner:** [docs/architecture/structure.md](../docs/architecture/structure.md)
(architecture D2, D5, D6, D13, D19, D24); [trace-contract.md](../docs/architecture/trace-contract.md);
[diagrams/stops.md](../docs/architecture/diagrams/stops.md); [docs/using.md](../docs/using.md); a new
`flows/README.md`

## Contents

- [Goal](#goal) · [Authority register](#authority-register) · [Non-goals](#non-goals)
- [Verified evidence](#verified-evidence) · [Current architecture](#current-architecture-and-source-of-truth)
- [Problem](#problem) · [Decision](#decision) · [Invariants](#required-invariants)
- [Tasks](#implementation-tasks) · [Verification](#test-first-and-verification-plan)
- [Documentation](#documentation-plan) · [Rollout](#rollout-and-rollback) · [Completion](#completion-criteria)
- [Review record](#review-record)

## Goal

The operator chooses, for each task, the order in which the roles work — research first or code
first, with or without their approval between steps, building or not — from flows they can read and
edit without a code change; a run keeps the flow it started with.

## Authority register

In this todo `D<n>` alone is this register's own entry; a decision of
[structure.md](../docs/architecture/structure.md) is written *architecture D<n>*. Entries recorded before
this convention keep their wording: in D5 and Q2, D11, D13 and D24 are the architecture's.

### Operator decisions

- **D1** A run follows a flow picked for its task.
  - Effect: the Start form and the CLI take a flow; a run's order of work is no longer one fixed
    sequence.
  - Reason: *"otherwise operator can't gain control"*
  - Date/source: 2026-09-25, operator — *"ui should give flow select for exact specific task"*;
    *"good goal just pick up needed flow"*
- **D2** A flow is an ordered list of `role:action` steps: the actions are a small fixed set the code
  owns — `research`, `plan`, `assess`, `build`, `verify` — plus the operator's gates, approve and
  merge; a review's PATCH returns to the work step before it, bounded, and BLOCKER stops for the
  operator; the flows live in one JSON file, shown on the page as a select with the chosen flow's steps
  as one line; a run keeps the flow it started with.
  - Effect: the shape of a flow and how it is shown.
  - Reason: not stated.
  - Date/source: 2026-09-25, operator, of that proposal — *"your flow understing is good!"*
- **D3** Two flows to support: **research-first** — the architect researches and writes an abstract
  todo, the operator agrees, then the engineer rechecks it against the current code and applies it —
  and **code-first**, the reverse, when the code matters more.
  - Effect: `research` is a new action, and a flow may start with the architect.
  - Reason: not stated.
  - Date/source: 2026-09-25, operator — *"he should start for investigation frist without ingeener at
    all"*; *"first need research some and then do abstract todo for architect, then operator agreed and
    give to ingeneer to recheck current code how it applied, or vise versa in case code is more
    importatins"*
- **D4** Flows are shown and edited in the most KISS and basic way, out of the box.
  - Effect: a JSON file edited by hand, re-read when used; no editor, no new service.
  - Reason: not stated.
  - Date/source: 2026-09-25, operator — *"we need in very KISS and basic understand how to show our
    flows and also quick edit them out of box"*
- **D5** D13 is to be understood and re-decided so that it gives the system flexibility rather than
  restricting it: flows as JSON, or whatever the industry's KISS standard recommends.
  - Effect: the clause of D13 that keeps the set and order of stages in code, and "There is no JSON
    workflow DSL", are the operator's to change; the new wording is this todo's proposal (Decision
    item 1) until approved.
  - Reason: *"goal not restict our system but give flexiblity to it, otherwise operator can't gain
    control"*
  - Date/source: 2026-09-25, operator — *"need to understand d13 … so code should use some jsons with
    flows or what best industrila standart recomment it KISS"*
- **D6** The architect is not restricted: it keeps its repository access. A repository-free architect
  — a web model fed attached, merged files — is optional and future, not this change.
  - Effect: no packaging of files for a model without repository access here.
  - Reason: not stated.
  - Date/source: 2026-09-25, operator — *"we not need restirct arhcitectore very hard - just
    optionally in case it web version in future … (focus not now, in future)"*
- **D7** The flows live apart from the policy: a folder of their own, one file per flow named by the
  flow, placed as the domain architecture places configuration.
  - Effect: closes Q1 — not a key in `policy.json`.
  - Reason: not stated.
  - Date/source: 2026-09-25, operator — *"ofcourse separate , different subfolder for all data and
    internal flows and inside exact flow name, check our domain driven architecture"*
- **D8** One switch skips every approval gate where the operator is needed, for all of a run's steps —
  never the final merge check.
  - Effect: closes Q3.
  - Reason: not stated.
  - Date/source: 2026-09-25, operator — *"I guess could globally skip approval for all stages where
    human needed except final merging check"*
- **D9** The code-based flow — the engineer's first turn, on the code — is the default; the flows get
  names without the word "first" that say who starts and from what.
  - Effect: closes Q4; the names are A8's until confirmed.
  - Reason: not stated.
  - Date/source: 2026-09-25, operator — *"code-frist let be default, but I guess need better names
    without first word emphasize that first turn will be engeener base on code?"*
- **D10** Reuse what the engine already integrated here provides out of the box, as much as possible,
  checked against its own documentation.
  - Effect: the design uses Temporal's own recommended pattern and its existing machinery, and builds
    only what Temporal leaves to its users (see the verified evidence).
  - Reason: *"wierd why we don't resue as mcuh as possible already ingetrated stuff?"*
  - Date/source: 2026-09-25, operator — *"we already have some engine brain orchestrator, it should give
    some out of box check web carefully and his docs"*; again: *"ok we need reuse temporal as much as
    possilbe"*
- **D11** The ending is flexible: a flow builds only when it has build steps, so a flow may end without
  building.
  - Effect: closes Q2; research-only and plan-only flows are allowed; a build, when there is one, still
    ends in a verify and the final merge check.
  - Reason: not stated.
  - Date/source: 2026-09-25, operator — *"bro why just not do this flexible if there are some to build
    then agent will be build no?"*
- **D12** Skipping approvals skips only the scheduled approval gates, never the emergency stops.
  - Effect: refines D8 — a blocker, an exhausted budget and a failed step still stop, as does the final
    merge check.
  - Reason: not stated.
  - Date/source: 2026-09-25, operator — *"yes here we skip only sheduled approvals not emergency"*
- **D13** The flows are named `engineer-code` and `architect-research`.
  - Effect: A8 confirmed.
  - Reason: not stated.
  - Date/source: 2026-09-25, operator, of A8 — *"good"*
- **D14** A flow that ends at its plan does not merge it: a merge is always human-gated. A way to merge
  such a todo, like a checkmark, may come in future; not now.
  - Effect: closes Q5; A11 confirmed.
  - Reason: *"because merfe always human gated"*
  - Date/source: 2026-09-25, operator — *"bro ofcourse no! … could be in future like checkmark but now
    hardly no!"*

### Operator gates

- **Q1 [CLOSED by D7]:** where the flows live — a `flows` key in `policy.json`, beside the roles
  and budgets it arranges, or a `flows.json` of its own. Default while open: A1.
- **Q2 [CLOSED by D11]:** whether every flow ends `engineer:build`, `architect:verify`,
  `you:merge`, which keeps the only path to a commit exactly as it is (D11, D24), or the tail is free
  too, under validation rules of its own. Default while open: A2.
- **Q3 [CLOSED by D8]:** whether *skip the plan approval* stays, skipping every `you:approve` of
  the chosen flow, or goes, replaced by flows without that gate. Default while open: A3.
- **Q4 [CLOSED by D9]:** which flow a run takes when none is named, and whether research-first
  ships beside code-first. Default while open: A4.
- **Q5 [CLOSED by D14]:** whether a flow that ends at its plan, without building, may merge that
  todo into the base branch — a merge after an assessment's PASS rather than a verify's — or ends keeping
  it in its worktree. Default while open: A11.

### Working assumptions

- **A1 [RESOLVED by D7 — not taken]:** flows are a `flows` object in `policy.json`: one owner of how
  runs behave, already validated strictly, re-read at every start and carried into each run's start
  input.
- **A2 [RESOLVED by D11 — not taken]:** the tail is fixed: every flow ends `engineer:build`,
  `architect:verify`, `you:merge`; what varies is everything before the build.
- **A3 [RESOLVED by D8]:** *skip the plan approval* stays and skips every `you:approve` of the chosen
  flow; never the final gate.
- **A4 [RESOLVED by D9]:** `code-first` — today's order — is the default, and `research-first` ships
  beside it.
- **A5 [ACTIVE]:** `research` writes no file: the architect is read-only, so its brief is its final
  message — taken from the turn's output as a verdict already is — returned in `run_role`'s result and
  kept in the run's state; the gate after it shows it and the next step's prompt carries it. Logs and the
  trace mirror it; nothing reads them to continue the run.
- **A6 [ACTIVE]:** `revise` at an approve gate returns to the work step before that gate; `guide` at a
  blocker or an exhausted budget re-enters the loop it stopped in, as today.
- **A7 [ACTIVE]:** the workflow never reads `flows/` or the policy's `default_flow`. A new run's flow is
  read and checked by the client at its start and sent in the start input as `{name, steps}`. A start
  input with no `flow` key — every recorded history and every run open at release — runs `LEGACY_FLOW`, a
  constant in code of today's order that issues exactly today's commands, so no `workflow.patched` is
  needed for it; it can retire, through replay and a patch, once no such history matters.
- **A8 [RESOLVED by D13]:** the two flows are named `engineer-code` — the engineer starts, from the
  code; today's order and the default — and `architect-research` — the architect starts, with research
  and an abstract todo (D9).
- **A9 [ACTIVE]:** the folder is `flows/` at the checkout root, beside `roles/`: operator-edited
  configuration sits there by the domain architecture ([app/README.md](../app/README.md): "`policy.json`,
  `repos.json` and `roles/` sit at the checkout root, because they are the operator's to edit"), and
  `roles/` is already a folder of one file each with a README routing to them. A flow is
  `flows/<name>.json`, holding its steps; `flows/README.md` routes to each. Reading and checking them is
  `app/foundation/flows.py`: foundation owns the contract every package reads — the policy and the
  stages of a run.
- **A10 [ACTIVE]:** which flow is the default is `policy.json`'s `default_flow`, which the policy checks
  by the flows' own grammar for a name; that it names a flow that holds is checked when a run starts on
  it, as for any flow named — and the Workbench keeps a default that is missing or refused chosen, so
  a start on it is refused as the command line's is. The policy already owns the defaults of a run, `auto_proceed` among them. Only the client
  reads it, when a new run names no flow (A7); with no default, such a run takes `LEGACY_FLOW`, and the
  Workbench offers that as a choice of its own.
- **A11 [RESOLVED by D14]:** a flow without a build ends `DONE` after its last step and never merges: its
  worktree and branch are kept for the operator, as a stopped run's are, with the Workbench's existing
  removal (architecture D31); a research brief stays in the run's state and is mirrored in the logs and
  the trace.
- **A12 [ACTIVE]:** `research` is the architect's action, as `assess` and `verify` are, so an engineer's
  work always goes to an architect's review (architecture D4) — owned by the action contract in
  `stages.py` (Decision item 3), where `research` is a work step and not a review.

## Non-goals

- No repository-free architect, no files packaged for a model without repository access (D6).
- No branches, conditions, parallel steps or loops beyond the review loop; no new roles — the two stay,
  with their access (architecture D2); no new brains.
- No editor for flows on the page (D4): the file is the editor.
- No change to the merge itself — it still follows a verify's PASS (architecture D11, D24) — nor to the
  stops' answers beyond an approve gate appearing where a flow puts it.
- No new Temporal machinery — no dynamic workflow types, child workflows, search attributes,
  continue-as-new, Nexus or worker versioning: the run stays one workflow type whose input carries its
  flow (D10).
- No schema version or checksum for a flow: there is one shape.
- No merge of a flow that ends without a build, nor a checkmark for one — a future option at most (D14).
- No scheduled or parallel runs (architecture D10).

## Verified evidence

**Verified facts**

- **Architecture D13 today** ([structure.md](../docs/architecture/structure.md)): brains, models,
  budgets, access, targets, repository descriptors and personas are configuration; "Stage asks (which
  artifact a stage produces or judges) and any new *stage* are code. There is no JSON workflow DSL."
  Architecture D2 fixes "Four stages, one workflow: `plan → assess → build → verify`".
- **Why the routing is code** ([history/decisions.md](../docs/history/decisions.md), "The workflow engine
  was not the first answer"): a hand-rolled state machine came first and "lost reviewer feedback on
  routing edges — the feedback lived on the edge rather than in the state"; the fix was ordinary
  workflow code over one compact state. structure.md, "Why there is no state machine here": "Do not
  re-derive a `states/` layer here."
- **Today's order is code:** `FeatureRun._loop` pairs `("plan", "assess")` and `("build", "verify")` by
  phase ([workflow.py](../app/orchestration/workflow.py), `_loop`); `routing.gate_reason_for` offers the
  approval only in the plan phase and only without `auto_proceed`; `_final_gate` sends a revise to
  `build` or back to review; `_plan_stands` re-assesses a plan changed after its PASS.
- **Feedback lives in state:** `_stage` writes `verdict`, `feedback` and clears `guidance`; the next
  prompt carries the task, persona, the stage's ask, the architect's findings and the operator's
  guidance ([nodes.py](../app/agents/nodes.py), `compose_prompt`). A role keeps one session across its
  stages (architecture D7).
- **Every consumer of the fixed set** (`grep` of `STAGE_ROLE`, `PHASES`, stage and phase names under
  `app/`): `stages.py` (`STAGES`, `STAGE_ROLE`, `PHASES`, `STAGE_ASK`); `workflow.py`; `routing.py`;
  `activities.run_role` (the role from `STAGE_ROLE[stage]`, `max_rounds[phase]`, the judged tree by
  stage); `agents/terminal.py` (a terminal's role from its log name's stage); `policy.validate`
  (`stage_skills` keys must be stages, `max_rounds` keys must be exactly the phases); `telemetry`
  (`PHASE_NAMES`, `PHASE_ROLES`, a step name per stage and role); `client.start`, the CLI's
  `--auto-proceed`, the Workbench's *skip the plan approval*.
- **A run carries its policy:** `client.start` loads `policy.json` at every start and puts the whole
  policy into the workflow's start input ([client.py](../app/application/client.py), `start`), so what a
  run was started with is in its recorded history.
- **Replay is guarded:** eight recorded histories under [tests/histories/](../tests/histories/), all
  replayed by [test_replay.py](../tests/orchestration/test_replay.py), whose control shows an
  unpatched change fails (architecture D25).
- **Access:** the architect runs Codex with `--sandbox read-only` and live web search; the engineer
  Claude with edits allowed in its worktree ([nodes.py](../app/agents/nodes.py), `build_argv`;
  `policy.json`). A read-only role cannot write a research file.
- **Read-only is taken for a reviewer today:** `run_role` sets `is_reviewer = role["workspace_access"]
  == "read"` ([activities.py](../app/application/activities.py)), and that flag chooses the prompt's
  wording, the tree snapshot, the verdict parse and what the trace records; `nodes.parse_review` raises
  "reviewer returned no parseable {verdict, feedback}" on an answer with no verdict. An architect's
  research step would fail there.
- **A turn's output is its final message:** `terminal.run_turn` returns Claude's final message, or
  Codex's events with its final message in them, which `parse_review` already takes apart
  ([terminal.py](../app/agents/terminal.py), [nodes.py](../app/agents/nodes.py)). Nothing bounds the
  length of a verdict's feedback in state today.
- **A web architect already has a home:** architecture D9 allows "a low-cost web chat whose account can
  be lost, such as DeepSeek" as "a detached architect — deliberately, never as a silent addition" — the
  future D6 names.
- **What the engine gives out of the box (D10):** Temporal ships no workflow language of its own; for
  workflows defined as data its own answer is one interpreter workflow given the definition as input.
  - Its sample: "how one can write a workflow to interpret arbitrary steps from a user-provided DSL",
    the definition passed as the workflow's input
    ([temporalio/samples-python, `dsl`](https://github.com/temporalio/samples-python/tree/main/dsl)).
  - Its co-founder, on the community forum: "I would avoid the code generation approach. Writing a
    single interpreter workflow for your JSON is the way to go"; a definition changed while runs are open
    is "up to your implementation of the interpreter"
    ([forum](https://community.temporal.io/t/how-will-temporal-store-the-workflow-status-if-we-read-the-workflow-definition-from-json-yaml-in-code/2600)).
  - Its staff: pass "the whole workflow definition as input to your workflow when you start it", and JSON
    is what most such languages use, being neutral
    ([forum](https://community.temporal.io/t/implementing-dsl-workflows/3413)).
  - Dynamic workflows (`@workflow.defn(dynamic=True)`) serve workflow *types* not registered in advance
    ([Python SDK](https://python.temporal.io/temporalio.workflow.html)); a run here is always one type,
    `FeatureRun`.
  - Its documentation on child workflows: "There is no reason to use Child Workflows just for code
    organization", and "It is typically recommended to start from a single Workflow Definition if your
    problem has bounded size" ([Child Workflows](https://docs.temporal.io/child-workflows)) — a run's few
    steps and stops are bounded.
  - What this design reuses of it, unchanged: the durable state of the loop, the recorded history the
    flow is kept in — the start input, shown for every run in Temporal's own web UI — Updates for the
    gates' answers, cancellation for a Stop, the visibility list the Workbench already reads its runs from
    ([client.py](../app/application/client.py), `runs`), and replay with `workflow.patched` for
    compatibility. What it builds is only the part Temporal leaves to its users: the interpreter, which
    is today's loop generalised.
- **Where configuration lives:** [app/README.md](../app/README.md) — "`policy.json`, `repos.json` and
  `roles/` sit at the checkout root, because they are the operator's to edit (D13)", the architecture's
  D13; `roles/` is a folder of one file per role with a README routing to them.
- **What a closed run keeps:** a run closed short of a merge or a discard keeps its worktree and branch
  until the operator removes them from the Workbench, through its host's own git (architecture D31;
  [docs/using.md](../docs/using.md), "The page").

**Inferences**

- What the operator wants to vary is the order of the steps and whether a run builds at all (D11); the
  guarantee of architecture D11 and D24 — only a verified tree is committed — holds as long as a merge
  comes only after a verify's PASS, whatever came before it.
- A flow expressed as today's order, run by the interpreter, can issue exactly today's commands, as the
  optional `stop_cleanup_seconds` did without `workflow.patched` (A7); the eight histories prove it or
  refute it.
- The history's lesson holds for any order: feedback and guidance stay in the run's state and reach the
  next step's prompt; a flow never carries them on its edges.
- What a run does on its own is bounded by its steps and `max_rounds`; `policy.validate` gives
  `max_rounds` no upper limit today — an existing setting this change leaves as it is. Past that, a run
  grows only by the operator's own answers.

**Assumptions / unverified**

- How long a research brief runs, and so how much of it the gate after it shows: measured on the first
  real `architect-research` run.
- Whether [tools/langfuse_dashboard.py](../tools/langfuse_dashboard.py) filters on phase names, which a
  research phase would need to join.

## Current architecture and source of truth

- [structure.md](../docs/architecture/structure.md) owns the roles and stages (architecture D2), budgets
  (D5), stops and their answers (D6), config versus code (D13), the architect's horizon (D15), skills per
  stage (D19), the worktree's lifecycle and the final gate (D24), a closed run's kept work (D31) and
  determinism (D25) — all the architecture's.
- The order of work is `FeatureRun._loop` over the routes of `routing.py`; what each stage asks is
  `stages.STAGE_ASK`, rendered by `nodes.compose_prompt`; a stage's role and access come from
  `policy.json` through `activities.run_role`.
- The trace's phases and steps are the [trace contract](../docs/architecture/trace-contract.md)'s.

## Problem

The order of a run's work is fixed in code — the engineer plans first, always — so a task that should
start from research, stop at a plan, or skip straight to code, cannot, and changing the order means a
release. Architecture D13 says so by design; the operator has asked for that design to change (D5).

## Decision

1. **A flow is data; its actions are code** — Temporal's own pattern (D10): one interpreter workflow,
   the definition as its input. A flow names its steps, `role:action`, in order; what each action asks
   for and produces stays in `stages.py`, and which role may do it stays with the policy's roles.
   Architecture D13 becomes: the actions, and the rules a flow must keep, are code; the flows — the order
   of a run's steps, and whether it builds — are configuration. "There is no JSON workflow DSL" gives way
   to that one list: no states, no transitions, no conditions.
2. **Where and how (D7, A9, A10):** a folder `flows/` at the checkout root, beside `roles/`, one file per
   flow named by it (the names are D13's), with `flows/README.md` routing to each:
   ```
   flows/engineer-code.json       ["engineer:plan", "architect:assess", "you:approve",
                                   "engineer:build", "architect:verify", "you:merge"]
   flows/architect-research.json  ["architect:research", "you:approve",
                                   "engineer:plan", "architect:assess", "you:approve",
                                   "engineer:build", "architect:verify", "you:merge"]
   ```
   `policy.json`'s `default_flow` is `engineer-code` (D9). `app/foundation/flows.py` reads and checks
   them; they are read at every start and each time the Workbench's Flow list is opened, as `repos.json`
   is.
3. **One action contract, and the rules a flow keeps.** `stages.py` owns, in plain mappings, each action's
   role, its ask, and whether it is a review — `research` (architect, work), `plan` (engineer, work),
   `assess` (architect, review of `plan`), `build` (engineer, work), `verify` (architect, review of
   `build`) — extending today's `STAGE_ROLE` and `STAGE_ASK`. Everything else derives from it: whether a
   step parses a verdict, judges a tree, loops back, and how its prompt and trace read. A read-only role
   is no longer taken for a reviewer (today `run_role` sets `is_reviewer` from read access); the read-only
   flags of the agent's command stay with access (`nodes.build_argv`). A flow's `role:action` is checked
   against the contract, never trusted over it. The rules, checked when a flow is read and refused with
   their reason:
   - known roles and actions; at least one step and at most `MAX_FLOW_STEPS`, 32, in `flows.py` — the
     bound that keeps a run the bounded work one workflow is recommended for (verified evidence), with
     room to spare over the six to eight steps a flow takes; a flow that genuinely outgrows it is evidence
     to revisit the limit and, should the history become the constraint, continue-as-new — child
     workflows only if an independently owned sub-workflow or a real partitioning boundary appears;
   - each step's role is the one the contract gives its action (A12), so a review is never done by the
     role whose work it judges (architecture D3);
   - every `plan` is directly followed by an `assess`, every `build` by a `verify`: an engineer's work
     always reaches an architect's review (architecture D4);
   - `you:approve` follows a review or a `research`;
   - `you:merge` only as the last step, directly after a `verify` — the only path to a commit
     (architecture D11, D24);
   - a flow that builds ends with `you:merge`; a flow without a build ends wherever its last step is
     (D11, D14).
4. **One run, one flow (A7):** the client reads and checks the chosen flow at the start, and the start
   input carries it as `{name, steps}` beside the policy — the name for people, the steps the run's own
   copy; no schema version or checksum. The workflow interprets the steps and never reads a file: a work
   step, its review loop (PATCH or UNVERIFIED back to the work step, bounded by `max_rounds` of that work
   action; BLOCKER or an exhausted budget to the operator's guide), then the step's gate. Feedback and
   guidance stay in the run's state. A start input with no `flow` key runs `LEGACY_FLOW`; a `flow` it
   gives, null included, is taken as given and must be `{name, steps}`.
5. **`research`:** its ask investigates the task and current practice, on the live web and in the
   repository as far as the role can read, and answers with a research brief and an abstract todo as its
   final message (A5). `run_role` returns that message as the step's output; the workflow keeps it in
   the run's state, the gate after it shows it, and the next step's prompt carries it, as prompts already
   carry everything from state (`nodes.compose_prompt`).
6. **Shown and chosen:** the Start form gains a Flow list with the chosen flow's steps as one line under
   it; a run's page shows its own flow with its current step; the CLI takes `--flow NAME`.
7. **One switch for approvals (D8, D12):** `auto_proceed` stays the field it is — in the start input, the
   policy and the CLI's `--auto-proceed` — and its meaning broadens to every scheduled `you:approve` of
   the run's flow; only its words change, to *skip approvals* on the page and in the CLI's help. It never
   skips the final merge check or an emergency stop: a blocker, an exhausted budget and a failed step
   still stop, because the run has no way on without the operator.
8. **A flow without a build (D11, D14):** after its last step the run ends `DONE`; it never merges; its
   worktree and branch are kept for the operator, and removed from the Workbench as a stopped run's are
   (architecture D31); a research brief stays in the run's state and is mirrored in the logs and the
   trace.
9. **Reused from Temporal, unchanged (D10):** the run stays one workflow type, `FeatureRun`, whose
   start input carries its flow — recorded in its history and shown in Temporal's web UI; the gates stay
   Updates, a Stop stays cancellation, the Workbench's run list stays Temporal's visibility query, and
   compatibility stays `workflow.patched` over the recorded histories. Built here: only the interpreter.

### Premise / KISS gate

- **Owner:** the workflow already owns the order of work, and Temporal already owns its durability,
  history, answers, cancellation and replay (D10); the flows are configuration beside the roles (D7).
  Nothing new owns the run.
- **Adds:** the `flows/` folder of two files and its README, one reader in `foundation`, one policy key
  (`default_flow`), one action with its ask, a review mapping beside `STAGE_ROLE`, one field in the start
  input, one constant (`LEGACY_FLOW`), one ending (`DONE`), one list on the page, one CLI flag, one trace
  phase — and no Temporal machinery (item 9).
- **Removes:** the hard-wired pairing of stages in `_loop`, and the plan-only approval in `routing.py`,
  which become the flow's own steps.
- **Given up:** graphs — branches, conditions, parallel steps. No flow the operator has named needs them.

### Alternatives considered

- **A few flows in code** (a research switch): the least code, but every new order is a release —
  it gives the operator no control (D1, D5).
- **A standard workflow language** (the Serverless Workflow specification, Amazon States Language,
  BPMN): expressive, but states, transitions and conditions for a linear run of two roles, and routing on
  edges is the machinery that lost feedback before (history). Rejected.
- **Code generated from each flow:** Temporal's co-founder advises against it (verified evidence); one
  interpreter reads every flow.
- **Temporal's dynamic workflows, a type per flow:** for types unknown when a worker registers; every run
  here is one type, and the flow is its input.
- **Temporal's sample language itself:** activity, sequence and parallel statements, parsed from YAML with
  `yaml` and `dacite` ([starter](https://github.com/temporalio/samples-python/blob/main/dsl/starter.py))
  — far more than a strict linear list needs. Its pattern is taken, not its language.
- **YAML:** easier to read, but a new dependency, and every configuration file here is JSON.
- **A `flows` key in `policy.json`:** not taken (D7).

## Required invariants

1. Only a review step's verdict routes; an engineer's work always reaches an architect's review
   (architecture D4).
2. A review is done by the read-only role, never by the role whose work it judges (architecture D3).
3. The only path to a commit is the final gate after `verify`'s PASS, and a merge commits exactly the
   verified tree (architecture D11, D24); a flow without a build never merges.
4. Feedback and guidance live in the run's state and reach the next step's prompt; a session born again
   gets the current step's ask (architecture D18b).
5. Every review loop is bounded; its limit stops for the operator (architecture D5).
6. Each stop publishes its own answers, and an answer it does not offer is rejected (architecture D6).
7. Skipping approvals skips only the scheduled approve gates — never a blocker, an exhausted budget, a
   failed step or the final gate (D8, D12).
8. The workflow stays deterministic; the recorded histories replay; a run keeps the flow it started with
   (architecture D25).
9. A flow that breaks a rule is refused when it is read, with the rule it broke; a run never starts on
   it and nothing half-runs.
10. One session per role per run, across all of that role's steps (architecture D7).
11. The trace records flows and never routes them (architecture D20).
12. The workflow never reads `flows/` or the policy's default: a new run's flow arrives in its start
    input, and a start input without a `flow` key runs `LEGACY_FLOW` (A7); any other ends `REFUSED`
    before any step unless it is `{name, steps}` and keeps the rules.
13. Nothing reads a log to continue a run: what a step hands on — a verdict, feedback, a research brief —
    returns as its activity's result and lives in the run's state (A5).
14. One action contract owns each action's role and whether it is a review; access decides only the
    agent's read-only flags (Decision item 3).
15. A flow holds from one to `MAX_FLOW_STEPS` steps, so a run stays the bounded work one workflow is
    meant for (D10).

## Implementation tasks

0. [x] **The operator's questions** answered: Q1–Q5, closed by D7, D11, D8, D9 and D14.
1. [x] **Guards, failing first:** reading and checking `flows/` — both shipped flows accepted, each
   broken rule refused with its reason, an empty flow and one over `MAX_FLOW_STEPS` among them; the
   workflow on the time-skipping server with the fake agents —
   `engineer-code` issuing today's sequence, `architect-research` end to end (research returning its brief
   with no verdict parsed and no tree judged, its gate showing the brief, revise back to research,
   approve, a plan whose prompt carries the brief, assess, build, verify, merge), a flow without a build
   ending `DONE` with its worktree kept and nothing merged, *skip approvals* skipping every approve gate
   while a blocker, an exhausted budget, a failed step and the final gate still stop, a run keeping its
   flow after its file changes, a recorded history with no flow replaying on `LEGACY_FLOW` while
   `flows/engineer-code.json` differs from it; the page's Flow list; the CLI's `--flow`.
2. [x] **The action contract:** `research` and its ask in `stages.py`, `STAGE_ROLE` extended to it, and a
   mapping of each review to the work it judges; the plan's ask carrying a brief when state holds one.
3. [x] **Flows:** `flows/` with its two files and README; `app/foundation/flows.py` reading them,
   checking each step against the contract and the length against `MAX_FLOW_STEPS`; `policy.json`'s
   `default_flow`; `stage_skills` and `max_rounds` keyed by action.
4. [x] **Start:** `client.start(flow=…)` reads and checks the flow, the default when none is named, and
   puts `{name, steps}` in the start input; the Workbench's run start and its flows read; the CLI's
   `--flow`; `auto_proceed` kept as it is, worded *skip approvals* on the page and in the CLI's help.
5. [x] **Workflow:** the interpreter over the start input's steps, the gates generalised in
   `routing.py`, the `DONE` ending, `LEGACY_FLOW` for a start input without a `flow` key, no file read; the
   brief kept in state from the step's result; the Workbench and the CLI read a `DONE` run as closed with
   its work kept, which `client.not_kept` decides today.
6. [x] **The role step:** the role and whether the step is a review from the action contract, not from
   read access; a research step returning its final message as its output; a terminal's role from the
   contract (`agents/terminal.py`).
7. [x] **Trace:** a research phase and its steps, its brief recorded as a role's response, in
   `telemetry` and the trace contract; the dashboard checked.
8. [x] **Page:** the Flow list, the steps line, a run's own flow with its current step.
9. [x] **Recorded histories** in `tests/histories/` — `research_revise_plan_merge` and
   `plan_only_done` — so replay guards the new paths.
10. [x] **Docs** (below).
11. [ ] **Verification:** the changed modules on both hosts; the whole suite once per host after the
    external reviewer's PASS; the operator's manual check.

## Test-first and verification plan

### Red evidence

| case | kind | today |
|---|---|---|
| a flow in `flows/` is accepted, a broken one refused with its rule | permanent guard | no `flows/`; the order is code |
| an `architect-research` run: research → gate → plan → … → merge | permanent guard | no `research`; the engineer always starts |
| revise at the gate after research returns to research | permanent guard | no such gate |
| *skip approvals* skips every approve gate, never the final gate | permanent guard | only the plan phase's approval |
| with *skip approvals*, a blocker, an exhausted budget and a failed step still stop | permanent guard | holds for the plan's approval only |
| a flow without a build ends `DONE`, keeps its worktree, merges nothing | permanent guard | every run builds; no `DONE` |
| a run keeps its flow when its file changes mid-run | permanent guard | no flow to keep |
| a history without a flow replays on `LEGACY_FLOW` while the flow file differs | permanent guard | no flows |
| an architect's research step returns its brief: no verdict parsed, no tree judged | permanent guard | read access makes it a reviewer; the parse fails |
| a flow giving an action a role the contract does not is refused | permanent guard | no flows |
| an empty flow and one of `MAX_FLOW_STEPS` + 1 steps are refused | permanent guard | no flows |
| `engineer-code` issues today's commands: the eight histories replay | acceptance | passes today; must still pass |
| the page lists flows and shows the chosen one's steps | permanent guard, in a browser | no Flow list |

### Green evidence

The cases above; `test_replay` with the new `architect-research` history and its control; the changed
modules on both hosts; `git diff --check`; `make public-check`; then the whole suite once per host after
the external reviewer's PASS, and a real `architect-research` run in the operator's manual check.

## Documentation plan

- **Authoritative owners:** [structure.md](../docs/architecture/structure.md) — architecture D2 (roles
  and flows), D5 (a budget per work action), D6 (an approve gate where a flow puts it), D13 (re-decided
  per this todo's D5), D19 (skills per action), D24 (a run that ends `DONE`);
  [diagrams/stops.md](../docs/architecture/diagrams/stops.md);
  [trace-contract.md](../docs/architecture/trace-contract.md) (the research phase);
  [docs/using.md](../docs/using.md) (choosing a flow, editing flows); `flows/README.md`, new, like
  [roles/README.md](../roles/README.md): what each flow is for, linking its file.
- **Router:** [app/README.md](../app/README.md)'s sentence on where configuration sits, and the root
  [README.md](../README.md)'s configuration table, gain `flows/`.
- **Duplication avoided:** the flows' rules live in `app/foundation/flows.py` and are stated once in
  architecture D13; the page, the CLI and `flows/README.md` name a flow and never restate its rules.
- Stable docs, code, comments, tests and configuration do not reference this todo.

## Rollout and rollback

- **Rollout:** a run open at release has no flow in its input and continues on the default's steps,
  with today's commands (A7).
- **Rollback:** a run started with any other flow cannot replay on the old code; roll back only once no
  such run is open.

## Completion criteria

- Tasks 0–11 done; every red case green; the recorded histories, the new one included, replay; the
  documentation owners updated; the external reviewer's PASS; the whole suite clean once per host; an
  `architect-research` run done end to end in the operator's manual check.

## Review record

### 2026-09-25 — opened

- **Trigger:** during the Workbench's live check — *"architector could switched in future to deepseek
  browser … and he should start for investigation frist"*, then *"ui should give flow select for exact
  specific task"*, and D1–D6.
- **Evidence gathered:** the architecture's D2, D13, D9 and the state-machine history; every consumer
  of the fixed stages; the start input's policy snapshot and the recorded histories; Temporal's DSL
  sample.

### 2026-09-25 — the operator's answers, and what the engine gives

- **Authority:** D7–D10 added; Q1 closed by D7, Q3 by D8, Q4 by D9; A1, A3, A4 resolved; A8–A10 added.
  Q2 stays open.
- **Evidence:** Temporal ships no workflow language; its sample, its co-founder and its staff give the
  interpreter pattern with the definition as input, which the Decision now names as its basis; where
  configuration sits by the domain architecture, and `roles/` as the precedent for `flows/`.

### 2026-09-25 — a flexible ending, and the todo made whole

- **Authority:** D11–D13 added; Q2 closed by D11; A2 and A8 resolved; A11, A12 and Q5 added. D10's
  source gains the operator's *"reuse temporal as much as possilbe"*.
- **Fix:** the rules now let a flow end without a build, which ends `DONE` keeping its work; skipping
  approvals never skips an emergency stop; what is reused of Temporal is listed as Decision item 9, and
  new Temporal machinery is a non-goal. The architecture's decisions are now written *architecture
  D<n>*, which this register's own numbers had made ambiguous.
- **Next:** the operator's external reviewer — *"update fully todo and wait reviewer"*.

### 2026-09-25 — the last question

- **Authority:** D14 added; Q5 closed by D14; A11 resolved. Every operator gate is closed.

### 2026-09-25 — the external review: PATCH, the architecture passed

- **Accepted as built:** the Temporal boundary — one `FeatureRun` interpreter, the flow as its input,
  Activities, Updates, cancellation, termination, history and replay reused; no new Temporal machinery.
- **Fixed, three findings, each checked against the code:**
  - an old run could have been read as today's default flow file: the workflow now never reads a flow,
    and a start input without one runs `LEGACY_FLOW` (A7, invariant 12);
  - the research brief lived in logs: it now returns as the step's result and lives in state (A5,
    invariant 13);
  - a read-only role was taken for a reviewer (`run_role`'s `is_reviewer`), so research would have
    failed at the verdict parse: one action contract in `stages.py` now owns each action's role and
    review behaviour (Decision item 3, invariant 14).
- **Kept, as the review asked:** `auto_proceed` as the stored field, with new words; a flow as
  `{name, steps}` with no schema version. A5, A7, A10 and A12 were rewritten in place.
- **Refuted:** nothing; the review's claim about Temporal's guidance on child workflows was checked at
  its source.
- **Next:** the operator's approval, then implementation.

### 2026-09-25 — the external review, second pass: PATCH, two fixes

- **Fixed:** the one-workflow premise is now enforced — a flow holds at most `MAX_FLOW_STEPS`, 32, beside
  its minimum of one, with a guard for both (invariant 15); A11 and Decision item 8 said the research
  brief stays in the logs, contradicting A5 and invariant 13 — both now keep it in the run's state,
  mirrored in the logs and the trace.
- **Added:** Temporal's sample language rejected in its own right — its pattern is taken, not its
  language, which the review's claim about it checked out against (activity, sequence and parallel
  statements; YAML read with `yaml` and `dacite`).
- **Refuted:** nothing.
- **Next:** the review's go was on these two fixes; the go to implement is the operator's.

### 2026-09-25 — built

- **Red, each observed before the code:** `test_flows` would not import; the workflow ran `plan` where
  `research` was scripted, with no `flow`, `step` or `DONE`; `/api/flows` answered 404; the CLI had no
  `--flow`; `default_flow` was an unknown policy key.
- **Green:** WSL, the changed modules — 64 classes, 294 tests; Windows, the host modules they touch —
  33 classes, 175 tests. Ten recorded histories replay, the two new ones among them, and fail under the
  control. `test_flows` joins the Windows host list.
- **Controls, each red with its fix out and green restored:** the legacy order read from a flow file;
  review taken from read access; the step bound taken out; the brief not carried to the plan; *skip
  approvals* skipping a blocker; the default flow ignored; a flow without a build ending at the final
  gate.
- **In a browser:** the Start form's Flow list offers both flows, picks `engineer-code` and shows each
  flow's steps.
- **Found while building:** the page drew only `plan` and `build` rounds, and the CLI counted `DONE` as a
  failure — both fixed; the trace-contract test expected every row kind from a code-first run, and now
  excepts research's, which a research-first run writes.

### 2026-09-25 — the agents' review round: PATCH, fixed

- **Fixed, every finding valid:** a run ending `DONE` left its terminals open; the approval's text showed
  at a blocker or an exhausted budget in a flow's last part, and a plan's text after a verify; the words a
  research was revised with reached the plan; an empty Codex brief became its raw events; research after a
  plan was taken — now a rule of its own; a research session born again lost the brief its feedback was
  about; a flow handed to the workflow past the client went unchecked — it now ends the run `REFUSED`; the
  page picked the first flow when the policy names no default; `--show` did not fit `research`; the
  package docs and D6, D13, D19, D20, D29 still said four stages or two phases. Found in the final
  re-read: every role's step asked for Codex reasoning, so an engineer bound to Codex would have written
  its own — now the architect's alone, a brief's as a verdict's.
- **Tests that could not fail, rebuilt or added:** a flow kept though its file changes to a different
  next step; *skip approvals* never skipping a spent budget; the brief's parse; research's read-only
  flags; the name guard against real files beside the folder; a flow file that cannot be read.
- **Evidence:** WSL, the changed modules — 41 classes, 184 tests, and after the reasoning fix the modules
  it touches — 25 classes, 122 tests; Windows, the host modules — 29 classes, 165 tests, again after it;
  21 controls red with the fix out and green restored; in a browser, the Flow list with a
  default and without one — control: the page's new option taken out; the recorder reproduces both new
  histories event for event — control: a plain-text research reply; `make public-check` passed, and the
  new untracked files, which it does not scan, have no leak under the same Gitleaks.
- **Next:** the external review; the full suite once it passes.

### 2026-09-25 — the external review, third pass: PATCH, three fixes

- **Fixed, each seen failing first:** the workflow made the flow it was handed into a list — a dict of
  steps became its keys, and `{"architect:research": …}` ran research; a string, or a flow with no
  steps, raised inside the workflow. It now takes `{name, steps}` as given (`flows.steps_of`), and any
  other shape ends the run `REFUSED` before any activity. A flow's name had two grammars — the
  policy's took `engineer:code`, which no file can be — and `flows.is_name` is now the one. A default
  that is missing or refused left the Start form on another flow, which Start would have run; the
  flow chosen, or the default, now stays chosen, marked so, and Start gets the server's reason.
- **Corrected, not refuted:** a run handed such a string does not fail — its first workflow task
  fails and Temporal retries it, so the run stayed open and stuck (observed on the test server).
- **Kept, as the review asked:** the flat action mappings in `stages.py`; no Child Workflows,
  Continue-As-New or Worker Versioning.
- **Evidence:** WSL, the affected modules — 33 classes, 174 tests; Windows, the host modules —
  29 classes, 167 tests; the ten histories replay; 25 controls red with the fix out and green
  restored; in a browser, a default named, none, missing and refused — Start pressed on the last two
  answered by the server, and each placeholder taken out failing its check; `make public-check`
  passed with the new files tracked.
- **Next:** the external review's PASS; then the full suite once per host.

### 2026-09-25 — the external review, fourth pass: PATCH, one fix

- **Fixed:** a start giving `"flow": null` took the order from before flows, as one with no `flow` key
  does — `start.get` cannot tell them apart, and the last report's "only a missing flow gets the old
  order" was not what the code did. The workflow now asks whether the key is there: absent is a run
  from before flows; any value, null included, goes through `flows.steps_of`, so null ends the run
  `REFUSED` before any activity.
- **Evidence:** red first — null started the plan. WSL and Windows, `test_flows`, `test_workflow`
  and the replay — 10 classes, 67 tests each; controls, each red then green: null taken as legacy
  again, the legacy order read from a file, the steps made into a list, the check taken out.
- **Next:** the external review's PASS; then the full suite once per host.

### 2026-09-25 — the external review: PASS; the final suite

- **Suite, on the committed tree:** WSL, `make test` — 99 classes, 439 tests, green. Windows, the host
  suite — 68 classes, 320 tests, one error: `test_terminal.Turns.test_a_timeout_ends_the_agent`'s
  cleanup met `WinError 32` on its temporary worktree, which the timed-out agent still held for a
  moment. Not this change: that test and the code it drives are untouched; alone it passed three
  times of three, and its class passed whole; no agent was left running.
- **Gate:** `git diff --check` clean; `make public-check` passed.
- **Next:** the operator's call on that Windows race; then the Workbench and the whole stack
  restarted together, and a live `architect-research` run.

### 2026-09-25 — the Windows race the final suite found, fixed

- **Cause:** the containment, not the test. `TerminateJobObject` only begins termination, and
  `_WindowsTree.kill()` returned at once: a process has its exit code while it still holds its
  handles, the directory it worked in among them. A discard or merge, which ends the run's terminals
  right before git removes the worktree, could meet the same refusal on a busy Windows host.
- **Fixed** in `launch.py`, on the operator's word: each process of the job is taken hold of before
  the termination and waited for, within `GRACE_SECONDS`; D17 and the module say so.
- **Evidence:** a new containment test — the tree ended, the folder it worked in removed at once — red
  three times of three before the fix, `WinError 32` though the process had its exit code, and green
  three of three after; the final suite again on this tree: WSL 99 classes, 441 tests, Windows
  68 classes, 322 tests, both green; `make public-check` passed; the stack restarted again, so its
  Windows worker runs the fix.
- **Next:** the operator's live `architect-research` run.
