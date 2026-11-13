# A maximized terminal takes its window's rows

**Status:** DONE (local implementation) 2026-11-13 — existing delivery reconciled and locally retested; live-state limits remain recorded below.
**Scope:** a role's terminal size — the PTY host ([ptyhost.py](../../app/agents/ptyhost.py)), the worker's terminal and
its socket ([terminal.py](../../app/agents/terminal.py) `Terminal`, `_Agent`, `serve`), the page's terminal
([terminals.js](../../app/interfaces/workbench/static/terminals.js)), and their proof ([test_terminal.py](../../tests/agents/test_terminal.py),
[demo_press.py](../../tools/demo_press.py), [demo.py](../../tools/demo.py)).
**Stable documentation owner:** the agents' [structure](../../app/agents/docs/architecture/structure.md) for the
terminal's size and how it changes; [using.md](../../docs/using.md) for Maximize.

## Contents

Goal · Authority register · Non-goals · Verified evidence · Current architecture · Problem · Decision · Required
invariants · Implementation tasks · Test-first and verification plan · Documentation plan · Rollout and rollback ·
Completion criteria · Review record

## Goal

A maximized terminal fills its window's whole height on any display — a portrait one included — with as many of
the agent's rows as fit, and Restore puts it back.

## Authority register

### Operator decisions

- **D1** The terminal follows the maximized window: the agent's terminal is resized to fit it (option A of three:
  A the grid follows the window, B a taller fixed grid, C history drawn in the space above).
  - Effect: the terminal's size is no longer one fixed grid for every viewer and turn.
  - Reason: *"maximize should be in full height (now it's half screen height on my vertical display)"*.
  - Date/source: 2026-11-06, operator: *"let's try A"*.

- **D2** Build it now, as a console window behaves: maximized, it takes the monitor's size.
  - 2026-11-09, operator, of the maximized terminal still half the height: *"check web how window acts in windows,
    cmd autosize by monitro when maximized simply"*.

### Operator gates

- **Q1 [CLOSED by D2, as A1]:** Rows only, or columns too? The page already fits the font so the 160 columns fill
  the window's width, so rows alone fill it as a console's autosize does, the agents' layout and the record's
  wrapping unchanged.
- **Q2 [CLOSED by D2, as A2]:** Another page watching draws the same rows.
- **Q3 [CLOSED by D2, as A3]:** The size holds until Restore, the next turns included.

### Working assumptions

- **A1 [ACTIVE]:** Rows only. The columns stay 160, the width the agents lay their screens out for and the page
  fits its font to; a maximized terminal takes the font that fits 160 columns across its window and as many rows
  as that font fits down it — on a 1080 × 1920 portrait window about 135, on a landscape 1920 × 1080 about the 48
  it has now.
- **A2 [ACTIVE]:** One size per terminal, which every viewer draws: the worker owns it, as it owns the agent.
- **A3 [ACTIVE]:** The size holds until a Restore or the worker's restart, the run's next turns starting at it;
  a page that goes while maximized leaves it, and the next Restore or a new page's Maximize sets it again.
- **A4 [ACTIVE]:** Bounds: 24 to 200 rows; a request outside them is refused, the size left as it was.

## Non-goals

- A grid that follows every viewer's box all the time — only Maximize and Restore change it.
- Columns other than 160 (A1).
- Re-flowing an agent's past output: what it drew at one size stays as it drew it.

## Verified evidence

**Verified facts**

- The size is one constant: `terminal.COLS, ROWS = 160, 48`; each turn starts a new PTY host with it
  (`_Agent.__init__`: `ptyhost.py 160 48 -- argv`), so a size set during a turn would end with it unless the
  terminal keeps it.
- The PTY host has no control channel: its stdin is the keyboard, written to the PTY as it comes
  (`ptyhost.windows`/`posix`, `keyboard()`); its stdout is the screen.
- A resize is native on both hosts: POSIX `ioctl(master, TIOCSWINSZ, …)` — the kernel then signals the agent's
  foreground group with `SIGWINCH` — already used at start in `ptyhost.posix`; Windows pywinpty 3.0.5
  `PtyProcess.setwinsize(rows, cols)`, present in this checkout's Windows environment (measured).
- The socket types every frame it receives, text or binary, into the agent (`serve.handler`:
  `terminal.type(message …)`); the page sends only text frames, the keys (`terminals.js` `term.onData`).
- The worker tells its viewers state as JSON text frames (`{"live": …}`, `Terminal.announce`) and the record as
  binary frames; a page ignores a JSON field it does not know.
- A connection replays the role's whole record from its start (`serve.handler`, `Terminal.attach`) into an xterm
  of the page's size (`CONFIG.terminal_size`, from `terminal.COLS`/`ROWS`).
