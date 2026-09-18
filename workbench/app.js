"use strict";
// The workbench page: the runs, one run's stop, terminals, rounds and change. Agent and run
// text is only ever set as text, never as markup.

const CONFIG = JSON.parse(document.getElementById("config").textContent);
const ROLES = ["engineer", "architect"];
const ANSWERS = {
  approval: [["approve", "Approve"], ["revise", "Revise the plan", "note"], ["abort", "Abort", "danger"]],
  blocker: [["guide", "Guide", "note"], ["abort", "Abort", "danger"]],
  exhausted: [["guide", "Guide", "note"], ["abort", "Abort", "danger"]],
  failed: [["continue", "Continue"], ["abort", "Abort", "danger"]],
  final: [["merge", "Merge"], ["revise:engineer", "Revise — engineer", "note"],
          ["revise:architect", "Revise — architect", "note"], ["discard", "Discard", "danger"]],
};
const TITLES = { approval: "Approve the plan", blocker: "The architect found a blocker",
  exhausted: "The review budget is used up", failed: "A stage failed", final: "Ready to merge" };

const $ = (id) => document.getElementById(id);
let selected = null;
let shownStop = null;
// The stop whose change was read on its own: a reread is the operator's, by the button.
let diffLoadedFor = null;
// Whether the selected run can still get a new terminal: it has not merged, been discarded or ended.
let runActive = false;
// Which change the page holds and how much of it: one too large for a single payload is read in parts.
let diffRead = { snapshot: null, total: 0, bytes: 0 };
const terminals = {};
// The older runs the operator has asked for, and where the next page of them starts.
let older = [];
let olderCursor = null;

async function api(path, body) {
  const options = { headers: { "X-Workbench-Token": CONFIG.token } };
  if (body !== undefined) {
    options.method = "POST";
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({ error: response.statusText }));
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}

// ---- the run list -------------------------------------------------------------------------

async function refreshRuns() {
  let page;
  try {
    page = await api("/api/runs");
    $("connection").textContent = "";
  } catch (error) {
    $("connection").textContent = "cannot reach Temporal: " + error.message;
    return;
  }
  // Only while no older page has been read: afterwards the cursor is where the operator got to,
  // and it is empty once the whole of the retained history is on the page.
  if (!older.length) olderCursor = page.cursor;
  $("runs-older").hidden = !olderCursor;
  // The newest page is read again every few seconds; older pages the operator asked for stay,
  // because a run Temporal has finished with never changes again.
  const seen = new Set(page.runs.map((run) => run.run_id));
  const list = page.runs.concat(older.filter((run) => !seen.has(run.run_id)));
  const groups = { "runs-waiting": [], "runs-running": [], "runs-finished": [] };
  for (const run of list) {
    // A run Temporal no longer runs is finished, whatever stop it last reported: it can take no answer.
    const group = run.execution !== "RUNNING" ? "runs-finished" : run.stop ? "runs-waiting" : "runs-running";
    groups[group].push(run);
  }
  for (const [id, runs] of Object.entries(groups)) {
    const ul = $(id);
    ul.replaceChildren();
    for (const run of runs) {
      const li = el("li");
      li.appendChild(el("span", run.task || run.run_id, "task"));
      const detail = [run.repo, run.target, run.stop ? "waiting: " + run.stop.reason : run.status, run.phase]
        .filter(Boolean).join(" · ");
      li.appendChild(el("span", detail, "muted"));
      if (run.run_id === selected) li.classList.add("selected");
      li.onclick = () => select(run.run_id);
      ul.appendChild(li);
    }
    if (!runs.length) ul.appendChild(el("li", "none", "muted"));
  }
}

$("runs-older").onclick = async () => {
  const button = $("runs-older");
  button.disabled = true;
  try {
    const page = await api("/api/runs?cursor=" + encodeURIComponent(olderCursor));
    const known = new Set(older.map((run) => run.run_id));
    older = older.concat(page.runs.filter((run) => !known.has(run.run_id)));
    olderCursor = page.cursor;
    await refreshRuns();
  } catch (error) {
    $("connection").textContent = error.message;
  } finally {
    button.disabled = false;
    button.hidden = !olderCursor;
  }
};

async function loadRepos() {
  for (const repo of await api("/api/repos")) {
    for (const id of ["start-repo", "worktrees-repo"]) {
      const option = el("option", repo.id + " (" + repo.target + ")");
      option.value = repo.id;
      $(id).appendChild(option);
    }
  }
}

// ---- the worktrees of a repository, and what is still unmerged -----------------------------

