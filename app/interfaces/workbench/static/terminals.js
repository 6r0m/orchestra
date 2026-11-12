// Each role's live terminal, straight from the worker of the run's host. This module alone owns a
// terminal's <details>, its xterm and its socket: no redraw of the run replaces them. Open runs parse
// both roles even behind closed disclosures; fitting waits until the panel has measurable dimensions.

import { api, CONFIG } from "./api.js";
import { $ } from "./ui.js";
import * as cache from "./terminal-cache.js";

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
let terminals = {};
// Six emulators at most, each with bounded scrollback; parked runs own no live socket.
const RUN_CACHE_LIMIT = 3;
const retained = new Map();
let reconciledCache = false;
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
const WRITE_CHUNK = 65536;
const STREAM_PROTOCOL = "workbench.v2";
const CHECKPOINT_MS = 2000;

function checkpoint(entry, force = false) {
  if (entry.disposed || entry.failed || entry.inWrite || entry.restoring || !entry.owner.retain ||
      entry.owner.closed || !entry.shown || entry.lastSaved === entry.shown) return;
  const wait = CHECKPOINT_MS - (Date.now() - entry.lastCheckpoint);
  if (!force && wait > 0) {
    if (!entry.cacheTimer) entry.cacheTimer = setTimeout(() => {
      entry.cacheTimer = null;
      checkpoint(entry, true);
    }, wait);
    return;
  }
  clearTimeout(entry.cacheTimer);
  entry.cacheTimer = null;
  entry.lastCheckpoint = Date.now();
  const cursor = entry.shown;
  cache.save(entry.runId, entry.target, entry.role, cursor, entry.term).then((saved) => {
    if (saved) entry.lastSaved = Math.max(entry.lastSaved, cursor);
    say(entry.role, entry);
  });
}

function checkpointVisible() {
  for (const entry of Object.values(terminals)) checkpoint(entry, true);
}
window.addEventListener("pagehide", checkpointVisible);
document.addEventListener("visibilitychange", () => { if (document.hidden) checkpointVisible(); });

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

function disconnect(entry) {
  checkpoint(entry, true);
  clearTimeout(entry.timer);
  entry.timer = null;
  const socket = entry.socket;
  entry.socket = null;
  entry.live = false;
  entry.size = null;
  if (socket) socket.close();
}

function dispose(entry) {
  checkpoint(entry, true);
  entry.disposed = true;
  clearTimeout(entry.cacheTimer);
  disconnect(entry);
  entry.term.dispose();
}

function forget(key) {
  const saved = retained.get(key);
  retained.delete(key);
  if (saved === run) {
    saved.retain = active = false;
    saved.closed = true;
    for (const [role, entry] of Object.entries(terminals)) say(role, entry);
    return;
  }
  for (const entry of Object.values(saved.roles)) dispose(entry);
}

// Missing rows are unknown, not closed: the rail may have read only one page of history.
export function noteTerminalRuns(rows) {
  for (const row of rows) {
    if (row.state !== "closed") continue;
    cache.close(row.run_id);
    for (const [key, saved] of retained) if (saved.id === row.run_id) forget(key);
  }
  if (!reconciledCache) {
    reconciledCache = true;
    const known = new Set(rows.map((row) => row.run_id));
    // A run can close while this browser is away, and its old cache may outlive the rail's first page.
    for (const id of cache.runs().filter((id) => !known.has(id))) {
      api("/api/runs/" + encodeURIComponent(id)).then((status) => {
        if (status.view?.state === "closed") noteTerminalRuns([{ run_id: id, state: "closed" }]);
      }).catch((error) => console.warn("Terminal cache lifecycle could not be checked", id, error));
    }
  }
}

// Restore parsed displays across navigation; vendor sessions and recorded output stay worker-owned.
export function showTerminals(runId, target) {
  if (run && runId && run.id === runId && run.target === target) return;
  if (run) {
    Object.assign(run, { active, lastShown, lastSince,
      opened: Object.fromEntries(ROLES.map((role) => [role, $("terminal-" + role).open])) });
    for (const entry of Object.values(terminals)) {
      if (run.retain) disconnect(entry);
      else dispose(entry);
    }
  }
  run = null;
  terminals = {};
  for (const role of ROLES) {
    $("terminal-" + role).classList.toggle("maximized", false);
    $("size-" + role).textContent = "Maximize";
    $("size-" + role).title = MAXIMIZE;
    $("terminal-" + role).open = false;
    $("term-" + role).replaceChildren();
    $("state-" + role).textContent = "";
  }
  document.body.classList.toggle("terminal-maximized", false);
  lastShown = lastSince = undefined;
  if (!runId) return;
  const key = JSON.stringify([runId, target]);
  run = retained.get(key) || { id: runId, target, roles: {}, retain: true, opened: {} };
  retained.delete(key);
  retained.set(key, run);
  terminals = run.roles;
  active = run.active ?? true;
  lastShown = run.lastShown;
  lastSince = run.lastSince;
  while (retained.size > RUN_CACHE_LIMIT) forget(retained.keys().next().value);
  for (const role of ROLES) {
    const entry = terminals[role];
    if (entry) {
      $("term-" + role).replaceChildren(entry.node);
      say(role, entry);
      entry.term.scrollToBottom();
      connect(role, entry, target);
    }
    $("terminal-" + role).open = Boolean(run.opened[role]);
    fit(role);
  }
}

