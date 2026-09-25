"use strict";
// The workbench page: the stack, the runs, one run's stop, terminals, rounds and change. Agent and
// run text is only ever set as text, never as markup.

const CONFIG = JSON.parse(document.getElementById("config").textContent);
const ROLES = ["engineer", "architect"];
// How an answer is shown. Which answers a stop takes comes with the stop, and whether one is accepted
// is the workflow's; an action named here only by the stop still gets its button.
const LABELS = { approve: "Approve", revise: "Revise", "revise:engineer": "Revise — engineer",
  "revise:architect": "Revise — architect", guide: "Guide", continue: "Continue",
  merge: "Merge", discard: "Discard" };
const DANGER = new Set(["discard"]);
// A second look before an answer that lands or removes the work.
const ASK = { merge: "Merge the verified change into the base branch?",
  discard: "Discard deletes the worktree and its branch. Discard?" };
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

// ---- what the stack and each run are doing now ----------------------------------------------

const PARTS = { temporal: "Temporal", wsl: "WSL worker", windows: "Windows worker" };
const HOSTS = { wsl: PARTS.wsl, windows: PARTS.windows };
const VERBS = { start: "Start", stop: "Stop", restart: "Restart" };
// What stopping a part interrupts, said before the operator confirms it; a restart stops it first.
const INTERRUPTS = {
  temporal: "Stopping Temporal pauses every run until it starts again. An agent at work goes on, but if " +
    "Temporal stays down longer than a role's heartbeat interval, its stage fails and waits for you to continue it.",
  wsl: "Stopping the WSL worker ends any agent at work on it — its stage then waits for you to continue it — " +
    "and pauses every run until it starts again. A merge or discard it is running may be cut off; its run " +
    "then waits at that step until the step fails or times out, and Force terminate ends it sooner.",
  windows: "Stopping the Windows worker ends any agent at work on it — its stage then waits for you to " +
    "continue it — and pauses the Windows runs until it starts again. A merge or discard it is running is " +
    "cut off; its run then waits at that step until the step times out, and Force terminate ends it sooner.",
  stack: "Stopping the stack stops both workers, then Temporal: every agent at work ends — its stage then " +
    "waits for you to continue it — a merge or discard running may be cut off, and every run pauses until " +
    "it starts again.",
};
// The stack's last reading: what the page shows of each part, and whether a blocked run's host can be
// started from here.
let stackReading = null;

// How long since an ISO time, as minutes and seconds, or hours and minutes past an hour.
function elapsed(since) {
  const seconds = Math.max(0, Math.floor((Date.now() - Date.parse(since)) / 1000));
  if (Number.isNaN(seconds)) return "";
  const [h, m, s] = [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60];
  return h ? h + "h " + String(m).padStart(2, "0") + "m" : m + ":" + String(s).padStart(2, "0");
}

// One line saying what a run is doing now and, when it is not moving, why — from its view.
function now(view) {
  const since = view.since ? " · for " + elapsed(view.since) : "";
  let text = view.status || "";
  // A terminated run's own status is wherever termination found it; how it ended is Temporal's.
  if (view.execution === "TERMINATED") text = "terminated";
  if (view.state === "running") text = [view.stage, view.role].filter(Boolean).join(" · ") + since;
  if (view.state === "stopping") text = "stopping" + (view.stage ? ": " + view.stage : "") + since;
  if (view.state === "waiting") text = "waiting for you: " + view.stop.reason + since;
  if (view.state === "failed") text = "failed: " + (view.failure || "").split("\n")[0] + since;
  const blocked = view.blocked_by.map((host) => "the " + (HOSTS[host] || host) + " is down");
  return { text: text, blocked: blocked.length ? "blocked: " + blocked.join(", ") : "" };
}

async function refreshStack() {
  try {
    stackReading = await api("/api/health");
  } catch (error) {
    return;
  }
  renderStack(stackReading);
}