async function loadWorktrees() {
  const list = $("worktrees");
  list.replaceChildren(el("li", "reading…", "muted"));
  $("worktrees-base").textContent = "";
  try {
    const repo = $("worktrees-path").value.trim() || $("worktrees-repo").value;
    const view = await api("/api/worktrees?repo=" + encodeURIComponent(repo));
    list.replaceChildren();
    for (const row of view.rows) {
      const li = el("li");
      li.appendChild(el("span", (row.branch || "(detached)") + " — " + row.state, "task"));
      li.appendChild(el("span", row.path, "muted"));
      list.appendChild(li);
    }
    if (!view.rows.length) list.appendChild(el("li", "none", "muted"));
    $("worktrees-base").textContent = "merged means merged into " + view.base_branch;
  } catch (error) {
    list.replaceChildren(el("li", error.message, "muted"));
  }
}
$("worktrees-load").onclick = loadWorktrees;
$("worktrees-repo").onchange = loadWorktrees;

$("start").onsubmit = async (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  $("start-result").textContent = "starting…";
  try {
    const started = await api("/api/runs", { task: $("start-task").value,
      repo: $("start-path").value.trim() || $("start-repo").value,
      auto_proceed: $("start-auto").checked });
    $("start-result").textContent = "started " + started.run_id;
    $("start-task").value = "";
    await refreshRuns();
    select(started.run_id);
  } catch (error) {
    $("start-result").textContent = "refused: " + error.message;
  } finally {
    button.disabled = false;
  }
};

// ---- one run ------------------------------------------------------------------------------

function select(runId) {
  if (selected === runId) return;
  selected = runId;
  shownStop = null;
  diffLoadedFor = null;
  for (const role of ROLES) closeTerminal(role);
  $("run").hidden = false;
  $("diff-summary").textContent = "";
  $("diff-patch").textContent = "";
  $("diff-more").hidden = true;
  diffRead = { snapshot: null, total: 0, bytes: 0 };
  refreshRun();
  refreshRuns();
}

async function refreshRun() {
  if (!selected) return;
  const runId = selected;
  let status;
  try {
    status = await api("/api/runs/" + encodeURIComponent(runId));
  } catch (error) {
    $("run-meta").textContent = error.message;
    return;
  }
  if (runId !== selected) return;
  const state = status.state;
  runActive = !["MERGED", "DISCARDED", "ABORTED", "REFUSED"].includes(state.status);
  $("run-task").textContent = state.task || runId;
  $("run-meta").textContent = [runId, state.repo + " on " + state.target, state.status,
    state.phase && "phase " + state.phase + ", round " + (state.round || 0), state.worktree_path]
    .filter(Boolean).join(" · ");
  $("link-temporal").href = status.links.temporal;
  $("link-trace").hidden = !status.links.trace;
  if (status.links.trace) $("link-trace").href = status.links.trace;
  renderStop(status.stop);
  renderTimeline(status.timeline);
  $("lines").textContent = status.lines.join("\n");
  for (const role of ROLES) openTerminal(role, runId, state.target);
  if (status.stop && status.stop.reason === "final" && diffLoadedFor !== status.stop.id) {
    diffLoadedFor = status.stop.id;
    loadDiff();
  }
}

function renderStop(stop) {
  const card = $("stop");
  if (!stop) {
    card.hidden = true;
    shownStop = null;
    return;
  }
  card.hidden = false;
  if (shownStop === stop.id) return;
  shownStop = stop.id;
  $("stop-title").textContent = TITLES[stop.reason] || stop.reason;
  $("stop-hint").textContent = stop.hint;
  $("stop-todo").textContent = stop.todo ? "todo: " + stop.todo : "";
  $("stop-feedback").textContent = stop.feedback || "";
  $("stop-note").value = "";
  $("stop-result").textContent = "";
  const actions = $("stop-actions");
  actions.replaceChildren();
  for (const [key, label, kind] of ANSWERS[stop.reason] || []) {
    const button = el("button", label, kind === "danger" ? "danger" : "");
    button.type = "button";
    button.onclick = () => answer(stop, key, kind === "note");
    actions.appendChild(button);
  }
}

async function answer(stop, key, needsNote) {
  const [action, role] = key.split(":");
  const text = $("stop-note").value.trim();
  if (needsNote && !text) {
    $("stop-result").textContent = "this answer needs your note";
    return;
  }
  const body = { stop: stop.id, action: action, text: text || action };
  if (role) body.role = role;
  if (action === "discard") {
    if (!window.confirm("Discard deletes the worktree and its branch. Discard?")) return;
    body.confirm = true;
  }
  if (action === "merge" && !window.confirm("Merge the verified change into the base branch?")) return;
  for (const button of $("stop-actions").children) button.disabled = true;
  $("stop-result").textContent = "sending…";
  try {
    await api("/api/runs/" + encodeURIComponent(selected) + "/answer", body);
    $("stop-result").textContent = "answered: " + action;
  } catch (error) {
    $("stop-result").textContent = "not accepted: " + error.message;
    for (const button of $("stop-actions").children) button.disabled = false;
    return;
  }
  refreshRun();
  refreshRuns();
}

