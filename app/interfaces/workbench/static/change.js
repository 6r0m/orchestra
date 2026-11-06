// A run's change as its target host's git reads it: one snapshot — the commit of its base the run stands on and
// the tree its files make — listed file by file, each opening into its diff, and its whole patch to copy. Read
// again, it is a new snapshot; nothing of the last one is mixed into it.

import { api, CONFIG } from "./api.js";
import { $, PARTS, clock, report } from "./ui.js";
import { copyPatch, fileItem, fileList } from "./diff.js";
import { stackReading } from "./stack.js";

const size = new Intl.NumberFormat(undefined, { style: "unit", unit: "kilobyte", unitDisplay: "short",
  maximumFractionDigits: 0 });
let runId = null;
// The snapshot shown, and its first read: the patch's first part, where the next begins, its whole size.
let shown = null;
// The stop whose change was read on its own: a reread is the operator's, by the button.
let loadedFor = null;

// The change of `run`, not yet read.
export function showChangeFor(run) {
  watchChange(null);
  runId = run;
  shown = null;
  loadedFor = null;
  $("change-said").textContent = "";
  report($("change-result"), "");
  $("diff-files").replaceChildren();
  $("diff-raw").hidden = true;
  $("diff-patch").textContent = "";
  $("diff-load").textContent = "Read the change";
  $("diff-load").title = "Read what the worktree holds now against the run's base: each file, and the whole patch";
  $("diff-load").hidden = false;
}

// Where the change sits: the run's result, so first after what the run does now — after a decision that does
// not judge it — and under the decision that does; or nowhere while the run has no worktree to read.
export function placeChange(where) {
  const section = $("change");
  section.hidden = where === "none";
  if (where !== "none" && section.previousElementSibling !== $("stop")) $("stop").after(section);
}

// ---- live, while the run works ---------------------------------------------------------------------------

// The change as the run's host's worker sends it, while the run works: a snapshot each time something in the
// worktree moved, listed as any snapshot is, each file opening through the same reader. The worker reads; the
// page only shows, and says plainly when it cannot.
let watching = null;

// Watches `run`'s change on its `target` host's worker; with no run, stops watching.
export function watchChange(run, target) {
  if (watching && watching.runId === run && watching.target === target) return;
  const was = watching;
  watching = run ? { runId: run, target: target, socket: null, retry: null, seen: false, rows: new Map() } : null;
  if (was) {
    clearTimeout(was.retry);
    if (was.socket) was.socket.close();
    // What was listed stays, said to be as last seen; the change now is the button's to read.
    if (was.seen && was.runId === runId) $("change-said").textContent = "As last seen while the run worked.";
  }
  if (!watching) {
    $("diff-load").hidden = false;
    return;
  }
  $("diff-load").hidden = true;
  $("diff-raw").hidden = true;
  report($("change-result"), "");
  $("change-said").textContent = "Watching the worktree…";
  listen(watching);
}

function listen(watch) {
  const port = CONFIG.terminal_ports[watch.target];
  // As a terminal is reached: the IPv4 loopback, the token in the handshake's own header, never in the URL.
  const socket = new WebSocket("ws://127.0.0.1:" + port + "/" + encodeURIComponent(watch.runId) + "/change",
    ["workbench.v1", "token." + CONFIG.token]);
  watch.socket = socket;
  let ended = false;
  socket.onmessage = (event) => {
    if (watching !== watch) return;
    const said = JSON.parse(event.data);
    if (said.gone) {
      ended = true;
      $("change-said").textContent = "The change cannot be read any more: " + said.gone + ".";
    } else if (said.waiting) {
      $("change-said").textContent = "No change yet: " + said.waiting + ".";
    } else if (said.error) {
      // What was shown last stays, said to be no longer current.
      $("change-said").textContent = "Not current — " + said.error + ". Asked again in a moment.";
    } else {
      showLive(watch, said);
    }
  };
  socket.onclose = () => {
    if (watching !== watch || ended) return;
    // A browser says no more of a refused socket than that it closed: the stack's own reading tells a worker
    // that is down from one that is up and sends no change — one started before it could.
    const reading = stackReading();
    const part = reading && reading.components.find((each) => each.name === watch.target);
    const worker = "the " + (PARTS[watch.target] || watch.target + " worker");
    $("change-said").textContent = (watch.seen ? "Not current — " : "") + (part && part.state === "up"
      ? worker + " is up but sends no live change: restart it when no turn is running, to load the code that does"
      : worker + " is not answering") + "; asked again in a few seconds.";
    watch.retry = setTimeout(() => { if (watching === watch) listen(watch); }, 5000);
  };
}

