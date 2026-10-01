// A change shown file by file: its files by their exact paths, each opening into its diff as an editor shows one —
// line numbers on both sides, added lines green, removed red, long unchanged runs folded — and its whole patch to
// copy. Every read names one snapshot, its base and its tree, so all of it is one change whatever the live
// worktree does meanwhile. File text reaches the page only as text.

import { api } from "./api.js";
import { el } from "./ui.js";

const STATUS = { A: "added", D: "deleted", M: "modified", R: "renamed", C: "copied", T: "type changed" };
// Unchanged lines kept beside a change, and the fewest a fold hides: a shorter run is shown whole.
const CONTEXT = 3;
const FOLD_AT = 4;
const SIGN = { add: "+", del: "-", ctx: " " };

function diffPath(runId, query) {
  return "/api/runs/" + encodeURIComponent(runId) + "/diff?" + new URLSearchParams(query);
}

// A snapshot's files, each a disclosure whose diff is read when it first opens.
export function fileList(runId, snapshot, files, total) {
  const box = el("div", null, "files");
  const list = el("ul", null, "file-list");
  list.append(...files.map((file) => fileItem(runId, snapshot, file)));
  box.append(list);
  if (total > files.length) {
    box.append(el("p", (total - files.length) + " more files are not listed here; Copy patch holds every one.",
      "hint"));
  }
  return box;
}

function fileItem(runId, snapshot, file) {
  const item = el("li");
  const box = el("details", null, "file");
  box.dataset.path = file.path;
  const summary = el("summary");
  const status = el("span", file.status, "status " + file.status);
  status.setAttribute("aria-hidden", "true");
  summary.append(chevron(), status, el("span", STATUS[file.status] || file.status, "visually-hidden"), " ",
    pathOf(file), counts(file));
  const body = el("div", null, "file-body");
  box.append(summary, body);
  box.addEventListener("toggle", () => {
    if (box.open && !box.dataset.loaded) loadFile(runId, snapshot, file, box, body);
  });
  item.append(box);
  return item;
}

// Whether a disclosure is open, drawn by the stylesheet from its `open`.
export function chevron() {
  const mark = el("span", null, "chevron");
  mark.setAttribute("aria-hidden", "true");
  return mark;
}

// A path whole, never cut: its folder quiet, its name in ink, a rename from its old path.
function pathOf(file) {
  const shown = el("span", null, "path");
  shown.translate = false;
  if (file.old) shown.append(split(file.old), el("span", " → ", "arrow"));
  shown.append(split(file.path));
  return shown;
}

function split(path) {
  const cut = path.lastIndexOf("/") + 1;
  const whole = el("span");
  whole.append(el("span", path.slice(0, cut), "dir"), el("span", path.slice(cut), "name"));
  return whole;
}

function counts(file) {
  const box = el("span", null, "counts");
  if (file.binary) {
    box.append(el("span", "binary", "hint"));
  } else {
    box.append(el("span", "+" + file.added, "added"), el("span", "−" + file.removed, "removed"));
  }
  return box;
}

async function loadFile(runId, snapshot, file, box, body) {
  if (file.binary) {
    box.dataset.loaded = "yes";
    body.replaceChildren(el("p", "Binary file — no text diff.", "hint"));
    return;
  }
  box.dataset.loaded = "loading";
  body.replaceChildren(el("p", "Reading the file…", "hint"));
  try {
    const read = await api(diffPath(runId, { base: snapshot.base, tree: snapshot.tree, file: file.path }));
    if (!box.isConnected) return;
    const shown = [viewer(read.patch, read.whole)];
    if (!read.whole) {
      shown.unshift(el("p", "Too large to show whole: its changes, with three lines around each.", "hint"));
    }
    body.replaceChildren(...shown);
    box.dataset.loaded = "yes";
  } catch (error) {
    if (!box.isConnected) return;
    delete box.dataset.loaded;
    const line = el("p", "The file cannot be read: " + error.message, "alert");
    line.setAttribute("role", "alert");
    const again = el("button", "Read again");
    again.type = "button";
    again.onclick = () => loadFile(runId, snapshot, file, box, body);
    body.replaceChildren(line, again);
  }
}