// Each part with its state, and — for one this stack manages — the controls that suit it.
function renderStack(health) {
  const parts = $("stack-parts");
  parts.replaceChildren();
  for (const part of health.components) {
    const box = el("span", null, "stack-part");
    box.appendChild(el("span", PARTS[part.name] || part.name, "name"));
    box.appendChild(el("span", part.state, part.state));
    box.title = [part.pid && "pid " + part.pid, part.detail, !part.managed && "not this stack's to start or stop"]
      .filter(Boolean).join(" · ");
    if (part.managed) {
      // One this side cannot start again gets no Start or Restart; its reason is in its detail.
      const actions = part.state === "down" ? ["start"] : ["restart", "stop"];
      for (const action of actions.filter((action) => part.startable || action === "stop")) {
        box.appendChild(stackButton(action, part.name, $("stack-result")));
      }
      if (!part.startable) {
        box.appendChild(el("span", part.state === "unknown" ? "its state cannot be read" : "cannot be started from here",
          "muted"));
      }
    }
    parts.appendChild(box);
  }
  const all = $("stack-all");
  all.replaceChildren();
  if (health.components.filter((part) => part.managed).length > 1) {
    for (const action of ["start", "restart", "stop"]) all.appendChild(stackButton(action, null, $("stack-result")));
  }
  $("connection").textContent = health.temporal === "up" ? "" : "Temporal is down: " + (health.error || "");
}

function stackButton(action, part, line, label) {
  const button = el("button", label || VERBS[action] + " " + (part ? PARTS[part] : "stack"),
    action === "stop" ? "danger" : "");
  button.type = "button";
  button.onclick = () => stackAction(action, part, line);
  return button;
}

