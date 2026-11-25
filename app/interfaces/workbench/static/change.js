// A run's change as its target host's git reads it: one snapshot — the commit of its base the run stands on and
// the tree its files make — listed file by file, each opening into its diff, and its whole patch to copy. Read
// again, it is a new snapshot; nothing of the last one is mixed into it.

import { api, CONFIG } from "./api.js";
import { $, PARTS, clock, el, report } from "./ui.js";
import { copyPatch, fileItem, fileList } from "./diff.js";
import { stackReading } from "./stack.js";

const size = new Intl.NumberFormat(undefined, { style: "unit", unit: "kilobyte", unitDisplay: "short",
  maximumFractionDigits: 0 });
let runId = null;
// The snapshot shown, and its first read: the patch's first part, where the next begins, its whole size.
let shown = null;
// The stop whose change was read on its own: a reread is the operator's, by the button.
let loadedFor = null;
let wholeEvidence = null;
let worktreeRetained = true;
const number = new Intl.NumberFormat();
const fileCount = (total) => number.format(total) + (total === 1 ? " file changed" : " files changed");
const hasMilestones = () => Boolean($("review-milestones").querySelector(".milestone-card"));

function updateChangeView() {
  const cards = $("review-milestones").querySelectorAll(".milestone-card").length;
  $("change-worktree").hidden = !worktreeRetained || cards > 0;
  if (cards) $("change-count").textContent = number.format(cards) + (cards === 1 ? " milestone" : " milestones");
  const evidence = wholeEvidence?.runId === runId ? wholeEvidence : null;
  const unavailable = !evidence ? "Reading run history…"
    : !worktreeRetained && (!evidence.latest?.tree || !evidence.latest.basis || evidence.latest.unavailable)
      ? "Latest saved snapshot or its base unavailable." : "";
  $("change-copy").disabled = Boolean(unavailable);
  $("change-range").textContent = unavailable || (worktreeRetained
    ? "Worktree changes against its current base · one net diff"
    : "Final worktree changes against their recorded base · one net diff");
}

// The change of `run`, not yet read.
export function showChangeFor(run) {
  watchChange(null);
  runId = run;
  shown = null;
  loadedFor = null;
  wholeEvidence = null;
  $("change").open = false;
  $("change-count").textContent = "Files and patch";
  $("change-said").textContent = "";
  report($("change-result"), "");
  $("diff-files").replaceChildren();
  $("diff-raw").hidden = true;
  $("diff-patch").textContent = "";
  $("diff-load").textContent = "Read the change";
  $("diff-load").title = "Read what the worktree holds now against the run's base: each file, and the whole patch";
  $("diff-load").hidden = false;
  updateChangeView();
}

