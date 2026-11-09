// Each role's live terminal, straight from the worker of the run's host. This module alone owns a
// terminal's <details>, its xterm and its socket: no redraw of the run replaces them. An xterm measures
// its parent as it opens, so a terminal is made only when its <details> is open, never while hidden.

import { CONFIG } from "./api.js";
import { $ } from "./ui.js";

export const ROLES = ["engineer", "architect"];
// What a terminal emulator answers a query with: its device attributes, a status or cursor report, a mode it
// reports, a window report, a colour or another setting. xterm answers every query in what it draws — those
// an agent's CLI made as it started among them, drawn again from the record on each connection — and such
// an answer is nobody's key: sent on, it lands in the agent's own prompt as text, ahead of what the operator
// types there. It is known by its bytes alone, and a cursor's report from the top row — `ESC [ 1 ; 2 R` —
// is spelled exactly as F3 held with Shift, Alt or Ctrl is. Nothing here tells the two apart, so neither is
// sent: a clean prompt is chosen over those chords.
const REPORT = new RegExp("^(?:\\x1b\\[[?>]?[\\d;]*c|\\x1b\\[\\??[\\d;]*n|\\x1b\\[\\??\\d+;\\d+R|" +
  "\\x1b\\[\\??[\\d;]+\\$y|\\x1b\\[[\\d;]+t|\\x1b\\][\\s\\S]*?(?:\\x07|\\x1b\\\\)|\\x1bP[\\s\\S]*?\\x1b\\\\)+$");
const terminals = {};
// The run these terminals are of, whether it can still get a new terminal, the role last shown, and since
// when the run last read has done what it does.
let run = null;
let active = false;
let lastShown;
let lastSince;

// The host's terminal has one size for every viewer, its worker's, and the agent lays its screen out for that, so
// the page never changes the columns — only how large they are drawn. A terminal's font is sized so its columns
// and its scrollbar fit its box: wider than its box, its text would lie over the scrollbar, which no drag could
// then reach. Maximized, the terminal fills the page's window, as a console window does: its font fits the columns
// across the window, and its worker is asked for as many rows as that font fits down it — the agent's own terminal
// grows, so its screen fills the window; Restore asks for the rows it had. A worker that does not name its size
// takes none, and is asked nothing: its terminal is drawn larger, as far as both sides allow. Every size change is
// marked in the record where it began, so a page — this one, another watching, one connecting later — draws each
// part at the size it was drawn at.
// An older Workbench serves only cols and rows while loading today's JavaScript from disk.
const { cols: COLS, rows: ROWS, min_rows: MIN_ROWS = 24, max_rows: MAX_ROWS = 200 } = CONFIG.terminal_size;
const SIZE_MARK = 5379;
const LARGEST = 18;
const MAXIMIZE = "Fill the window with this terminal: the agent's terminal takes as many rows as fit";
const RESTORE = "Put this terminal back in its place on the page, at its usual rows";

for (const role of ROLES) {
  const box = $("terminal-" + role);
  box.addEventListener("toggle", () => {
    if (box.open) make(role);
    else maximize(role, false);
  });
  // A button in a summary is its own control: pressing it neither opens nor closes the terminal.
  $("size-" + role).title = MAXIMIZE;
  $("size-" + role).addEventListener("click", (event) => {
    event.preventDefault();
    maximize(role, !box.classList.contains("maximized"));
  });
  new ResizeObserver(() => fit(role)).observe($("term-" + role));
  // A press on the scrollbar is the scrollbar's. xterm takes any press in its element as the start of a selection
  // — or, where the agent takes the mouse, as a click for the agent — so a drag of the thumb would also select
  // text: the press is kept from xterm, and the browser still drags the thumb.
  $("term-" + role).addEventListener("mousedown", (event) => {
    const view = $("term-" + role).querySelector(".xterm-viewport");
    if (view && event.clientX >= view.getBoundingClientRect().left + view.clientWidth) event.stopPropagation();
  }, true);
}

// `role`'s terminal filling the page's window, inside the page — not the browser's full screen, where Esc, the
// key that interrupts an agent, would leave full screen instead — or back in its place.
function maximize(role, on) {
  const box = $("terminal-" + role);
  const button = $("size-" + role);
  box.classList.toggle("maximized", on);
  document.body.classList.toggle("terminal-maximized", ROLES.some((each) =>
    $("terminal-" + each).classList.contains("maximized")));
  button.textContent = on ? "Restore" : "Maximize";
  button.title = on ? RESTORE : MAXIMIZE;
  if (on && !box.open) box.open = true;
  fit(role);
  ask(role, on ? fitting(role) : ROWS);
}

