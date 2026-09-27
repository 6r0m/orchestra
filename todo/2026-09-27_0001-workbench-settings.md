# Pluggable agents under every role, set up in the Workbench

**Status:** REVIEW REQUIRED
**Scope:**
- `app/agents/`: an adapter per kind of agent, behind one contract;
- the modules that name an agent today: `nodes.py`, `terminal.py`, `turn_hook.py`, `trust.py`,
  `activities.py`, `telemetry.py`, `policy.py`;
- the settings files and their environment variables, renamed and layered;
- the Workbench's settings API and view.

**Stable documentation owner:**
- [the architecture's D3, D13, D17, D19 and D29](../docs/architecture/structure.md);
- [the agents' structure](../app/agents/docs/architecture/structure.md), for the adapter contract;
- [the foundation's structure](../app/foundation/docs/architecture/structure.md), for the settings'
  layers;
- [docs/using.md](../docs/using.md) and [README.md](../README.md), for the operator.

## Contents

- Goal · Authority register · Not in this change
- Verified evidence · Current architecture and source of truth · Problem and capability gap
- Decision (Premise / KISS gate, Alternatives considered)
- Required invariants · Implementation tasks · Test-first and verification plan
- Documentation plan · Rollout and rollback · Completion criteria · Review record

## Goal

Any agent system can run under any role. The operator chooses, configures and swaps agents in the
Workbench, and nothing else in Orchestra knows which agent is running: today Claude Code and Codex, and
others later.

Every agent runs in its role's live terminal, which the operator can watch and type into.

The same place sets:

- each role's persona;
- the skill that leads each stage;
- how the roles interact: review rounds per phase, and the default flow.

Settings follow a conventional hierarchy of shared and personal files. They are saved when applied,
reach every run started afterwards, and keep personal ones out of the public repository.

## Authority register

### Operator decisions

- **D1** A convenient, global place in the Workbench's UI to understand and edit each role's agent
  binding — Codex and Claude for now — per role.
  - Effect: a settings view in the Workbench, global rather than per run.
  - Reason: "how to better understand and edit our agents binding".
  - Date/source: operator, 2026-09-26.
- **D2** The same place sets up the policy for the engineer's and the architect's interactions, and
  the prompt they read once when a run starts — "for example architect investigate skill for
  arhitector, and implement investigate for ingeener" (operator's words).
  - Effect: personas, stage skills and the interaction policy are in scope.
  - Reason: not stated.
  - Date/source: operator, 2026-09-26.
- **D3** Settings are set up for good through a data layer, and saved when applied.
  - Effect: an explicit Apply, never saving as the operator types; settings persist across restarts.
  - Reason: not stated.
  - Date/source: operator, 2026-09-26 ("setup it constantly via data layer that saved after we apply").
- **D4** Check carefully: investigate first, and implement only after the external reviewer's PASS
  and the operator's explicit GO.
  - Effect: this todo; no implementation before both.
  - Reason: "check carefully", and the operator's standing process for this Workbench's changes.
  - Date/source: operator, 2026-09-26.
- **D5** "our goal flexible change any agent system under every role — so today codex cli, tomorrow
  deepseek under pi and etc — why so boundaries and restrictions, all should be flexible as possible
  without coupling".
  - Effect:
    - Any agent can run under any role, chosen by configuration.
    - No code outside an agent's own adapter names or branches on an agent.
  - Reason: flexibility; today's agents are not the last ones.
  - Date/source: operator, 2026-09-27.
- **D6** Codex runs on the operator's CLI subscription, as Claude does — "why codex pay call? we use
  cli subscription like claude".
  - Effect: a measuring turn of either CLI is not a paid call, and needs no special approval.
  - Reason: stated.
  - Date/source: operator, 2026-09-27.
- **D7** Every agent's terminal takes typing — "we implemented live terminals — that the full point of
  bench".
  - Effect: every kind of agent runs interactively in its role's live terminal. An agent driven one
    turn per process is not a way to add one.
  - Reason: stated.
  - Date/source: operator, 2026-09-27.
- **D8** pi — "it's future not now".
  - Effect: no pi adapter, install or proof in this change. The contract must let a new kind of agent
    be added later as one module.
  - Reason: not stated.
  - Date/source: operator, 2026-09-27.
- **D9** The two roles may run the same model — "it's operator descisions if he need the same model but
  wiht didfferent promts".
  - Effect: the independent-judge refusal (today's D3, `policy.py:185-196`) goes. Whether the reviewer
    is a different model is the operator's choice.
  - Reason: stated.
  - Date/source: operator, 2026-09-27.
- **D10** The reviewer stays read-only — "ofcourse reviewr read only we already decided it".
  - Effect: the reviewing role is read-only whatever agent runs it.
  - Reason: already decided.
  - Date/source: operator, 2026-09-27.
- **D11** `ORCH_POLICY` is a bad name — "pick proper hierarchy and naming for similar cases from web".
  - Effect:
    - the settings get a conventional hierarchy of files;
    - the settings files and every `ORCH_*` variable are named by common practice;
    - the pick is delegated to this investigation (A1).
  - Reason: stated.
  - Date/source: operator, 2026-09-27.

### Operator gates

- **Q1 [CLOSED by D11]:** Where do applied settings live?
- **Q2 [CLOSED by D5]:** Should the view also edit each role's persona text?
- **Q3 [CLOSED by D6]:** A real Codex turn to measure its skills. Measured: fact 21.
- **Q4 [CLOSED by D9]:** Keep the independent-judge rule?
- **Q5 [CLOSED by D10]:** Read-only for a reviewer whose agent has no read-only mode.
- **Q6 [CLOSED by D7]:** No typing into an agent driven one turn per process.
- **Q7 [CLOSED by D8]:** A live proof with pi.

### Working assumptions

- **A1 [ACTIVE]:** The settings hierarchy and names, picked under D11 from how comparable tools do it:

  | today | picked | the precedent |
  |---|---|---|
  | `policy.json`, committed | `settings.json`: shared, committed, what every checkout gets | Claude Code's `.claude/settings.json`, "everyone in the project" |
  | none | `settings.local.json`: yours, ignored by git, written by the Workbench's Settings view; it can override any key | Claude Code's `.claude/settings.local.json`, "you, this project"; `.env.local`; Compose's `compose.override.yaml` |
  | `ORCH_POLICY` | `ORCHESTRA_SETTINGS`: another settings file, for a stack of its own — the demo, the acceptance — taken alone, with no local layer | an application-prefixed variable naming the file it points at: `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `GIT_CONFIG_GLOBAL`, `KUBECONFIG` |
  | `ORCH_REPOS` | `ORCHESTRA_REPOS` | the same prefix, whole |
  | `ORCH_WORKFLOW_UNDER_TEST` | `ORCHESTRA_WORKFLOW_UNDER_TEST` (the suite's own) | the same |
  | `repos.json`, `repos.example.json` | unchanged | `.env` and `.env.example` |

  - **Precedence, lowest first:** the shared `settings.json`, then your `settings.local.json`. Objects
    merge key by key; a value or a list replaces the one below it.
  - With `ORCHESTRA_SETTINGS` set, that one file is all there is.
  - The result is validated as one. It is the policy a run starts with and keeps; `policy.py` and the
    word "policy" keep that meaning.
- **A2 [ACTIVE]:** What the Settings view edits:
  - agents: named profiles — the kind, the model, the effort, extra arguments, and the names of the
    environment variables it reads, never their values;
  - each role's profile, persona and per-stage skills;
  - review rounds per phase, and the default flow.

  A hand edit of `settings.local.json` can override anything else.
- **A3 [ACTIVE]:** The operator's example maps onto the three global skills D19 names, one per stage:
  - the engineer's `plan` → `investigate-change`, and its `build` → `implement-approved-change`;
  - the architect's `research`, `assess` and `verify` → `architect`.

  This mapping is for the acceptance evidence only. The shared `settings.json` binds no skill.
- **A4 [ACTIVE]:** A persona is edited as a local text that overrides the shipped file, with a way back
  to the shipped one. The view marks an override that differs from the shipped text.
- **A5 [ACTIVE]:** A skill is stored by its name, and each kind of agent renders its invocation.
  - Claude: `/name`, as measured.
  - Codex: `$name`, the form OpenAI documents. `/name` was measured to work too (fact 21).
  - A kind with no skills says so in the view. A value written as `/name` stays valid.
- **A6 [ACTIVE]:** An Apply reaches runs started after it. An open run keeps the policy it started with.
- **A7 [ACTIVE]:** Kinds of agent are code, one adapter module each, behind one contract.
  - Every kind runs its agent interactively in the role's live terminal, where the operator can type
    (D7).
  - Each kind brings its own signal that a turn ended, and its own read-only mode (D10).
  - The first two kinds are `claude-code` and `codex`: today's integrations, moved behind the contract.
  - Agent profiles, and which profile a role uses, are configuration.
- **A8 [ACTIVE]:** The contract's openness is proven in the suite by a third, test-only kind: a fake
  agent with a turn-end signal of its own, run through the real terminal and typed into, whose adapter
  is its only code. pi follows later (D8).
- **A9 [REJECTED by D7]:** An agent driven one turn per process shows its turn live, but takes no
  typing mid-turn.

## Not in this change

Any of these can follow as a change of its own:

- a pi adapter (D8);
- editing a flow's steps in the page — flows stay files, and the view chooses the default among them;
- the stack's settings in the view: targets, hosts, ports, queues, timeouts. A hand edit of
  `settings.local.json` can still set them; they take effect at the stack's next start;
- a global "skip approvals" — the Start form's per-run choice stays;
- a list of models to choose from (D18: no model registry);
- settings per repository or per run;
- finding out which skills each host has installed;
- renaming `policy.py`, or the word "policy" for the policy a run carries.

## Verified evidence

**Verified facts**

1. **The shipped `policy.json`** binds the engineer to `claude` with no model, and the architect to
   `codex` with a pinned model and `reasoning_effort: high`. It sets `max_rounds` to plan 2 and build 2,
   `default_flow` to `engineer-code`, and binds no `stage_skills`.
2. **The validator** (`app/foundation/policy.py:153-264`):
   - brains must be `KNOWN_BRAINS` (`:28`);
   - the two roles' `(brain, model)` must differ (`:185-196`);
   - the architect must be read-only and the engineer able to write (`:197-200`);
   - each `stage_skills` value must start with `/` (`:157-167`).
3. **A run keeps the policy it started with.**
   - `client.start` loads it at each start and puts it in the start input
     (`app/application/client.py:198-217`).
   - The workflow keeps it (`app/orchestration/workflow.py:108`) and hands it to every role-run
     (`app/application/activities.py:217`).
4. **A persona is read when its session is born** (`app/agents/nodes.py:241-266`).
5. **A bound skill must lead the prompt.** It opens the prompt's first characters at a session's or a
   stage's first turn (`nodes.py:255-262`). A trailing `/name` was measured inert.
6. **The shipped policy binds no skill.** `tests/orchestration/test_workflow.py:319` asserts it, and the
   suite's own policy binds the three global skills (`tests/temporal_env.py:36-39`).
7. **The README's route for your own skills is `ORCH_POLICY`** (`README.md:159-163`).
8. **A policy other than the checkout's own is another stack.** It manages only its WSL worker
   (`app/application/stack.py:54-62`; D32), and its workers get `ORCH_POLICY` (`stack.py:93-97`).
9. **Where a host has `ORCH_POLICY`, an edit fails open runs.** Each role-run refuses unless the host's
   file says what the run's policy says (`policy.py:97-99, 138-150`; `activities.py:240-243`).
10. **The live stack's workers run without `ORCH_POLICY`** (`stack.py:93-97`).
11. **The Workbench reads the policy afresh.** It reads the default flow at each request
    (`app/interfaces/workbench/server.py:198`), and starts runs through `client.start`.
12. **The decisions this touches** ([the architecture](../docs/architecture/structure.md)):
    - D3: the judge is never the builder, and the architect is read-only;
    - D13: the set of brains that can be bound is code;
    - D17: a role's turn runs in its live terminal;
    - D18: no model registry;
    - D19: the global skills lead each stage through `stage_skills`;
    - D29: the page's writes.
13. **Installed CLIs:** Codex `0.155.1` on WSL and `0.153.4` on Windows; Claude Code `2.1.276` on WSL
    and `2.1.282` on Windows.
14. **Installed skills,** by folder name only:
    - `~/.claude/skills` and `~/.codex/skills` hold `architect`, `investigate-change` and
      `implement-approved-change`, on both hosts.
    - `~/.agents/skills` is empty on both.
15. **How OpenAI documents Codex skills**
    ([build skills](https://learn.chatgpt.com/docs/build-skills)): invoked by mentioning
    `$skill-name`.
16. **The page shows no agent, model or skill today.**
17. **`.gitignore` ignores `repos.json`** — "yours".
18. **Where the code names an agent today.** Agent-specific branches sit in seven modules:
    - the bindable list: `policy.KNOWN_BRAINS`;
    - launch flags, sessions and failures: `nodes.build_argv`, `extract_session` and
      `classify_failure`;
    - host differences: `activities.host_argv`;
    - turn-end wiring and detection: `terminal.claude_hooks`, `codex_notify` and `completion`, with
      `run_turn` refusing any agent outside the list (`terminal.py:327-392`);
    - the hook script: `turn_hook.py`;
    - trust records: `trust.ensure` and `forget`;
    - tracing: `telemetry.py`.
19. **pi** runs interactively, in print mode, as JSON or over RPC, and its RPC mode says when a turn
    ends ([pi's RPC document](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/rpc.md)).
    It is not installed on either host.
20. **A review turn that changes the worktree already fails its step** (`activities.py:253-256`).
21. **Measured: Codex loads a skill named at a prompt's start, in either form, on both hosts.**
    - Method: one `codex exec` turn each, with a read-only sandbox and three prompts:
      - one starting `$architect`;
      - one starting `/architect`;
      - one naming no skill.

      Each asked the model to quote the first sentence of a loaded skill's body, or to say
      `NO SKILL LOADED`.
    - Result, the same on 0.155.1 (WSL) and 0.153.4 (Windows):
      - both forms quoted the `architect` skill's first sentence verbatim, read from `~/.codex/skills`;
      - the prompt naming none answered `NO SKILL LOADED`.
22. **The rename's reach, beyond finished todos, which keep their history:**
    - `policy.json`: 18 files, 47 lines;
    - `ORCH_POLICY`: 15 files, 48 lines;
    - `ORCH_REPOS`: 4 files;
    - `ORCH_WORKFLOW_UNDER_TEST`: 2 files.
23. **How comparable tools layer their settings:**
    - Claude Code, highest first: managed; the command line; `.claude/settings.local.json` — "you, this
      project", kept out of git; `.claude/settings.json` — shared; `~/.claude/settings.json`. It is
      relocated by `CLAUDE_CONFIG_DIR` ([its settings page](https://code.claude.com/docs/en/settings)).
    - Compose merges `compose.override.yaml` over `compose.yaml`
      ([its merge page](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/)).
    - `.env.local` overrides `.env`, and is the one kept out of git.

**Inferences**

- **I1 — Codex-run stages can take a skill already** (fact 21). The validator's `/` form works on both
  CLIs. Still to confirm: the same in Codex's interactive mode, which a role's turn uses (U1).
- **I2 — A third agent costs edits across the code.** Today it means editing all seven places in fact 18.
- **I3 — The `ORCH_POLICY` route degrades the live deployment** (facts 8–9).

**Assumptions / unverified areas**

- **U1:** Codex's interactive mode, which a role's turn uses, loads a skill named at its first prompt
  as `codex exec` does. Confirmed in the operator's live check.
- **U2:** what each CLI does when a bound skill is not installed on the host running the stage.
- **U3:** that replacing a file atomically works on the checkout's filesystem as the Workbench reaches
  it — a Windows drive through WSL.

**Refuted**

- "Codex-run stages cannot take a skill today": refuted by fact 21.
- "The set of agents must be code": refuted as a limit on which agents may be bound. The mechanics D13
  names belong to an adapter per kind of agent.
- "Edit the shipped policy from the page": refuted by facts 6 and 7, and the public-repository rule.
- "A policy of your own through `ORCH_POLICY` for the live deployment": refuted by facts 8 and 9.

## Current architecture and source of truth

- **Configuration:** `policy.json`, loaded and validated by `app/foundation/policy.py`, which also
  resolves personas. Every process loads through it.
- **A run's copy:** each run keeps the policy it started with.
- **The execution seam (D17):** a role's turn runs in its live terminal. How each agent is launched,
  resumed, finished, trusted and traced is spread over the seven modules of fact 18, keyed by the
  brain's name.
- **The page's writes:** D29. **The stack:** the checkout's own settings' (D32).

## Problem and capability gap

1. **Binding an agent is fixed.** Only two agents can be bound, and a third costs edits in seven modules
   (I2), against D5.
2. **Nothing shows or edits the setup** (D1).
3. **The settings have no personal layer,** and their one override is a badly named variable that
   degrades the stack (D11, I3).
4. **Two rules go against the operator's decisions:** the independent-judge refusal (D9), and a skill
   syntax fixed for every agent (D5).

## Decision

1. **One adapter contract** in `app/agents/`. An adapter answers, for one turn of its kind of agent:
   - the command that runs it interactively in the role's live terminal — new or resumed session,
     model, effort, extra arguments, this host's differences;
   - its read-only mode, which a read-only role requires;
   - how the end of its turn is signalled, and where the final message and session come from;
   - how a lost session shows;
   - how a skill is invoked, or that it has none;
   - optionally, trust setup and tracing.

   Nothing else in Orchestra names an agent. Roles, stages, flows, the workflow and the page see only
   the contract.
2. **Two adapters:** `claude-code` and `codex` — today's code moved behind the contract, behaving
   exactly as now.
3. **Agent profiles** are named settings: a kind, the model, the effort, extra arguments, and the names
   of the environment variables it reads. Two ship in `settings.json`, matching today's bindings.
4. **Each role binds a profile, its persona and its stages' skills.**
   - Access stays per role: the engineer writes, the architect reads (D10). A profile whose kind has no
     read-only mode cannot take the architect.
   - Which model each role runs is free (D9). The view shows both roles side by side.
5. **The settings hierarchy and names of A1:**
   - the loader applies `settings.local.json` over `settings.json`, or takes `ORCHESTRA_SETTINGS` alone;
   - a writer beside it validates the whole result, refuses a stale Apply, replaces the file
     atomically, and changes nothing when it refuses.
6. **The Settings view** (`#settings`, beside *Worktrees*):
   - **Agents:** profiles — add, edit, remove — each saying how it takes a skill and whether it can
     review.
   - **Roles:** each role's profile, persona and per-stage skills, with each stage's invocation shown.
   - **Interactions:** rounds per phase, and the default flow with its steps.
   - **Applying:** one Apply, a Revert, a refusal said beside its field, and "applies to runs started
     from now on".
7. **Documents amended:**
   - D3: the reviewer is read-only; whether it is another model is the operator's choice;
   - D13: kinds of agent are code, and bindings are configuration;
   - D17: the seam runs through an adapter;
   - D19: a skill is named, and rendered by its kind;
   - D29: a settings change through the policy's owner joins the page's writes;
   - the README and using.md: the new names.

### Premise / KISS gate

**The owner** of an agent's mechanics becomes that agent's adapter: the one place a kind of agent is
known. Everything that names an agent today (fact 18) goes through it.

**It adds:**

- the contract;
- agent profiles;
- the local layer;
- two endpoints;
- one page module.

**It removes:**

- seven modules' agent branches;
- the fixed list of bindable agents;
- the one skill syntax;
- the independent-judge refusal;
- the `ORCH_*` names.

**It knowingly gives up:** a new kind of agent still needs one adapter module, because each CLI signals
a turn's end and runs read-only in its own way, and typing needs its interactive mode (D7).

### Alternatives considered

- **Keep two agents, with a settings page over them.** Fails D5; it was this todo's first version.
- **Drive agents one turn per process, to need no module per kind.** It cannot take typing, so it fails
  D7.
- **A plugin system that loads code from outside the repository.** More moving parts, and trust in code
  not reviewed here. An adapter is a module in `app/agents/`.
- **Keep `ORCH_POLICY` for personal settings.** It fails D11, and degrades the stack (facts 8–9).

## Required invariants

1. **Claude and Codex behave exactly as today** behind the contract: the suite, `make demo`, and the
   recorded histories replay (D25).
2. **A run started before the change completes** on the policy it started with: the role-run accepts
   the old shape, with the brain and model written inline. A persona still resolves from where that
   policy was read, whatever its file is called now.
3. **No module outside the adapters names an agent** — a guard in `test_architecture.py`.
4. **Every agent's terminal takes typing (D7),** and the reviewing role is read-only, through its
   agent's own mode and the step's failure on a changed tree (D10).
5. **One loader and one validator** for the page, the command line and both workers. A refusal in the
   view is the validator's own reason.
6. **An Apply never changes an open run.** The stack stays the checkout's own (D32), and
   `ORCHESTRA_SETTINGS` takes no local layer.
7. **The suite never reads the operator's `settings.local.json`,** and the shared `settings.json` binds
   no skill.
8. **Writes are atomic and checked.** A refused or stale Apply leaves the file as it was, and a local
   file that does not validate stops the loader with its name and reason.
9. **Settings hold names, never secrets.** Keys stay in `.env`.
10. **No `ORCH_*` name, and no `policy.json`, is left** in code, configuration or current documents.
    Finished todos keep theirs as history.
11. **D18 still holds:** no model registry; an empty model is the provider's default, shown as such.
12. **D29:** the page holds no run state, and a settings change goes through the policy's owner,
    under the page's token and origin checks.

## Implementation tasks

0. [x] Q1–Q7 answered (D5–D11). Codex's skills measured (fact 21).
1. [ ] Red guards, each observed failing first (Test-first and verification plan).
2. [ ] The rename (A1): `settings.json`, and the `ORCHESTRA_*` variables. Mechanical, with the suite and
   `make demo` green after it.
3. [ ] The adapter contract, with `claude-code` and `codex` moved behind it and behaviour unchanged. The
   suite and `make demo` stay green at every step.
4. [ ] Profiles and role bindings in the policy:
   - their validation: read-only for the architect's kind, and no independent-judge refusal;
   - the old shape still accepted;
   - skills by name, rendered by the kind.
5. [ ] The local layer: the loader, the writer, the `.gitignore` entry, and the suite's isolation.
6. [ ] The settings API and the Settings view — `frontend-design`, with each field saying what it
   changes and when.
7. [ ] Documentation (Documentation plan).
8. [ ] Verification matrix:
   - `web-design-review`;
   - one agent review round, fixed without further agents;
   - the external review;
   - the whole suite once per host;
   - the operator's live check, including U1.

## Test-first and verification plan

### Red evidence

- **Acceptance evidence:**
  - Today, a role given any agent but `claude` or `codex` is refused at load, and `run_turn` refuses it
    (`terminal.py:390-391`).
  - After the change:
    - the view binds either profile to either role, and the same model to both;
    - a run started after the Apply shows the chosen agent in each role's live terminal;
    - the operator can type into both terminals.
- **Permanent regression guards,** each written and run failing before any production code:
  1. **No agent named outside the adapters** (`test_architecture.py`). Red today in seven modules.
     Control: a name planted outside them.
  2. **A new kind is one module** (`agents/test_terminal.py`). A test-only kind:
     - runs a fake agent interactively through the real terminal;
     - takes typed keys;
     - ends its turn on its own signal;
     - resumes its session on the next turn.

     Control: a kind without a turn-end signal, which times out as today.
  3. **Any profile under any role** (`orchestration/test_workflow.py`, over the fake seams):
     - both roles on one profile plan, review and build (D9);
     - the architect on a kind with no read-only mode is refused (D10).

     Control: the old shape of the policy, still accepted.
  4. **The layers** (`foundation/test_policy.py`):
     - `settings.local.json` merges over `settings.json`, objects by key and lists replaced, and is
       validated whole;
     - `ORCHESTRA_SETTINGS` is taken alone;
     - the suite never sees the local file.

     Control: the local file applied to every policy.
  5. **The writer, the API and a skill's invocation per kind:**
     - a refused or stale Apply changes nothing;
     - no token, no write;
     - `/name` for Claude, `$name` for Codex, none for a kind without skills.
- **Reviewer-checked judgements:**
  - the view's words;
  - that nothing in it reads as a model registry;
  - that a profile's environment holds names only;
  - that no `ORCH_*` or `policy.json` is left where invariant 10 says, checked by one scripted search
    at the end rather than a permanent test.

### Green evidence

- The same guards green, and the whole existing suite green at every step of tasks 2 and 3.
- `make demo` passes whole.
- `make public-check` and `git diff --check` are clean.
- Browser probes of the view.
- The whole suite once per host, after the external PASS.
- The operator's live check:
  - skills bound in the view reach a real turn, for Claude and for Codex (U1);
  - either agent is swapped under either role;
  - both terminals take typing.

## Documentation plan

- **Authoritative stable owners:**
  - [the architecture](../docs/architecture/structure.md): D3, D13, D17, D19 and D29, as in the
    Decision;
  - [the agents' structure](../app/agents/docs/architecture/structure.md): the adapter contract, and
    how to add a kind of agent;
  - [the foundation's structure](../app/foundation/docs/architecture/structure.md): the settings'
    layers and names;
  - [docs/using.md](../docs/using.md): the Settings view, and the new names;
  - [README.md](../README.md): the configuration table — `settings.json`, `settings.local.json`,
    `ORCHESTRA_SETTINGS` — and the skills route, now the Settings view.
- **Duplication avoided:** the schemas are the validator's; documents name them rather than list them.
- Stable docs, code, comments, tests and configuration will not reference this todo.

## Rollout and rollback

- **The rename:** the stack's scripts, the Makefile, the systemd unit and the demo change with the code,
  so a stack restarted on the new checkout finds its settings. A shell that still exports `ORCH_POLICY`
  is ignored, and the checkout's own settings are used.
- **Open runs** keep working through the change (invariant 2).
- **Rollback of personal settings:** delete `settings.local.json`. A rollback of the code is a revert;
  open runs survive it because the old shape stays readable.

## Completion criteria

- Every guard observed red, then green, and the existing suite green throughout.
- `make demo`, `make public-check` and `git diff --check` pass. The whole suite passes on each host
  after the external PASS.
- The operator's live check passes, U1 included.
- The documentation plan is done, with nothing unrelated in the diff.

## Review record

### 2026-09-27 — opened

- **Trigger:** "how to better understand and edit our agents binding (codex and claude for now) per role
  … in some convenient ui place that global … check carefully".
- **Authority:** D1–D4 recorded; Q1–Q3 opened.

### 2026-09-27 — the operator's redirect

- **Trigger:** "our goal flexible change any agent system under every role … all should be flexible as
  possible without coupling".
- **Root cause:** the first version took D13's fixed set of agents as given.
- **Fix:** the design rewritten around an adapter per kind of agent, with profiles bound to roles.
- **Authority:** D5 added; Q2 closed by D5; Q4–Q7 opened.

### 2026-09-27 — the operator's answers

- **Trigger:** the operator answered Q1 and Q3–Q7.
- **Measured:** Codex loads a skill named at a prompt's start in either form, on both hosts (fact 21),
  which refuted I1's earlier form.
- **Fix:**
  - The generic one-turn adapter dropped: it cannot take typing (D7).
  - The independent-judge refusal removed (D9).
  - The settings named and layered by common practice (A1).
- **Authority:**
  - D6–D11 added.
  - Q1 closed by D11, Q3 by D6, Q4 by D9, Q5 by D10, Q6 by D7, Q7 by D8.
  - A1, A2, A5, A7 and A8 rewritten in place; A9 rejected by D7.