// One summary shown: its line — how many files, lines added and removed, and when it was read — then its files. A
// file the summary says nothing new of keeps its row as it was, open with its diff as read; a file that changed
// gets a new row, open again, and so read again, when the operator had opened it. A diff is read only when its row
// opens: as the change is now, since a live summary writes no snapshot.
function showLive(watch, summary) {
  watch.seen = true;
  shown = summary;
  const said = $("change-said");
  if (!summary.files_total) {
    said.replaceChildren("No change yet: the worktree holds what its base does. Read ", clock(summary.read, "ago"),
      ".");
    $("diff-files").replaceChildren();
    watch.rows = new Map();
    return;
  }
  const counted = summary.files.filter((file) => typeof file.added === "number");
  const added = counted.reduce((sum, file) => sum + file.added, 0);
  const removed = counted.reduce((sum, file) => sum + file.removed, 0);
  said.replaceChildren((summary.files_total === 1 ? "1 file" : summary.files_total + " files") + " changed · +"
    + added + " −" + removed + " · read ", clock(summary.read, "ago"), ", and again as the worktree changes.");
  let list = $("diff-files").querySelector("ul.file-list");
  if (!list) {
    $("diff-files").replaceChildren(fileList(watch.runId, summary, [], 0));
    list = $("diff-files").querySelector("ul.file-list");
  }
  const rows = new Map();
  list.replaceChildren(...summary.files.map((file) => {
    const key = JSON.stringify([file.status, file.old, file.added, file.removed, file.binary, file.stamp]);
    const had = watch.rows.get(file.path);
    if (had && had.key === key) {
      rows.set(file.path, had);
      return had.item;
    }
    const item = fileItem(watch.runId, summary, file);
    if (had && had.item.querySelector("details.file").open) item.querySelector("details.file").open = true;
    rows.set(file.path, { key: key, item: item });
    return item;
  }));
  watch.rows = rows;
  if (summary.files.length < summary.files_total) said.append(" The first " + summary.files.length + " are listed.");
}

// At a stop that asks the operator to judge a change, the change is read once, on its own.
export function readOnceFor(stop) {
  if (loadedFor === stop.id) return;
  loadedFor = stop.id;
  loadDiff();
}

async function loadDiff(asked) {
  const reading = runId;
  $("change-said").textContent = "Reading the worktree…";
  try {
    const read = await api("/api/runs/" + encodeURIComponent(reading) + "/diff");
    if (reading !== runId) return;
    shown = read;
    const counted = read.files_total === 1 ? "1 file changed" : read.files_total + " files changed";
    // What the change is read against, as the read itself says: a run from before runs recorded their base
    // is read against its worktree's last commit, or the base merged into it after a conflict.
    const against = { tip: "the base this run stands on", merged: "the base merged into this worktree" }[read.against]
      || "the worktree's last commit";
    $("change-said").textContent = "Against " + read.base.slice(0, 10) + ", " + against + ": "
      + (read.files_total ? counted + "." : "the worktree holds no change.");
    $("diff-files").replaceChildren(...(read.files_total ? [fileList(reading, read, read.files, read.files_total)] : []));
    $("diff-raw").hidden = !read.total;
    $("diff-patch").textContent = read.patch;
    $("diff-size").textContent = read.next < read.total
      ? "the first " + size.format(Math.ceil(read.next / 1024)) + " of " + size.format(Math.ceil(read.total / 1024))
        + " shown; Copy patch copies all of it" : size.format(Math.ceil(read.total / 1024));
    // What is listed is the change as it was when read: Refresh reads the worktree again.
    $("diff-load").textContent = "Refresh";
    $("diff-load").title = "What is listed is the change as it was when read; read the worktree again for the change now";
    if (asked) report($("change-result"), read.files_total ? counted : "The worktree holds no change.");
  } catch (error) {
    if (reading !== runId) return;
    $("change-said").textContent = "The change cannot be read: " + error.message;
    if (asked) report($("change-result"), "The change cannot be read: " + error.message, true);
  }
}

// A read the operator asked for is said in its status line; one the page makes at a stop is not.
$("diff-load").onclick = () => loadDiff(true);
$("diff-copy").onclick = () => shown && copyPatch(runId, shown, $("diff-copy"));
// The whole change as the worktree holds it now — every file, however long — read by the press itself, at any time:
// while the run works, at a stop, or once it is closed.
$("change-copy").onclick = () => runId && copyPatch(runId, api("/api/runs/" + encodeURIComponent(runId) + "/diff"),
  $("change-copy"), "Copy all changes");
