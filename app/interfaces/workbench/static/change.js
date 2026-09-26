// A run's change as its target host's git reads it. One too large for a single payload is read in parts,
// each carrying the identity of the change it came from, so parts of two changes are never shown as one.

import { api } from "./api.js";
import { $, el, report } from "./ui.js";

const size = new Intl.NumberFormat(undefined, { style: "unit", unit: "kilobyte", unitDisplay: "short",
  maximumFractionDigits: 0 });
let runId = null;
// Which change the page holds, how much of it, and its patch as read so far.
let read = { snapshot: null, total: 0, bytes: 0 };
let patch = "";
// The stop whose change was read on its own: a reread is the operator's, by the button.
let loadedFor = null;

// The change of `run`, not yet read.
export function showChangeFor(run) {
  runId = run;
  read = { snapshot: null, total: 0, bytes: 0 };
  patch = "";
  loadedFor = null;
  $("change-said").textContent = "";
  report($("change-result"), "");
  $("diff-summary").textContent = "";
  $("diff-patch").replaceChildren();
  $("diff-more").hidden = true;
  $("diff-load").textContent = "Read the change";
}

// Where the change sits: under the decision when it is what the decision judges, after the history
// otherwise, or nowhere while the run has no change to read.
export function placeChange(where) {
  const section = $("change");
  section.hidden = where === "none";
  const after = where === "evidence" ? $("stop") : $("history");
  if (where !== "none" && section.previousElementSibling !== after) after.after(section);
}

// At a stop that asks the operator to judge a change, the change is read once, on its own.
export function readOnceFor(stop) {
  if (loadedFor === stop.id) return;
  loadedFor = stop.id;
  loadDiff(0);
}

async function loadDiff(offset, note, asked) {
  const from = offset || 0;
  const reading = runId;
  $("diff-more").hidden = true;
  if (!from) $("change-said").textContent = "Reading the worktree…";
  try {
    const diff = await api("/api/runs/" + encodeURIComponent(reading) + "/diff?offset=" + from);
    if (reading !== runId) return;
    if (from && diff.snapshot !== read.snapshot) {
      // The worktree changed under the reading — an edit of the same size looks identical by length —
      // so the parts are of two changes and would not fit together.
      return loadDiff(0, "The change moved while it was being read, so it was read again from the start.", asked);
    }
    // Where the next part starts is the reader's own answer: a part never ends inside a character.
    read = { snapshot: diff.snapshot, total: diff.total, bytes: diff.next };
    patch = from ? patch + diff.patch : diff.patch;
    // Only its end is trimmed: the stat's first column starts with a space, and its columns must line up.
    const summary = diff.summary.replace(/\s+$/, "");
    $("change-said").textContent = [note, "Against " + diff.base + ", the worktree's last commit.",
      summary.trim() ? "" : "The worktree holds no change.",
      new TextEncoder().encode(summary).length < diff.summary_total ? "The file list is too long to show whole." : ""]
      .filter(Boolean).join(" ");
    $("diff-summary").textContent = summary;
    drawPatch();
    const left = diff.total - read.bytes;
    $("diff-more").hidden = left <= 0;
    $("diff-more").textContent = "Read the next part (" + size.format(Math.ceil(left / 1024)) + " left)";
    $("diff-load").textContent = "Read it again";
    if (asked) {
      report($("change-result"), summary.trim() ? summary.trim().split("\n").pop().trim() : "The worktree holds no change.");
    }
  } catch (error) {
    if (reading !== runId) return;
    $("change-said").textContent = "The change cannot be read: " + error.message;
    if (asked) report($("change-result"), "The change cannot be read: " + error.message, true);
  }
}

// The patch read so far, a line each, marked by what the line is: a file's header, a hunk, a line added or
// removed. A new file's lines are its text, without the marks.
function drawPatch() {
  const lines = patch.split("\n");
  if (lines[lines.length - 1] === "") lines.pop();
  let created = false;
  $("diff-patch").replaceChildren(...lines.map((line) => {
    let kind = "";
    if (line.startsWith("diff --git ")) {
      kind = "file";
      created = false;
    } else if (line.startsWith("new file mode")) {
      kind = "meta";
      created = true;
    } else if (/^(index |--- |\+\+\+ |deleted file mode|old mode|new mode|similarity|rename |\\ )/.test(line)) {
      kind = "meta";
    } else if (line.startsWith("@@")) {
      kind = "hunk";
    } else if (line.startsWith("+")) {
      return created ? el("span", line.slice(1), "new") : el("span", line, "add");
    } else if (line.startsWith("-")) {
      kind = "del";
    }
    return el("span", line, kind);
  }));
}

// A read the operator asked for is said in its status line; one the page makes at a stop is not.
$("diff-load").onclick = () => loadDiff(0, null, true);
$("diff-more").onclick = () => loadDiff(read.bytes, null, true);