function renderTimeline(timeline) {
  const root = $("timeline");
  root.replaceChildren();
  for (const phase of ["plan", "build"]) {
    const entries = timeline.filter((entry) => entry.phase === phase);
    if (!entries.length) continue;
    const box = el("div", null, "phase");
    box.appendChild(el("h3", phase === "plan" ? "Plan" : "Build"));
    for (const entry of entries) {
      const row = el("div", null, "entry");
      const head = el("div");
      head.appendChild(el("span", entry.stage + " · episode " + entry.episode + " · round " + entry.round + " "));
      if (entry.verdict) head.appendChild(el("span", entry.verdict, "verdict " + entry.verdict));
      if (entry.gate) head.appendChild(el("span", " → stop: " + entry.gate, "muted"));
      head.appendChild(el("span", " " + (entry.at || "").slice(0, 19).replace("T", " "), "muted"));
      row.appendChild(head);
      if (entry.feedback) row.appendChild(el("pre", entry.feedback, "text"));
      box.appendChild(row);
    }
    root.appendChild(box);
  }
  if (!root.children.length) root.appendChild(el("p", "no stage has finished yet", "muted"));
}

async function loadDiff(offset, note) {
  const from = offset || 0;
  $("diff-more").hidden = true;
  if (!from) $("diff-summary").textContent = "reading the worktree…";
  try {
    const diff = await api("/api/runs/" + encodeURIComponent(selected) + "/diff?offset=" + from);
    if (from && diff.snapshot !== diffRead.snapshot) {
      // The worktree changed under the reading — an edit of the same size looks identical by length —
      // so the parts are of two changes and would not fit together.
      $("diff-patch").textContent = "";
      return loadDiff(0, "the change moved while it was being read; reading it again from the start");
    }
    // Where the next part starts is the reader's own answer: a part never ends inside a character.
    diffRead = { snapshot: diff.snapshot, total: diff.total, bytes: diff.next };
    const summary = diff.summary.trim() || "(no changes)";
    $("diff-summary").textContent = (note ? note + "\n" : "") + "base " + diff.base + "\n" + summary +
      (new TextEncoder().encode(summary).length < diff.summary_total
        ? "\n(the file list is too long to show whole)" : "");
    $("diff-patch").textContent = from ? $("diff-patch").textContent + diff.patch : diff.patch;
    const left = diff.total - diffRead.bytes;
    $("diff-more").hidden = left <= 0;
    $("diff-more").textContent = "Read the next part (" + Math.ceil(left / 1024) + " KB left)";
  } catch (error) {
    $("diff-summary").textContent = "could not read the change: " + error.message;
  }
}
$("diff-load").onclick = () => loadDiff(0);
$("diff-more").onclick = () => loadDiff(diffRead.bytes);

// ---- terminals ----------------------------------------------------------------------------

function openTerminal(role, runId, target) {
  const current = terminals[role];
  if (current && current.runId === runId) return;
  closeTerminal(role);
  const term = new Terminal({ cols: 160, rows: 48, fontSize: 12, scrollback: 5000, convertEol: false });
  $("term-" + role).replaceChildren();
  term.open($("term-" + role));
  const entry = { runId: runId, term: term, socket: null, timer: null, live: false };
  terminals[role] = entry;
  term.onData((data) => {
    if (entry.live && entry.socket && entry.socket.readyState === WebSocket.OPEN) entry.socket.send(data);
  });
  connect(role, entry, target);
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
      $("state-" + role).textContent = entry.live ? "live — Esc interrupts, typing reaches the agent"
        : runActive ? "recorded — waiting for a turn" : "recorded";
      return;
    }
    entry.term.write(new Uint8Array(event.data));
  };
  socket.onclose = () => {
    if (terminals[role] !== entry) return;
    const wasLive = entry.live;
    entry.live = false;
    $("state-" + role).textContent = wasLive ? "disconnected — retrying" : runActive ? "recorded — waiting for a turn" : "recorded";
    // A terminal appears with its role's next turn, and again after a worker restart; a finished run's stays recorded.
    if (wasLive || runActive) entry.timer = setTimeout(() => connect(role, entry, target), wasLive ? 3000 : 15000);
  };
}

function closeTerminal(role) {
  const entry = terminals[role];
  if (!entry) return;
  delete terminals[role];
  clearTimeout(entry.timer);
  if (entry.socket) entry.socket.close();
  entry.term.dispose();
  $("state-" + role).textContent = "";
}

loadRepos().catch((error) => { $("start-result").textContent = error.message; });
refreshRuns();
setInterval(refreshRuns, 5000);
setInterval(refreshRun, 2500);
