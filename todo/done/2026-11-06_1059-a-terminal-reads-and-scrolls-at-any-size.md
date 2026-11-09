# A terminal reads and scrolls at any size

**Status:** DONE 2026-11-09 — the goal met: proven on the live Workbench and in `make demo`, with mutation
controls; reviewer PASS; the full suite green on both hosts; closed on the operator's word.
**Scope:** a role's terminal on the run's page — its size, a way to read it large, its scrollbar, its copy
([terminals.js](../../app/interfaces/workbench/static/terminals.js), [index.html](../../app/interfaces/workbench/static/index.html),
[style.css](../../app/interfaces/workbench/static/style.css), and the size the page's config gives it in
[server.py](../../app/interfaces/workbench/server.py)) — and how Codex draws into it
([codex.py](../../app/agents/adapters/codex.py) `command`); their proof in [demo_press.py](../../tools/demo_press.py)
and [demo.py](../../tools/demo.py). The terminal's 160 by 48 on the host does not change.
**Stable documentation owner:** [using.md](../../docs/using.md) for what the operator sees; the agents'
[structure](../../app/agents/docs/architecture/structure.md) for how Codex is started.

## Goal

A role's terminal fits the page with nothing cut off, reads large with one press and back with another, and
scrolls through its whole session by wheel or by dragging its scrollbar — whichever agent is in it.

## Authority register

### Operator decisions

- **D1** A terminal fits its box, and a button maximizes it inside the page and restores it.
  - 2026-11-06, operator: *"this windows is very hard to read because it's not properly auto scale content - so
    maybe easily some button to maximize ot full scrren and minimize? check if some simple out of box could do"*;
    on maximizing inside the page rather than the browser's full screen: *"yes inside the page we should try"*.
- **D2** Its scrollbar works, for every agent.
  - 2026-11-06, operator: *"scrollbox don't work properly in windows agents - check what problem could be and
    verify live"*; *"the box that I could drag in scroll box isn't worked, becuase weird rendering, no matter
    codex , claude"*.

### Decided by the agent, by the direction set

- **Inside the page, not the browser's full screen:** there Esc leaves full screen, and Esc is how the operator
  interrupts an agent.
- **The font fits the box, the columns stay:** the host's terminal is 160 by 48 for every viewer, and the
  agent lays its screen out for that; xterm's fit add-on changes the columns, which would garble it.
- **Ctrl+C with text selected copies it.** The operator is told to copy an agent's words into Guide; without a
  selection Ctrl+C still reaches the agent, as in any terminal.

## Verified evidence

- **The scrollbar cannot be grabbed.** Measured on the live Workbench at the operator's window width (1032 px):
  the terminal's box is 687 px, its viewport — which carries the scrollbar — 669 px, its text 1,125 px (160
  columns at 12 px). The text lies over the viewport's right edge, so a drag of the thumb there selects text
  instead (shown as a grey selection); set by script, the same viewport scrolls the engineer's 4,400 lines.
- **Codex keeps nothing to scroll.** Its TUI takes the alternate screen (`?1049h`) and every mouse event
  (`?1003;1006h`) on both hosts; replayed into the page's xterm.js at 160 by 48, a resumed Windows session
  left 0 lines of scrollback and the mouse captured. With `--no-alt-screen` — offered by both hosts' Codex
  (0.159, 0.166) — it sets neither: the same replay left 151 lines, the session's history, and the wheel the
  page's. A turn resumed inline prints the session's history again, so earlier turns come again further up.
- **Claude's terminal scrolls** — no alternate screen, no mouse capture — once its scrollbar can be reached.
- **Ctrl+C is the agent's.** The page hands xterm.js's keys to the agent, Ctrl+C as `\x03`; in Codex a second
  one quits.

## Build

- **Fit:** the terminal's font is sized so its 160 columns and the scrollbar fit its box, again when the window
  or the box changes size.
- **Maximize / Restore** beside the terminal's name: the terminal fills the page's window, its font sized to it,
  until Restore.
- **Copy:** Ctrl+C with a selection copies it and sends nothing.
- **Codex inline:** `--no-alt-screen` on every Codex turn, fresh or resumed.
- **One size, one owner:** the page draws the grid its workers give a terminal from its config's `terminal_size`,
  which the server takes from `terminal.COLS` and `ROWS`, never a copy; Maximize's hint names the largest font
  from the same constant that caps it.
