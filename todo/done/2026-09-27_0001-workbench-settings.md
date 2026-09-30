# Pluggable agents under every role, set up in the Workbench

**Status:** DONE — deterministic Settings gate passed on WSL and Windows; D14 supersedes the
Settings-specific D13 live gate
**Scope:**
- `app/agents/adapters/`: one generic loader and contract, and a module per kind of agent;
- the modules that hold agent mechanics today: `nodes.py`, `terminal.py`, `turn_hook.py`, `trust.py`,
  `activities.py`, `telemetry.py`, `policy.py`, and the agents' preflight, moved out of `repos.py`;
- `app/application/settings.py`: the one place settings are loaded, validated with each kind's own
  checks, and applied;
- the settings, moved into `.orchestra/` and layered, with the public check following them, run by CI
  as it is by hand;
- every `orch` name, spelled `orchestra` (D12);
- the run's policy, made whole at its start;
- the Workbench's settings API and view.

**Stable documentation owner:** the owners in the Documentation plan — above all
[the architecture](../../docs/architecture/structure.md),
[the agents'](../../app/agents/docs/architecture/structure.md),
[the application's](../../app/application/docs/architecture/structure.md) and
[the foundation's](../../app/foundation/docs/architecture/structure.md) structures, and
[docs/using.md](../../docs/using.md) and [README.md](../../README.md) for the operator.

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

D1–D12 below are this change's operator decisions. The architecture's own decisions are cited as
*the architecture's* D-number, or with a link, where the two could be confused (D3).

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
- **D12** "we need proper name orchestra, not some ugly orch".
  - Effect: every name Orchestra gives spells `orchestra` in full — its variables, and also its
    containment's units, its temporary folders and its tools' constants (A1, invariant 11).
  - Reason: stated — the proper name.
  - Date/source: operator, 2026-09-27.
- **D13** Build this change now, and check it live once, at the end — "why I need check now? we need
  fully prepare flow first with our settings and rest that will be prove that workbench will good, and
  then only test live after all syntetic tests pass".
  - Effect: the implementation starts at once. The live check that
    [the Workbench UX todo](../2026-09-25_2334-workbench-ux.md) and
    [the flows todo](../2026-09-25_1458-configurable-flows.md) still hold happens once, after every
    synthetic gate of this change has passed, and covers the flows, the page and Settings together.
  - Reason: stated.
  - Date/source: operator, 2026-09-28, with the external review's PASS and GO.
- **D14** The Settings-to-run contract is accepted through deterministic mocked-agent tests; a live
  agent walkthrough is no longer a completion gate for this Settings change.
  - Effect: D13's live gate is superseded for this todo. The Workbench UX and configurable-flows todos
    retain any live acceptance they independently require. Their results do not decide whether applied
    Settings reach the role-turn seam.
  - Reason: the real Settings API, client, Temporal workflow, activities, role-turn inputs and stops are
    exercised by the deterministic suite on both hosts.
  - Date/source: operator, 2026-09-30.

### Operator gates

- **Q1 [CLOSED by D11]:** Where do applied settings live?
- **Q2 [CLOSED by D5]:** Should the view also edit each role's persona text?
- **Q3 [CLOSED by D6]:** A real Codex turn to measure its skills. Measured: fact 21.
- **Q4 [CLOSED by D9]:** Keep the independent-judge rule?
- **Q5 [CLOSED by D10]:** Read-only for a reviewer whose agent has no read-only mode.
- **Q6 [CLOSED by D7]:** No typing into an agent driven one turn per process.
- **Q7 [CLOSED by D8]:** A live proof with pi.

### Working assumptions

- **A1 [ACTIVE]:** The settings hierarchy and names, picked under D11 and D12 from how comparable tools
  do it:

  | today | picked | the precedent |
  |---|---|---|
  | `policy.json` | `.orchestra/settings.json`: shared, committed, what every checkout gets | a tool's settings in its own folder: `.claude/settings.json`, `.vscode/settings.json` |
  | none | `.orchestra/settings.local.json`: yours, ignored by git, written by the Settings view — a JSON Merge Patch over the shared file | `.claude/settings.local.json`, "you, this project"; `.env.local`; `compose.override.yaml` |
  | `ORCH_POLICY` | `ORCHESTRA_SETTINGS`: one complete settings file, for a stack of its own — the demo, the acceptance — with no patch applied to it | an application-prefixed variable naming what it points at: `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `GIT_CONFIG_GLOBAL` |
  | `repos.json`, `repos.example.json` | `.orchestra/repos.json` (yours, ignored), `.orchestra/repos.example.json` | the same folder, for the similar case D11 names |
  | `ORCH_REPOS`, `ORCH_WORKFLOW_UNDER_TEST` | `ORCHESTRA_REPOS`: one complete descriptor file, taken alone — the demo's, the acceptance's, the suite's; `ORCHESTRA_WORKFLOW_UNDER_TEST` (the suite's own) | the same prefix, whole |
  | `orch-` and `ORCH` elsewhere: the containment's units, temporary folders' prefixes, a constant in two tools (fact 22) | `orchestra-`: `orchestra-<id>` units; `orchestra-trace-`, the private folder a traced turn's keys live in, which names no vendor (A7); `orchestra-index-`; and the tests' and tools' folders. The tools' constant is named for what it holds, the checkout | D12; a unit named for its application, as Docker's `docker-<id>.scope` |
  | the command line's `--policy PATH` | `--settings PATH`: one complete settings file, taken alone, as `ORCHESTRA_SETTINGS` is | the file it names, as the variable does |

  - **The local file is a JSON Merge Patch** (RFC 7396, fact 26): an object merges into the one below
    it member by member; any other value, a list included, replaces; `null` removes the member. A
    profile shipped in the shared file is removed locally by `null`. Reverting a setting removes its
    entry from the patch.
  - **The result is validated as one.** It is the effective settings, and `policy.py` and the word
    "policy" keep that meaning.
  - **Paths are from the checkout's root.** A path inside settings — a persona file, for one — resolves
    from the checkout's root, never from `.orchestra/`.
  - **The settings' identity is their source, never the patch.**
    - A layered load's origin is `.orchestra/settings.json`, with or without a local patch.
    - With `ORCHESTRA_SETTINGS`, the origin is the file it names.
    - `stack.own()` compares that origin (fact 32), so no Apply ever turns the deployment into
      another stack.
  - **Settings named by `ORCHESTRA_SETTINGS` or `--settings` are read-only.** Such a stack — the
    demo's, the acceptance run's, each with a Workbench of its own — has no local patch. Its view shows
    its settings and refuses every Apply, which would otherwise write the operator's own patch, a file
    that stack never reads.
  - **Repositories come from one file, chosen as settings are.**
    - With `ORCHESTRA_REPOS` set, exactly the file it names. Neither `.orchestra/repos.json` nor a root
      `repos.json` is looked at, so the demo's, the acceptance's and the suite's descriptors never meet
      the operator's. A named file that does not exist is refused, naming it: an explicit choice that
      names nothing is a mistake, and "no descriptors" would surface later as fact 33's misleading
      refusal.
    - Without it, `.orchestra/repos.json`:
      - a `repos.json` left at the checkout's root, with no `.orchestra/repos.json`, is refused, saying
        to move it there;
      - both present is refused as ambiguous;
      - neither present is today's "no descriptors".
    - The file at the old place is never read, and no load moves a file. The choice is made when
      descriptors are loaded, so a refused layout fails what needs them — a start, the picker — with
      its reason, never a process's import.
    - This checkout's own file is moved once, by hand, as part of the change (task 2).
  - **The sweep keeps removing what an older worker left.** A Claude role-run's tracing settings hold
    the trace store's key, and the sweep removes those a dead worker left, by their prefix
    (`app/observability/telemetry.py:683-715`). A worker that died before the upgrade left them under
    `orch-claude-settings-`, so the sweep removes that prefix as well as `orchestra-trace-`. That old
    prefix is the one `orch` left in code, and the one vendor name outside the adapters (invariants 3
    and 11). It goes once every host has started on the new code (Not in this change).
- **A2 [ACTIVE]:** What the Settings view edits:
  - agents: named profiles — the kind, and the model and effort where the kind takes them;
  - each role's profile, persona and per-stage skills;
  - review rounds per phase, and the default flow.

  A profile has no list of extra arguments or environment variables. They are the vendor mechanics the
  adapter owns, and could undo its read-only mode, its session and its turn-end wiring. A kind that
  needs another setting brings its own named, validated option when it does.

  Nothing sets a role's access. It is the role's contract — the engineer writes, the architect reads —
  never a setting, and the view neither shows nor edits one (Decision 4).
- **A3 [ACTIVE]:** The operator's example maps onto the three global skills D19 names, one per stage:
  - the engineer's `plan` → `investigate-change`, and its `build` → `implement-approved-change`;
  - the architect's `research`, `assess` and `verify` → `architect`.

  This mapping is for the acceptance evidence only. The shared settings bind no skill.
- **A4 [ACTIVE]:** Personas:
  - the shared settings name each role's persona file, `roles/*.md`, which the page never edits;
  - a role's `persona` text, when present, takes the place of its `persona_file`. Otherwise its
    persona is that file's text. The Settings view writes `persona` into the local patch, marks it, and
    Revert removes it, so the file serves again;
  - the persona in effect is at most `MAX_PERSONA_BYTES = 16 * 1024` bytes of UTF-8, a constant of the
    repository's own. It is sized on Temporal's own wire, measured (fact 39):
    - every role turn carries the whole policy, both personas in it. The converter escapes each
      non-ASCII character, so a persona's bytes on the wire run up to three times its UTF-8 bytes, and
      up to six for control characters;
    - at 16 KiB each, a turn's input is at most 100,451 bytes for any text, and 198,755 bytes in the
      worst case of control characters. Both are under Temporal's 256 KiB warning, which is the
      invariant (invariant 10). 64 KiB crossed it for anything but plain ASCII letters;
    - today's personas are 1,895 and 1,597 bytes, and a persona carries only what its skill cannot
      know (the architecture's D19);
    - each turn adds one such input to the run's history. In that worst case about 52 of them alone
      would total 10 MB, Temporal's history warning. The whole history also holds outputs and other
      events, so it may reach the warning sooner. Today's runs take a few turns.
- **A5 [ACTIVE]:** Skills:
  - settings name a skill and nothing else, by the Agent Skills specification's name rule, never an
    invocation (fact 49);
  - each kind renders the invocation: `/name` for Claude, `$name` for Codex;
  - `/name` is read only from a policy of the old shape, which the suite's own policy is today
    (fact 24);
  - where a vendor installs skills is not a setting. A kind whose launch needs that folder owns it
    inside its adapter, as Claude's `--add-dir` does today (fact 25).
- **A6 [ACTIVE]:** An Apply reaches only runs started after it.
  - `client.start` makes the run's policy whole, through `application.settings`: each role's kind,
    model, effort, access, persona text and stage skills.
  - The run carries that copy, and no worker reads settings or a persona file for it.
  - A run started before the change keeps its policy of the old shape — a brain, a persona file's
    path — and still runs as today: `prepare` and `run_role` read that shape from the run's own
    input. The loader takes only the new shape, so no new run starts on the old one.
- **A7 [ACTIVE]:** Adapters live in `app/agents/adapters/`.
  - `__init__.py` holds the contract and a generic loader, and no list of kinds.
  - Each kind is one module, named from the kind by a one-to-one rule: lowercase letters, digits and
    single hyphens, each hyphen an underscore — `claude-code` becomes `claude_code.py`.
  - The loader imports a kind's module, checks it meets the contract, and reads its capabilities: its
    display name, the access it can run with — read-only, writing, or both — how it takes a skill, and
    whether model and effort apply.
  - The page gets kinds and capabilities from that boundary through the API, never from a list of its
    own.
  - **The loader's `available()` is how kinds are found.**
    - It enumerates the package's public modules: `__init__` and any name starting with `_` are
      skipped.
    - It turns each module's name back into its kind by the same one-to-one rule, loads it through the
      same contract check, and returns its capabilities: `claude_code.py` is `claude-code`, and
      `codex.py` is `codex`.
    - It answers per module: a module that fails to import or to meet the contract is returned as
      refused, with its reason, beside the others. One broken module never hides the rest, and a role
      bound to a refused kind is refused by validation.
    - Importing an adapter only defines it. Anything that touches the host happens in its answers, so
      the page can list kinds on a host that has none of their CLIs.
    - No production module and no page code holds a list of kinds. Tests may name the kinds they test
      — an adapter's own tests must.
  - Every kind runs its agent interactively in the role's live terminal (D7), with its own turn-end
    signal and read-only mode.
  - **No agent inherits any vendor's session markers** — the architecture's D17, which today strips
    Claude Code's markers from every agent, Codex's included (fact 37). Each adapter declares the
    variables a session of its vendor leaves. The application strips the union of every available
    kind's from every agent's environment, never only the agent's own.
  - **An old run's `brain` is resolved by the adapters.** Each adapter declares the brain name the old
    shape used for it — `claude` for `claude-code`, `codex` for `codex` — and the loader resolves an
    old policy's `brain` through those declarations. No generic module maps one name to another, and
    the declaration goes with the old-shape readers (Not in this change).
  - **A kind validates its own profile, composed in the application** (fact 36).
    - `policy.py` validates what every profile shares: the names, the `kind` and its grammar, the
      shape, and the roles' references. It cannot load an adapter: `app/foundation` imports nothing of
      ours.
    - `app/application/settings.py` composes the two. It runs that generic validation, then each bound
      kind's own: whether `model` and `effort` apply to it and which values it takes, and whether it can
      run with the access its role's contract requires (Decision 4). It is the one loader and validator
      (invariant 5).
    - Today's plain-token rule (fact 30) moves into `claude-code` and `codex`, because they put those
      values on a command line. It is not the contract for a kind that does not.
  - **The verdict's grammar stays one parser.** An adapter says only where its agent's messages are in
    its turn's output: Claude's final message, Codex's `agent_message` items. Finding the
    `{verdict, feedback}` object that ends a review, and checking it, stay in `nodes`, generic, for
    every kind (fact 41). A second verdict parser per kind would be a second authority over what
    routes (the architecture's D4).
  - **The packages keep their direction** (fact 28).
    - `app/agents`, adapters included, never imports `app/observability`, and `telemetry` never
      branches on a kind.
    - `app/application` loads the adapter, uses it for the agent's mechanics, and passes tracing
      between it and `telemetry` as plain data, both ways (fact 38):
      - **Before a turn**, the adapter is handed the step's trace context — its traceparent, the run's
        environment and release — and, when the step is traced and Langfuse's keys are set, the keys
        and a private folder. It returns what its agent needs: arguments and environment. Claude's
        adapter writes its plugin's settings, keys included, into that folder, with its turn hooks in
        the same file, since Claude takes one `--settings` (fact 42). Codex's adds nothing, as today.
      - **After a turn**, the adapter answers from its own session what the trace records:
        - the reasoning summaries — Codex's, from its rollout;
        - the vendor uploader to run — its command, environment and payload;
        - and what the installed build of that uploader lacks.

        `telemetry` runs that command within its bounded timeout and records the outcome and any
        degradation, knowing no vendor. This is today's Codex upload, moved as it is: it is not
        rebuilt as records `telemetry` uploads itself.
      - **The private folder stays `telemetry`'s.** It is made for one traced turn, only this user
        can enter it, it is named `orchestra-trace-` after the worker's process, it is removed when
        the turn ends, and it is swept once that process is gone (the architecture's D20). Every kind's
        keys get today's guarantee, and no adapter names or cleans a folder of its own.
    - `telemetry` records a step's kind and profile name, model and effort only as data — the trace
      contract's step metadata, which names the brain today (fact 38).
    - `turn_hook.py` stays outside the adapters as a sink that knows no vendor. Where a payload comes
      from — stdin or its last argument — becomes a mode the adapter passes, and the adapter alone
      decides how its CLI invokes the sink and which events end a turn.
- **A8 [ACTIVE]:** The contract's openness is proven in the suite by a test-only kind.
  - Its module is planted for the test only, in a temporary folder added to the adapters package's own
    search path. `available()` finds it with no production file edited and nothing written into the
    checkout, and it is never shipped.
  - It runs a fake agent interactively through the real terminal, takes typed keys, and ends its turn
    on its own signal.
  - Its kind's name differs from its executable's, so nothing can take one for the other (guard 11).
  - That module is its only code. pi follows later (D8).
- **A9 [REJECTED by D7]:** An agent driven one turn per process shows its turn live, but takes no
  typing mid-turn.

## Not in this change

Any of these can follow as a change of its own:

- a pi adapter (D8);
- editing a flow's steps in the page — flows stay files, and the view chooses the default among them;
- the stack's settings in the view: targets, hosts, ports, queues. A hand edit of the local patch can
  still set them.
  - Each takes effect when the process reading it restarts: the stack for hosts, queues and terminal
    ports; the Workbench for its own port and the terminal ports it connects to.
  - Until then, a start is refused where no worker polls the queue it names (`client.py:106-115`).
  - Timeouts are a run's own, taken at its start;
- a global "skip approvals" — the Start form's per-run choice stays;
- a list of models to choose from (D18: no model registry);
- settings per repository or per run — `.orchestra/` in a target repository is where they would live;
- editing repositories in the Settings view — `.orchestra/repos.json` moves, and stays a file edited by
  hand;
- finding out which skills each host has installed;
- removing what reads the old shape, once no run of the old shape is open: `prompt_path`'s old rules
  and the copy check behind them, and the adapters' old brain names (A7);
- dropping the sweep's old prefix, once every host has started on the new code (A1);
- a persona kept out of the run's history and passed by reference — the claim-check pattern — should
  a persona ever need more than `MAX_PERSONA_BYTES` (A4);
- a bound on the run's own text — its task, feedback, brief and guidance — which rides in every turn's
  input beside the personas and has none today. The persona bound leaves it at least 63 KB under the
  256 KiB warning, and 161 KB for personas of any text (fact 39);
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
12. **The decisions this touches** ([the architecture](../../docs/architecture/structure.md)):
    - D3: the judge is never the builder, and the architect is read-only;
    - D13: the set of brains that can be bound is code;
    - D17: a role's turn runs in its live terminal;
    - D18: no model registry;
    - D19: the global skills lead each stage through `stage_skills`;
    - D20, D21 and D28: the tracing plugins, the session stores and the accepted limits, each naming
      a vendor's mechanics;
    - D26: where a repository's facts come from;
    - D29: the page's reads and writes.
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
18. **Where agent mechanics sit today.** Agent-specific branches are spread over nine places:
    - the bindable list: `policy.KNOWN_BRAINS`;
    - the preflight: `repos.resolve` looks up `git` and each brain's name as a command, refusing before
      any work when one is missing (`app/workspace/repos.py:185-187`). `activities.prepare` hands it
      the brains (`activities.py:173-176`). It holds only while a brain's name is its executable,
      which `claude-code` running `claude` breaks;
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

    `telemetry.py:447` also records a role's brain as plain data. Two names are prose, not branches:
    `ptyhost.py` sends a lone Esc as Windows key events for every agent, naming Codex only as the reason
    (`app/agents/ptyhost.py:10-12`); and `stages.py:11` names a brain in its docstring.
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
22. **The rename's reach, outside `todo/`,** whose files keep their wording as history:
    - `policy.json`: 14 files, 26 lines;
    - `ORCH_POLICY`: 14 files, 34 lines;
    - `ORCH_REPOS`: 5 files, 7 lines;
    - `ORCH_WORKFLOW_UNDER_TEST`: 2 files, 3 lines;
    - `repos.json` and `repos.example.json`: 27 files, 52 lines;
    - the other `orch` names (D12): 24 files, 68 lines. Most are temporary folders' prefixes in tests.
      The rest are:
      - the containment's unit (`app/agents/launch.py:136`), which nothing finds by its prefix;
      - Claude's tracing settings folders (`app/observability/telemetry.py:616`), which the sweep does
        find by their prefix;
      - a private index's folder (`app/workspace/worktrees.py:162`);
      - a constant in `tools/trust_probe.py` and `tools/ui_fixture.py`;
      - the public check's debris glob (`tools/public_check.sh:53`), which follows the acceptance's
        folder prefix (`tests/acceptance_restart.py:129`).
    - `docs/history/`, a record kept as history, names `repos.json` too
      (`docs/history/extraction.md:34, 59`).
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
    once, after the reviewer's final pass, before the operator's live check ([tests/README.md](../../tests/README.md)).
32. **Which stack a policy's is.** `stack.own()` compares a policy's recorded origin (`_policy_path`) with
    the deployment file's (`stack.py:54-57`). Only the deployment's stack manages Temporal and the
    Windows worker (`stack.py:60-62`).
33. **With no `repos.json`, a named repository is refused, misleadingly.**
    - `repos.load()` then gives no descriptors — "not an error" (`app/workspace/repos.py:50-57`).
    - A repository named from the old list is then taken as a path from the process's folder, and refused
      as one that "does not exist" (`repos.py:123-133`).
    - Only a start that names no repository works on Orchestra's own checkout, and it does so today too.
    - In the page, the picker offers no repositories, and says only that repos.json has none.
34. **The public check guards private files by their paths** — the only automated check (AGENTS.md).
    - It fails when `.env`, `secrets`, `repos.json` or `tmp` is tracked (`tools/public_check.sh:30-36`),
      and its `repos.json` is the root's alone.
    - Measured in a throwaway repository: with `.orchestra/repos.json` and
      `.orchestra/settings.local.json` tracked, its pathspec found neither. Control: a tracked root
      `repos.json`, which it found.
    - `.gitignore`'s `repos.json` matches at any depth (`.gitignore:9`), so `.orchestra/repos.json` is
      ignored already. Nothing ignores or guards `.orchestra/settings.local.json` yet.
35. **The suite reads the operator's descriptors today.**
    - The Workbench's access test calls `/api/repos` on the checkout's default file
      (`tests/interfaces/test_workbench.py:128`).
    - The example test loads it whenever it exists (`tests/workspace/test_repos.py:190-192`).
    - Neither prints it. A root file left there would fail both once the loader refuses it (A1).
36. **Where settings can be validated.**
    - `app/foundation` imports nothing of ours, and `app/agents` only `foundation`
      (`tests/test_architecture.py:39-55`), so `policy.py` cannot load an adapter.
    - Settings are loaded only in `app/application` and `app/interfaces`: `client.py:204, 407`,
      `cli.py:297`, `workbench/server.py:198, 374` and `worker.py:45`.
    - An interface's behaviour belongs to `app/application` or below
      (`app/interfaces/docs/architecture/structure.md:16-18`).
37. **Every agent loses Claude Code's session markers today.** `agent_env` strips them whatever the
    agent (`app/application/activities.py:48-52, 83-88`), as the architecture's D17 states for every
    agent (`docs/architecture/structure.md:236-238`).
38. **Tracing holds each vendor's mechanics** (`app/observability/telemetry.py`):
    - Claude:
      - a traceparent variable (`:573-595`);
      - a settings file holding Langfuse's keys, in a folder only this user can enter, named after the
        worker's process, removed when the turn ends (`:614-681`) and swept after a dead worker
        (`:683-715`).
    - Codex:
      - its reasoning summaries, read from its rollout (`:777-815`);
      - after the turn, the plugin's own uploader, run through `node` with the keys in its
        environment, its build checked for what the trace needs (`:749-929`).
    - Every step's metadata names its brain, model and reasoning effort (`:446-449`), as the trace
      contract lists (`docs/architecture/trace-contract.md:38`). No saved view or dashboard selects on
      them (`trace-contract.md:133-151`).
39. **Every role turn carries the whole policy.**
    - `prepare` and each `run_role` are handed it (`app/orchestration/workflow.py:128, 232`); the
      `status` query is not (`:476-480`).
    - Measured on the ten recorded histories in `tests/histories/`: 31–115 KB each, 1–7 role turns,
      and 823–929 bytes of policy in each input.
    - Temporal's limits ([its defaults](https://docs.temporal.io/self-hosted-guide/defaults)):
      - a payload warns at 256 KB and fails at 2 MB;
      - a history warns at 10 MB and fails at 50 MB.

      This server overrides only `limit.maxIDLength` (`temporal/dynamicconfig.yaml`).
    - **The converter on the wire.** The project sets no converter or codec of its own, so a payload is
      `DataConverter.default`'s. Its JSON is `json.dumps` with its ASCII escaping left on (temporalio
      1.33.0, `converter/_payload_converter.py:786-788`), so on the wire:
      - each non-ASCII character becomes `\uXXXX`, and one outside the Basic Multilingual Plane
        becomes two of them;
      - a quote, a backslash and the five control characters JSON names — newline and tab among them —
        take two bytes, and any other control character six.
    - **Measured through that converter.** The largest recorded `run_role` input (2,119 bytes on the
      wire) was taken, both roles were given a persona of one character class at a bound, and the
      input's `Payloads` message was sized:

      | each persona | ASCII letters | quotes, newlines | 3-byte (CJK, em dash) | 2-byte (Cyrillic), 4-byte (emoji) | control characters |
      |---|---|---|---|---|---|
      | 64 KiB | 133,219 | 264,291 | 264,287 | 395,363 | 788,579 |
      | 32 KiB | 67,683 | 133,219 | 133,211 | 198,755 | 395,363 |
      | 16 KiB | 34,915 | 67,683 | 67,679 | 100,451 | 198,755 |

      256 KiB is 262,144 bytes. Today's persona files are 1,895 and 1,597 bytes.
40. **The one persona resolver reads from the policy file's folder.**
    - `prompt_path` resolves a relative persona against its origin's folder
      (`app/foundation/policy.py:101-117`). For the new origin that is `.orchestra/`, where A1 reads
      from the checkout's root.
    - The foundation's and the application's structures each name it the one resolver
      (`structure.md:56` and `:49`).
41. **Verdicts are parsed in two layers** (`app/agents/nodes.py:154-234`):
    - finding the agent's messages in its output — Claude's final message, Codex's `agent_message`
      items;
    - the one `{verdict, feedback}` grammar that routes.
42. **Claude's turn hooks share a traced turn's settings file.** Claude takes one `--settings`, so its
    hooks go into the file holding the keys whenever there is one (`app/agents/terminal.py:286-300`).
43. **Trust, and the guard over it.**
    - `tests/test_architecture.py:295-317` finds a unit test's `trust.ensure` or `trust.forget` that
      names no home, which would write the operator's own `~/.claude.json` or `~/.codex/config.toml`.
      It knows those calls only by that spelling.
    - Tools and the acceptance run name brains for trust: `tools/demo.py:578`,
      `tools/trust_probe.py:50, 93`, `tests/acceptance_restart.py:380, 524`.
44. **CI checks what is tracked with a copy of the public check's list**
    (`.github/workflows/ci.yml:23-35`).
    - The copy has the same root-only `repos.json`, and already lacks the acceptance-debris check.
    - The script itself needs only bash, git and docker (`tools/public_check.sh`), all of which the
      CI runner has.
45. **The page answers requests on parallel threads** (`app/interfaces/workbench/server.py:366-369`),
    and says a refusal as one string (`:159-165`).
46. **The command line's `--policy PATH`** names a policy file (`app/interfaces/cli.py:336`), and the
    acceptance run uses it (`tests/acceptance_restart.py:361, 447`).
47. **The agents' preflight sits in the repositories' owner.**
    - `repos.py` owns a run's repository, target, base branch and worktree root
      (`app/workspace/repos.py:1-13`), yet checks each brain's executable (fact 18).
    - Each kind runs one executable, `claude` or `codex` (`app/agents/nodes.py:60, 83`).
    - `node` serves only Codex's uploader, after the turn and best effort (`telemetry.py:916`).
48. **The architecture's D19 says "which skill a stage invokes stays code"**
    (`docs/architecture/structure.md:516-517`). Yet `stage_skills` is policy (`policy.py:157-167`),
    and D2 sets skills in the view.
49. **Skill names follow the Agent Skills specification**
    ([its name rule](https://agentskills.io/specification)):
    - 1–64 characters of lowercase letters, digits and hyphens;
    - no hyphen at either end, and none doubled;
    - the same as the skill's folder's name.

    The three installed skills keep it (fact 14).
50. **A role's access is not a choice today.**
    - The validator admits one value per role: the architect `read`, the engineer `write`
      (`app/foundation/policy.py:197-200`).
    - The value's one reader picks the read-only flags (`app/agents/nodes.py:56`).
51. **Measured through the role's terminal, 2026-09-28, Windows** — one real turn each, through
    `terminal.run_turn` in a throwaway repository, trust recorded and taken back:
    - Codex 0.153.4, interactive, read-only, a prompt starting `$architect`: it named the skill and
      quoted its first sentence verbatim (U1).
    - Codex, a prompt starting `$no-such-skill-orchestra`: it answered `NO SKILL LOADED`, and the turn
      completed as any other — the skill dropped without a word (U2).
    - Claude Code 2.1.283, a prompt starting `/no-such-skill-orchestra`: it printed `Unknown command`,
      called no model, fired no hook and sat at its prompt, so the turn would end only at its timeout,
      an hour in the shipped settings (U2).

**Inferences**

- **I1 — Codex-run stages can take a skill already** (fact 21), in the exec form.
- **I2 — A third agent costs edits across the code.** Today it means editing all nine places in fact 18.
- **I3 — The `ORCH_POLICY` route degrades the live deployment** (facts 8–9).
- **I4 — "An Apply reaches only new runs" is false for personas today** (fact 4). It holds only once a
  run's policy carries each persona's text from its start.

**Assumptions / unverified areas**

- **U1 [MEASURED — fact 51]:** interactive Codex loads a skill named at its first prompt.
- **U2 [MEASURED — fact 51]:** neither CLI fails a turn that names a skill no folder holds, so
  preparation looks for each bound skill in the folders its kind's vendor documents, and `prepare`
  refuses the run before any work, naming the skill and where it looked (guard 17).
- **U3:** that replacing a file atomically works on the checkout's filesystem as the Workbench reaches
  it — a Windows drive through WSL.
  - Also, what a replace does while a Windows process holds the file open: Windows refuses to replace
    a file opened without shared deletion.
  - The writer takes any error there as a refused Apply that leaves the file as it was. Measured in
    task 5.

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
  resumed, finished, trusted, traced, checked for on the host and given its environment is spread over
  nine places, keyed by the brain's name (fact 18).
- **The page's writes:** D29. **The stack:** the checkout's own settings' (D32).

## Problem and capability gap

1. **Binding an agent is fixed.** Only two agents can be bound, and a third costs edits in nine places
   (I2), against D5. One of them, the preflight, takes a brain's name for the command it runs.
2. **Nothing shows or edits the setup** (D1).
3. **The settings have no personal layer,** and their one override is a badly named variable that
   degrades the stack (D11, I3). Many of Orchestra's names shorten its own to `orch` (D12, fact 22).
4. **A run's personas can change after it starts** (I4).
5. **Two rules go against the operator's decisions:** the independent-judge refusal (D9), and a skill
   syntax fixed for every agent (D5).
6. **The check that guards what is published has two copies.** They have already drifted, and the
   move changes the list both hold (facts 34, 44).

## Decision

1. **Adapters** (A7) in `app/agents/adapters/`:
   - a contract and a generic loader, and one module per kind. The loader's `available()` finds the
     kinds by their modules (A7), so a new kind is its module alone;
   - `claude-code` and `codex` are today's code moved behind the contract, behaving exactly as now.

   An adapter answers, for one turn of its kind of agent:
   - `executable`: the one program its turn runs, which its launch command starts and the preflight
     looks for — one name, from one place in the adapter;
   - the command that runs it interactively in the role's live terminal — new or resumed session,
     model, effort, and this host's differences;
   - its read-only mode;
   - the session markers its vendor leaves, which no agent inherits (A7);
   - how the end of its turn is signalled, and where its agent's messages and its session are in the
     turn's output — never the verdict's grammar, which stays generic (A7);
   - how a lost session shows;
   - how a skill is invoked, or that it has none;
   - the brain name the old shape used for it (A7);
   - optionally, trust setup — recording a repository for its CLI and taking the record back — and
     tracing, as plain data both ways (A7);
   - its capabilities, for the page.

   **The agents' preflight belongs to the application, and the repositories' to `repos`** (fact 47).
   - `prepare` runs on the target host (`app/orchestration/workflow.py:128, 389`). Before anything
     else, it takes each bound role's adapter and looks up its `executable` on this host.
   - A missing one refuses the run naming it, before `repos.resolve` reads any git, before the
     worktree and before any agent. A refused preparation already creates nothing
     (`tests/orchestration/test_stops.py:209-215`).
   - `repos.resolve` looks up `git` and resolves the repository, its base branch and its worktree root,
     and takes no agent's name at all.
   - One executable per kind is what the evidence needs: `node` serves only Codex's uploader, after the
     turn and best effort. A list waits for a kind that needs two.
2. **The settings' shape.** In `.orchestra/settings.json`, and the local patch over it:
   - `agents`: a profile's name maps to its `kind` and, where the kind takes them, `model` and `effort`.
     Two ship, matching today's bindings.
   - `roles`: each role's `agent` — a profile's name — its `persona_file`, and, when given, its
     `persona` text, which takes the file's place (A4). No access: that is the role's contract
     (Decision 4), and a role holding any key besides these is refused.
   - `stage_skills`: a stage maps to a skill's name, by the Agent Skills name rule (A5, fact 49).
   - Everything else as today: rounds, the default flow, and the stack's keys.
3. **The run's policy, made whole at its start (A6).**
   - `client.start` resolves each role to its kind, model, effort and persona text, and each stage's
     skill to its name, through `application.settings`, and hands the run that copy.
   - It writes each role's access into that copy from the role's contract (Decision 4), as the key the
     role-runs read today (fact 50). The run's policy keeps `workspace_access`, and the settings never
     hold it.
   - The persona text is `persona` when present, else `persona_file`'s text, checked against
     `MAX_PERSONA_BYTES` there.
   - **One persona resolver still** (fact 40). `prompt_path` gains the new shape's rule: a
     `persona_file` resolves from the checkout's root, on the host starting the run. Its old rules stay
     for old runs, on the host running the role. No second resolver is written.
   - No later Apply, and no later edit to a persona file, changes that run.

   The old shape is read only from a run's own input, by `prepare` and `run_role`, for a run started
   before the change:
   - its `brain` is resolved to a kind by the adapters' own declarations (A7);
   - a persona file's path resolves as today;
   - a `/name` skill is the skill `name`.

   The loader takes only the new shape. A file of the old shape is refused, naming the new keys, and
   the suite's, the demo's and the acceptance run's settings move to the new shape with this change.
4. **Access is the role's contract, and the choice is the agent's** (fact 50).
   - The engineer writes and the architect reads: the architecture's D2 and this change's D10.
     `policy.py` holds that contract beside `ROLES`, as code, since no other value is valid.
   - A bound kind that cannot run with its role's access is refused: one without a read-only mode
     for the architect, one without a writing mode for the engineer.
   - Which model each role runs is free (D9), and the view shows both roles side by side, with no
     access field.
   - A run of the old shape keeps reading the `workspace_access` it stored, as today.
5. **The layers of A1, and who holds each part.**
   - **`policy.py`, in the foundation, owns the files.**
     - It reads the shared file and applies the local patch, or takes `ORCHESTRA_SETTINGS` alone.
     - It computes a sparse edit of the patch and replaces the file atomically.
     - It gives each read a revision: a hash of both files' bytes, an absent file included.
     - It validates what every profile shares, and loads no adapter (fact 36).
   - **`application.settings` composes them** — the one entry for the page, the command line, both
     workers and `client.start`. It validates the result with each bound kind's own checks (A7),
     makes a run's policy whole, lists the kinds, and applies.
   - The result's origin is its source: `.orchestra/settings.json`, or the file `ORCHESTRA_SETTINGS`
     names, and never the patch (A1).
   - Repositories come from the file `ORCHESTRA_REPOS` names, alone, which must exist; else from
     `.orchestra/repos.json`, where the loader refuses a root `repos.json` left behind, and both being
     present (A1).
   - **The public check follows the move.**
     - It fails on a tracked `repos.json` wherever it is, and on a tracked
       `.orchestra/settings.local.json`, which `.gitignore` gains (fact 34).
     - CI runs `tools/public_check.sh` itself, so the list of private paths has one owner (fact 44).
   - An Apply:
     - edits the existing local patch only at the paths of the settings submitted, never rebuilding it
       from the effective settings. So:
       - a member the view does not show — a hand-written target or timeout — survives an Apply;
       - an unchanged shared value is never copied into the patch, where it would hide a later shared
         change;
       - a submitted value equal to what lies below removes its member, rather than keeping a copy;
       - removing a shipped member writes RFC 7396's `null`;
       - Revert removes only that setting's member, pruning objects it leaves empty;
       - a patch left empty removes the file;
     - validates the whole result, through `application.settings`;
     - carries the revision its view was read at. It is refused as a conflict — the page's 409, as for
       a stop already answered — when either file has changed since;
     - is compared and replaced under one lock in the page's process, so two Applies never interleave
       (fact 45). A hand edit landing between the compare and the replace is the one window left;
     - replaces the local patch atomically, and takes an error there as a refusal (U3);
     - changes nothing when it refuses.
   - **A refusal names its setting.** It carries the JSON Pointer (RFC 6901) of the setting it is about
     — `/agents/review/model`, say — beside its reason. One about no single setting carries none.
   - **A local patch that does not load** — a hand edit gone wrong — stops every loader, naming its
     file and reason (invariant 8). The view then shows that refusal and takes no Apply, and the
     operator fixes or deletes the file by hand.
6. **The Settings view** (`#settings`, beside *Worktrees*):
   - **Agents:** profiles — add, edit, and remove, including one shipped below — each with its kind's
     capabilities: whether it can review, how it takes a skill, whether model and effort apply. A kind
     whose module is refused is listed as unusable, with its reason.
   - **Roles:** each role's profile, persona — with its size against `MAX_PERSONA_BYTES` — and
     per-stage skills, with each stage's invocation shown.
   - **Interactions:** rounds per phase, and the default flow with its steps.
   - **Applying:**
     - one Apply, carrying the revision the view was read at;
     - a Revert per setting;
     - a refusal said beside the field its JSON Pointer names, or above the view when it names none;
     - "applies to runs started from now on";
     - read-only, saying why, where the settings come from `ORCHESTRA_SETTINGS` (A1).
7. **Documents amended** — the architecture's decisions and the owners the Documentation plan names:
   - D3: the reviewer is read-only; whether it is another model is the operator's choice;
   - D13: kinds of agent are code, one module each, and which agent a role runs is configuration. A
     role's access leaves D13's list of configuration: it is the role's contract, code (Decision 4);
   - D17: the seam runs through an adapter, and no agent inherits any vendor's session markers;
   - D18: model and effort stay configuration, and no registry. Their accepted values are their kind's
     adapter's to check;
   - D19: a skill is named, and rendered by its kind. Which skill leads a stage is configuration, set in
     the Settings view, so "which skill a stage invokes stays code" goes (fact 48);
   - D20: a traced turn's keys live in `telemetry`'s private folder for as long as the turn runs, and
     the adapter decides only what its vendor's file inside it says;
   - D26: descriptors come from `.orchestra/repos.json`, or the file `ORCHESTRA_REPOS` names;
   - D29: the page reads and applies settings through `application.settings`, beside its other reads
     and writes;
   - vendor mechanics now spelled out at the architecture's level move down to the adapters that own
     them, and the architecture keeps the generic rule. That covers Claude's permission modes and
     Codex's Windows sandbox in D17, the flags in D18, the session stores' paths and reasoning
     summaries in D21, and the tracing plugins and trust dialogs in D28;
   - the README and using.md: `.orchestra/` and the new names.

### Premise / KISS gate

**The owner** of an agent's mechanics becomes that agent's adapter. The settings' files stay
`policy.py`'s, and their composition with the adapters is `application.settings`'s, since the
foundation can load no adapter. The owner of a run's policy stays `client.start`, which now makes it
whole. Every other owner keeps its concern: `repos` its repositories, `telemetry` a traced turn's keys.

**It adds:**

- one adapter package, with its contract and loader;
- one application module, `settings`, composing what exists;
- agent profiles;
- the merge patch, with a revision and one lock;
- two endpoints;
- one page module;
- one old prefix the sweep still removes, until every host has started on the new code (A1).

**It removes:**

- nine places' agent branches, the preflight's taking a brain's name for its command among them;
- the fixed list of bindable agents;
- one skill syntax for every agent;
- the independent-judge refusal;
- a persona read long after a run started;
- CI's copy of the public check;
- every `orch` name (D12).

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
- **`policy.py` loading adapters to validate.** It turns the package graph into a cycle, which
  `test_architecture.py` refuses (fact 36).
- **A JSON Schema per kind, validated by a library.** A new dependency for what the adapter's own check
  already does, with no present need.
- **Each adapter making and cleaning its own secret files.** The sweep could not find a new kind's, so
  its keys would outlive a dead worker (fact 38).
- **Personas passed by reference, outside the run's history.** More moving parts than the bound needs
  today (A4). It stays open as a later change.
- **The agents' preflight given to `repos.resolve` as command names.** It removes the vendor names but
  leaves the repositories' owner answering for agents (fact 47).

## Required invariants

1. **Claude and Codex behave exactly as today** behind their adapters: the suite, `make demo`, and the
   recorded histories replay (D25).
2. **Old runs keep running.** A run started before the change completes on the policy of the shape it
   started with (Decision 3).
3. **Agent mechanics live only in the adapters.** No production module outside `app/agents/adapters/`
   contains agent-specific mechanics or branches — `turn_hook.py` and `telemetry.py` included. A kind
   may travel elsewhere only as opaque data — for settings, the page, telemetry — and the page learns
   kinds and capabilities from the adapter boundary.
   - A guard in `test_architecture.py` enforces it over code, not prose. No string outside the adapters,
     docstrings apart, contains an available kind's name or its executable.
   - Its one listed exception is the sweep's old prefix (A1), which goes with it.
   - It cannot see a vendor's mechanic that carries no vendor name — `CC_LANGFUSE_TRACEPARENT`, say —
     so the review checks those.
3a. **The packages keep their direction.** `app/agents` never imports `app/observability`;
    `app/application` joins them, handing tracing across as plain data (A7). No foundation module loads
    an adapter. The existing boundary check in `test_architecture.py` stays green.
3b. **A kind owns its profile's values.** The generic validator checks shape and references, and the
    kind's adapter checks whether `model` and `effort` apply and which values they take — composed in
    `application.settings` (A7).
3c. **The agents' preflight stays early, and in the application.**
    - A run whose agent's `executable` is missing on its target host is refused by `prepare` before
      `repos.resolve` reads any git, before its worktree and before any agent, naming the executable.
    - The executable is the adapter's one answer, the one its launch runs. `repos.py` checks `git` and
      takes no agent's name.
3d. **No agent inherits any vendor's session markers** (the architecture's D17): every agent's
    environment is stripped of the union every available kind declares (A7).
3e. **A traced turn's keys live only in `telemetry`'s private folder.** It is made for that turn and
    removed when it ends, swept once its worker is gone, and never named or cleaned by an adapter
    (A7).
3f. **The verdict has one parser.** Adapters locate their agent's messages; the `{verdict, feedback}`
    grammar and its checks stay generic, in `nodes` (A7).
4. **Every agent's terminal takes typing (D7),** and the reviewing role is read-only, through its kind's
   own mode and the step's failure on a changed tree (D10).
   - A role's access is its contract, written into every run's policy at the start: the architect's
     always `read`, the engineer's always `write`.
   - No setting can change it, since settings hold no access key.
5. **One loader and one validator — `application.settings` — for the page, the command line, both
   workers and `client.start`.**
   - No other production module calls `policy.load`.
   - A refusal in the view is the validator's own reason, about the effective settings, with the JSON
     Pointer of its setting (Decision 5).
6. **An Apply reaches only runs started after it.**
   - A run's policy is whole from its start, persona text included, so no Apply and no edit to a
     persona file changes an open run.
   - The stack stays the checkout's own (D32): with a local patch present, `stack.own()` is true of the
     loaded settings, and `stack.managed()` is still Temporal and both workers.
   - `ORCHESTRA_SETTINGS` takes no patch, and a Workbench running under it refuses every Apply,
     leaving the operator's local patch as it was.
7. **The suite never reads the operator's local patch or descriptors** (fact 35). Its harness names the
   shared settings alone through `ORCHESTRA_SETTINGS`, and descriptors of its own through
   `ORCHESTRA_REPOS`. The shared settings bind no skill.
8. **Writes are atomic, checked, serialized and sparse.**
   - A refused Apply, or one against a stale revision of either file, leaves both as they were.
   - Two Applies at once never interleave: one lands, and the other is refused as stale.
   - An Apply changes the local patch only at the settings it carries: every other member survives, and
     no unchanged shared value is copied in.
   - A patch whose result does not validate stops the loader with the file's name and the reason.
9. **Settings hold names, never mechanics or secrets.** A skill is a name; a profile has no raw
   arguments or environment; keys stay in `.env`.
10. **A persona is at most `MAX_PERSONA_BYTES = 16 * 1024` bytes of UTF-8.** The bound is measured on
    the persona in effect — `persona` when present, else `persona_file`'s text — and refused, naming
    the role, one byte past it.
    - **The invariant it serves is the wire's:** a `run_role` input with both personas at the bound,
      of any content, serialized by `DataConverter.default`, stays under Temporal's 256 KiB payload
      warning (A4, fact 39).
    - Should a converter or content ever cross it, the bound comes down; the invariant does not move.
11. **No `orch` name (D12), and no root `policy.json` or `repos.json`, is left** in code, configuration,
    tools, tests or current documents; `todo/` and `docs/history/` keep their wording as history.
    - Only what the change must recognise from before it keeps an old name: the sweep's old prefix
      (A1), and the loader's refusal of a root `repos.json`.
    - A root `repos.json` in a checkout is refused, naming its new place, and so are both being present.
    - `ORCHESTRA_REPOS` takes the file it names alone, and refuses one that does not exist.
    - The loader never reads the old place and never moves a file.
11a. **A new kind is its module alone.** `available()` finds kinds from the package's modules, and no
     production module and no page code lists them.
11b. **The public check covers what moved, and has one owner** (facts 34, 44). A tracked `repos.json`
     anywhere, a tracked `.orchestra/settings.local.json`, and acceptance debris under the new prefix
     each fail it. CI runs the same script.
12. **D18 still holds:** no model registry; an empty model is the provider's default, shown as such.
13. **D29:** the page holds no run state. It reads and applies settings through
    `application.settings`, under the page's token and origin checks, which cover every `/api/` path
    (`server.py:149-157`).
14. **Trust writes in unit tests name a home.** The guard over them follows the calls into the adapters,
    so no unit test writes the operator's own CLI configuration (fact 43).

## Implementation tasks

**Progress (2026-09-28).** Order taken: task 2 without the settings file's move, then task 3, then that
move with task 4 — a settings file of the old shape in `.orchestra/` would resolve its persona files from
the wrong folder (`tests/foundation/test_policy.py:121-134`). Each guard is written with the task whose
code it guards, and observed failing first.

- Task 2, all but the settings file: done. Guard 10 red first (`workspace/test_repos.py`, `Source`). The
  public check, in a throwaway repository: clean passes, and a tracked `.orchestra/repos.json`,
  `.orchestra/settings.local.json`, nested `repos.json` or acceptance debris each fails it.
- Task 3: done.
  - Guard 1 red first: 55 strings in six modules of the committed `app/`. Now only `policy.py`'s
    `KNOWN_BRAINS` is left, which task 4 removes.
  - Guard 15 red first against today's trust guard.
  - Guards 2 (all but its access control, which comes with guard 4), 9, 11, 12, 13 and 14 are written
    with the suite's own kind, `tests/stand_in.py`.
  - Focused modules: WSL 93 classes, 430 tests; Windows 58 classes, then the six it failed, rerun after
    their fixes: 33 classes, 140 tests. All green but guard 1.
- Found in task 3, and fixed there:
  - the review parser still probed a `result` field, Claude's old print-mode envelope, which no kind
    writes now;
  - Codex's upload notes named the architect, whichever role it runs.
- Task 2's settings move and task 4: done. `policy.json` is `.orchestra/settings.json`, in the new shape.
  - Guard 3's control is today's path: a run of the old shape still reads its persona file when its
    session is born, so an edit made during the plan reaches the architect.
  - Guards 1 and 3–4, 7, 16–18 and 2's access control are green, 16 with its 64 KiB control over the
    bound. WSL 111 classes; Windows 85 classes, 381 tests.
  - An old run's persona resolves by its own origin alone. The host copy that `ORCH_POLICY` named has
    no successor, since a host's settings file can no longer be a copy of an old run's policy; the
    deployment's old runs name `policy.json` from the checkout's root, which both hosts read.
- Task 5: done. U3 measured from WSL on the Windows drive: a replace works, and while a Windows process
  holds the patch open it is refused with `PermissionError(13)`, the file as it was. Guards 5, 6 and 8
  are green on WSL (48 classes, 238 tests). They were written right after the code, not before it, and
  each shows it can fail through its control: a writer that rebuilds the patch, an Apply without the
  lock, an Apply that ignores where its settings came from.

0. [x] Q1–Q7 answered (D5–D11). Codex's skills measured (fact 21).
1. [x] U1 and U2 measured first, one real turn each through the role's terminal (their plan is under
   Assumptions). Then the red guards, each observed failing first (Test-first and verification plan).
2. [x] The move and the rename (A1, D12): `.orchestra/`, the `ORCHESTRA_*` variables, `--settings`,
   and every other `orch` name (fact 22). Mechanical, checked by the tests of the modules it touches.
   - This checkout's own `repos.json`, ignored and private, is moved once into `.orchestra/` by hand,
     never printed, because git will not carry it.
   - The loader's refusal of a root one covers every other checkout.
   - The suite's harness names the shared settings alone and descriptors of its own (invariant 7).
   - The public check's private paths and debris glob follow the move, and CI runs the script in place
     of its copy (invariant 11b).
   - The sweep removes both prefixes (A1).
3. [x] The adapter package: the contract, the loader, and `claude-code` and `codex` moved behind them,
   behaviour unchanged. That includes:
   - `turn_hook.py` made a vendor-blind sink;
   - tracing split as A7 says: the vendors' files and uploader behind their adapters, and the private
     folder, its sweep and the uploader's run left generic in `telemetry`;
   - the agents' preflight moved from `repos.resolve` into `prepare`, which looks up each adapter's
     `executable` (Decision 1);
   - the union of every kind's session markers stripped from every agent's environment;
   - the verdict's grammar left in `nodes`, with each adapter locating its messages;
   - trust behind the adapters, and its callers — `tools/demo.py`, `tools/trust_probe.py` and the
     acceptance run — going through every available kind, with the trust guard following the calls.

   Checked by the touched concerns' tests — the agents', the application's, observability's — and by
   the recorded histories' replay.
4. [x] The settings' new shape, and the run's policy made whole at `client.start`:
   - `application.settings`: the one loader and validator. It composes the generic shape with each kind's
     own values through its adapter; each role's access from its contract, with a kind unable to run
     with it refused; no independent-judge refusal; skill names by their rule; and
     `MAX_PERSONA_BYTES`, with guard 16 run on the real wire before the bound is settled;
   - persona files through the one resolver, from the checkout's root (Decision 3);
   - the old shape read only from a run's own input, by `prepare` and `run_role`, with the replay of
     recorded histories. The loader refuses it, and the suite's, the demo's and the acceptance run's
     settings move to the new shape.
5. [x] The merge patch: the loader, the sparse writer with its revision and lock, the refusals' JSON
   Pointers, the `.gitignore` entries, and the suite's isolation. U3 is measured here.
6. [x] The settings API — kinds and capabilities from the adapter boundary, through
   `application.settings` — and the Settings view, through `frontend-design`, with each field saying
   what it changes and when, and the state of a local patch that does not load.
7. [x] Documentation (Documentation plan).
8. [x] Verification, in the standing order (fact 31), as revised by D14:
   - tasks 2–6 each iterate on the tests of the concerns they touch, named, with the replay of recorded
     histories wherever a run's policy is read, and focused browser probes for the view;
   - `make demo` once, on the finished implementation;
   - `web-design-review`;
   - one agent review round, fixed without further agents;
   - the external review;
   - after its PASS, the whole suite once on WSL and once on Windows;
   - the Settings-to-run deterministic gate on both hosts, including the exact 10+10 Plan and Build
     boundaries and all four role/event prompt additions.

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
  1. **Mechanics only in the adapters** (`test_architecture.py`). Red today in nine places, the turn
     hook, telemetry and the preflight among them.
     - It reads code, not prose (fact 18): no string outside the adapters, docstrings apart, contains
       an available kind's name or executable. Its one listed exception is the sweep's old prefix.
     - Control: a kind's branch planted outside the package.
  2. **A new kind is one module** (`agents/test_terminal.py`). A test-only kind, handed to the loader:
     - runs a fake agent interactively through the real terminal;
     - takes typed keys;
     - ends its turn on its own signal;
     - resumes its session.

     Its review is parsed by the one generic parser: an answer with text after its verdict object is
     refused, as it is for Claude and Codex (invariant 3f).

     The loader refuses an unknown kind by name, a name outside the grammar, and a module that lacks
     part of the contract, saying what.

     Controls:
     - a kind without a turn-end signal, which times out as today;
     - a module missing its read-only mode, refused for the architect;
     - a parser of the kind's own, which lets the trailing text through.
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
     - the architect on a kind with no read-only mode is refused (D10), and so is the engineer on a
       kind with no writing mode;
     - a run whose input has the old shape — a brain, a file path, a `/name` skill — runs as before,
       its `prepare` preflighting through the adapters' old brain names;
     - the loader refuses a settings file of the old shape, naming the new keys.
  5. **The layers** (`foundation/test_policy.py`):
     - the merge patch — objects merge, lists replace, `null` removes a shipped profile — validated as a
       whole;
     - `ORCHESTRA_SETTINGS` taken alone;
     - under the suite's harness, no local patch is read;
     - a persona file resolves from the checkout's root through the one resolver, and an old run's as
       today.
  6. **The writer and the API** (`application/test_settings.py` and the Workbench's tests, over a
     temporary checkout with `ORCHESTRA_SETTINGS` cleared, save the one case that sets it):
     - a refused Apply changes nothing, and so does a stale one after a hand edit of either file;
     - a hand-written `targets` or timeout override survives an Apply that changes a role's agent;
     - an Apply changing one setting copies no unrelated shared value into the patch;
     - Revert removes that setting's member alone;
     - removing a shipped profile writes a `null`;
     - removing the last override removes the file;
     - no token, no write;
     - kinds and capabilities come from the adapter boundary;
     - a skill's invocation per kind: `/name` for Claude, `$name` for Codex, none for a kind without
       skills;
     - two Applies made against one revision, released together: one lands, the other is refused as
       stale;
     - a refusal carries the JSON Pointer of its setting;
     - while the local patch does not load, the view's read returns that refusal and every Apply is
       refused;
     - under `ORCHESTRA_SETTINGS`, every Apply is refused, and the checkout's local patch stays as it
       was, byte for byte.

     Controls:
     - a writer that rebuilds the patch from the effective settings;
     - one without the lock, under which both concurrent Applies land;
     - one that ignores where the settings came from, which writes the operator's patch from the
       demo's page.
  7. **A kind validates its own values** (`application/test_settings.py`, new, with a test-only kind):
     - a kind that takes no effort refuses one;
     - `claude-code` and `codex` refuse a model that is not a plain token;
     - the generic validator in `policy.py` takes a value it does not know the meaning of, and leaves it
       to the kind;
     - every loader goes through `application.settings`: no other production module calls
       `policy.load`.

     Controls: the plain-token rule kept generic, refusing the test-only kind's own value; and a call to
     `policy.load` planted in another module, which the check finds.
  8. **A local patch leaves the stack the deployment's** (`application/test_stack.py`). With a local
     patch present, the loaded settings are `stack.own()` and `stack.managed()` is Temporal and both
     workers; with `ORCHESTRA_SETTINGS`, they are that file's. Control: an origin taken from
     `settings.local.json`, which makes the stack another's.
  9. **Kinds found, not listed** (`agents/test_terminal.py` or the adapters' own test module):
     - a valid test-only module, planted on the package's search path (A8), is returned by
       `available()`;
     - `__init__` and a `_`-prefixed module are not;
     - a module failing the contract is returned refused, saying what it lacks, beside the others;
     - it all holds with an empty `PATH` and an empty home, so no adapter probes its host when it is
       imported.

     Control: a fixed list of kinds, which misses the planted one.
  10. **The repositories' source is chosen, never guessed** (`workspace/test_repos.py`, over a
      temporary checkout):
      - without `ORCHESTRA_REPOS`:
        - a root `repos.json` alone is refused, naming `.orchestra/repos.json`;
        - both present is refused as ambiguous;
        - neither present is "no descriptors", as today;
        - no load reads or moves the root file;
      - with `ORCHESTRA_REPOS`:
        - its file's entries are the descriptors, with a root `repos.json` and a `.orchestra/repos.json`
          both present, and neither is read nor refused;
        - a file it names that does not exist is refused, naming it;
      - under the suite, the descriptors are the suite's own, never the checkout's (invariant 7).

      Controls: a loader that falls back to the root file, which the first case catches; one that
      looks at the checkout's files before the variable, which the first explicit case catches; and the
      suite without its variable, whose descriptors are then the checkout's.
  11. **`prepare` looks up an adapter's executable, never its kind** (`application/test_activities.py`,
      new: the concern's own folder). The test-only kind's name differs from its executable (A8):
      - its executable found: `prepare` goes on to `repos.resolve`, and succeeds;
      - missing: `prepare` is refused, naming the executable, not the kind, and `repos.resolve` is
        never called — no git read, no worktree, no agent. A refused preparation already creates
        nothing (`test_stops.py`);
      - for `claude-code`, `codex` and the test-only kind, the launch runs the adapter's `executable`;
      - `repos.resolve` checks `git` alone and takes no agent's name (`workspace/test_repos.py`, whose
        missing-tool case now covers `git` only).

      Control: today's lookup of the kind's name, which refuses the first case.
  12. **The sweep still removes what an older worker left** (`observability/test_stale_settings.py`).
      A dead worker's folder is removed under `orchestra-trace-` and under `orch-claude-settings-`.
      Control: a sweep knowing only the new prefix, which leaves the old folder and its key.
  13. **No agent inherits any vendor's session markers** (`application/test_activities.py`). The
      environment of the test-only kind's agent, and of each shipped kind's, holds no marker that any
      available kind declares — Claude Code's included. Control: stripping only the agent's own kind's
      markers, which leaves Claude's in a Codex agent's environment.
  14. **A traced turn's keys stay in `telemetry`'s private folder** (`application/test_activities.py`,
      with a test-only kind that writes a file into the folder it is handed):
      - the file exists only there, and only during the turn;
      - the folder is gone after the turn, whether the turn passed or failed;
      - a folder whose process is gone is swept.

      Control: an adapter making a folder of its own, which the sweep never finds.
  15. **The trust guard follows the calls** (`test_architecture.py`). A unit test's call to an adapter's
      trust answer that names no home is found. Control: today's guard, which knows only
      `trust.ensure` and `trust.forget` and misses it.
  16. **A role turn's input stays under Temporal's payload warning, on the real wire**
      (`application/test_settings.py`).
      - A run's policy is made whole with both personas at `MAX_PERSONA_BYTES`, and put in a
        `run_role` input with the largest state the recorded histories hold.
      - It is serialized by `DataConverter.default`, the converter the project runs on, and the
        `Payloads` message's bytes are what is measured — never a persona's own length, nor a
        `json.dumps` of one's own.
      - It is under 256 KiB for each character class: ASCII letters, quotes and newlines, 2-, 3- and
        4-byte UTF-8, and control characters.
      - The number measured replaces fact 39's wherever they differ.

      Control: a bound of 64 KiB, which crosses it for 2-byte text (fact 39).
  17. **A bound skill is never dropped, nor left to hang** (`application/test_activities.py`), since
      neither CLI fails a turn over it (fact 51).
      - A bound skill that the kind's documented folders do not hold refuses `prepare` before any
        work, naming the skill and where it looked.
      - Only the skills of the stages the run's flow takes are looked for.

      Control: a preparation without the check, under which the run starts.
  18. **Access is the role's, never a setting's** (`application/test_settings.py`):
      - the architect's run policy always says `read`, and the engineer's `write`, whatever profile
        each is bound to;
      - a bound kind that cannot run with its role's access is refused (guard 4);
      - a `workspace_access`, or any other key a role does not take, in the settings — shared or
        local — is refused as unknown.

      Control: a validator that lets `workspace_access` through into the run's policy, under which a
      settings file makes the architect write.
- **Reviewer-checked judgements:**
  - the view's words;
  - that nothing in it reads as a model registry;
  - that no kind is named in the page's own code;
  - that no `orch` name and no root `policy.json` / `repos.json` is left where invariant 11 says,
    checked by one scripted search at the end rather than a permanent test. Outside `todo/`,
    `docs/history/` and the vendored scripts, `git grep -P -i '(?<![a-z])orch(?!estra)'` finds nothing
    but the sweep's old prefix;
  - that the public check covers what moved (invariant 11b), proven once in a throwaway clone that
    tracks `.orchestra/repos.json`, `.orchestra/settings.local.json` or acceptance debris under the new
    prefix, each of which fails it;
  - that CI runs that same script, whose first run on CI is the operator's next push;
  - that no vendor mechanic without a vendor's name is left outside the adapters (invariant 3).

### Green evidence

- The same guards green, and each task's touched concerns green as it goes (task 8), with the recorded
  histories replaying wherever a run's policy is read.
- Browser probes of the view.
- `make demo` passes whole, once, on the finished implementation.
- `make public-check` and `git diff --check` are clean, and the public check's control in a throwaway
  clone fails as invariant 11b says.
- The whole suite once on WSL and once on Windows, after the external PASS.
- The Settings-to-run deterministic gate (D14): both shipped flows; role/profile, model, effort,
  persona and stage-skill delivery; Apply during an open run leaving its snapshot unchanged; exact
  10+10 Plan and Build prompts and stops; and Discard, with mocked role turns on both hosts.

## Documentation plan

- **Authoritative stable owners:**
  - [the architecture](../../docs/architecture/structure.md): D3, D13, D17, D18, D19, D20, D21, D26, D28
    and D29, as in Decision 7, and the Composition table's rows for `policy.json`, `repos.json`,
    `nodes.py`, `trust.py` and the settings;
  - [the main view](../../docs/architecture/diagrams/main.md) and
    [the processes view](../../docs/architecture/diagrams/processes.md): the agents' CLIs as kinds behind
    adapters, where they name `claude · codex` today;
  - [the agents' structure](../../app/agents/docs/architecture/structure.md) and
    [its main view](../../app/agents/docs/architecture/diagrams/main.md): the adapter package as a part —
    its contract, its loader and naming rule, a kind's own validation, the turn hook as a sink that
    knows no vendor, and how to add a kind.
    - `app/agents/adapters/` routes by pattern — one module per kind — never by a list, so adding a
      kind edits no document.
    - Each adapter's docstring owns its vendor's facts, moved down from the architecture's decisions.
  - [the application's structure](../../app/application/docs/architecture/structure.md): `settings`, the
    one loader and validator; the agents' preflight in `prepare`; tracing passed across as plain data;
    and the persona resolver's invariant, now also at a run's start;
  - [the foundation's structure](../../app/foundation/docs/architecture/structure.md) and
    [its main view](../../app/foundation/docs/architecture/diagrams/main.md): `.orchestra/`, the merge
    patch, its sparse writer and revision, `MAX_PERSONA_BYTES` and the wire invariant it serves, the
    role contract's access, and the one persona resolver's two rules;
  - [the workspace's structure](../../app/workspace/docs/architecture/structure.md): `.orchestra/repos.json`,
    `ORCHESTRA_REPOS`, and a preflight of `git` alone;
  - [the observability's structure](../../app/observability/docs/architecture/structure.md) and
    [its main view](../../app/observability/docs/architecture/diagrams/main.md): the private folder, its
    sweep and the uploader's run, with no vendor's settings of its own;
  - [the interfaces' structure](../../app/interfaces/docs/architecture/structure.md): the settings API and
    the Settings view's module;
  - [the trace contract](../../docs/architecture/trace-contract.md): a step's metadata names its kind and
    profile, model and effort, where it names the brain today;
  - [docs/using.md](../../docs/using.md): the Settings view, and the new names;
  - [README.md](../../README.md): the configuration table — `.orchestra/settings.json`, the local patch,
    `.orchestra/repos.json`, `ORCHESTRA_SETTINGS`, `ORCHESTRA_REPOS`, `--settings` — and the skills
    route, now the Settings view;
  - [tools/README.md](../../tools/README.md): the new names;
  - [tests/README.md](../../tests/README.md): the rows of the modules whose guards change, and one each for
    `application/test_activities.py` and `application/test_settings.py`.
- **Duplication avoided:** the schemas are the validator's, and documents name them rather than list
  them. RFC 7396, RFC 6901 and the Agent Skills name rule are cited, never restated. A vendor's
  mechanics live in its adapter alone.
- Stable docs, code, comments, tests and configuration will not reference this todo.

## Rollout and rollback

- **The move and the rename:** the stack's scripts, the Makefile, the systemd unit and the demo change
  with the code, so a stack restarted on the new checkout finds its settings.
- **The upgrade, in order:**
  1. with no role turn at work — a turn cut short by its worker's restart stops the run, to be
     continued (the architecture's D16);
  2. `make down`, on the old code;
  3. the new code, and this checkout's `repos.json` moved by hand;
  4. `make up`;
  5. `make workbench-restart`, since the page is outside the stack (the architecture's D32) and would
     otherwise keep the old code, which reads a `policy.json` no longer there.
- **The operator's own `repos.json`:** moved once into `.orchestra/`, by hand, in this checkout (task 2).
  In any other checkout, the loader refuses the one left at the root and names where it goes. It
  neither reads it nor moves it.
- **A variable set by hand under an old name** is renamed by hand; the code reads only the new names.
  `.env` never passed one to Orchestra's processes: they read only Langfuse's keys from it
  (`app/observability/telemetry.py:42-45, 91-97`), and Temporal's compose its own settings
  (`workers.sh:33-35`).
- **The settings folders a worker left before the upgrade** are removed by each host's first start on
  the new code (A1).
- **Open runs** keep working through the change (invariant 2).
- **Rollback of personal settings:** delete `.orchestra/settings.local.json`.
- **Rollback of the code:** a revert, in the upgrade's order.
  - A run started on the new shape cannot go on under the old code, which reads no profile or kind.
    Such runs are finished or stopped first.
  - `.orchestra/repos.json` goes back to the checkout's root by hand. The old code never reads the local
    patch, which can stay.

## Completion criteria

- Every guard observed red, then green, and each task's touched concerns green as it goes.
- `make demo`, `make public-check` and `git diff --check` pass on the finished implementation. The
  whole suites passed after the external PASS. The later Settings delivery change was checked by the
  whole WSL suite and focused Settings delivery tests on both WSL and Windows, following the
  deterministic-test rule in [tests/README.md](../../tests/README.md); a failure is reported as one,
  never counted as a pass.
- U1 and U2 measured before the adapters were built, and the design adjusted to what they found.
- The Settings-to-run deterministic gate passes on both hosts (D14); further real-agent behavior
  belongs to the independent UX and flows todos.
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

### 2026-09-27 — the external review: PATCH, three integration details

- **Accepted, each checked against the code:**
  1. **A local patch never changes which stack the settings are.** `stack.own()` compares the recorded
     origin (fact 32), so a layered load's origin is `.orchestra/settings.json`, never the patch. It
     comes with its guard and control.
  2. **`available()` in the loader.** It finds kinds by the package's public modules, through the same
     naming rule and contract check, and nothing lists them. Proven by a module planted on the
     package's search path.
  3. **The repositories' move fails safe.** A root `repos.json` alone, or both files, is refused; the
     loader never reads or moves the old one; this checkout's own file is moved by hand in task 2.
- **Refined:**
  - "No hard-coded list of kinds, including tests": tests may name the kinds they test, and an
    adapter's own tests must. The ban holds for production code and the page, as the review's closing
    instruction says.
  - "A run may fall back to Orchestra's own checkout": not for a named repository, which is refused as
    one that "does not exist" (fact 33). The harm is that refusal's misleading reason and a picker
    offering nothing — the fix stands as given.
- **Authority:** A1, A7 and A8 rewritten in place; invariants 6, 11 and 11a. No decision changed.

### 2026-09-27 — the external review: PATCH, two integration gaps; the operator's naming

- **Accepted, each checked against the code:**
  1. **`ORCHESTRA_REPOS` against "`.orchestra/repos.json` alone".** The two contradicted each other.
     The variable now takes its file alone, and the checkout's files, legacy included, are looked at
     only without it. It comes with guards for the explicit case.
  2. **The preflight's `brain == executable`.** `repos.resolve` looks up each brain's name as a
     command (`repos.py:185-187`). That is a ninth coupling edge (fact 18), which the adapter's
     commands answer now removes (Decision 1, invariant 3c, guard 11).
- **Refined:**
  - The preflight needs no host argument. `prepare` runs on the target host itself (`workflow.py:128,
    389`), so an adapter answers for its own host, as it does for its launch command. The adapter names
    its executable once, so its preflight and its launch cannot disagree.
  - A file `ORCHESTRA_REPOS` names that does not exist is refused, rather than read as "no
    descriptors".
- **Added here:**
  - the public check misses the moved private files, measured (fact 34; invariant 11b);
  - the suite reads the operator's descriptors (fact 35; invariant 7);
  - under D12, the sweep also removes the old prefix, because those folders hold the trace store's
    key (A1, guard 12).
- **Authority:** D12 added. A1 and A8 rewritten in place; Decision 1 and 5; invariants 3c, 7, 11 and
  11b.

### 2026-09-27 — the external review: PATCH, the preflight's owner; the architect's audit: PATCH

- **Accepted from the review, checked against the code:** the agents' preflight moves out of
  `repos.resolve`, the repositories' owner, into `prepare`, and each adapter names one `executable`
  that its launch and the preflight share (fact 47; Decision 1; invariant 3c; guard 11). The todo's
  earlier "commands its turn needs" becomes that one name: `node` serves only Codex's uploader, after
  the turn.
- **Found by the audit, each with its evidence, and fixed here:**
  1. `policy.py` cannot load adapters: the foundation imports nothing of ours. So kind validation is
     composed in `application.settings`, the one loader (fact 36; A7; Decision 5; invariant 5).
  2. Per-kind environment hygiene would give Codex agents Claude's markers, against the architecture's
     D17. So every agent now loses every kind's markers (fact 37; invariant 3d; guard 13).
  3. Tracing is more than an environment and records: a key-bearing file, a vendor uploader run after
     the turn, and rollout reading. It is now split as plain data, with the keys' folder staying
     generic (fact 38; A7; invariant 3e; guard 14).
  4. A4's bound was reasoned on one payload, while every turn carries both personas. The bound is
     kept, with the history budget measured (fact 39; invariant 10; guard 16).
  5. `prompt_path` would resolve new persona files from `.orchestra/`. The one resolver gains the new
     rule, with no second resolver (fact 40; Decision 3).
  6. The verdict's grammar stays one generic parser, and adapters only locate messages (fact 41;
     invariant 3f; guard 2).
  7. The trust guard knows only today's calls, and would stop protecting the operator's CLI
     configuration (fact 43; invariant 14; guard 15). Tools and the acceptance run name brains for
     trust (task 3).
  8. CI checks a copy of the public check, already drifted. CI now runs the script (fact 44;
     invariant 11b).
  9. Concurrent Applies could lose an update. So an Apply carries a revision under one lock; a refusal
     names its setting by JSON Pointer; a patch that does not load is shown, not fatal (fact 45;
     Decision 5; guard 6).
  10. `--policy PATH` is renamed `--settings PATH`, taken alone (fact 46; A1).
  11. The old shape is read only from a run's input — by `prepare` too — through the adapters' old
      brain names, and the loader refuses it (A6; A7; Decision 3; guard 4).
  12. The architecture's D19 still called a stage's skill code (fact 48). Vendor mechanics at the
      architecture's level move down to the adapters, and the trace contract's metadata follows
      (Decision 7; Documentation plan).
  13. Rollout and rollback gain their order, the Workbench's restart, and what a revert costs a run on
      the new shape. The stack's hand-set keys say when they take effect.
  14. U1 and U2 are measured before any adapter is built, and U2's answer decides guard 17. U3 now
      covers a replace over a file Windows holds open.
  15. The demo's and the acceptance run's own Workbench would have written the operator's local patch.
      Settings named by `ORCHESTRA_SETTINGS` are now read-only there (A1; invariant 6; guard 6).
- **Authority:** A1, A4, A5, A6 and A7 rewritten in place; Decisions 1, 3, 5, 6 and 7; invariants 3,
  3a–3f, 5, 7, 8, 10, 11, 11b, 13 and 14; a numbering note on the register. No decision changed.

### 2026-09-28 — the external review: PATCH, two settings corrections

- **Accepted, each checked against the code:**
  1. **`workspace_access` leaves the settings.** It has one valid value per role
     (`policy.py:197-200`), so it was a knob with nothing to choose. The role's contract holds it,
     `client.start` writes it into the run's policy, where the role-runs read it today (fact 50), and a
     kind unable to run with it is refused. Old runs read what they stored (Decision 4; guard 18).
  2. **The persona bound is proven on Temporal's own wire.** `DataConverter.default` escapes every
     non-ASCII character (fact 39), so a persona's wire bytes are not its UTF-8 bytes.
- **Measured now, rather than left to the guard:** at 64 KiB each, a `run_role` input crossed
  256 KiB for every class but plain ASCII letters — quotes and newlines as well, which double on the
  wire, and control characters, which grow sixfold. `MAX_PERSONA_BYTES` is 16 KiB: 198,755 bytes in
  the worst case, 100,451 for any text (A4; invariant 10; guard 16).
- **Refined:** only the settings drop `workspace_access`; the run's policy keeps it, written at the
  start. D13's list of configuration loses access (Decision 7).
- **Noted, not this change's:** the Windows suite gate recorded in
  [the Workbench UX todo](../2026-09-25_2334-workbench-ux.md) is still red on the test runner's tree
  wait, and waits on the operator's disposition there.
- **Authority:** A2, A4 and A7 rewritten in place; Decisions 2, 3, 4 and 7; invariants 4 and 10;
  guards 4, 16 and 18. No decision changed.

### 2026-09-28 — the external review of the implementation: PATCH, four integration defects

- **Accepted, each checked against the code, and fixed:**
  1. A finished Windows class's job was only closed, which begins its processes' end without proving it,
     and `end()` printed an unproved end and went on. Every class now leaves through the one proved end,
     and an unproved end fails it ([the Workbench UX todo](../2026-09-25_2334-workbench-ux.md) holds the
     runner's record). A POSIX class's group is ended when it finishes, too.
  2. `/api/flows` reads the settings, so a local patch that does not load failed the read that listed the
     flows, and the Settings view never showed its refusal. The view reads the settings first, and lists
     flows only for settings that load.
  3. New run kept the flow it showed over a newly applied default. It now takes up a new default, unless
     the operator chose a flow there, and an Apply asks it to read the flows again.
  4. The acceptance run read a settings role as a run's role. It resolves each role's kind through
     `application.settings`, as production does.
- **Evidence:**
  - runner: its tests on both hosts, and the close-only mutation, as the UX todo records;
  - page: the headless probe's 23 checks pass; with fixes 2 and 3 taken back, four of them fail.
- **Declined:** the whole Windows suite now. By the standing order, each host runs it once after the
  external PASS, and this change runs in that one.


### 2026-09-28 — settings implementation

- Shipped four role-specific agent profiles, preferred Claude role bindings, the accepted stage skills, and 10 normal + 10 extended review budgets. The settings page discovers skill names through adapter-owned roots, stages Reset for page-owned settings, and continues writing sparse local patches; unrelated local settings survive.
- Added version-gated routing for new `review_rounds` runs, a code-owned convergence reflection, and evidence summary at exhaustion. Old run policies with `max_rounds` keep the recorded route. Focused Temporal replay passed.
- Updated the current settings owner and user/architecture/test docs. Replaced stale `policy.json`/`ORCH_POLICY` examples with `.orchestra/settings.json` and `ORCHESTRA_SETTINGS`.
- Focused Windows verification passed: 26 classes, 158 tests, including settings Apply/Reset/reload, policy shape and layers, adapter skill discovery, Workbench API, workflow thresholds, replay, observability and architecture boundaries. `node --check`, settings JSON parse, and `git diff --check` passed. The focused Settings browser probe from this task passed before the final additions of control names and removal of the legacy budget from Reset; those last edits do not change the interaction path.
- Claude Code 2.1.283 and current Anthropic model docs support the selected `claude-opus-5` and `claude-fable-5` IDs. The installed Codex CLI 0.153.4 model catalog lists `gpt-5.6-sol` but not `gpt-6-luna`; the shared Codex engineer profile keeps the operator-selected ID, with local execution pending a Codex CLI update. No system-wide CLI update was performed.
- Per the accepted gate, the full WSL and Windows suites and the final live Workbench walkthrough remain deferred until external implementation PASS.

### 2026-09-28 — PATCH checked against the code; four fixes and synthetic gates

- **Accepted and fixed:** `round` owns the bounded `review_rounds` episode, while `phase_rounds` stays
  cumulative until `_next()` enters another phase. Routing, reflection, exhaustion, role trace data and
  the final-summary prompt now read the budget counter. Guidance, plan reassessment, final revise and
  merge-conflict re-entry clear convergence state without resetting the trace count.
- **Accepted and fixed:** discovery lists a directory only when it contains `SKILL.md`, matching the
  worker preflight. Its test includes both real skill markers and an empty-directory control.
- **Accepted and fixed:** Settings Reset no longer sends a revert for hidden legacy `max_rounds`; the
  Apply test and browser probe prove that it and an unrelated local timeout survive.
- **Accepted and fixed:** current `.env.example`, README, `app/README.md`, workspace docs, user guide and
  tools guide use `.orchestra/repos.json` / `.orchestra/repos.example.json` and `ORCHESTRA_REPOS`. The
  old root `repos.json` remains named only where code refuses the old layout or historical material
  explains the migration.
- **Found while running the required demo:** its fake CLIs expect the Claude engineer and Codex architect
  contracts, but it inherited shared role bindings. The demo now pins those roles in its temporary policy;
  shared defaults are unchanged. The first demo run failed at the architect output, cleaned its run,
  worker, Workbench, repository and trust records, and the rerun passed all six runs and removed its
  Temporal records.
- **Verification:** 14 focused Windows test classes, 58 tests passed (workflow routing, both round-count
  regressions, Settings/application and activities); the isolated Settings browser probe completed Reset
  and Apply with API 200s, its POST omitted `/max_rounds`, and the response retained `max_rounds` and the
  unrelated local timeout; `node --check`, `git diff --check`, `make public-check` and `make demo` passed.
  The wider initial Windows selection also hit unrelated host-bound tests: a cross-drive relative path in
  the telemetry file-error test and entry-point tests that invoke GNU make directly from Windows.
- The full WSL and Windows suites and final live Workbench walkthrough remain deferred until external
  implementation PASS.

### 2026-09-29 — Settings UX and round guidance

- Collapsed the profile table and creation controls behind a count-bearing disclosure while keeping role bindings, round budgets and the default flow visible. Added a disclosure with four labeled, role-specific prompt additions: after normal rounds and at the final allowed iteration.
- The built-in normal reflection asks each role to examine its own work and the opposite role's evidence. At the budget limit, the engineer is asked for its factual handoff in its final message, and the architect's evidence prompt directs it to inspect that message in the role-run log; the architect's exhausted feedback separates Engineer contribution from Architect assessment. The handoff prompt does not modify the reviewed todo. Custom additions follow the code-owned instructions, are shared across Plan and Build, and have a combined 4,096 UTF-8 byte limit.
- Updated the user guide and package owners for the new behavior. Windows focused verification passed: 4 classes, 44 tests; JavaScript syntax, shared settings JSON and git diff check passed. The live Settings API returned 200; the profile and prompt disclosures rendered, all four prompt fields staged without Apply, and a 390 px layout had no horizontal overflow. A page reload cleared the temporary UI-only draft; no settings Apply was sent.
- Full WSL and Windows suites and the final live Workbench walkthrough remain at the accepted external review gate.

### 2026-09-29 — PATCH: built-in guidance and compact Settings hierarchy

- **Accepted and fixed:** architect convergence and exhaustion prompts retain Orchestra's BLOCKER
  meaning for unsafe premises or architecture, accepted-invariant conflicts, locally unrepairable
  blockers, D15's harmful or mismatched tasks, and a specific human or external decision. The prompt
  contract is tested at both boundaries.
- **Accepted and fixed:** code-owned review prompts are exposed read-only from `nodes.py`; Settings
  presents them before optional per-role additions. The empty shared `review_prompts` scaffold is
  removed. Policy validation now accepts sparse event/role additions while continuing to reject
  unknown keys and oversized content; a single-leaf Apply/revert test proves the shared policy needs
  no empty scaffold.
- **Accepted and refined:** Settings shows roles, compact `normal + after reflection = max` budgets,
  then Default flow. Agent profiles and advanced guidance are collapsed by default. Disabled Apply is
  neutral and Reset is hidden without a visible override. Desktop max width is 1160 px; mobile skill
  input sizing keeps the longest built-in skill name visible at 390 px.
- **Reviewer corrections:** Agent profiles were already collapsed in the prior UI. The screenshot's
  claim of abundant unused width does not hold at 1080 px, where the sidebar and page padding leave a
  761 px settings column; widening still improves larger desktop windows. Removing the blank prompt
  scaffold alone would have made sparse additions fail the old strict event/role validator, so that
  validation contract was updated with the sparse setting.
- **Verification:** 6 focused Windows test classes, 87 tests passed; JavaScript syntax, shared settings
  JSON parsing and `git diff --check` passed. The Workbench API returned built-ins matching runtime
  constants, the Settings browser probe verified additive editors and live budget totals without
  applying settings; the 390 px viewport has no horizontal overflow and the longest skill label
  measures 168.6 px against 178 px of input content width. Desktop collapsed and Advanced-open
  screenshots were captured; the browser screenshot helper timed out on the final mobile capture, so
  that layout was verified from viewport and input geometry instead. No settings Apply was sent.
- Full WSL and Windows suites and the final live Workbench walkthrough remain at the accepted external
  review gate.

### 2026-09-29 — PATCH: convergence prompts and Settings wording

- **Accepted and fixed:** the final engineer prompt now asks for a concise handoff in its final message, not the reviewed todo. The architect's evidence prompt directs it to inspect engineer plan/build reports in their per-run logs, so the existing evidence path can carry the handoff without adding workflow state or changing the approved artifact.
- **Accepted and fixed:** after-normal guidance now asks both roles to audit their own work/review, check the opposite role's evidence, identify scope boundaries, and continue normal work. Final-turn guidance requires a factual engineer report and explicit operator-handoff sections from the architect for PATCH/UNVERIFIED.
- **Accepted and fixed:** the review-guidance disclosure now names optional additions, says built-in instructions always apply, and labels the second budget **After reflection** while preserving the `extended` settings key. The user guide uses the same visible term.
- **Verification:** the Windows focused run passed 2 classes / 25 tests (`Routing`, `TraceShape`). The regression checks one reflection per role at the boundary, its absence on the following round, final-turn handoffs, empty additions, and additive custom guidance; a control restoring the old todo-handoff prompt failed at the expected assertion. `node --check` and `git diff --check` passed. The fresh Settings read returned HTTP 200, displayed the revised copy and four empty role fields at 390 px with no horizontal overflow, and no setting was applied.
- Full WSL and Windows suites and the final live Workbench walkthrough remain at the accepted external review gate.

### 2026-09-29 - final Settings evidence

- Captured fresh final-tree screenshots at desktop default, desktop Advanced with the after-normal event and one built-in instruction open, and 390 by 844 mobile default. At 390 px, the profile and Advanced disclosures are closed and the document has no horizontal overflow.
- The final UI checklist found that `main:focus` suppressed the skip link target's focus ring. Added a `main:focus-visible` outline and confirmed its computed style in the live page. Settings HTML, CSS and JavaScript otherwise pass the checklist.
- The live page read `/api/settings` and `/api/flows` successfully; its background `/api/repos` request returned 400. This did not prevent Settings from rendering and remains a separate, undiagnosed Workbench issue.
- `make public-check` and `git diff --check` passed after the CSS fix. No Settings changes were applied in the browser.
- `make demo` remains pending: `tools/README.md` documents writes to the configured real Langfuse project when credentials exist, and the required operator authorization for that external write has not arrived. Full WSL and Windows suites remain deferred until the external review gate.

### 2026-09-29 — final acceptance attempt after the descriptor migration

- Per the operator's GO, moved the ignored root `repos.json` to `.orchestra/repos.json`; its 2,744-byte size and SHA-256 matched across the move. The settings service has no `ORCHESTRA_REPOS` override. The repository loader accepted 35 entries, and a fresh authenticated `GET /api/repos` returned HTTP 200 with the same repository set.
- Ran `make demo` with dummy Langfuse credentials and `LANGFUSE_HOST=http://127.0.0.1:65535`. All six runs passed; the demo reported its Workbench, worker, temporary repository, trust records, and Temporal records removed. `make public-check` and `git diff --check` passed. No production code changed.
- The conditional implementation gate passed. The once-only whole suites did not: WSL reported 121 classes / 524 tests and failed `tests.orchestration.test_workflow.Flows`, `tests.observability.test_trace_parity.TraceParity`, `tests.agents.test_trust.Wiring`, and `tests.interfaces.test_workbench.Runs` (600-second class timeout). Windows reported 83 classes / 385 tests and failed the first three.
- Focused reproductions confirmed test/config drift: the client and Workbench tests use Codex-formatted fake reviewer output while runs load the shared Claude architect profile; the trust wiring assertion still expects both `claude-code` and `codex` although both shipped roles now use `claude-code`; and the trace golden lacks the current engineer profile's model/effort metadata. The one Workbench test reproduced the malformed reviewer output and exhausted its 120-second wait.
- Headless Windows launch check: ran `tests.agents.test_launch.DetachedProcessTree` through `run-tests.ps1` in a hidden PowerShell process with output redirected; all 8 tests passed in 14 seconds. The runner does not request `CREATE_NEW_CONSOLE`; its process trees inherit the hidden host console. This proves the launch path for this Windows process-tree class, not a hidden rerun of the entire suite.
- Disposition: suite acceptance remains red. The Workbench/worker restart and real `architect-research` walkthrough were not run; the deferred Workbench UX walkthrough remains deferred. Keep this todo in progress until the test fixtures are reconciled and the required gates are satisfied.

### 2026-09-29 — configured-agent fixtures reconciled

- The failing tests were stale against the checked-in configurable profiles, not production regressions. Provider-shaped fake review output now follows the role's bound kind in client and Workbench run scenarios; trust wiring expects the distinct kinds in the run policy; and the trace rows include the current engineer profile name, model and effort.
- The four focused reproductions passed after the fixture updates. The full WSL suite passed: 121 classes / 545 tests. The full Windows suite passed: 83 classes / 385 tests. `make public-check` and `git diff --check` passed.
- The Windows process-tree class also passed through hidden PowerShell: 1 class / 8 tests. The regular Windows suite runs through the same host test script without requesting a new console per class.
- Restarted the stack with `make restart` and the Workbench with `make workbench-restart`; `make check` reports Temporal, both workers and Workbench up. A fresh Workbench load returned HTTP 200 for `/api/repos` and `/api/flows`, and Settings shows the configured Claude profiles. The prior root-descriptor error was stale page state and cleared after a full reload; the old root path is absent and `.orchestra/repos.json` remains the original 2,744 bytes.
- No live run was started. The real walkthrough can emit an external Langfuse trace using credentials loaded from `.env`; a `systemd-run --scope` control showed that shell-provided dummy Langfuse variables do not reach the WSL scope, so that route does not prove the run is local-only. The live walkthrough remains pending the operator's choice about one real Langfuse trace or a separately proven local-only route.

### 2026-09-29 — convergence diagnosis wording

- The review correctly identified that the final architect handoff had only a broad `Likely cause` label and omitted legitimate complexity and mixed/unknown causes. The bounded fix updates the code-owned reflection and final handoff prompts; it preserves workflow state, Settings shape, verdict routing, and BLOCKER semantics.
- Both normal-boundary prompts now ask for an evidence-backed diagnosis, self-review, and ordinary continuation. The final architect PATCH/UNVERIFIED handoff uses `Why not converged` with cause classes, evidence, unresolved and disputed findings, and any exact operator decision. The user and architecture guides describe the updated handoff.
- `tests/__init__.py` pins `ORCHESTRA_SETTINGS` to the shared settings file, so the profile-bound fixture helpers do not read a private local settings patch. The focused Windows `Routing` and `TraceShape` classes passed: 2 classes / 25 tests. `git diff --check` passed.
- The prior full WSL and Windows suites remain green. The final live walkthrough is still pending explicit operator authorization for a normal Langfuse trace or a separately proven local-only route.
- The final engineer handoff now asks for its own evidence-backed non-convergence diagnosis. It names the compact cause classes because `extended=0` can reach that turn without a prior reflection. Two focused Routing cases failed on the old prompt and passed after the correction; `git diff --check` passed. With no open feature runs, the stack and Workbench were restarted on the final code; `make check` reports all components up.

### 2026-09-29 - local-only live walkthrough, stopped by Claude usage limit

- The operator deferred Langfuse pairing for Settings acceptance. The earlier conclusion that `systemd-run --user --scope` drops shell environment values was a command-quoting error: a harmless sentinel reached a scoped child. Explicit dummy Langfuse keys and a loopback-only host override `.env` in the WSL worker. The disposable run targeted WSL; the Windows worker's separate WMI launch does not inherit this override. A CLI Stop under the same override reported connection refused at the loopback trace host. Langfuse was not an acceptance dependency.
- Applied a temporary architect binding to the existing Codex profile, started one disposable WSL `architect-research` run through Workbench, then applied the original Claude binding again. Settings showed no pending changes. The active run still used Codex for both research and the later assessment: its terminal showed the configured model and effort, and both saved architect prompts began with `$architect`. The engineer's first prompt began with `/investigate-change`, and its Claude terminal ran the plan. Each live terminal accepted a typed character and Backspace without submitting a turn.
- The first research approval and the plan review loop worked. The architect's PATCH correctly identified that testing only the CLI's default name would miss a hardcoded greeting. On the engineer's revision turn, Claude Code exited with `StopFailure` / `rate_limit` and reported a usage-limit reset at 3pm Europe/Moscow. Retrying before that reset would repeat the provider refusal. No plan approval, build, verification or final merge/discard gate was reached.
- Stopped the run with Orchestra's CLI, then used the Workbench's authenticated local removal API. Workbench showed `STOPPED`; Git showed no run branch or worktree. The disposable base fixture and its empty worktree category were removed. The WSL worker was restarted in its normal environment; `make check` showed Temporal, both workers and Workbench up. During browser automation, confirmation dialogs closed without sending their action, and a fresh dialog control also failed to emit a `close` event in that browser backend. This does not establish a product UI defect; the human confirmation path remains unverified by this attempt.
- Keep this todo in progress. The live acceptance still needs the later plan approval, build, verify and final Discard path when the chosen engineer provider is available. The previous full WSL and Windows suites passed before the final prompt-wording patch; its focused regressions passed afterward.

### 2026-09-30 - joined Settings-to-run smoke with fake agents

- Added one Workbench API smoke on the existing disposable Settings checkout and Temporal fake-agent harness. It applies an architect-research default flow, role/profile/model, persona, skill, review budget, and per-role guidance overrides; starts a run; changes Settings again; then checks the original run's research, plan reflection and exhaustion, guidance re-entry, approval, build, verification and final Discard. The recorded fake invocations prove the open run retains its selected Claude/Codex kinds, model and effort arguments, persona, skill, prompt additions, and 2+1 plan budget despite the later Apply. The literal 10+10 boundary remains covered by `Routing.test_review_rounds_reflect_once_after_ten_and_exhaust_with_evidence_at_twenty`.
- Known-bad control: forced the run start to read the shared file while ignoring the applied patch; the smoke failed on the wrong first stage. Restoring the layered loader made it pass. Focused Windows smoke passed; focused WSL Workbench Settings API, Runs and Routing passed (3 classes / 40 tests); the full WSL suite passed (121 classes / 547 tests).
- This closes the Settings-to-workflow logic gap without provider calls. The accepted live operator check still owns actual CLI skill loading, terminal interaction and human confirmation controls; the earlier walkthrough did not reach plan approval, build, verification or final Discard.

### 2026-09-30 - Settings delivery regression suite

- Moved the joined smoke into `tests/interfaces/test_settings_delivery.py` and expanded it into a Settings API to client to Temporal to scripted role-turn suite. It covers both shipped flows; an applied default and an explicit flow; role bindings, newly added and removed profiles, models and effort, personas, all five stage skills, Plan and Build normal/extended budgets, each role's reflection and final-turn addition, later Apply leaving an open run unchanged, restored settings reaching a new run, invalid local settings refusing a start, and final Discard. `tests/orchestration/test_round_boundaries.py` adds PASS and BLOCKER controls at the literal 10 and 20 review boundaries. Existing Settings API tests retain Apply, Revert, Reset and conflict coverage.
- A previously hidden source mismatch surfaced when the joined test stopped patching the loader: a Workbench with its own `root` and `environ` read and applied settings there, but `POST /api/runs` started from the client's default settings source. The smoke failed on `plan-e1-1` instead of the configured `research-e1-1`. The Workbench now passes that same source to the client for run start; the formerly failing smoke passed without a loader patch.
- Focused WSL verification passed: 20 classes / 104 tests across Settings delivery, Workbench and workflow. Focused Windows verification passed: 2 classes / 5 tests for Settings delivery and exact round boundaries. The full WSL suite passed: 123 classes / 551 tests. `make public-check` and `git diff --check` passed. The extra 10th-round BLOCKER case was added after these runs and checked separately on both hosts. These scripted turns prove what Orchestra sends to the runner seam and how its workflow routes; vendor skill loading, prompt interpretation and real terminal interaction still belong to a real-agent check.
- A final coverage audit found that the literal 10+10 budget and prompt checks entered the workflow directly, while the Settings API smoke used 2+1. Added joined Settings API cases for Plan and Build 10+10 and all four role/event additions. Each proves no boundary guidance at turn 10, one reflection per role at turn 11, none at turn 12, both final handoffs at turn 20, the exhausted stop, guidance re-entry and Discard. A focused rerun exposed a test race: Discard's API acknowledgment precedes its Git activity. The suite now waits for the run's `DISCARDED` state before asserting cleanup. The updated focused suite passed on WSL and Windows: 2 classes / 7 tests on each. This covers the exact Settings-to-run boundary without asserting that every combination of editable values or a vendor's prompt interpretation has been exercised.
- **Deterministic Settings gate: passed within its stated contract.** The scripted tests exercise the real Settings Apply, run snapshot, flow selection, Temporal workflow and activity path through the role-turn seam, then assert the selected kind, model, effort, skill invocation, persona, per-role review guidance, round boundaries and resulting stops. D14 supersedes the Settings-specific live gate. The UX and flows todos independently own any remaining real-agent walkthrough.
- The operator closed this manually authored todo under D14 before a commit. Moving it exposed a
  `public-check` export defect: it attempted to copy the removed tracked path, silently skipped that
  copy and reported PASS. The export now skips deleted working-tree paths whose old content remains
  in history, and records any other copy failure while keeping its tracked-file boundary. The
  corrected `make public-check` passed without a missing-file error; the new todo file will be
  scanned once staged by the operator. All 30 local links in this moved todo resolve.
