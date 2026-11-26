// A repository's worktrees and what is still unmerged, and the removal of what a closed run kept.

import { api, CONFIG } from "./api.js";
import { $, code, confirmAction, copyButton, el, report, showReading, wrote } from "./ui.js";
import { chooseRepository, clearRecordedRepository, isRepositoryPath, isSavedRepository, reposRead,
  showRecordedRepository, sourceChoice } from "./picker.js";
import { openRepositoryEditor } from "./repository-editor.js";

const chosenRepo = sourceChoice("worktrees");
const line = $("worktrees-result");
const load = $("worktrees-load");
const overview = $("worktrees-overview");
const count = $("worktrees-count");
let reading = 0;
let recordedRun = null;
let detection = null;
const writable = CONFIG.repositories_writable !== false;
$("repository-add").hidden = !writable;
$("repositories-managed").hidden = writable;
$("repository-add").onclick = () => openRepositoryEditor("worktrees");
$("repository-edit").onclick = () => openRepositoryEditor("worktrees", chosenRepo(), detection);
const STATES = { merged: ["Merged", "No commits missing from the base"],
  unmerged: ["Unmerged", "The base is missing commits"],
  uncommitted: ["Uncommitted", "Changes are pending a commit"], detached: ["Detached", "No branch"] };

function clearWorktrees() {
  reading++;
  detection = null;
  overview.hidden = true;
  count.hidden = true;
  showReading("worktrees-reading", false);
  report(line, "");
}

function updateLoad(manual = false) {
  load.disabled = !recordedRun && !chosenRepo();
  load.textContent = manual ? "Load worktrees" : "Refresh";
  load.title = manual ? "Read the worktrees at this repository path" : "Read the chosen repository's worktrees again";
  $("repository-edit").hidden = !(writable && isSavedRepository("worktrees"));
  $("worktrees-recorded").hidden = !recordedRun;
}

export async function openWorktrees(repo, run = null) {
  clearWorktrees();
  recordedRun = run;
  if (run) {
    showRecordedRepository("worktrees", "Run repository");
    loadWorktrees();
    return;
  }
  clearRecordedRepository("worktrees");
  updateLoad(isRepositoryPath("worktrees"));
  load.disabled = true;
  const request = reading, route = location.hash;
  showReading("worktrees-reading", true);
  const ready = await reposRead();
  if (request !== reading || location.hash !== route) return;
  if (repo) chooseRepository("worktrees", repo);
  if (repo || (!isRepositoryPath("worktrees") && chosenRepo())) loadWorktrees();
  else {
    showReading("worktrees-reading", false);
    updateLoad(isRepositoryPath("worktrees"));
    if (ready === false) report(line, "Saved repositories could not be read. Reopen the repository picker to retry.", true);
  }
}

async function loadWorktrees() {
  const run = recordedRun, repo = run ? null : chosenRepo();
  if (!run && !repo) return;
  clearWorktrees();
  const request = reading, route = (run ? "#worktrees-run=" : "#worktrees=") + encodeURIComponent(run || repo);
  if (location.hash !== route) history.replaceState(null, "", route);
  const here = () => request === reading && location.hash === route && recordedRun === run && (run || chosenRepo() === repo);
  updateLoad();
  showReading("worktrees-reading", true);
  report(line, "Reading worktrees…");
  try {
    const view = await api("/api/worktrees?" + (run ? "run=" : "repo=") + encodeURIComponent(run || repo));
    if (request !== reading || !here()) return;
    if (run && view.recorded) showRecordedRepository("worktrees", view.recorded.path, view.recorded.target);
    if (view.descriptor_revision) detection = { revision: view.descriptor_revision, branch: view.base_branch };
    renderWorktrees(view, here);
    report(line, view.rows.length ? "" : "This repository has no worktrees.");
  } catch (error) {
    if (request === reading && here()) report(line, "The worktrees cannot be read. " + error.message, true);
  } finally {
    if (request === reading && here()) showReading("worktrees-reading", false);
  }
}

function pathDetails(path) {
  const details = el("div", null, "worktree-path");
  details.append(code(path), copyButton(path, "the worktree path"));
  return details;
}