- The record's plain reading (`terminal.plain`, `_ANSI`) strips OSC sequences; the vendored xterm.js 5.5 has
  `parser.registerOscHandler`, and ignores an OSC it has no handler for.
- Page files go live when saved; a worker's code when it restarts. A page newer than its worker is normal.

**Inferences**

- Replayed at one size, a record that was drawn at several garbles where a full-screen redraw assumed another
  size. Marking each size change in the record lets the page replay each part at the size it was drawn at.

**Unverified — to be measured in the build**

- How Claude and Codex redraw on a row change through ConPTY and on POSIX (both handle `SIGWINCH`/console resize
  in their TUIs; what lands in the record is to be read).

## Current architecture and source of truth

The worker owns a role's terminal: one `Terminal` per run and role holds the record, its viewers and the agent
under it; each turn's agent runs under a PTY host it starts (D17 in the [architecture](../../docs/architecture/structure.md)).
The page draws what the worker sends, at the size the page's config names, and sends keys; it owns how large it
draws the columns (`fit`) and Maximize/Restore, inside the page.

## Problem and root cause

The grid is fixed at 48 rows, so on a window taller than 160 columns' width-fitted font needs for 48 rows,
Maximize fills only part of its height (on the operator's portrait display about a third). More rows in the page
alone would garble: on Windows ConPTY draws for exactly its own size, so the page must draw the size the PTY has —
the PTY's size has to change.

## Decision

The worker's terminal owns its size; Maximize asks for one, Restore for the default; every viewer, and the record,
follow it.

1. **The PTY host takes a resize in its stdin stream:** one control sequence the keyboard never makes — an APC,
   `ESC _ orchestra-size;<rows>;<cols> ESC \` — parsed out of the stream (whole across reads) and applied with
   `TIOCSWINSZ` or `setwinsize`; everything else goes on to the PTY as now.
2. **The worker's terminal holds the size:** `Terminal.resize(rows)` checks A4, keeps it, writes the control
   sequence to the agent under it, if any, writes a size marker — an OSC, `ESC ] 5379;<cols>;<rows> BEL` — into
   the record and so to every viewer, and announces it in the state frame (`{"live": …, "size": [cols, rows]}`).
   A new turn's agent starts at the size held, and its start writes the marker too. Keys carrying the control
   sequence are refused, so no page types a resize.
3. **The socket carries a resize as a binary frame of JSON** (`{"rows": <n>}`) — the page sends no binary frame
   today. The page sends one only to a worker whose state frame names `size`; to an older worker, never.
4. **The page follows the size:** an OSC 5379 handler resizes its xterm to the marker's size where it stands in
   the record, so a replay draws each part at the size it was drawn at; Maximize fits the font to 160 columns
   across the window and asks for the rows that font fits down it; Restore asks for 48.

### Premise / KISS gate

- **Owner:** the worker's `Terminal`, which already owns the agent, the record and the viewers.
- **Added:** one control sequence in a stream that exists, one marker in the record, one JSON frame on the socket
  that exists, one field in the state frame. No new process, port, file, channel or store.
- **Kept against a requirement:** the record replayed from its start — the page's "never drawn again under you"
  rests on it; the marker keeps it faithful across sizes.
- **Given up:** a grid sized to each viewer at once — one size per terminal, every viewer drawing it (A2).

### Alternatives considered

- **B — a taller fixed grid (160 × 96):** one constant, but every in-page box twice as tall and a landscape
  maximize smaller; not the operator's choice (D1).
- **C — history drawn above the 48 live rows:** no colours, a second view to keep in step; not chosen (D1).
- **A second pipe to the PTY host for control:** a cleaner channel, but the host is started through the
  containment's stub (D17), which hands on stdin, stdout and stderr only; carrying another descriptor through
  the systemd scope's stub and the Windows job is more moving parts than one sequence in stdin.
- **More rows in the page only:** garbles under ConPTY, which draws for its own size (Problem).

## Required invariants

- Agent text still reaches the page only as terminal bytes or as text; the marker is the worker's, never an
  agent's to set (an agent's own OSC 5379 is ignored by the page unless the worker wrote it — the build decides how:
  the worker strips it from agent output, or signs the marker; measured in task 2).
- No keystroke is ever taken as a resize: the control sequence in a key frame is refused.
- A worker that does not name `size` is never sent a binary frame.
- Only the page's token and origin reach the socket (as now); sizes outside A4 are refused.
- The workflow, the turn's completion and the record's text reading are unchanged.

## Implementation tasks

1. `ptyhost.py`: the APC parser on the stdin stream, whole across reads, both hosts; `TIOCSWINSZ` / `setwinsize`.
2. `terminal.py`: `Terminal.resize` and its bounds; the size held across turns and given to each new agent; the
   marker in the record; `size` in the state frame; binary JSON frames to `resize`; the control sequence refused
   in keys; an agent's own OSC 5379 kept from reaching the page as the worker's marker.
3. `terminals.js`: the OSC 5379 handler; Maximize asking for the rows its window fits, Restore for 48, only to a
   worker naming `size`; `fit` taking the width-fitted font when maximized.
4. Docs: the agents' structure (the size, who owns it, how it changes, the marker); using.md (Maximize); the
   interfaces' structure if the page's part needs a line; tests' and tools' READMEs.

## Test-first and verification plan

- **Red, then green, on both hosts** (`tests.agents.test_terminal`): a PTY host given the control sequence —
  split across two writes — resizes its PTY, a `fake_cli` turn reporting its size after the change; a key frame
  carrying the sequence resizes nothing; `Terminal.resize` outside A4 refused and the size kept; a new turn
  starting at the held size; the marker in the record and `size` in the state frame; an agent's own OSC 5379 not
  taken for the worker's.
- **Red, then green, in the browser** (`demo_press.py`, a new mode, in `make demo`): in a tall window, Maximize
  makes the worker's terminal taller — the page's xterm and the agent's reported size both — and Restore puts it
  back to 48; a reconnect replays the record at each part's size.
- **Live:** the operator's run on the Windows worker, once restarted with it, maximized on a portrait-shaped window.

## Documentation plan

- The agents' structure: the terminal's size is the worker's, changed by Maximize and Restore, marked in the
  record; the PTY host's control sequence.
- using.md: Maximize fills the window's height with the agent's rows.
- The tests' and tools' READMEs: the new checks.

## Rollout and rollback

- Page and worker deploy apart; the page sends a resize only to a worker that names `size`, so either order is
  safe. A record with markers replays on an older page at the default size (it ignores the marker), as records do
  now.
- Rollback: the page without the handler, the worker without `resize` — the default size everywhere again.

## Completion criteria

- On a portrait window, Maximize fills the whole height with the agent's rows on both hosts; Restore puts back 48.
- Every viewer draws the size the worker holds; a reconnect replays each part of the record at its own size.
- No keystroke resizes; out-of-bounds sizes are refused; an older worker is never sent a resize.
- Tests on both hosts, the browser check in `make demo`, and the live check pass; the docs say it.

## Verification

- **How a console does it** (2026-11-09, the web): Windows Terminal resizes its pseudo-console to its window with
  `ResizePseudoConsole` (columns X, rows Y); a browser terminal computes the rows its box fits and sends them to
  its server, which resizes the PTY — as built here.
- **Both hosts, the real PTY host** (`tests.agents.test_terminal`): `Resize` — the PTY host reads a size whole
  across reads, a lone Esc and every other key passing at once; sizes out of bounds and keys carrying the sequence
  change nothing; a size held, given to the agent, marked and announced. `Socket` — a binary frame resizes, a key
  never does, the state frame names the size. `Turns.test_a_resize_reaches_the_agent_and_the_next_turn_starts_at_it`
  — a fake agent saw its PTY take 100 rows, its next turn began at them and Restore put back 48, each size marked
  where it began: WSL, and Windows through ConPTY's `setwinsize`. WSL 221 tests and Windows 76, OK.
- **The browser** (`demo_press.py terminal-rows:engineer`, in `make demo`): in a 1,000 × 1,700 window, Maximize
  took the engineer's terminal from 48 rows to 138, its screen down to 1,580 px of 1,608; Restore put back 48.
  DEMO PASSED, 121 checks.
- **Accepted, not guarded:** an agent printing an `OSC 5379` of its own can change how a page draws the terminal —
  160 columns and 24 to 200 rows only — never the PTY, until the worker's next mark.
- **Not measured yet:** the real Claude and Codex redrawing at a new row count, and the operator's portrait
  display — the live check, after the workers' restart.

### 2026-11-13 — Local acceptance and operator closeout

- Operator approved completion, architectural review and local retesting of the current todos.
  The existing implementation remains with its documented owners; no replacement service or workflow
  authority was introduced for this delivery.
- Full host acceptance passed sequentially: Windows, 704 tests; WSL, 933 tests. The first WSL run
  exposed three CLI fixtures missing the new required name; valid named-start fixtures restored their
  original preflight, telemetry-isolation and collision checks. Their focused rerun and the replacement
  full WSL suite passed. New terminal-cache/merge regressions have additional focused browser acceptance.
- Closure covers implemented behavior and local test acceptance. No live worker/service restart,
  real push, Git identity mutation or new paid call was performed. Earlier live evidence is historical;
  current production health, physical portrait-display acceptance and provider invoice completeness
  are not newly asserted by this closeout. The previously recorded billing-coverage limitations remain.