// A start, stop or restart of the stack or one part, as its one owner does it; what each part came to.
async function stackAction(action, part, line) {
  const named = part ? PARTS[part] : "the stack";
  if (action !== "start" && !window.confirm(INTERRUPTS[part || "stack"] + " " + VERBS[action] + " " + named + "?")) {
    return;
  }
  const buttons = document.querySelectorAll("#stack button, #run-blocked button");
  for (const button of buttons) button.disabled = true;
  line.textContent = "sending…";
  try {
    const done = await api("/api/stack", { action: action, component: part });
    const failed = done.results.filter((result) => !result.ok);
    line.textContent = (failed.length ? "failed: " : "done: ") + action + " " + named + " — " +
      done.results.map((result) => PARTS[result.component] + ": " + result.said).join("; ");
    stackReading = done.health;
    renderStack(stackReading);
  } catch (error) {
    line.textContent = "not accepted: " + error.message;
  } finally {
    for (const button of buttons) button.disabled = false;
  }
  refreshRuns();
  refreshRun();
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
    const group = { waiting: "runs-waiting", failed: "runs-waiting", running: "runs-running",
      stopping: "runs-running" }[run.state];
    groups[group || "runs-finished"].push(run);
  }
  for (const [id, runs] of Object.entries(groups)) {
    const ul = $(id);
    ul.replaceChildren();
    for (const run of runs) {
      const li = el("li");
      li.appendChild(el("span", run.goal || run.run_id, "task"));
      const shown = now(run);
      li.appendChild(el("span", [run.repo, run.host, shown.text].filter(Boolean).join(" · "), "muted"));
      if (shown.blocked) li.appendChild(el("span", shown.blocked, "blocked"));
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

// ---- the repositories: each list a menu of their owners ------------------------------------

// The repositories as last shown, so an unchanged answer leaves an open menu as it is.
let shownRepos = "";

// A repository's name may carry its owners — `work/platform/service` — and is then found under `work`,
// then `platform`, each opening to the right as it is hovered or reached with Tab.
function repoTree(listed) {
  const root = { owners: new Map(), repos: [] };
  for (const repo of listed) {
    let node = root;
    for (const owner of repo.id.split("/").slice(0, -1)) {
      if (!node.owners.has(owner)) node.owners.set(owner, { owners: new Map(), repos: [] });
      node = node.owners.get(owner);
    }
    node.repos.push(repo);
  }
  return root;
}

function repoMenu(node, choose) {
  const list = el("ul", null, "menu");
  for (const [name, owned] of node.owners) {
    const item = el("li", null, "owner");
    const button = el("button", name);
    button.type = "button";
    item.append(button, repoMenu(owned, choose));
    list.appendChild(item);
  }
  for (const repo of node.repos) {
    const button = el("button", repo.id.split("/").pop() + " (" + repo.target + ")");
    button.type = "button";
    button.onclick = () => choose(repo.id);
    const item = el("li");
    item.appendChild(button);
    list.appendChild(item);
  }
  return list;
}

// A list stays the <select> the forms read, hidden behind the button that opens its menu.
function picker(select) {
  if (select.nextElementSibling && select.nextElementSibling.classList.contains("picker")) {
    return select.nextElementSibling;
  }
  const box = el("div", null, "picker");
  const button = el("button", "none", "picker-button");
  button.type = "button";
  // Opening reads repos.json again, so an entry added to it shows without reloading the page.
  button.onclick = () => {
    const menu = box.querySelector(".menu");
    menu.hidden = !menu.hidden;
    if (!menu.hidden) reloadRepos();
  };
  box.onkeydown = (event) => {
    if (event.key !== "Escape") return;
    box.querySelector(".menu").hidden = true;
    button.focus();
  };
  box.append(button, el("ul", null, "menu"));
  box.lastChild.hidden = true;
  select.hidden = true;
  select.after(box);
  return box;
}

function setRepo(select, id) {
  select.value = id;
  const chosen = select.selectedOptions[0];
  picker(select).querySelector(".picker-button").textContent = chosen ? chosen.textContent : "none";
}

async function loadRepos() {
  const listed = await api("/api/repos");
  const shown = JSON.stringify(listed);
  if (shown === shownRepos) return;
  shownRepos = shown;
  const tree = repoTree(listed);
  for (const id of ["start-repo", "worktrees-repo"]) {
    const select = $(id);
    const chosen = select.value;
    select.replaceChildren(...listed.map((repo) => {
      const option = el("option", repo.id + " (" + repo.target + ")");
      option.value = repo.id;
      return option;
    }));
    const box = picker(select);
    const menu = repoMenu(tree, (repo) => {
      setRepo(select, repo);
      box.querySelector(".menu").hidden = true;
      select.dispatchEvent(new Event("change"));
    });
    if (!listed.length) menu.appendChild(el("li", "none in repos.json: type its path", "muted"));
    const open = box.querySelector(".menu");
    menu.hidden = open.hidden;
    open.replaceWith(menu);
    setRepo(select, listed.some((repo) => repo.id === chosen) ? chosen : select.value);
  }
}

// ---- the flows a run may follow -------------------------------------------------------------

// A flow's steps as one line, `role action` each; the step at `current`, if given, set apart.
function flowLine(steps, current) {
  const line = el("span");
  steps.forEach((step, index) => {
    if (index) line.appendChild(document.createTextNode(" → "));
    const words = step.replace(":", " ");
    line.appendChild(index === current ? el("strong", words) : document.createTextNode(words));
  });
  return line;
}

// The flows as last shown, so an unchanged answer leaves an open list as it is.
let shownFlows = "";
let listedFlows = [];

function showFlowSteps() {
  const chosen = listedFlows.find((flow) => flow.name === $("start-flow").value);
  $("start-flow-steps").replaceChildren(chosen && chosen.steps ? flowLine(chosen.steps) : "");
}

async function loadFlows() {
  const answer = await api("/api/flows");
  const shown = JSON.stringify(answer);
  if (shown === shownFlows) return;
  shownFlows = shown;
  listedFlows = answer.flows;
  const select = $("start-flow");
  // The flow chosen, else the policy's default; "" when the policy names none.
  const chosen = select.value || answer.default || "";
  const options = answer.flows.map((flow) => {
    // A flow that breaks a rule is listed, never offered: its reason is what to fix in its file. The one
    // chosen stays chosen, so a start on it is refused with that reason, never made on another flow.
    const option = el("option", flow.error ? flow.name + " (refused)" : flow.name);
    option.value = flow.name;
    option.disabled = Boolean(flow.error) && flow.name !== chosen;
    if (flow.error) option.title = flow.error;
    return option;
  });
  if (chosen && !answer.flows.some((flow) => flow.name === chosen)) {
    // So does a flow chosen, or named the default, that has no file.
    const missing = el("option", chosen + " (missing)");
    missing.value = chosen;
    options.unshift(missing);
  }
  if (!answer.default) {
    // With no default in the policy a run names no flow, as the command line's does, and takes the
    // order runs took before flows.
    const none = el("option", "none — the order from before flows");
    none.value = "";
    options.unshift(none);
  }
  select.replaceChildren(...options);
  select.value = chosen;
  showFlowSteps();
}

// flows/ is read again each time the list is opened, so a flow added or edited there shows without a reload.
const reloadFlows = () => loadFlows().catch((error) => { $("start-result").textContent = error.message; });
$("start-flow").onfocus = reloadFlows;
$("start-flow").onchange = showFlowSteps;

// A click anywhere but in a repository menu closes it.
document.addEventListener("click", (event) => {
  for (const menu of document.querySelectorAll(".picker > .menu")) {
    if (!menu.parentElement.contains(event.target)) menu.hidden = true;
  }
});

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
      if (row.run) li.appendChild(el("span", "run " + row.run.toLowerCase(), "muted"));
      if (row.removable) {
        const remove = el("button", "Remove", "danger");
        remove.type = "button";
        remove.onclick = (event) => {
          event.stopPropagation();
          removeKept(row.branch, $("worktrees-result"), loadWorktrees);
        };
        li.appendChild(remove);
      }
      if (row.run) li.onclick = () => select(row.branch);
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
      flow: $("start-flow").value, auto_proceed: $("start-auto").checked });
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
  $("run-kept").hidden = true;
  $("run-task").textContent = "";
  shownStop = null;
  diffLoadedFor = null;
  for (const role of ROLES) closeTerminal(role);
  $("run").hidden = false;
  $("diff-summary").textContent = "";
  $("diff-patch").textContent = "";
  $("diff-more").hidden = true;
  $("run-control-result").textContent = "";
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
  const view = status.view;
  runActive = view.state !== "closed";
  if (!status.unreadable || !$("run-task").textContent) {
    $("run-task").textContent = view.goal || runId;
    $("run-meta").textContent = [runId, view.repo && view.repo + " on " + view.host,
      view.phase && "phase " + view.phase + ", round " + (view.round || 0), view.worktree]
      .filter(Boolean).join(" · ");
  }
  // The run's own flow, as it was started — a run started before flows took the order shown.
  $("run-flow").replaceChildren(...(view.flow ? [
    el("span", "flow " + (view.flow.name || "from before flows") + ": "),
    flowLine(view.flow.steps, view.state === "closed" ? null : view.step)] : []));
  const shown = now(view);
  $("run-now").replaceChildren(el("span", status.unreadable || shown.text),
    el("span", shown.blocked ? " · " + shown.blocked : "", "blocked"));
  $("run-controls").hidden = !runActive;
  $("run-stop").disabled = view.state === "stopping";
  renderBlocked(view);
  renderKept(runId, view);
  // With its worker down the run is shown from its listing alone: what it last said stays on the page.
  if (status.unreadable) return;
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

