// The runs: every one Temporal holds, grouped by whether it waits for the operator, works, has closed or was
// rejected, each a link that opens it; older closed runs a page at a time.

import { api } from "./api.js";
import { $, blockedBy, clock, drainingBy, el, headline, showReading, unchanged } from "./ui.js";

// The older runs the operator has asked for, and where the next page of them starts.
let older = [];
let olderCursor = null;
let listed = [];
let read = false;
let unavailable = false;
let selected = null;
let runTitle = "";
let groups = { waiting: [], running: [], finished: [], rejected: [] };

const narrow = matchMedia("(max-width: 1000px)");
const roomy = matchMedia("(min-width: 1200px) and (min-height: 760px)");
const panel = $("runs-panel");
const toggle = $("runs-toggle");
let expanded = null;

export function prepareRuns(openingRun) {
  if (openingRun && narrow.matches) expanded = false;
  renderVisibility();
}

roomy.addEventListener("change", () => {
  if (expanded === null) renderVisibility();
});

function renderVisibility() {
  panel.hidden = !(expanded ?? roomy.matches);
  toggle.hidden = false;
  toggle.setAttribute("aria-expanded", String(!panel.hidden));
  showAttention();
}

function showAttention() {
  const waiting = read && !unavailable ? groups.waiting.length : 0;
  const badge = $("nav-runs-count");
  const link = $("nav-runs");
  badge.hidden = !panel.hidden || !waiting;
  if (badge.hidden) {
    link.removeAttribute("aria-label");
    return;
  }
  badge.textContent = waiting > 99 ? "99+" : waiting;
  link.setAttribute("aria-label", "Runs, " + waiting + (waiting === 1 ? " needs attention" : " need attention"));
}

function closeRuns() {
  expanded = false;
  renderVisibility();
  toggle.focus();
}

toggle.onclick = () => {
  expanded = true;
  renderVisibility();
  $("runs-list-title").focus({ preventScroll: !narrow.matches });
};
$("runs-close").onclick = closeRuns;
panel.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !event.defaultPrevented) {
    event.preventDefault();
    closeRuns();
  }
});

export function setRunTitle(text) {
  runTitle = text;
  title();
}

function title() {
  const waitingCount = groups.waiting.length;
  document.title = (waitingCount ? "(" + waitingCount + ") " : "") +
    (runTitle ? runTitle + " | " : "") + "Orchestra Workbench";
}

const GROUPS = { waiting: "waiting", failed: "waiting", running: "running", stopping: "running" };

// The list a run is shown in. A closed run is under Rejected only by its own ending, which only the operator's
// Reject gives it; a stopped run, and one whose ending cannot be read, stays under Closed.
function listOf(run) {
  if (run.agent_prompt) return "waiting";
  return GROUPS[run.state] || (run.status === "REJECTED" ? "rejected" : "finished");
}

// The runs as last read, and whether they have been read at all.
export const runsListed = () => listed;
export const runOverview = () => ({ groups, read, unavailable, more: Boolean(olderCursor) });

export async function refreshRuns() {
  let page;
  try {
    page = await api("/api/runs");
    unavailable = false;
    showUnreadable("");
  } catch (error) {
    unavailable = true;
    showReading("rail-reading", false);
    showUnreadable("The runs cannot be read: " + error.message);
    showAttention();
    document.dispatchEvent(new Event("workbench:runs"));
    return;
  }
  // Only while no older page has been read: afterwards the cursor is where the operator got to,
  // and it is empty once the whole of the retained history is on the page.
  if (!older.length) olderCursor = page.cursor;
  $("runs-older").hidden = !olderCursor;
  // The newest page is read again every few seconds; older pages the operator asked for stay,
  // because a run Temporal has finished with never changes again.
  const seen = new Set(page.runs.map((run) => run.run_id));
  listed = page.runs.concat(older.filter((run) => !seen.has(run.run_id)));
  groups = { waiting: [], running: [], finished: [], rejected: [] };
  for (const run of listed) groups[listOf(run)].push(run);
  read = true;
  render();
  showReading("rail-reading", false);
  document.dispatchEvent(new Event("workbench:runs"));
}

function showUnreadable(text) {
  $("connection").textContent = text;
  $("connection").hidden = !text;
}

// The run now open, set apart in the list.
export function select(runId) {
  selected = runId;
  render();
}

function render() {
  const focused = document.activeElement?.closest(".rail .row");
  for (const [group, runs] of Object.entries(groups)) {
    const id = "runs-" + group;
    $(id + "-count").textContent = read ? String(runs.length) : "–";
    $(id + "-count").parentElement.classList.toggle("has-runs", runs.length > 0);
    const list = $(id);
    if (unchanged(list, runs)) continue;
    list.replaceChildren(...runs.map(row));
  }
  for (const link of document.querySelectorAll(".rail .row")) {
    if (link.dataset.run === selected) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
    if (focused && !focused.isConnected && focused.dataset.run === link.dataset.run) {
      const collapsed = link.closest("details:not([open])");
      (collapsed?.querySelector("summary") || link).focus({ preventScroll: true });
    }
  }
  showAttention();
  title();
}

function row(run) {
  const said = headline(run);
  const link = el("a", null, "row");
  link.href = "#run=" + encodeURIComponent(run.run_id);
  link.dataset.tone = said.tone;
  if (run.state === "closed" && run.status) link.dataset.outcome = run.status;
  link.dataset.run = run.run_id;
  const task = el("span", run.short_name || run.goal || "Untitled run", "row-task");
  task.title = task.textContent;
  if (run.short_name) task.translate = false;
  const repo = el("span", run.repo || "Repository unavailable", "row-repo");
  repo.translate = false;
  repo.title = repo.textContent;
  const meta = el("span", null, "row-meta");
  meta.append(el("span", said.text, "row-what"));
  if (run.state === "closed" && run.closed) meta.append(clock(run.closed, "ago"));
  if (run.state !== "closed" && run.since) meta.append(clock(run.since));
  link.append(task, repo, meta);
  const blocked = blockedBy(run);
  if (blocked.length) link.appendChild(el("span", "Blocked: " + blocked.join(", "), "row-blocked"));
  const updating = drainingBy(run);
  if (updating.length) link.appendChild(el("span", "Updating: " + updating.join(", "), "row-update"));
  const item = el("li");
  item.appendChild(link);
  return item;
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
    showUnreadable("Older runs cannot be read: " + error.message);
  } finally {
    button.disabled = false;
    button.hidden = !olderCursor;
  }
};