// What the run is doing, at every read: whether it can still get a terminal, the role whose terminal it
// shows — the one at work, or the one whose step failed — the role at work, and since when it has done what
// it does now. When the role shown changes, its terminal opens and the other closes; what the operator opens
// or closes holds until the next change. A terminal with no socket is connected again while its role is at
// work — its turn has begun, on a worker that may have restarted since — and once whenever the run moves
// on, for a turn shorter than the time between two reads.
export function updateTerminals({ open, shown, working, since }) {
  if (run && !open) run.closed = true;
  active = open && !run?.closed;
  if (run && !open) {
    cache.close(run.id);
    run.retain = false;
    retained.delete(JSON.stringify([run.id, run.target]));
  }
  const movedOn = since !== lastSince;
  lastSince = since;
  if (shown !== lastShown) {
    lastShown = shown;
    if (shown && ROLES.includes(shown)) {
      for (const role of ROLES) $("terminal-" + role).open = role === shown;
      terminals[shown]?.term.scrollToBottom();
    }
  }
  for (const role of ROLES) {
    // Warm the other role before its next turn, without opening its panel or taking focus.
    if (active) make(role);
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
  if (!run || !active || !ROLES.includes(role)) return false;
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
  const node = document.createElement("div");
  mount.replaceChildren(node);
  term.open(node);
  // The worker's mark of a new size, where it begins in the record: what follows is drawn at it. The parser waits
  // for the resize, made outside its own pass, and a mark that is not a size this terminal takes is dropped.
  term.parser.registerOscHandler(SIZE_MARK, (data) => new Promise((resolve) => {
    const [cols, rows] = data.split(";").map(Number);
    setTimeout(() => {
      if (cols === COLS && rows >= MIN_ROWS && rows <= MAX_ROWS && rows !== term.rows) {
        term.resize(cols, rows);
        if (terminals[role]?.term === term) fit(role);
      }
      resolve(true);
    }, 0);
  }));
  // `shown` counts parsed record bytes: streaming workers resume there, and legacy replay skips them.
  // `size` is the worker's, as it last said — none from a worker that takes no size.
  const entry = { runId: run.id, target: run.target, role, owner: run, term: term, node, disposed: false,
    socket: null, timer: null, live: false, shown: 0, skip: 0, size: null,
    writing: Promise.resolve(), buffer: [], rendering: false, pending: 0,
    connecting: false, failed: false, catchingUp: false, replayUntil: 0,
    cacheTimer: null, lastCheckpoint: 0, lastSaved: 0, inWrite: false, restoring: false, saved: null };
  terminals[role] = entry;
  fit(role);
  // The agent is sent what the operator types and presses, and never this terminal's own answers.
  term.onData((data) => {
    if (REPORT.test(data)) return;
    if (active && terminals[role] === entry && entry.live && entry.socket && entry.socket.readyState === WebSocket.OPEN)
      entry.socket.send(data);
  });
  const saved = active && !run.closed ? cache.read(run.id, run.target, role) : null;
  if (saved) {
    entry.saved = saved;
    entry.restoring = true;
    say(role, entry);
    entry.writing = cache.restore(term, saved).then((cursor) => {
      entry.shown = entry.lastSaved = cursor;
    }).catch((error) => {
      console.warn("Cached terminal could not be restored; replaying its record", error);
      resetCached(entry);
    }).finally(() => {
      entry.restoring = false;
      if (terminals[role] === entry && !entry.disposed) { fit(role); connect(role, entry, entry.target); }
    });
  } else connect(role, entry, run.target);
}

function resetCached(entry) {
  cache.remove(entry.runId, entry.target, entry.role);
  entry.saved = null;
  entry.shown = entry.skip = entry.lastSaved = entry.replayUntil = 0;
  entry.term.reset();
  entry.term.resize(COLS, ROWS);
}

function say(role, entry) {
  if (terminals[role] !== entry) return;
  const remaining = Math.max(entry.pending, entry.replayUntil - entry.shown);
  let text = entry.failed ? "terminal display failed; reload this page"
    : entry.restoring ? "restoring cached terminal…"
    : entry.catchingUp || remaining > WRITE_CHUNK * 4
      ? "catching up terminal output… " + Math.max(1, Math.ceil(remaining / 1048576)).toLocaleString() + "\u00a0MB remaining"
    : entry.live && active ? "live: Esc interrupts it, and typing reaches it"
    : active ? "recorded, until its next turn" : "recorded";
  if (cache.issue()) text += " · " + cache.issue();
  if ($("state-" + role).textContent !== text) $("state-" + role).textContent = text;
}

function draw(role, entry, data) {
  entry.buffer.push(data);
  entry.pending += data.length;
  if (entry.pending > WRITE_CHUNK * 4) entry.catchingUp = true;
  say(role, entry);
  if (entry.rendering) return entry.writing;
  entry.rendering = true;
  const parsed = Promise.resolve().then(async () => {
    let head = 0;
    while (entry.pending) {
      if (entry.disposed || entry.failed) return;
      // A CLI's redraw can arrive as thousands of tiny frames. Join them before asking xterm to parse,
      // so its scheduled write callbacks cost one per bounded chunk rather than one per frame.
      const length = Math.min(WRITE_CHUNK, entry.pending);
      const part = new Uint8Array(length);
      let filled = 0;
      while (filled < length) {
        const first = entry.buffer[head];
        const take = Math.min(first.length, length - filled);
        part.set(first.subarray(0, take), filled);
        filled += take;
        if (take === first.length) entry.buffer[head++] = null;
        else entry.buffer[head] = first.subarray(take);
      }
      entry.inWrite = true;
      await new Promise((resolve) => entry.term.write(part, resolve));
      entry.inWrite = false;
      if (entry.disposed) return;
      // Only parsed bytes may be skipped or acknowledged after reconnecting.
      entry.shown += part.length;
      entry.pending -= part.length;
      checkpoint(entry);
      if (!entry.pending && entry.shown >= entry.replayUntil) entry.catchingUp = false;
      say(role, entry);
    }
    entry.buffer.length = 0;
  });
  entry.writing = parsed.catch((error) => {
    entry.failed = true;
    console.error("Terminal rendering failed", error);
    if (entry.socket) entry.socket.close();
    say(role, entry);
  }).finally(() => {
    entry.rendering = false;
  });
  return entry.writing;
}

function connect(role, entry, target) {
  if (entry.failed || entry.restoring || entry.connecting || terminals[role] !== entry) return;
  if (entry.pending) {
    entry.connecting = true;
    entry.writing.then(() => {
      entry.connecting = false;
      if (!entry.socket) connect(role, entry, target);
    });
    return;
  }
  const port = CONFIG.terminal_ports[target];
  // The workers listen on the IPv4 loopback only, whatever name the page was opened by.
  const url = "ws://127.0.0.1:" + port + "/" + encodeURIComponent(entry.runId) + "/" + role;
  // The token travels as a subprotocol, in the handshake's own header: a URL is printed to the
  // browser's console on every failed connection and written to logs.
  const socket = new WebSocket(url, [STREAM_PROTOCOL, "workbench.v1", "token." + CONFIG.token]);
  socket.binaryType = "arraybuffer";
  entry.socket = socket;
  entry.skip = entry.shown;
  let requested = false;
  const read = () => {
    if (!entry.failed && entry.socket === socket && socket.readyState === WebSocket.OPEN) {
      requested = true;
      socket.send(new TextEncoder().encode(JSON.stringify({ read: entry.shown })));
    }
  };
  socket.onopen = () => {
    if (socket.protocol === STREAM_PROTOCOL) {
      entry.skip = 0;
      if (!entry.saved && !requested) read();
    } else if (entry.saved) {
      // Legacy workers cannot validate a persistent cursor against their replay length.
      resetCached(entry);
    }
  };
  $("state-" + role).textContent = entry.shown ? "cached screen; reconnecting…" : "connecting…";
  socket.onmessage = (event) => {
    if (terminals[role] !== entry || entry.socket !== socket || entry.failed) return;
    if (typeof event.data === "string") {
      // The first state comes before the record; each later one says an agent started or ended, or the size
      // changed. A terminal maximized here before its worker said its size asks for its rows now.
      const state = JSON.parse(event.data);
      if (entry.saved && socket.protocol === STREAM_PROTOCOL) {
        if (!Number.isSafeInteger(state.replay) || state.replay < entry.shown) resetCached(entry);
        entry.saved = null;
        read();
      }
      entry.live = state.live;
      const first = !entry.size && state.size;
      entry.size = state.size || null;
      if (Number.isSafeInteger(state.replay) && state.replay >= 0) entry.replayUntil = state.replay;
      if (entry.replayUntil - entry.shown > WRITE_CHUNK * 4) entry.catchingUp = true;
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
    draw(role, entry, data).then(() => {
      if (socket.protocol === STREAM_PROTOCOL) read();
    });
  };
  socket.onclose = (event) => {
    if (terminals[role] !== entry || entry.socket !== socket) return;
    const wasLive = entry.live;
    entry.live = false;
    entry.socket = null;
    // The next worker says its size again — or, older, says none and is asked nothing: one that does not name it
    // would take a size's frame for keys.
    entry.size = null;
    if (event.code === 1008) {
      entry.failed = true;
      cache.remove(entry.runId, entry.target, entry.role);
    }
    // An unfinished replay needs the same reconnect as live output, even after the run has closed.
    // A fully drawn record stays closed until the role works again or the run moves on.
    const unfinished = entry.pending > 0 || entry.shown < entry.replayUntil;
    if (!entry.failed && (wasLive || unfinished)) {
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