// The rows `role`'s maximized window fits at the font that fits its columns across; null when it is not maximized
// or not drawn.
function fitting(role) {
  const entry = terminals[role];
  const mount = $("term-" + role);
  const screen = mount.querySelector(".xterm-screen");
  const view = mount.querySelector(".xterm-viewport");
  if (!entry || !screen || !view || !$("terminal-" + role).classList.contains("maximized")) return null;
  const style = getComputedStyle(mount);
  const width = mount.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)
    - (view.offsetWidth - view.clientWidth);
  const height = mount.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
  const drawn = screen.getBoundingClientRect();
  // A row's height at the font that fits the columns across: rows scale with the font, as columns do.
  const across = Math.min(width / drawn.width, LARGEST / entry.term.options.fontSize);
  return Math.max(MIN_ROWS, Math.min(MAX_ROWS, Math.floor(height / (drawn.height / entry.term.rows * across))));
}

// `rows` asked of `role`'s worker — only one that names its size, and only when they differ from the size it holds;
// the worker's mark in the record, drawn here and by every page watching, then resizes the terminal. Only this
// page's Maximize, its window changing size while maximized, and its Restore ask: a page that merely connects or
// watches never does, so it never undoes another's Maximize.
function ask(role, rows) {
  const entry = terminals[role];
  if (!rows || !entry || !entry.size || !entry.socket || entry.socket.readyState !== WebSocket.OPEN) return;
  if (rows === entry.size[1]) return;
  entry.socket.send(new TextEncoder().encode(JSON.stringify({ rows: rows })));
}

// A maximized terminal's window changing size — turned, or the browser resized — asks again, once it settles.
let settling = null;
window.addEventListener("resize", () => {
  clearTimeout(settling);
  settling = setTimeout(() => {
    for (const role of ROLES) ask(role, fitting(role));
  }, 300);
});

// The font that fits `role`'s 160 columns and its scrollbar across its box — and, maximized, its rows down it.
// A cell's size follows the font closely but not exactly, so the size is measured again once set.
function fit(role) {
  const entry = terminals[role];
  const mount = $("term-" + role);
  const screen = mount.querySelector(".xterm-screen");
  const view = mount.querySelector(".xterm-viewport");
  if (!entry || !screen || !view || !mount.clientWidth) return;
  const style = getComputedStyle(mount);
  const width = mount.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)
    - (view.offsetWidth - view.clientWidth);
  const tall = $("terminal-" + role).classList.contains("maximized");
  const height = mount.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
  for (let tries = 0; tries < 4; tries++) {
    const drawn = screen.getBoundingClientRect();
    const font = entry.term.options.fontSize;
    const scale = Math.min(width / drawn.width, tall ? height / drawn.height : Infinity);
    const next = Math.min(LARGEST, Math.floor(font * scale * 10) / 10);
    const fits = drawn.width <= width + 0.5 && (!tall || drawn.height <= height + 0.5);
    if (fits && next - font < 0.2) return;
    entry.term.options.fontSize = next;
  }
}

// The terminals of run `runId` on host `target`; another run's are disposed of, the same run's kept.
export function showTerminals(runId, target) {
  if (run && runId && run.id === runId && run.target === target) return;
  for (const role of ROLES) close(role);
  run = runId ? { id: runId, target: target } : null;
  lastShown = undefined;
  lastSince = undefined;
  for (const role of ROLES) {
    maximize(role, false);
    $("terminal-" + role).open = false;
    $("state-" + role).textContent = "";
  }
}

// What the run is doing, at every read: whether it can still get a terminal, the role whose terminal it
// shows — the one at work, or the one whose step failed — the role at work, and since when it has done what
// it does now. When the role shown changes, its terminal opens and the other closes; what the operator opens
// or closes holds until the next change. A terminal with no socket is connected again while its role is at
// work — its turn has begun, on a worker that may have restarted since — and once whenever the run moves
// on, for a turn shorter than the time between two reads.
export function updateTerminals({ open, shown, working, since }) {
  active = open;
  const movedOn = since !== lastSince;
  lastSince = since;
  if (shown !== lastShown) {
    lastShown = shown;
    if (shown && ROLES.includes(shown)) {
      for (const role of ROLES) $("terminal-" + role).open = role === shown;
    }
  }
  for (const role of ROLES) {
    const entry = terminals[role];
    if (!entry) {
      $("state-" + role).textContent = active ? "open it to watch its turns" : "open it to see its record";
    } else if (active && (movedOn || role === working) && !entry.socket && !entry.timer) {
      connect(role, entry, run.target);
    }
  }
}

