// Each role's live terminal, straight from the worker of the run's host. This module alone owns a
// terminal's <details>, its xterm and its socket: no redraw of the run replaces them. An xterm measures
// its parent as it opens, so a terminal is made only when its <details> is open, never while hidden.

import { CONFIG } from "./api.js";
import { $ } from "./ui.js";

export const ROLES = ["engineer", "architect"];
const terminals = {};
// The run these terminals are of, whether it can still get a new terminal, and the role last at work.
let run = null;
let active = false;
let lastWorking;

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
  lastWorking = undefined;
  for (const role of ROLES) {
    $("terminal-" + role).open = false;
    $("state-" + role).textContent = "";
  }
}

// What the run is doing, at every read: whether it can still get a terminal, and which role is at work.
// When that role changes, its terminal opens and the other closes; what the operator opens or closes
// holds until the next change.
export function updateTerminals(open, working) {
  active = open;
  if (working !== lastWorking) {
    lastWorking = working;
    if (working && ROLES.includes(working)) {
      for (const role of ROLES) $("terminal-" + role).open = role === working;
    }
  }
  for (const role of ROLES) {
    if (!terminals[role]) $("state-" + role).textContent = active ? "open it to watch its turns" : "open it to see its record";
  }
}

function make(role) {
  if (!run || terminals[role]) return;
  const mount = $("term-" + role);
  mount.replaceChildren();
  const term = new Terminal({ cols: 160, rows: 48, fontSize: 12, scrollback: 5000, convertEol: false,
    fontFamily: '"Cascadia Mono", Consolas, "Courier New", monospace' });
  term.open(mount);
  const entry = { runId: run.id, term: term, socket: null, timer: null, live: false };
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
  entry.replayed = false;
  $("state-" + role).textContent = "connecting…";
  socket.onmessage = (event) => {
    if (typeof event.data === "string") {
      // The first state comes before the record; each later one says an agent started or ended.
      entry.live = JSON.parse(event.data).live;
      if (!entry.replayed) entry.term.reset();
      entry.replayed = true;
      say(role, entry);
      return;
    }
    entry.term.write(new Uint8Array(event.data));
  };
  socket.onclose = () => {
    if (terminals[role] !== entry) return;
    const wasLive = entry.live;
    entry.live = false;
    if (wasLive) $("state-" + role).textContent = "disconnected, trying again…";
    else say(role, entry);
    // A terminal appears with its role's next turn, and again after a worker restart; a finished run's stays recorded.
    if (wasLive || active) entry.timer = setTimeout(() => connect(role, entry, target), wasLive ? 3000 : 15000);
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