function renderWorktrees(view, here) {
  const base = view.rows.find((worktree) => worktree.state === "base");
  const additional = view.rows.filter((worktree) => worktree.state !== "base");
  count.textContent = view.rows.length;
  count.hidden = false;
  const baseHint = $("worktrees-base");
  baseHint.hidden = !!base || !view.base_branch;
  if (!baseHint.hidden) baseHint.replaceChildren("Base branch ", code(view.base_branch));
  const checkout = $("worktrees-checkout");
  checkout.hidden = !base;
  if (base) {
    const head = el("div", null, "worktree-overview");
    const title = el("h3");
    title.append(code(base.branch));
    head.append(title, el("span", "Base branch", "hint"));
    checkout.replaceChildren(head, pathDetails(base.path));
  }
  $("worktrees-none").hidden = !base || additional.length > 0;
  $("worktrees-table-wrap").hidden = !additional.length;
  $("worktrees").replaceChildren(...additional.map((worktree) => row(worktree, view, here)));
  overview.hidden = !view.rows.length;
}

function row(worktree, view, here) {
  const tr = el("tr");
  tr.setAttribute("role", "row");
  const branch = el("td");
  branch.append(code(worktree.branch || "(detached)"));
  const state = el("td");
  state.className = "worktree-state";
  state.dataset.state = worktree.state;
  const [label, meaning] = STATES[worktree.state] || [worktree.state, ""];
  state.append(label, el("span", meaning, "gloss"));
  const run = el("td");
  if (worktree.run) {
    const status = worktree.run.toLowerCase().replaceAll("_", " ");
    const link = el("a", status[0].toUpperCase() + status.slice(1));
    link.href = "#run=" + encodeURIComponent(worktree.branch);
    link.title = "Open run " + worktree.branch;
    link.setAttribute("aria-label", link.title + ", " + status);
    run.append(link);
  }
  const path = el("td");
  path.append(pathDetails(worktree.path));
  const act = el("td");
  if (worktree.removable) {
    const remove = el("button", "Remove", "danger quiet");
    remove.type = "button";
    remove.setAttribute("aria-label", "Remove run " + worktree.branch + "'s worktree and branch");
    remove.title = "Delete run " + worktree.branch + "'s worktree and branch, through its host's git";
    const displayed = { path: worktree.path, target: view.target, queue: view.target_queue };
    remove.onclick = () => removeKept(worktree.branch, line, loadWorktrees, remove, here, displayed);
    act.appendChild(remove);
  }
  for (const cell of [branch, state, run, path, act]) {
    cell.setAttribute("role", "cell");
    tr.append(cell);
  }
  return tr;
}

function editRepository() {
  clearWorktrees();
  if (location.hash !== "#worktrees" && location.hash.startsWith("#worktrees")) history.replaceState(null, "", "#worktrees");
  updateLoad(isRepositoryPath("worktrees"));
}

$("worktrees-source").addEventListener("change", () => {
  if ($("view-worktrees").hidden) return;
  recordedRun = null;
  if (!isRepositoryPath("worktrees") && chosenRepo()) loadWorktrees();
  else editRepository();
});
$("worktrees-path").addEventListener("input", editRepository);
$("worktrees-form").onsubmit = (event) => {
  event.preventDefault();
  loadWorktrees();
};

// What a closed run kept — its worktree and branch, unmerged — removed through its host's own git, once
// the operator confirms it. What came of it is said at `line`, and `then` follows, only while `here` holds:
// while the page still shows what it was asked from.
export async function removeKept(runId, line, then, button, here = () => true, worktree) {
  const go = await confirmAction({ title: "Remove this run's worktree and branch?",
    body: "Remove deletes run " + runId + "'s worktree and its branch, with any of its work that is not merged.",
    confirm: "Remove", danger: true, returnTo: button });
  if (!go || !here()) return;
  report(line, "sending…");
  try {
    await api("/api/runs/" + encodeURIComponent(runId) + "/remove", { confirm: true, worktree });
  } catch (error) {
    if (here()) report(line, "not accepted: " + error.message, true);
    return;
  }
  if (here()) {
    report(line, "removed");
    then();
  }
  wrote();
}
