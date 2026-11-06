# Guidance goes to the role you choose, an agent's answer in one press

**Status:** BUILT 2026-11-06 — the reviewer's PATCH taken: red, then green. It awaits the reviewer's final pass,
the full suite then, the operator's deployment — the Workbench's restart for the answers' order — and their word
to close it.
**Scope:** a stop's guidance answers ([workflow.py](../app/orchestration/workflow.py) `GUIDED`, the loop's
`review_next`), whom a stop's words go to ([client.py](../app/application/client.py) `recipient`), what the run's
view carries at a stop that takes guidance ([server.py](../app/interfaces/workbench/server.py) `role_reply`), how a
kind reads its own reply from its events (`reply` in [adapters](../app/agents/adapters/__init__.py),
[codex.py](../app/agents/adapters/codex.py), [claude_code.py](../app/agents/adapters/claude_code.py)), the stop's
card ([run.js](../app/interfaces/workbench/static/run.js), [index.html](../app/interfaces/workbench/static/index.html))
and the command line ([cli.py](../app/interfaces/cli.py) `answer_line`).
**Stable documentation owner:** D6 in the [architecture](../docs/architecture/structure.md) and its
[stops](../docs/architecture/diagrams/stops.md); [using.md](../docs/using.md); the interfaces' and agents'
structure.

## Goal

At a stop that takes guidance the operator says whom it is for — the engineer, whose work goes on, or the
architect, who judges the work as it stands again — and what they settled with an agent in its terminal is sent
on with one press, nothing copied by hand.

## Authority register

### Operator decisions

- **D1** One press sends the agent's last answer on, whichever agent the operator talked with.
  - 2026-11-06, operator: *"how to very quick with one click I could proceed this last guidance to ingeener, need
    copy paste or just one button that somehow get last architect response and send it to ingeener?"*; then
    *"if we are talknig with architect then button works for ingeener since we could speak to architect
    directly , if talk with ingeener then button will be work for architect vise versa?"*
- **D2** Guidance names whom it goes to: one button for the engineer, one for the architect.
  - 2026-11-06, operator: *"after I press guide (means to architect, becasue I don't talk withit ) - ingeener
    receive works, need to proper name button then!"*; *"I guess better 2 buttons - one for architect , 1 for
    ingeeneer if system can't decide, please double check"*

### Decided by the agent, by the direction set

- **The system cannot decide it:** a blocker or exhausted rounds come only from the architect's review of the
  engineer's work, and the operator's words may mean the work must change or the judgement must; only they know.
  So both are offered, as the final gate's revise is.
- **The architect's route is the review again:** `guide:architect` sets the guidance and has the architect judge
  the work as it stands — the loop's `review_next`, which a plan changed at approval already takes — the engineer
  taking no turn first. Behind `workflow.patched("guide-the-architect")`, so a run recorded before it replays
  offering the one route it did (D25).
- **Whom plain guidance goes to is the view's:** `client.recipient`, from the workflow's stages, never a copy in
  the page.
- **Still a press, never on its own:** a stop waits for the operator by design, and only their press — recorded
  as the stop's answer — moves the run; a terminal is evidence, never a way to answer the workflow.

## Verified evidence

- **The talk is already recorded.** Each kind's hook writes each answer into its role's newest turn's events,
  the operator's talk at a stop included — on the operator's run, *guide ingeener* answered by the architect's
  handoff. Codex's own catch-up summaries come from threads of their own; a reply in its session lists the
  inputs so far, the newest the operator's words. Claude's `Stop` names the prompt it answers.
- **Guide went to the engineer, unnamed.** On the operator's run, guidance written for the architect at its
  blocker became the engineer's next plan turn's — the route was right for the words' half that was the
  engineer's, and the button never said where they would go.

## What changed

- The workflow: a blocker or exhausted rounds offer `guide` and `guide:architect`; the latter's guidance has the
  architect judge the work as it stands again, no work turn first.
- `client.recipient`: whom a stop's words go to when its answer names none; the run's view's stop carries it.
- `adapters.reply`, `role_reply`: what the role talked with last answered the operator since its turn.
- The stop's card: *Guide the engineer* and *Guide the architect*, each saying on hover what follows; an agent's
  answer offered under *Send to the engineer* and *Send to the architect*, the one not talked with first.
- The command line: `guide architect <your guidance>` listed among a blocker's answers.
- Docs: D6 and the stops diagram; using.md; the interfaces', agents' and application's structure; the tests'
  and tools' READMEs.

## Review record

- **External reviewer, 2026-11-06 — PATCH, three findings and two checks, each taken:** the workflow's route to
  the architect passed on its logic. (1) `guide architect` with no words became guidance *architect* for the
  engineer — now no answer at all, and the run waits on. (2) The role talked with last was taken from which record
  changed last, and a record gains events that answer no one — Codex's catch-up summaries among them, seen on the
  operator's run — so the hook stamps each event with when it recorded it (`_at`), and the answer given last
  decides; a record older than the stamp keeps its file's time. (3) The card's key left out who answered, so the
  other's same words kept the old name and order — now in the key. The checks: guidance to the architect at
  rounds run out, and a browser check that presses each destination and reads what it sends (`demo_press.py
  handoff`, in `make demo`).
