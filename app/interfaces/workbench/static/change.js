// A run's change as its target host's git reads it: one snapshot — the worktree's last commit and the tree its
// files make, or, while its base is merged into it after a conflict, that base and the tree — listed file by
// file, each opening into its diff, and its whole patch to copy. Read again, it is a new snapshot; nothing of the
// last one is mixed into it.

import { api } from "./api.js";
import { $, report } from "./ui.js";
import { copyPatch, fileList } from "./diff.js";

const size = new Intl.NumberFormat(undefined, { style: "unit", unit: "kilobyte", unitDisplay: "short",
  maximumFractionDigits: 0 });
let runId = null;
// The snapshot shown, and its first read: the patch's first part, where the next begins, its whole size.
let shown = null;
// The stop whose change was read on its own: a reread is the operator's, by the button.
let loadedFor = null;

// The change of `run`, not yet read.
export function showChangeFor(run) {
  runId = run;
  shown = null;
  loadedFor = null;
  $("change-said").textContent = "";
  report($("change-result"), "");
  $("diff-files").replaceChildren();
  $("diff-raw").hidden = true;
  $("diff-patch").textContent = "";
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
    $("change-said").textContent = "Against " + read.base.slice(0, 10)
      + (read.merging ? ", the base merged into this worktree: " : ", the worktree's last commit: ")
      + (read.files_total ? counted + "." : "the worktree holds no change.");
    $("diff-files").replaceChildren(...(read.files_total ? [fileList(reading, read, read.files, read.files_total)] : []));
    $("diff-raw").hidden = !read.total;
    $("diff-patch").textContent = read.patch;
    $("diff-size").textContent = read.next < read.total
      ? "the first " + size.format(Math.ceil(read.next / 1024)) + " of " + size.format(Math.ceil(read.total / 1024))
        + " shown; Copy patch copies all of it" : size.format(Math.ceil(read.total / 1024));
    $("diff-load").textContent = "Read it again";
    if (asked) report($("change-result"), read.files_total ? counted : "The worktree holds no change.");
  } catch (error) {
    if (reading !== runId) return;
    $("change-said").textContent = "The change cannot be read: " + error.message;
    if (asked) report($("change-result"), "The change cannot be read: " + error.message, true);
  }
}

// A read the operator asked for is said in its status line; one the page makes at a stop is not.
$("diff-load").onclick = () => loadDiff(true);
$("diff-copy").onclick = () => shown && copyPatch(runId, shown, shown, $("diff-copy"));