- **Proof:** `demo_press.py terminal-fit:<role>` — the text within the box, a drag of the thumb that scrolls,
  Maximize filling the window with a larger font, Restore, and Ctrl+C on a selection copying with nothing
  sent; `make demo` runs it. The workflow's test of Codex's arguments asks for the flag.

## Review record

- **External reviewer, 2026-11-06 — PASS:** the fixed grid, the fitted font, Maximize and Restore inside the page,
  the scrollbar's guard and Codex drawn inline, on browser checks that exercise layout, dragging and copying.

## Verification

- **Live, before the change** (`tmp/agent/terminal-scroll/drag.py`, throwaway): the measurements above, and a drag
  of the engineer's thumb that selected text and scrolled nothing.
- **Live, after it:** `demo_press.py terminal-fit:engineer` on the operator's run in a 1032 px window — its text
  647 px and scrollbar 15 px within the 687 px box at font 6.9; its thumb dragged from 40,000 to 19,093 of
  40,000, nothing selected; maximized 988 by 988 at font 10.1, restored at 6.9; Ctrl+C on a selection copied it
  and sent nothing, and with nothing selected reached the live agent (the stand-in dropped it). The architect's
  terminal, a Codex session still on its alternate screen, has nothing to scroll until its next turn.
- **Found while fixing, all three fixed:** xterm takes any press in its element, its scrollbar's included, as the
  start of a selection, so even a drag that scrolled selected text — the press on the scrollbar is now kept from
  xterm; a details element's content sits in a part of its own, so a flex on it never stretched the maximized
  terminal — it is placed instead; and the box, scrolling too, showed a second scrollbar for xterm's hidden
  pixels below its rows, its width — and so the font fitted to it — changing with the font, 6.8 one time and
  6.9 the next — the box is clipped.
- **Mutation controls:** with the fit, the scrollbar's guard and the copy switched off, the check failed on each
  — its text 1,125 px over a 687 px box, a drag that scrolled nothing and selected text, Maximize no larger,
  Ctrl+C copying nothing — and `terminals.js` was restored byte for byte. With Codex's flag taken out,
  `test_workflow.Sessions.test_architect_readonly_engineer_write` failed — `'--no-alt-screen' not found` — and
  `codex.py` was restored byte for byte.
- **Green on WSL:** `tests.orchestration.test_workflow`, `tests.agents.test_adapters`,
  `tests.agents.test_prompt_size`, `tests.application.test_activities`, `tests.test_demo`,
  `tests.interfaces.test_workbench`, `tests.test_architecture` — 216 tests, OK. On Windows
  `tests.agents.test_adapters`, `tests.agents.test_prompt_size`, `tests.application.test_activities.LongPrompt`,
  `tests.orchestration.test_workflow.Sessions` — 6 classes, 30 tests, OK.
- **`make demo`:** DEMO PASSED, 116 checks, none failed — the new one at the run's approval: the engineer's
  terminal fitted at font 6.9, its thumb dragged from 152 to 0 of 152 with nothing selected, maximized at 10.1 and
  restored at 6.9, Ctrl+C copying a selection and sending nothing. The fake agents now show the prompt they were
  given, so their terminals hold more than a screen.
- **The size from its owner, after the architect's review:** `tests.interfaces.test_workbench.Access` asked the
  page's config for `terminal_size` — red, `KeyError`; green once the server serves `terminal.COLS` and `ROWS`.
- **Headless Edge's own crash at Ctrl+C, in `make demo`:** the check lost its browser at the first Ctrl+C on a
  selection in two demos of five, never in eleven live runs. Its Crashpad dump: exception `0x80000003` — a
  breakpoint, a check of Edge's own failing — in `msedge.dll`, in the browser process (its own `--headless=new`
  command line), with Edge's *Microsoft Clipboard Extension* among its strings: the browser breaks in its own
  clipboard handling before the page is told of the key, so the page's handler has no part in it. The handler now
  also cancels the key it handles — the browser's own copy of xterm's hidden input never runs beside it — but the
  crash came again after that, so the check gives the page its Ctrl+C at the terminal's input, the selection still
  made by the mouse. Mutation control: with the copy switched off it failed — *copied []* — and `terminals.js` was
  restored byte for byte. Then `make demo`: DEMO PASSED, 117 checks, none failed.
- **Not yet seen live:** a Codex turn drawn inline through the Windows worker — it runs this code once restarted,
  with no turn of the operator's run at work.