- **External reviewer, 2026-11-06, second round — PATCH, one finding, taken:** the CLI, the card's key, the
  rounds-run-out route and the browser check passed. An answer recorded before the hook stamped events took its
  file's time, which an event answering no one can move past a stamped answer given after it. Every agent's hook
  runs the one script of this checkout, so an unstamped answer came before any stamped one: a stamped answer now
  ranks first, and files' times order only two unstamped ones.

## Verification

- **Red:** `tests.agents.test_adapters.Reply`, `tests.interfaces.test_workbench.RoleReply` — no `adapters.reply`,
  no `role_reply`; `tests.orchestration.test_workflow.Routing` — a blocker offering `['guide']` alone;
  the approval views in `tests.interfaces.test_workbench` — no stop `to`;
  `tests.interfaces.test_cli` — `"guide architect <feedback>"`.
- **Green on WSL:** `tests.orchestration.test_replay`, `tests.orchestration.test_workflow`,
  `tests.interfaces.test_cli`, `tests.interfaces.test_workbench`, `tests.agents.test_adapters`,
  `tests.test_architecture`, `tests.test_demo` — 211 tests, OK: guidance to the architect has it judge again with
  no plan turn and the words in its prompt; every recorded history replays.
- **On Windows:** `tests.agents.test_adapters`, `tests.agents.test_prompt_size`, `tests.interfaces.test_cli`,
  `tests.orchestration.test_workflow.Routing` and `.Sessions`, `tests.application.test_activities.LongPrompt` — 12
  classes, 59 tests, OK. `make demo` on the final code: DEMO PASSED, 116 checks, none failed.
- **A history of the new route:** `blocker_guidance_to_the_architect_stop`, recorded — 86 events, the
  `guide-the-architect` marker and the operator's words in it — and replayed with the rest.
- **On the operator's run, the first form:** its blocker card showed the architect's handoff under *Send to the
  engineer*; the operator pressed it, and the engineer's next turn, `plan-e6-1`, was given it as its *Operator
  guidance* — 1,822 characters, the part's heading and the handoff's 1,801.
- **The card, its run's status stood in for** (`tmp/agent/terminal-scroll/guide_card.py`, throwaway, nothing
  pressed): at a blocker, *Guide the engineer* first and *Guide the architect*, each saying on hover what
  follows; with the architect's answer offered, *Send to the engineer* first; with the engineer's, *Send to the
  architect* first.
- **The review's fixes, red then green:** `tests.interfaces.test_cli` — `guide architect` parsed as guidance
  *architect*; `tests.orchestration.test_workflow.Routing` — that answer started `plan-e2-1`, the run moved on;
  `tests.agents.test_adapters.Reply` — an answer without its time; `tests.interfaces.test_workbench.RoleReply` —
  the reviewer's sequence offered the architect's older answer; `tests.agents.test_terminal.Hook` — no `_at`. The
  rounds-run-out route passed at once: it is the blocker's branch. Green on WSL: `tests.interfaces.test_cli`,
  `tests.agents.test_terminal.Hook`, `tests.agents.test_adapters`, `tests.interfaces.test_workbench`,
  `tests.orchestration.test_workflow`, `tests.orchestration.test_replay`, `tests.test_architecture`,
  `tests.test_demo` — 217 tests, OK; on Windows `tests.agents.test_terminal.Hook`, `tests.agents.test_adapters`,
  `tests.interfaces.test_cli`, `tests.orchestration.test_workflow.Routing` — 9 classes, 40 tests, OK.
- **`demo_press.py handoff`, on the live Workbench:** the architect's answer offered *Send to the engineer* first;
  the same words, the engineer's, drawn anew with *Send to the architect* first; the four presses sent
  `guide:architect`, `guide`, `guide` and `guide:architect`, each with exactly its words, none reaching the
  Workbench. Mutation control: with who answered taken out of the card's key, it failed — *gave up waiting for the
  card to name the engineer* — and `run.js` was restored byte for byte.
- **`make demo`, the handoff check among its own:** DEMO PASSED, 117 checks, none failed.
- **The second round, red then green:** `tests.interfaces.test_workbench.RoleReply` — the architect's unstamped
  answer, its file moved to 300 by a later catch-up event, offered over the engineer's stamped at 200; green once a
  stamped answer ranks first — 4 tests, OK.
- **Live as saved, without a restart:** the hook (`turn_hook.py` is run afresh for every event) and the page's
  files. The Workbench orders answers by their stamps once restarted, which waits for the operator's deployment.
- **Not yet seen live:** the two routes on a real blocker. Temporal remembers a patch's answer for the whole run,
  so a run that met a blocker before the WSL worker's restart replays it without the marker and keeps the one
  route for its life — the operator's run among them; a run that meets its first blocker after the restart
  offers both.