// Where the change sits: the run's result, so first after what the run does now — after a decision that does
// not judge it — and under the decision that does. Retained milestones outlive the worktree reader.
export function placeChange(where, worktree = true) {
  const section = $("change");
  section.hidden = where === "none";
  worktreeRetained = worktree;
  updateChangeView();
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
  if (currentReview?.runId === watch.runId) currentReview.refresh();
  watch.seen = true;
  if (hasMilestones()) return;
  shown = summary;
  $("change-count").textContent = fileCount(summary.files_total);
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
  if (hasMilestones()) return;
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
    const counted = fileCount(read.files_total);
    if (!hasMilestones()) $("change-count").textContent = counted;
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
$("change-copy").onclick = async () => {
  const reading = runId, evidence = wholeEvidence;
  if (!reading || evidence?.runId !== reading) return;
  const query = new URLSearchParams();
  if (!worktreeRetained) {
    if (!evidence.latest?.tree || !evidence.latest.basis || evidence.latest.unavailable) return;
    query.set("base", evidence.latest.basis);
    query.set("tree", evidence.latest.tree);
  }
  report($("change-result"), "");
  const copied = await copyPatch(reading, api("/api/runs/" + encodeURIComponent(reading) + "/diff?" + query),
    $("change-copy"), "Copy all changes");
  if (!copied && reading === runId) report($("change-result"), $("change-copy").title, true);
};

// Operator review intervals come from Temporal; their bytes use the same immutable diff reader.
let drawn = null;
let currentReview = null;
let currentBoundary = null;
const refreshCurrent = () => {
  currentReview?.refresh();
  for (const box of $("review-milestones").querySelectorAll(".milestone-card[open]")) {
    if (box.dataset.review !== "current") box.loadReview?.();
  }
};
$("change").addEventListener("toggle", refreshCurrent);
document.addEventListener("visibilitychange", refreshCurrent);
const action = (row) => ({ approve: "approval", revise: "revision", guide: "guidance", continue: "Continue",
  merge: "Merge", discard: "Discard" }[row.action] || row.action) + (row.role ? " to " + row.role : "");

export function showReviews(runId, review, open, stage = null, turns = []) {
  const root = $("review-milestones");
  const key = JSON.stringify([runId, review, open, stage, turns]);
  if (drawn === key) return;
  drawn = key;
  const focused = root.contains(document.activeElement) ? document.activeElement : null;
  const expanded = new Set([...root.querySelectorAll("details[open][data-review]")].map((box) => box.dataset.review));
  const bodies = new Map([...root.querySelectorAll("details[data-review]")]
    .filter((box) => box.dataset.run === runId).map((box) => [box.dataset.review, box]));
  root.replaceChildren();
  if (!runId || !review) {
    currentReview = null; currentBoundary = null; wholeEvidence = null;
    updateChangeView();
    return;
  }
  wholeEvidence = { runId, initial: review.initial, latest: review.boundaries.at(-1), count: review.boundaries.length };
  const endpoints = [{ stop: "start", label: "Run start", after: null, tree: review.initial, basis: review.initial }, ...review.boundaries.map((row, index) =>
    ({ ...row, label: (index + 1) + " · After " + action(row) }))];
  const intervals = review.boundaries.map((row, index) => ({ stop: row.stop, at: row.at, index: index,
    label: "Milestone " + (index + 1), action: action(row) }));
  intervals.reverse();
  const boundary = JSON.stringify([runId, endpoints.at(-1).stop]);
  const newCurrent = open && currentBoundary !== boundary;
  currentBoundary = open ? boundary : null;
  if (open) intervals.unshift({ stop: "current", index: endpoints.length - 1,
    label: "Milestone " + endpoints.length, action: "Current" });
  currentReview = null;
  if (!intervals.length) { updateChangeView(); return; }
  const all = el("div", null, "milestone-list");
  const turnPositions = new Map(turns.map((turn, index) => [turn.stage + ":" + turn.episode + ":" + turn.round, index]));
  const position = (endpoint) => endpoint.after === null ? -1 : turnPositions.get(endpoint.after);
  for (const interval of intervals) {
    const index = interval.index;
    const live = interval.stop === "current";
    const evidence = JSON.stringify([endpoints[index], live ? "current" : endpoints[index + 1]]);
    const firstTurn = position(endpoints[index]);
    const lastTurn = live ? turns.length - 1 : position(endpoints[index + 1]);
    const work = firstTurn === undefined || lastTurn === undefined || firstTurn > lastTurn
      ? null : turns.slice(firstTurn + 1, lastTurn + 1);
    const working = live && stage?.role ? stage : null;
    const saved = bodies.get(interval.stop);
    if (saved?.dataset.evidence === evidence) {
      saved.updateWork(work, working);
      all.append(saved);
      if (live) currentReview = { runId: runId, refresh: saved.refreshReview };
      continue;
    }
    const box = el("details", null, "round-change milestone-card" + (live ? " current" : ""));
    box.dataset.review = interval.stop;
    box.dataset.run = runId;
    box.dataset.evidence = evidence;
    box.open = (live && newCurrent) || expanded.has(interval.stop) || (!open && !bodies.size && interval === intervals[0]);
    const summary = el("summary");
    const heading = el("span", null, "milestone-heading");
    heading.append(el("strong", interval.label + " · " + (index ? "After " + action(endpoints[index]) : "Initial work")),
      el("span", live ? "Current" : "User " + interval.action, "milestone-badge"));
    const workLine = el("span", "", "milestone-subtitle");
    heading.append(workLine);
    const baseline = index ? "Since milestone " + index : "Since run start";
    const subtitle = el("span", baseline, "milestone-subtitle");
    if (interval.at) {
      const stamp = el("time", new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(interval.at)));
      stamp.dateTime = interval.at;
      subtitle.append(stamp);
    }
    heading.append(subtitle);
    const count = el("span", "", "milestone-count");
    const arrow = el("span", "", "chevron");
    arrow.setAttribute("aria-hidden", "true");
    summary.append(arrow, heading, count);
    const body = el("div", null, "round-change-body");
    const iterations = el("details", null, "milestone-iterations");
    const iterationsTitle = el("summary");
    const iterationsText = el("pre", "", "code");
    iterations.append(iterationsTitle, iterationsText);
    box.updateWork = (work, working) => {
      const turnName = (turn) => (turn.role ? turn.role + " " : "") + turn.stage;
      const iteration = (turn) => turnName(turn) + " · round " + turn.round + " · episode " + turn.episode;
      workLine.textContent = work === null ? "Role iteration context unavailable."
        : work.length ? "Completed stages: " + [...new Set(work.map(turnName))].join(" · ") : "No completed role turns in this interval.";
      if (working) workLine.append(" · Current step: " + iteration(working));
      iterations.hidden = !work?.length;
      iterationsTitle.textContent = "Completed role turns · " + number.format(work?.length || 0);
      iterationsText.textContent = (work || []).map(iteration).join("\n");
    };
    box.updateWork(work, working);
    const label = el("label", "Compare from ");
    const from = el("select");
    from.name = "review-from";
    const defaultOption = el("option", endpoints[index].label);
    defaultOption.value = endpoints[index].stop;
    from.append(defaultOption);
    from.value = endpoints[index].stop;
    box.addEventListener("toggle", () => {
      if (!box.open || from.dataset.loaded) return;
      const selected = from.value;
      from.replaceChildren(...endpoints.slice(0, index + 1).map((endpoint) => {
        const option = el("option", endpoint.label);
        option.value = endpoint.stop;
        return option;
      }));
      from.value = selected;
      from.dataset.loaded = "yes";
    });
    label.append(from);
    const controls = el("div", null, "section-head");
    const read = el("button", "Read changes");
    const copy = el("button", "Copy milestone");
    read.title = "Read the changes from the selected comparison point";
    copy.title = "Copy the patch from the selected comparison point";
    copy.className = "milestone-copy";
    read.type = copy.type = "button";
    const status = el("p", live ? "Current files, not independently verified." : "Open to read this milestone’s changes.", "hint");
    status.setAttribute("role", "status");
    const files = el("div");
    let snapshot = null;
    let busy = false, dirty = false;
    const visible = () => box.isConnected && box.open &&
      !$("change").hidden && $("change").open && document.visibilityState === "visible";
    const fetchSnapshot = async (start = endpoints[index].stop) => {
      const result = await api("/api/runs/" + encodeURIComponent(runId) + "/milestone?" +
        new URLSearchParams({ from: start, through: interval.stop }));
      if (result.review_range?.base_updated && (!result.alignment?.from || !result.alignment?.to ||
          result.aligned_from !== endpoints.find((point) => point.stop === start)?.tree))
        throw new Error("The reader has not confirmed worktree-only scope; load current Workbench and target-worker code before copying.");
      return result;
    };
    const refresh = async (automatic = false) => {
      if (automatic && !visible()) return;
      if (busy) { dirty = true; return; }
      busy = true;
      read.disabled = !automatic;
      status.textContent = "Reading milestone changes…";
      try {
        const result = await fetchSnapshot();
        if (!box.isConnected) return;
        if (!snapshot || snapshot.base !== result.base || snapshot.tree !== result.tree) {
          const opened = new Set([...files.querySelectorAll("details.file[open]")].map((file) => file.dataset.path));
          const focusedFile = files.contains(document.activeElement) && document.activeElement.closest("details.file")?.dataset.path;
          files.replaceChildren(...(result.files_total ? [fileList(runId, result, result.files, result.files_total)] : []));
          for (const file of files.querySelectorAll("details.file")) {
            file.open = opened.has(file.dataset.path);
            if (file.dataset.path === focusedFile) file.querySelector("summary").focus({ preventScroll: true });
          }
        }
        snapshot = result;
        count.textContent = fileCount(result.files_total);
        status.textContent = result.files_total ? fileCount(result.files_total) + " in this snapshot."
          : "No files differ between these snapshots.";
        if (live) status.append(" Sampled ", clock(new Date().toISOString(), "ago"), ". Not independently verified.");
        if (result.review_range?.base_updated)
          status.append(" Base branch changed during this interval; incoming base changes are excluded.");
        read.textContent = "Refresh";
      } catch (error) {
        if (box.isConnected) status.textContent = "Unavailable: " + error.message;
      } finally {
        busy = false;
        read.disabled = false;
        if (dirty) { dirty = false; refresh(true); }
      }
    };
    read.onclick = () => refresh();
    box.loadReview = () => { if (!snapshot) refresh(true); };
    box.addEventListener("toggle", () => { if (box.open && (live || !snapshot)) refresh(true); });
    if (live) {
      box.refreshReview = () => refresh(true);
      currentReview = { runId: runId, refresh: box.refreshReview };
    }
    copy.onclick = async () => {
      read.disabled = true;
      try {
        if (!await copyPatch(runId, live ? fetchSnapshot() : snapshot || fetchSnapshot(), copy, "Copy milestone"))
          status.textContent = copy.title;
      } finally { read.disabled = false; }
    };
    controls.append(copy, read);
    body.append(controls, iterations, status, files);
    if (index) {
      const comparison = el("details", null, "milestone-compare");
      comparison.append(el("summary", "Compare with an earlier checkpoint"));
      const rangeCopy = el("button", "Copy range");
      rangeCopy.type = "button";
      const rangeStatus = el("p", "", "result");
      rangeStatus.setAttribute("role", "status");
      from.onchange = () => { rangeStatus.textContent = ""; };
      rangeCopy.onclick = async () => {
        from.disabled = true;
        try {
          if (!await copyPatch(runId, fetchSnapshot(from.value), rangeCopy, "Copy range"))
            rangeStatus.textContent = rangeCopy.title;
        } finally { from.disabled = false; }
      };
      const rangeControls = el("div", null, "section-head");
      rangeControls.append(label, rangeCopy);
      comparison.append(rangeControls, rangeStatus);
      body.append(comparison);
    }
    box.append(summary, body);
    all.append(box);
  }
  root.append(el("p", "Milestones run from one accepted action to the next (Approve, Revise, guidance or Continue). "
    + "Current shows changes since your last action.", "hint"), all);
  const retention = el("details", null, "milestone-retention");
  retention.append(el("summary", "About saved milestones"), el("p", "Milestones are saved after accepted operator actions. "
    + "Snapshots remain after worktree cleanup until explicitly released and use disk space. Opening or copying creates no milestone."));
  root.append(retention);
  updateChangeView();
  refreshCurrent();
  if (focused?.isConnected) focused.focus({ preventScroll: true });
}