// A run blocked by a host whose worker this stack can start offers that start where it says so.
function renderBlocked(view) {
  const box = $("run-blocked");
  const down = new Set((stackReading ? stackReading.components : [])
    .filter((part) => part.managed && part.startable && part.state === "down").map((part) => part.name));
  const startable = view.blocked_by.filter((host) => down.has(host));
  box.hidden = !startable.length;
  if (box.dataset.shown === startable.join()) return;
  box.dataset.shown = startable.join();
  box.replaceChildren(...startable.map((host) => stackButton("start", host, $("run-control-result"),
    "Start the " + PARTS[host])));
}

// What a closed run kept — its worktree and branch, unmerged — until the operator removes them.
function renderKept(runId, view) {
  $("run-kept").hidden = !view.kept;
  if (!view.kept) return;
  $("run-kept-text").textContent = "It keeps its worktree " + view.worktree + " and its branch " + runId +
    ": look at its change below, and remove them once you are done with them.";
  $("run-kept-show").onclick = () => showWorktrees(view.repo);
  $("run-remove").onclick = () => removeKept(runId, $("run-control-result"), refreshRun);
}

async function removeKept(runId, line, then) {
  if (!window.confirm("Remove deletes run " + runId + "'s worktree and its branch, with any of its work that " +
    "is not merged. Remove them?")) return;
  line.textContent = "sending…";
  try {
    await api("/api/runs/" + encodeURIComponent(runId) + "/remove", { confirm: true });
    line.textContent = "removed";
  } catch (error) {
    line.textContent = "not accepted: " + error.message;
    return;
  }
  then();
}