// The Esc the operator's own key would send `role`'s agent, sent for them: its terminal is opened, as a click
// on it opens it, the one byte goes over the socket every key goes over, and the terminal is given the
// keyboard, so what is typed next reaches the agent with no click. True once sent; false when no agent is
// under that terminal to hear it within a moment.
export async function interrupt(role) {
  if (!run || !ROLES.includes(role)) return false;
  $("terminal-" + role).open = true;
  make(role);
  const entry = terminals[role];
  const live = () => entry.live && entry.socket && entry.socket.readyState === WebSocket.OPEN;
  for (let waited = 0; entry && !live() && waited < 5000; waited += 100) {
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  if (!entry || terminals[role] !== entry || !live()) return false;
  entry.socket.send("\x1b");
  $("terminal-" + role).scrollIntoView({ block: "nearest" });
  entry.term.focus();
  return true;
}

function make(role) {
  if (!run || terminals[role]) return;
  const mount = $("term-" + role);
  mount.replaceChildren();
  const term = new Terminal({ cols: COLS, rows: ROWS, fontSize: 12, scrollback: 5000, convertEol: false,
    fontFamily: '"Cascadia Mono", Consolas, "Courier New", monospace' });
  // Ctrl+C with text selected copies it, and the agent is sent nothing; with nothing selected it is the
  // agent's, as in any terminal. The key is the page's then, so the browser's own copy — of xterm's hidden
  // input, not of the selection — never runs beside it. A copy the browser refuses leaves the text selected.
  term.attachCustomKeyEventHandler((event) => {
    if (event.type !== "keydown" || !(event.ctrlKey || event.metaKey) || event.shiftKey || event.altKey ||
        event.code !== "KeyC" || !term.hasSelection()) return true;
    event.preventDefault();
    navigator.clipboard.writeText(term.getSelection()).then(() => term.clearSelection(), () => {});
    return false;
  });
  term.open(mount);
  // The worker's mark of a new size, where it begins in the record: what follows is drawn at it. The parser waits
  // for the resize, made outside its own pass, and a mark that is not a size this terminal takes is dropped.
  term.parser.registerOscHandler(SIZE_MARK, (data) => new Promise((resolve) => {
    const [cols, rows] = data.split(";").map(Number);
    setTimeout(() => {
      if (cols === COLS && rows >= MIN_ROWS && rows <= MAX_ROWS && rows !== term.rows) {
        term.resize(cols, rows);
        fit(role);
      }
      resolve(true);
    }, 0);
  }));
  // `shown` counts the record's bytes on screen: every connection streams the record from its start, and
  // the record only grows, so a connection made again skips what is shown and adds only what is new. `size` is
  // the worker's, as it last said — none from a worker that takes no size.
  const entry = { runId: run.id, term: term, socket: null, timer: null, live: false, shown: 0, skip: 0, size: null };
  terminals[role] = entry;
  fit(role);
  // The agent is sent what the operator types and presses, and never this terminal's own answers.
  term.onData((data) => {
    if (REPORT.test(data)) return;
    if (entry.live && entry.socket && entry.socket.readyState === WebSocket.OPEN) entry.socket.send(data);
  });
  connect(role, entry, run.target);
}

function say(role, entry) {
  $("state-" + role).textContent = entry.live ? "live: Esc interrupts it, and typing reaches it"
    : active ? "recorded, until its next turn" : "recorded";
}

function connect(role, entry, target) {
  const port = CONFIG.terminal_ports[target];
  // The workers listen on the IPv4 loopback only, whatever name the page was opened by.
  const url = "ws://127.0.0.1:" + port + "/" + encodeURIComponent(entry.runId) + "/" + role;
  // The token travels as a subprotocol, in the handshake's own header: a URL is printed to the
  // browser's console on every failed connection and written to logs.
  const socket = new WebSocket(url, ["workbench.v1", "token." + CONFIG.token]);
  socket.binaryType = "arraybuffer";
  entry.socket = socket;
  entry.skip = entry.shown;
  if (!entry.shown) $("state-" + role).textContent = "connecting…";
  socket.onmessage = (event) => {
    if (typeof event.data === "string") {
      // The first state comes before the record; each later one says an agent started or ended, or the size
      // changed. A terminal maximized here before its worker said its size asks for its rows now.
      const state = JSON.parse(event.data);
      entry.live = state.live;
      const first = !entry.size && state.size;
      entry.size = state.size || null;
      say(role, entry);
      if (first) ask(role, fitting(role));
      return;
    }
    let data = new Uint8Array(event.data);
    if (entry.skip) {
      const seen = Math.min(entry.skip, data.length);
      entry.skip -= seen;
      data = data.subarray(seen);
    }
    if (!data.length) return;
    entry.term.write(data);
    entry.shown += data.length;
  };
  socket.onclose = () => {
    if (terminals[role] !== entry) return;
    const wasLive = entry.live;
    entry.live = false;
    entry.socket = null;
    // The next worker says its size again — or, older, says none and is asked nothing: one that does not name it
    // would take a size's frame for keys.
    entry.size = null;
    // A live terminal that drops is its worker gone mid-turn: tried again shortly. One that was only its
    // record — the worker holds no terminal for the role until its next turn — stays as it is, and is
    // connected again once the run reads that role at work, or moves on.
    if (wasLive) {
      $("state-" + role).textContent = "disconnected, trying again…";
      entry.timer = setTimeout(() => {
        entry.timer = null;
        connect(role, entry, target);
      }, 3000);
    } else {
      say(role, entry);
    }
  };
}

function close(role) {
  const entry = terminals[role];
  if (!entry) return;
  delete terminals[role];
  clearTimeout(entry.timer);
  if (entry.socket) entry.socket.close();
  entry.term.dispose();
  $("term-" + role).replaceChildren();
}
