# Pluggable agents under every role, set up in the Workbench

**Status:** REVIEW REQUIRED
**Scope:**
- `app/agents/adapters/`: one generic loader and contract, and a module per kind of agent;
- the modules that hold agent mechanics today: `nodes.py`, `terminal.py`, `turn_hook.py`, `trust.py`,
  `activities.py`, `telemetry.py`, `policy.py`;
- the settings, moved into `.orchestra/` and layered;
- the run's policy, made whole at its start;
- the Workbench's settings API and view.

**Stable documentation owner:**
- [the architecture's D3, D13, D17, D19 and D29](../docs/architecture/structure.md);
- [the agents' structure](../app/agents/docs/architecture/structure.md), for the adapters;
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
Workbench, and nothing else in Orchestra holds any agent's mechanics: today Claude Code and Codex, and
others later.

Every agent runs in its role's live terminal, which the operator can watch and type into.

The same place sets:

- each role's persona;
- the skill that leads each stage;
- how the roles interact: review rounds per phase, and the default flow.

Settings follow a conventional hierarchy of shared and personal files. They are saved when applied,
reach only runs started afterwards, and keep personal ones out of the public repository.

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
  - Effect: any agent can run under any role, chosen by configuration; no code outside an agent's own
    adapter holds its mechanics or branches on it.
  - Reason: flexibility; today's agents are not the last ones.
  - Date/source: operator, 2026-09-27.
- **D6** Codex runs on the operator's CLI subscription, as Claude does — "why codex pay call? we use
  cli subscription like claude".
  - Effect: a measuring turn of either CLI is not a separately billed API call. It uses the plan's
    allowance, and needs no special approval.
  - Reason: stated.
  - Date/source: operator, 2026-09-27.
- **D7** Every agent's terminal takes typing — "we implemented live terminals — that the full point of
  bench".
  - Effect: every kind of agent runs interactively in its role's live terminal. An agent driven one
    turn per process is not a way to add one.
  - Reason: stated.
  - Date/source: operator, 2026-09-27.
- **D8** pi — "it's future not now".
  - Effect: no pi adapter, install or proof in this change. The design must let a new kind of agent be
    added later as one module.
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
  - Effect: the settings get a conventional hierarchy, and they and every `ORCH_*` variable are named
    by common practice. The pick is delegated to this investigation (A1).
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
  | `policy.json` | `.orchestra/settings.json`: shared, committed, what every checkout gets | a tool's settings in its own folder: `.claude/settings.json`, `.vscode/settings.json` |
  | none | `.orchestra/settings.local.json`: yours, ignored by git, written by the Settings view — a JSON Merge Patch over the shared file | `.claude/settings.local.json`, "you, this project"; `.env.local`; `compose.override.yaml` |
  | `ORCH_POLICY` | `ORCHESTRA_SETTINGS`: one complete settings file, for a stack of its own — the demo, the acceptance — with no patch applied to it | an application-prefixed variable naming what it points at: `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `GIT_CONFIG_GLOBAL` |
  | `repos.json`, `repos.example.json` | `.orchestra/repos.json` (yours, ignored), `.orchestra/repos.example.json` | the same folder, for the similar case D11 names |
  | `ORCH_REPOS`, `ORCH_WORKFLOW_UNDER_TEST` | `ORCHESTRA_REPOS`, `ORCHESTRA_WORKFLOW_UNDER_TEST` (the suite's own) | the same prefix, whole |

  - **The local file is a JSON Merge Patch** (RFC 7396, fact 26): an object merges into the one below
    it member by member; any other value, a list included, replaces; `null` removes the member. A
    profile shipped in the shared file is removed locally by `null`. Reverting a setting removes its
    entry from the patch.
  - **The result is validated as one.** It is the effective settings, and `policy.py` and the word
    "policy" keep that meaning.
  - **Paths are from the checkout's root.** A path inside settings — a persona file, for one — resolves
    from the checkout's root, never from `.orchestra/`.
- **A2 [ACTIVE]:** What the Settings view edits:
  - agents: named profiles — the kind, and the model and effort where the kind takes them;
  - each role's profile, persona and per-stage skills;
  - review rounds per phase, and the default flow.

  A profile has no list of extra arguments or environment variables. They are the vendor mechanics the
  adapter owns, and could undo its read-only mode, its session and its turn-end wiring. A kind that
  needs another setting brings its own named, validated option when it does.
- **A3 [ACTIVE]:** The operator's example maps onto the three global skills D19 names, one per stage:
  - the engineer's `plan` → `investigate-change`, and its `build` → `implement-approved-change`;
  - the architect's `research`, `assess` and `verify` → `architect`.

  This mapping is for the acceptance evidence only. The shared settings bind no skill.
- **A4 [ACTIVE]:** Personas:
  - the shared settings name each role's persona file, `roles/*.md`, which the page never edits;
  - a role's `persona` text, when present, takes the place of its `persona_file`. Otherwise its
    persona is that file's text. The Settings view writes `persona` into the local patch, marks it, and
    Revert removes it, so the file serves again;
  - the persona in effect is at most `MAX_PERSONA_BYTES = 64 * 1024` bytes of UTF-8, a constant of the
    repository's own. That keeps a run's policy far inside what Temporal takes (fact 27), without tying
    correctness to that service's limit.
- **A5 [ACTIVE]:** Skills:
  - settings name a skill and nothing else, by a strict name grammar, never an invocation;
  - each kind renders the invocation: `/name` for Claude, `$name` for Codex;
  - `/name` is read only from a policy of the old shape, which the suite's own policy is today
    (fact 24);
  - where a vendor installs skills is not a setting. A kind whose launch needs that folder owns it
    inside its adapter, as Claude's `--add-dir` does today (fact 25).
- **A6 [ACTIVE]:** An Apply reaches only runs started after it.
  - `client.start` makes the run's policy whole: each role's kind, model, effort, access, persona
    text and stage skills.
  - The run carries that copy, and no worker reads settings or a persona file for it.
  - A policy of the old shape — a brain, a persona file's path — still runs as today.
- **A7 [ACTIVE]:** Adapters live in `app/agents/adapters/`.
  - `__init__.py` holds the contract and a generic loader, and no list of kinds.
  - Each kind is one module, named from the kind by a one-to-one rule: lowercase letters, digits and
    single hyphens, each hyphen an underscore — `claude-code` becomes `claude_code.py`.
  - The loader imports a kind's module, checks it meets the contract, and reads its capabilities: its
    display name, whether it can run read-only, how it takes a skill, and whether model and effort
    apply.
  - The page gets kinds and capabilities from that boundary through the API, never from a list of its
    own.
  - Every kind runs its agent interactively in the role's live terminal (D7), with its own turn-end
    signal, read-only mode, and environment hygiene — the variables a parent session of its own
    leaves, which its agent must not inherit.
  - **A kind validates its own profile.** The generic owner, `policy.py`, validates what every
    profile shares: the names, the `kind` and its grammar, the shape, and the roles' references.
    The loaded adapter validates what it owns: whether `model` and `effort` apply to it, and which
    values it takes. Today's plain-token rule (fact 30) moves into `claude-code` and `codex`, because
    they put those values on a command line; it is not the contract for a kind that does not.
  - **The packages keep their direction** (fact 28).
    - `app/agents`, adapters included, never imports `app/observability`, and `telemetry` never
      branches on a kind.
    - `app/application` loads the adapter, uses it for the agent's mechanics, and hands `telemetry`
      what the adapter provides for tracing — its environment for a tracing plugin, and the records
      of a session to upload — as plain data. `telemetry` records a kind only as data.
    - `turn_hook.py` stays outside the adapters as a sink that knows no vendor. Where a payload comes
      from — stdin or its last argument — becomes a mode the adapter passes, and the adapter alone
      decides how its CLI invokes the sink and which events end a turn.
- **A8 [ACTIVE]:** The contract's openness is proven in the suite by a test-only kind.
  - Its module is handed to the loader for the test, and never shipped.
  - It runs a fake agent interactively through the real terminal, takes typed keys, and ends its turn
    on its own signal.
  - That module is its only code. pi follows later (D8).
- **A9 [REJECTED by D7]:** An agent driven one turn per process shows its turn live, but takes no
  typing mid-turn.

## Not in this change

Any of these can follow as a change of its own:

- a pi adapter (D8);
- editing a flow's steps in the page — flows stay files, and the view chooses the default among them;
- the stack's settings in the view: targets, hosts, ports, queues, timeouts. A hand edit of the local
  patch can still set them; they take effect at the stack's next start;
- a global "skip approvals" — the Start form's per-run choice stays;
- a list of models to choose from (D18: no model registry);
- settings per repository or per run — `.orchestra/` in a target repository is where they would live;
- editing repositories in the Settings view — `.orchestra/repos.json` moves, and stays a file edited by
  hand;
- finding out which skills each host has installed;
- removing the persona-path resolver kept for old runs (`prompt_path`, and the copy check behind it),
  once no run of the old shape is open;
- renaming `policy.py`, or the word "policy".

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
4. **A run's persona is read later, not at its start.** It is read when the role's session is born
   (`app/agents/nodes.py:241-266`), through the persona file's path, resolved at that role-run
   (`activities.py:240-243`).

   So an edit made after a run started reaches any of its roles whose session had not yet begun.
5. **A bound skill must lead the prompt.** It opens the prompt's first characters at a session's or a
   stage's first turn (`nodes.py:255-262`). A trailing `/name` was measured inert.
6. **The shipped policy binds no skill.** `tests/orchestration/test_workflow.py:319` asserts it, and the
   suite's own policy binds the three global skills (`tests/temporal_env.py:36-39`).
7. **The README's route for your own skills is `ORCH_POLICY`** (`README.md:159-163`).
8. **A policy other than the checkout's own is another stack.** It manages only its WSL worker
   (`app/application/stack.py:54-62`; D32), and its workers get `ORCH_POLICY` (`stack.py:93-97`).
9. **Where a host has `ORCH_POLICY`, an edit fails open runs.** Each role-run refuses unless the host's
   file says what the run's policy says (`policy.py:97-99, 138-150`).
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
    `$skill-name`; user skills in `~/.agents/skills`.
16. **The page shows no agent, model or skill today.**
17. **`.gitignore` ignores `repos.json`** — "yours".
18. **Where agent mechanics sit today.** Agent-specific branches are spread over eight places:
    - the bindable list: `policy.KNOWN_BRAINS`;
    - launch flags, sessions and failures: `nodes.build_argv`, `extract_session` and
      `classify_failure`;
    - host differences: `activities.host_argv`;
    - the parent-session variables stripped from an agent's environment: `activities.agent_env`
      (`activities.py:51-52, 85`);
    - turn-end wiring and detection: `terminal.claude_hooks`, `codex_notify` and `completion`, with
      `run_turn` refusing any agent outside the list (`terminal.py:327-392`);
    - the hook script: `turn_hook.py`;
    - trust records: `trust.ensure` and `forget`;
    - tracing: `telemetry.py`.

    `telemetry.py:447` also records a role's brain as plain data.
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
      - both forms quoted the `architect` skill's first sentence verbatim;
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
24. **Only the suite's own policy binds a skill.** `stage_skills` appears in no policy but
    `tests/temporal_env.py`'s, and `git log -S stage_skills -- policy.json` finds none in its history.
    So no run started on the checkout's own policy carried a `/name`; a hand-made `ORCH_POLICY` file is
    the only way one could have.
25. **Claude reads a skill's references from its skills folder.** `activities.host_argv` adds that
    folder with `--add-dir`, so the references, outside the worktree, can be read without approval
    (`activities.py:70-80`).
26. **JSON Merge Patch** ([RFC 7396](https://www.rfc-editor.org/rfc/rfc7396)): a patch's object members
    merge recursively, `null` removes the member, and any other value replaces it.
27. **Temporal refuses a payload past its own limit** (D29). Today's persona files are 28 and 31 lines.
28. **The packages' direction today.** `app/agents` and `app/observability` import nothing of each other;
    `app/application` imports both (`activities.py:20-28`).
29. **The turn hook names its vendors.**
    - `turn_hook.py` records whatever payload a vendor's hook hands it. It reads that payload from its
      last argument when its label is `notify` — Codex's word — and from stdin otherwise, as Claude's
      hooks send it (`app/agents/turn_hook.py:17`).
    - Its docstring names both.
    - It is launched by path and imports nothing of ours (`app/agents/README.md`).
30. **Model and effort share one rule today:** a plain token, because both reach a command line
    (`policy.py:32-33, 181-184`).
31. **The standing test rule.** An iteration runs only the modules it touches, named; the whole suite runs
    once, after the reviewer's final pass, before the operator's live check ([tests/README.md](../tests/README.md)).

**Inferences**

- **I1 — Codex-run stages can take a skill already** (fact 21), in the exec form.
- **I2 — A third agent costs edits across the code.** Today it means editing all eight places in fact 18.
- **I3 — The `ORCH_POLICY` route degrades the live deployment** (facts 8–9).
- **I4 — "An Apply reaches only new runs" is false for personas today** (fact 4). It holds only once a
  run's policy carries each persona's text from its start.

**Assumptions / unverified areas**

- **U1:** whether Codex's interactive mode — the one a role's turn uses — loads a skill named at its
  first prompt as `codex exec` does. Measured only through `codex exec` (fact 21); unverified until the
  operator's live check of a real Codex role-turn.
- **U2:** what each CLI does when a bound skill is not installed on the host running the stage.
- **U3:** that replacing a file atomically works on the checkout's filesystem as the Workbench reaches
  it — a Windows drive through WSL.

**Refuted**

- "Codex-run stages cannot take a skill today": refuted by fact 21.
- "The set of agents must be code": refuted as a limit on which agents may be bound. The mechanics D13
  names belong to an adapter per kind of agent.
- "Edit the shipped policy from the page": refuted by facts 6 and 7, and the public-repository rule.
- "A policy of your own through `ORCH_POLICY` for the live deployment": refuted by facts 8 and 9.
- "An Apply leaves open runs alone, with personas read lazily": refuted by fact 4 (I4).

## Current architecture and source of truth

- **Configuration:** `policy.json`, loaded and validated by `app/foundation/policy.py`, which also
  resolves personas. Every process loads through it.
- **A run's copy:** each run keeps the policy it started with, except for persona text, which is read
  from its file when a role's session is born (fact 4).
- **The execution seam (D17):** a role's turn runs in its live terminal. How each agent is launched,
  resumed, finished, trusted, traced and given its environment is spread over eight places, keyed by
  the brain's name (fact 18).
- **The page's writes:** D29. **The stack:** the checkout's own settings' (D32).

## Problem and capability gap

1. **Binding an agent is fixed.** Only two agents can be bound, and a third costs edits in eight places
   (I2), against D5.
2. **Nothing shows or edits the setup** (D1).
3. **The settings have no personal layer,** and their one override is a badly named variable that
   degrades the stack (D11, I3).
4. **A run's personas can change after it starts** (I4).
5. **Two rules go against the operator's decisions:** the independent-judge refusal (D9), and a skill
   syntax fixed for every agent (D5).

## Decision

1. **Adapters** (A7) in `app/agents/adapters/`:
   - a contract and a generic loader, and one module per kind;
   - `claude-code` and `codex` are today's code moved behind the contract, behaving exactly as now.

   An adapter answers, for one turn of its kind of agent:
   - the command that runs it interactively in the role's live terminal — new or resumed session,
     model, effort, and this host's differences;
   - its read-only mode;
   - its environment hygiene;
   - how the end of its turn is signalled, and where its final message and session come from;
   - how a lost session shows;
   - how a skill is invoked, or that it has none;
   - optionally, trust setup and tracing;
   - its capabilities, for the page.
2. **The settings' shape.** In `.orchestra/settings.json`, and the local patch over it:
   - `agents`: a profile's name maps to its `kind` and, where the kind takes them, `model` and `effort`.
     Two ship, matching today's bindings.
   - `roles`: each role's `agent` — a profile's name — its `workspace_access`, its `persona_file`, and,
     when given, its `persona` text, which takes the file's place (A4).
   - `stage_skills`: a stage maps to a skill's name (A5).
   - Everything else as today: rounds, the default flow, and the stack's keys.
3. **The run's policy, made whole at its start (A6).**
   - `client.start` resolves each role to its kind, model, effort, access and persona text, and each
     stage's skill to its name, and hands the run that copy.
   - The persona text is `persona` when present, else `persona_file`'s text, checked against
     `MAX_PERSONA_BYTES` there.
   - No later Apply, and no later edit to a persona file, changes that run.

   A role-run reads the old shape as well:
   - a `brain` of `claude` is the `claude-code` kind;
   - a persona file's path resolves as today;
   - a `/name` skill is the skill `name`.
4. **Access and choice.** Access stays per role: the engineer writes, the architect reads (D10). A
   profile whose kind cannot run read-only cannot take the architect. Which model each role runs is
   free (D9), and the view shows both roles side by side.
5. **The layers of A1.**
   - The loader reads the shared file, applies the local patch, and validates the result; or it takes
     `ORCHESTRA_SETTINGS` alone.
   - A writer beside it:
     - edits the existing local patch only at the paths of the settings submitted, never rebuilding it
       from the effective settings. So:
       - a member the view does not show — a hand-written target or timeout — survives an Apply;
       - an unchanged shared value is never copied into the patch, where it would hide a later shared
         change;
       - a submitted value equal to what lies below removes its member, rather than keeping a copy;
       - removing a shipped member writes RFC 7396's `null`;
       - Revert removes only that setting's member, pruning objects it leaves empty;
       - a patch left empty removes the file;
     - validates the whole result;
     - refuses an Apply made against a revision of either file other than the current one;
     - replaces the local patch atomically;
     - changes nothing when it refuses.
6. **The Settings view** (`#settings`, beside *Worktrees*):
   - **Agents:** profiles — add, edit, and remove, including one shipped below — each with its kind's
     capabilities: whether it can review, how it takes a skill, whether model and effort apply.
   - **Roles:** each role's profile, persona and per-stage skills, with each stage's invocation shown.
   - **Interactions:** rounds per phase, and the default flow with its steps.
   - **Applying:** one Apply, a Revert per setting, a refusal said beside its field, and "applies to
     runs started from now on".
7. **Documents amended:**
   - D3: the reviewer is read-only; whether it is another model is the operator's choice;
   - D13: kinds of agent are code, one module each, and which agent a role runs is configuration;
   - D17: the seam runs through an adapter;
   - D18: model and effort stay configuration, and no registry. Their accepted values are their kind's
     adapter's to check;
   - D19: a skill is named, and rendered by its kind;
   - D29: a settings change through the policy's owner joins the page's writes;
   - the README and using.md: `.orchestra/` and the new names.

### Premise / KISS gate

**The owner** of an agent's mechanics becomes that agent's adapter, and the owner of a run's policy
stays `client.start`, which now makes it whole.

**It adds:**

- one adapter package, with its contract and loader;
- agent profiles;
- the merge patch;
- two endpoints;
- one page module.

**It removes:**

- eight places' agent branches;
- the fixed list of bindable agents;
- one skill syntax for every agent;
- the independent-judge refusal;
- a persona read long after a run started;
- the `ORCH_*` names.

**It knowingly gives up:** a new kind of agent still needs one adapter module, because each CLI signals
a turn's end and runs read-only in its own way, and typing needs its interactive mode (D7). A setting a
kind does not declare cannot be passed to it.

### Alternatives considered

- **Keep two agents, with a settings page over them.** Fails D5.
- **Drive agents one turn per process, needing no module per kind.** It cannot take typing, so it fails
  D7.
- **A central list of kinds.** One more place to edit for every kind.
- **A plugin system that loads code from outside the repository.** More moving parts, and trust in code
  not reviewed here.
- **Extra arguments and environment variables per profile.** They would break the adapter's read-only,
  session and turn-end guarantees (A2).
- **A merge that cannot remove.** It cannot take a shipped profile away (fact 26).
- **Keep `ORCH_POLICY` for personal settings.** It fails D11, and degrades the stack (facts 8–9).

## Required invariants

1. **Claude and Codex behave exactly as today** behind their adapters: the suite, `make demo`, and the
   recorded histories replay (D25).
2. **Old runs keep running.** A run started before the change completes on the policy of the shape it
   started with (Decision 3).
3. **Agent mechanics live only in the adapters.** No production module outside `app/agents/adapters/`
   contains agent-specific mechanics or branches — `turn_hook.py` and `telemetry.py` included. A kind
   may travel elsewhere only as opaque data — for settings, the page, telemetry — and the page learns
   kinds and capabilities from the adapter boundary. A guard in `test_architecture.py` enforces it.
3a. **The packages keep their direction.** `app/agents` never imports `app/observability`;
    `app/application` joins them, handing on the adapter's tracing data (A7). The existing boundary
    check in `test_architecture.py` stays green.
3b. **A kind owns its profile's values.** The generic validator checks shape and references, and the
    kind's adapter checks whether `model` and `effort` apply and which values they take.
4. **Every agent's terminal takes typing (D7),** and the reviewing role is read-only, through its kind's
   own mode and the step's failure on a changed tree (D10).
5. **One loader and one validator** for the page, the command line and both workers. A refusal in the
   view is the validator's own reason, about the effective settings.
6. **An Apply reaches only runs started after it.**
   - A run's policy is whole from its start, persona text included, so no Apply and no edit to a
     persona file changes an open run.
   - The stack stays the checkout's own (D32), and `ORCHESTRA_SETTINGS` takes no patch.
7. **The suite never reads the operator's local patch,** and the shared settings bind no skill.
8. **Writes are atomic, checked and sparse.**
   - A refused Apply, or one against a stale revision of either file, leaves both as they were.
   - An Apply changes the local patch only at the settings it carries: every other member survives, and
     no unchanged shared value is copied in.
   - A patch whose result does not validate stops the loader with the file's name and the reason.
9. **Settings hold names, never mechanics or secrets.** A skill is a name; a profile has no raw
   arguments or environment; keys stay in `.env`.
10. **A persona is at most `MAX_PERSONA_BYTES = 64 * 1024` bytes of UTF-8.** The bound is measured on
    the persona in effect — `persona` when present, else `persona_file`'s text — and refused, naming
    the role, one byte past it.
11. **No `ORCH_*` name, and no root `policy.json` or `repos.json`, is left** in code, configuration or
    current documents. Finished todos keep theirs as history.
12. **D18 still holds:** no model registry; an empty model is the provider's default, shown as such.
13. **D29:** the page holds no run state, and a settings change goes through the policy's owner, under
    the page's token and origin checks.

## Implementation tasks

0. [x] Q1–Q7 answered (D5–D11). Codex's skills measured (fact 21).
1. [ ] Red guards, each observed failing first (Test-first and verification plan).
2. [ ] The move and the rename (A1): `.orchestra/`, and the `ORCHESTRA_*` variables. Mechanical, checked
   by the tests of the modules it touches.
3. [ ] The adapter package: the contract, the loader, and `claude-code` and `codex` moved behind them,
   behaviour unchanged. That includes:
   - `turn_hook.py` made a vendor-blind sink;
   - `telemetry` given the adapter's tracing data by the application, and branching on no kind.

   Checked by the touched concerns' tests — the agents', the application's, observability's — and by
   the recorded histories' replay.
4. [ ] The settings' new shape, and the run's policy made whole at `client.start`:
   - validation: the generic shape, and each kind's own values through its adapter; read-only for the
     architect's kind; no independent-judge refusal; skill names; `MAX_PERSONA_BYTES`;
   - the old shape still read by role-runs, with the replay of recorded histories.
5. [ ] The merge patch: the loader, the sparse writer, the `.gitignore` entries, and the suite's
   isolation.
6. [ ] The settings API — kinds and capabilities from the adapter boundary — and the Settings view,
   through `frontend-design`, with each field saying what it changes and when.
7. [ ] Documentation (Documentation plan).
8. [ ] Verification, in the standing order (fact 31):
   - tasks 2–6 each iterate on the tests of the concerns they touch, named, with the replay of recorded
     histories wherever a run's policy is read, and focused browser probes for the view;
   - `make demo` once, on the finished implementation;
   - `web-design-review`;
   - one agent review round, fixed without further agents;
   - the external review;
   - after its PASS, the whole suite once on WSL and once on Windows;
   - the operator's live check, including U1.

## Test-first and verification plan

### Red evidence

- **Acceptance evidence:**
  - Today:
    - a role given any agent but `claude` or `codex` is refused at load, and `run_turn` refuses it
      (`terminal.py:390-391`);
    - a persona edited after a run started reaches that run's later sessions (fact 4).
  - After the change:
    - the view binds either profile to either role, the same model to both, and removes a shipped
      profile;
    - a run started after the Apply shows the chosen agent in each role's live terminal, and both take
      typing;
    - an Apply made while a run is open leaves that run as it started.
- **Permanent regression guards,** each written and run failing before any production code:
  1. **Mechanics only in the adapters** (`test_architecture.py`). Red today in eight places, the turn
     hook and telemetry among them. Control: a kind's branch planted outside the package.
  2. **A new kind is one module** (`agents/test_terminal.py`). A test-only kind, handed to the loader:
     - runs a fake agent interactively through the real terminal;
     - takes typed keys;
     - ends its turn on its own signal;
     - resumes its session.

     The loader refuses an unknown kind by name, a name outside the grammar, and a module that lacks
     part of the contract, saying what. Controls: a kind without a turn-end signal, which times out as
     today; and a module missing its read-only mode, refused for the architect.
  3. **A run keeps its personas** (`orchestration/test_workflow.py`, over the fake seams). The persona
     is changed after a run starts and before its architect's session is born, and the architect still
     receives the text the run started with. Red today (fact 4). Control: the persona read at the
     session, as today.

     The persona in effect:
     - `persona` wins over `persona_file`;
     - one of exactly `MAX_PERSONA_BYTES` is taken;
     - one byte more is refused, naming the role, and bytes of UTF-8 are what is counted — a persona of
       multi-byte characters is refused by its bytes, not its characters.
  4. **Any profile under any role, and the old shape:**
     - both roles on one profile plan, review and build (D9);
     - the architect on a kind with no read-only mode is refused (D10);
     - a policy of the old shape — a brain, a file path, a `/name` skill — runs as before.
  5. **The layers** (`foundation/test_policy.py`):
     - the merge patch — objects merge, lists replace, `null` removes a shipped profile — validated as a
       whole;
     - `ORCHESTRA_SETTINGS` taken alone;
     - the suite never sees the local patch;
     - a path in settings resolves from the checkout's root.
  6. **The writer and the API:**
     - a refused Apply changes nothing, and so does a stale one after a hand edit of either file;
     - a hand-written `targets` or timeout override survives an Apply that changes a role's agent;
     - an Apply changing one setting copies no unrelated shared value into the patch;
     - Revert removes that setting's member alone;
     - removing a shipped profile writes a `null`;
     - removing the last override removes the file;
     - no token, no write;
     - kinds and capabilities come from the adapter boundary;
     - a skill's invocation per kind: `/name` for Claude, `$name` for Codex, none for a kind without
       skills.

     Control: a writer that rebuilds the patch from the effective settings.
  7. **A kind validates its own values** (`foundation/test_policy.py`, with a test-only kind):
     - a kind that takes no effort refuses one;
     - `claude-code` and `codex` refuse a model that is not a plain token;
     - the generic validator takes a value it does not know the meaning of, and leaves it to the kind.

     Control: the plain-token rule kept generic, refusing the test-only kind's own value.
- **Reviewer-checked judgements:**
  - the view's words;
  - that nothing in it reads as a model registry;
  - that no kind is named in the page's own code;
  - that no `ORCH_*` or root `policy.json` / `repos.json` is left where invariant 11 says, checked by one
    scripted search at the end rather than a permanent test.

### Green evidence

- The same guards green, and each task's touched concerns green as it goes (task 8), with the recorded
  histories replaying wherever a run's policy is read.
- Browser probes of the view.
- `make demo` passes whole, once, on the finished implementation.
- `make public-check` and `git diff --check` are clean.
- The whole suite once on WSL and once on Windows, after the external PASS.
- The operator's live check:
  - skills bound in the view reach a real turn, for Claude and for Codex (U1);
  - either agent is swapped under either role;
  - both terminals take typing;
  - an Apply during an open run leaves it as it was.

## Documentation plan

- **Authoritative stable owners:**
  - [the architecture](../docs/architecture/structure.md): D3, D13, D17, D19 and D29, as in the
    Decision;
  - [the agents' structure](../app/agents/docs/architecture/structure.md): the adapter package, its
    contract, its loader and naming rule, a kind's own validation, the turn hook as a sink that knows
    no vendor, and how to add a kind;
  - [the application's structure](../app/application/docs/architecture/structure.md): the adapter's
    tracing data handed to observability, with the packages' direction unchanged;
  - [the foundation's structure](../app/foundation/docs/architecture/structure.md): `.orchestra/`, the
    merge patch and its sparse writer, `MAX_PERSONA_BYTES`, and the run's policy made whole at its
    start;
  - [docs/using.md](../docs/using.md): the Settings view, and the new names;
  - [README.md](../README.md): the configuration table — `.orchestra/settings.json`, the local patch,
    `.orchestra/repos.json`, `ORCHESTRA_SETTINGS` — and the skills route, now the Settings view.
- **Duplication avoided:** the schemas are the validator's, and documents name them rather than list
  them. RFC 7396 is cited, never restated.
- Stable docs, code, comments, tests and configuration will not reference this todo.

## Rollout and rollback

- **The move and the rename:** the stack's scripts, the Makefile, the systemd unit and the demo change
  with the code, so a stack restarted on the new checkout finds its settings.
- **The operator's own `repos.json`:** moved once into `.orchestra/`. A loader that finds none names the
  new place.
- **Open runs** keep working through the change (invariant 2).
- **Rollback of personal settings:** delete `.orchestra/settings.local.json`. A rollback of the code is
  a revert; open runs survive it because the old shape stays readable.

## Completion criteria

- Every guard observed red, then green, and each task's touched concerns green as it goes.
- `make demo`, `make public-check` and `git diff --check` pass on the finished implementation. The whole
  suite passes once on each host after the external PASS, and a failure there is reported as one,
  never counted as a pass.
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
- **Fix:** the design rewritten around an adapter per kind of agent, with profiles bound to roles.
- **Authority:** D5 added; Q2 closed by D5; Q4–Q7 opened.

### 2026-09-27 — the operator's answers

- **Measured:** Codex loads a skill named at a prompt's start in either form, on both hosts (fact 21).
- **Fix:** the one-turn adapter dropped (D7); the independent-judge refusal removed (D9); the settings
  named and layered (A1).
- **Authority:** D6–D11 added; Q1 and Q3–Q7 closed; A9 rejected by D7.

### 2026-09-27 — the external review: PATCH, six findings

- **Accepted:**
  1. The settings moved into `.orchestra/`.
  2. The local file made a JSON Merge Patch, with its stale guard covering both files.
  3. The run's policy made whole at its start, persona text included (I4).
  4. Settings name skills, and a `/name` is read only from the old shape.
  5. A profile's extra arguments and environment variables dropped.
  6. The adapter package, with its loader and naming rule, and no central list. Invariant 3 reworded.

  Also: D6's effect worded as the plan's allowance, not a separate bill, and U1 left unverified until
  the live check.
- **Added here:**
  - fact 18's eighth place (`activities.agent_env`);
  - the bound on a persona's text (fact 27);
  - `repos.json` moved beside the settings, as D11's similar case;
  - the note that a vendor's skills folder stays inside the adapter that needs it (fact 25).
- **Authority:** A1, A2 and A4–A8 rewritten in place. No decision changed.

### 2026-09-27 — the external review: PATCH, five corrections

- **Accepted, each checked against the code:**
  1. **The standing test rule (fact 31).** Iteration runs only the touched concerns, with the histories'
     replay; `make demo` runs once at the end; the whole suite runs once per host after the external
     PASS. Tasks, green evidence and completion criteria had said otherwise.
  2. **The sparse writer.** An Apply edits the patch only at the settings it carries, so hand-written
     and out-of-view members survive and no shared value is copied in. It comes with its controls.
  3. **The persona's exact contract.** `persona` wins over `persona_file`, resolved once at the start,
     and `MAX_PERSONA_BYTES = 64 * 1024` bytes of UTF-8, guarded at the limit and one past it.
  4. **The packages' direction.** `app/agents` and `app/observability` import nothing of each other
     (fact 28). The application hands the adapter's tracing data to telemetry, which branches on no
     kind, and the turn hook becomes a sink that knows no vendor (fact 29).
  5. **A kind validates its own profile values.** The plain-token rule moves into today's two adapters
     (fact 30).
- **Also:** the reviewer accepted `.orchestra/repos.json`, and editing repositories in the view is left
  out.
- **Authority:** A4 and A7 rewritten in place; invariants 3, 3a, 3b, 8 and 10 rewritten. No decision
  changed.