function showWorktrees(repo) {
  $("worktrees-path").value = "";
  setRepo($("worktrees-repo"), repo);
  loadWorktrees();
  $("worktrees").scrollIntoView({ behavior: "smooth", block: "nearest" });
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
  for (const action of stop.actions || []) {
    const button = el("button", LABELS[action] || action, DANGER.has(action) ? "danger" : "");
    button.type = "button";
    button.onclick = () => answer(stop, action);
    actions.appendChild(button);
  }
}

// The action as the stop published it, and the note: what an answer needs is the workflow's to refuse.
async function answer(stop, action) {
  const text = $("stop-note").value.trim();
  const body = { stop: stop.id, action: action };
  // Only words you wrote: an empty note must reach the workflow empty, for it to refuse.
  if (text) body.text = text;
  if (ASK[action]) {
    if (!window.confirm(ASK[action])) return;
    body.confirm = true;
  }
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

// A run's lifecycle, beside its stop's answers: Stop ends it from whatever it is doing and keeps its
// work; force terminate is for a run a Stop cannot finish, and says what it cannot stop.
const LIFECYCLE = {
  stop: { ask: "Stop this run? Its worktree and branch stay as they are.", said: "stopping" },
  terminate: { ask: "Force terminate closes the run at once, with no cleanup, but cannot stop what its host " +
    "is already doing. An agent at work ends at its turn's next heartbeat; a worktree's creation, a merge " +
    "or a discard already running goes on, and may still change the repository afterwards. The run's " +
    "terminals stay until its host's worker restarts. Force terminate?", said: "terminated",
  body: { confirm: true } },
};

async function lifecycle(kind) {
  const control = LIFECYCLE[kind];
  if (!window.confirm(control.ask)) return;
  $("run-control-result").textContent = "sending…";
  try {
    await api("/api/runs/" + encodeURIComponent(selected) + "/" + kind, control.body || {});
    $("run-control-result").textContent = control.said;
  } catch (error) {
    $("run-control-result").textContent = "not accepted: " + error.message;
    return;
  }
  refreshRun();
  refreshRuns();
}
$("run-stop").onclick = () => lifecycle("stop");
$("run-terminate").onclick = () => lifecycle("terminate");

function renderTimeline(timeline) {
  const root = $("timeline");
  root.replaceChildren();
  // A run's phases are its flow's work stages, in the order it took them.
  for (const phase of [...new Set(timeline.map((entry) => entry.phase))]) {
    const entries = timeline.filter((entry) => entry.phase === phase);
    const box = el("div", null, "phase");
    box.appendChild(el("h3", phase.charAt(0).toUpperCase() + phase.slice(1)));
    for (const entry of entries) {
      const row = el("div", null, "entry");
      const head = el("div");
      head.appendChild(el("span", entry.stage + " · episode " + entry.episode + " · round " + entry.round + " "));
      if (entry.verdict) head.appendChild(el("span", entry.verdict, "verdict " + entry.verdict));
      if (entry.gate) head.appendChild(el("span", " → stop: " + entry.gate, "muted"));
      head.appendChild(el("span", " " + (entry.at || "").slice(0, 19).replace("T", " "), "muted"));
      row.appendChild(head);
      if (entry.feedback) row.appendChild(el("pre", entry.feedback, "text"));
      if (entry.brief) row.appendChild(el("pre", entry.brief, "text"));
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

const reloadRepos = () => loadRepos().catch((error) => { $("start-result").textContent = error.message; });
reloadRepos();
reloadFlows();
refreshStack();
refreshRuns();
setInterval(refreshStack, 5000);
setInterval(refreshRuns, 5000);
setInterval(refreshRun, 2500);
