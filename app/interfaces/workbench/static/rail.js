// The runs: every one Temporal holds, grouped by whether it waits for you, works or has finished, each a
// link that opens it; older finished runs a page at a time.

import { api } from "./api.js";
import { $, blockedBy, clock, el, headline, unchanged } from "./ui.js";

// The older runs the operator has asked for, and where the next page of them starts.
let older = [];
let olderCursor = null;
let listed = [];
let read = false;
let selected = null;

const GROUPS = { waiting: "runs-waiting", failed: "runs-waiting", running: "runs-running", stopping: "runs-running" };
const NONE = { "runs-waiting": "Nothing waits for you.", "runs-running": "Nothing is working.",
  "runs-finished": "No finished runs yet." };

// The runs as last read, and whether they have been read at all.
export const runsListed = () => listed;
export const runsRead = () => read;

export async function refreshRuns() {
  let page;
  try {
    page = await api("/api/runs");
    showUnreadable("");
  } catch (error) {
    showUnreadable("The runs cannot be read: " + error.message);
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
  read = true;
  render();
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
  const groups = { "runs-waiting": [], "runs-running": [], "runs-finished": [] };
  for (const run of listed) groups[GROUPS[run.state] || "runs-finished"].push(run);
  for (const [id, runs] of Object.entries(groups)) {
    const count = $(id + "-count");
    if (count) count.textContent = runs.length ? String(runs.length) : "";
    const list = $(id);
    if (unchanged(list, [runs, read])) continue;
    list.replaceChildren(...runs.map(row));
    if (read && !runs.length) list.appendChild(el("li", NONE[id], "none"));
  }
  for (const link of document.querySelectorAll(".rail .row")) {
    if (link.dataset.run === selected) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  const waiting = groups["runs-waiting"].length;
  document.title = (waiting ? "(" + waiting + ") " : "") + "Orchestra Workbench";
}

function row(run) {
  const said = headline(run);
  const link = el("a", null, "row");
  link.href = "#run=" + encodeURIComponent(run.run_id);
  link.dataset.tone = said.tone;
  link.dataset.run = run.run_id;
  link.append(el("span", said.text, "row-what"), el("span", run.goal || run.run_id, "row-task"));
  const meta = el("span", null, "row-meta");
  const repo = el("span", run.repo || "");
  repo.translate = false;
  meta.append(repo, run.state === "closed" ? (run.closed ? clock(run.closed, "ago") : el("span"))
    : run.since ? clock(run.since) : el("span"));
  link.appendChild(meta);
  const blocked = blockedBy(run);
  if (blocked.length) link.appendChild(el("span", "Blocked: " + blocked.join(", "), "row-blocked"));
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