// One file's unified diff, read from its first hunk: git's header lines before it are not shown, the list names
// the file. A whole file is one hunk, its unchanged runs folded; a changes-only diff keeps its hunks apart.
export function viewer(text, whole) {
  const rows = parse(text);
  if (!rows.length) return el("p", "No text changes in this file: its name or its mode changed.", "hint");
  // The lines in one column as wide as the widest, so a scrolled line keeps its colour to the end.
  const lines = el("div", null, "diff-lines");
  const shown = whole ? rows.filter((row) => row.kind !== "hunk") : rows;
  let at = 0;
  while (at < shown.length) {
    if (shown[at].kind !== "ctx") {
      lines.append(line(shown[at]));
      at += 1;
      continue;
    }
    let end = at;
    while (end < shown.length && shown[end].kind === "ctx") end += 1;
    const changed = (row) => row && (row.kind === "add" || row.kind === "del");
    const head = changed(shown[at - 1]) ? CONTEXT : 0;
    const tail = changed(shown[end]) ? CONTEXT : 0;
    if (end - at - head - tail >= FOLD_AT) {
      lines.append(...shown.slice(at, at + head).map(line), fold(shown.slice(at + head, end - tail)),
        ...shown.slice(end - tail, end).map(line));
    } else {
      lines.append(...shown.slice(at, end).map(line));
    }
    at = end;
  }
  const box = el("div", null, "diff");
  box.translate = false;
  box.append(lines);
  return box;
}

function parse(text) {
  const lines = text.split("\n");
  if (lines[lines.length - 1] === "") lines.pop();
  const rows = [];
  let older = 0;
  let newer = 0;
  let begun = false;
  for (const text of lines) {
    const hunk = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(text);
    if (hunk) {
      begun = true;
      older = Number(hunk[1]);
      newer = Number(hunk[2]);
      rows.push({ kind: "hunk", text: text });
    } else if (!begun) {
      continue;
    } else if (text.startsWith("+")) {
      rows.push({ kind: "add", newer: newer++, text: text.slice(1) });
    } else if (text.startsWith("-")) {
      rows.push({ kind: "del", older: older++, text: text.slice(1) });
    } else if (text.startsWith("\\")) {
      rows.push({ kind: "note", text: text.slice(2) });
    } else {
      rows.push({ kind: "ctx", older: older++, newer: newer++, text: text.slice(1) });
    }
  }
  return rows;
}

function line(row) {
  if (row.kind === "hunk") return el("div", row.text, "ln hunk");
  if (row.kind === "note") return el("div", row.text, "ln note");
  const shown = el("div", null, "ln " + row.kind);
  shown.append(el("span", row.older ?? "", "no"), el("span", row.newer ?? "", "no"), el("span", SIGN[row.kind], "sign"),
    el("span", row.text, "text"));
  return shown;
}

// Unchanged lines out of the way, a click from being shown in place.
function fold(rows) {
  const button = el("button", "Show " + rows.length + " unchanged lines (" + rows[0].newer + "–"
    + rows[rows.length - 1].newer + ")", "fold");
  button.type = "button";
  button.onclick = () => button.replaceWith(...rows.map(line));
  return button;
}

// The snapshot's whole patch, every part of it read from the same snapshot, and put on the clipboard.
export async function copyPatch(runId, snapshot, first, button) {
  const whole = (async () => {
    let patch = first.patch;
    let next = first.next;
    while (next < first.total) {
      const part = await api(diffPath(runId, { base: snapshot.base, tree: snapshot.tree, offset: next }));
      patch += part.patch;
      next = part.next;
    }
    return patch;
  })();
  button.disabled = true;
  try {
    // Written as the click's own, so a patch read in several parts still reaches the clipboard.
    if (window.ClipboardItem && navigator.clipboard.write) {
      await navigator.clipboard.write([new ClipboardItem({
        "text/plain": whole.then((text) => new Blob([text], { type: "text/plain" })) })]);
    } else {
      await navigator.clipboard.writeText(await whole);
    }
    button.textContent = "Copied";
  } catch (error) {
    button.textContent = "Copy failed";
    button.title = error.message;
  }
  button.disabled = false;
  setTimeout(() => { button.textContent = "Copy patch"; }, 1500);
}
