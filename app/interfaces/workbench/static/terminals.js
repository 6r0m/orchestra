// Each role's live terminal, straight from the worker of the run's host. This module alone owns a
// terminal's <details>, its xterm and its socket: no redraw of the run replaces them. An xterm measures
// its parent as it opens, so a terminal is made only when its <details> is open, never while hidden.

import { CONFIG } from "./api.js";
import { $ } from "./ui.js";

export const ROLES = ["engineer", "architect"];
const terminals = {};
// The run these terminals are of, whether it can still get a new terminal, the role last shown, and since
// when the run last read has done what it does.
let run = null;
let active = false;
let lastShown;
let lastSince;

for (const role of ROLES) {
  const box = $("terminal-" + role);
  box.addEventListener("toggle", () => {
    if (box.open) make(role);
  });
}

// The terminals of run `runId` on host `target`; another run's are disposed of, the same run's kept.
export function showTerminals(runId, target) {
  if (run && runId && run.id === runId && run.target === target) return;
  for (const role of ROLES) close(role);
  run = runId ? { id: runId, target: target } : null;
  lastShown = undefined;
  lastSince = undefined;
  for (const role of ROLES) {
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

function make(role) {
  if (!run || terminals[role]) return;
  const mount = $("term-" + role);
  mount.replaceChildren();
  const term = new Terminal({ cols: 160, rows: 48, fontSize: 12, scrollback: 5000, convertEol: false,
    fontFamily: '"Cascadia Mono", Consolas, "Courier New", monospace' });
  term.open(mount);
  // `shown` counts the record's bytes on screen: every connection streams the record from its start, and
  // the record only grows, so a connection made again skips what is shown and adds only what is new.
  const entry = { runId: run.id, term: term, socket: null, timer: null, live: false, shown: 0, skip: 0 };
  terminals[role] = entry;
  term.onData((data) => {
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
      // The first state comes before the record; each later one says an agent started or ended.
      entry.live = JSON.parse(event.data).live;
      say(role, entry);
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
