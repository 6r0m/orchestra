// A repository's worktrees and what is still unmerged, and the removal of what a closed run kept.

import { api } from "./api.js";
import { $, code, confirmAction, copyButton, el, report, wrote } from "./ui.js";
import { chooseListed, choosePath, reposRead, sourceChoice } from "./picker.js";

const chosenRepo = sourceChoice("worktrees");
// What each state means, beside it.
const MEANS = { base: "the base branch itself", merged: "nothing in it the base lacks",
  unmerged: "commits the base lacks", uncommitted: "changes not yet committed", detached: "on no branch" };

// The view `#worktrees`, or `#worktrees=<repo>` with that repository's worktrees read at once: a name the
// list offers chosen from it, anything else given as its path.
export async function openWorktrees(repo) {
  if (!repo) return;
  await reposRead();
  if ([...$("worktrees-repo").options].some((option) => option.value === repo)) chooseListed("worktrees", repo);
  else choosePath("worktrees", repo);
  loadWorktrees();
}

async function loadWorktrees() {
  const table = $("worktrees-table");
  const repo = chosenRepo();
  if (!repo) {
    table.hidden = true;
    report($("worktrees-result"), "Choose a repository, or give its path.", true);
    return;
  }
  report($("worktrees-result"), "reading…");
  $("worktrees-base").textContent = "";
  try {
    const view = await api("/api/worktrees?repo=" + encodeURIComponent(repo));
    $("worktrees").replaceChildren(...view.rows.map(row));
    table.hidden = !view.rows.length;
    $("worktrees-base").textContent = "Merged means merged into " + view.base_branch + ".";
    report($("worktrees-result"), view.rows.length ? "" : "It has no worktrees.");
  } catch (error) {
    table.hidden = true;
    report($("worktrees-result"), "The worktrees cannot be read: " + error.message, true);
  }
}

function row(worktree) {
  const line = el("tr");
  const branch = el("td");
  if (worktree.run) {
    const link = el("a", worktree.branch);
    link.href = "#run=" + encodeURIComponent(worktree.branch);
    link.translate = false;
    branch.appendChild(link);
  } else {
    branch.appendChild(code(worktree.branch || "(detached)"));
  }
  const state = el("td");
  state.append(worktree.state, el("span", MEANS[worktree.state] || "", "gloss"));
  const run = el("td", worktree.run ? worktree.run.toLowerCase() : "");
  const path = el("td");
  path.append(code(worktree.path), " ", copyButton(worktree.path, "the worktree's path"));
  const act = el("td");
  if (worktree.removable) {
    const remove = el("button", "Remove", "danger");
    remove.type = "button";
    remove.setAttribute("aria-label", "Remove run " + worktree.branch + "'s worktree and branch");
    remove.onclick = () => removeKept(worktree.branch, $("worktrees-result"), loadWorktrees, remove);
    act.appendChild(remove);
  }
  line.append(branch, state, run, path, act);
  return line;
}

$("worktrees-form").onsubmit = (event) => {
  event.preventDefault();
  loadWorktrees();
};

// What a closed run kept — its worktree and branch, unmerged — removed through its host's own git, once
// the operator confirms it. What came of it is said at `line`, and `then` follows, only while `here` holds:
// while the page still shows what it was asked from.
export async function removeKept(runId, line, then, button, here = () => true) {
  const go = await confirmAction({ title: "Remove this run's worktree and branch?",
    body: "Remove deletes run " + runId + "'s worktree and its branch, with any of its work that is not merged.",
    confirm: "Remove", danger: true, returnTo: button });
  if (!go || !here()) return;
  report(line, "sending…");
  try {
    await api("/api/runs/" + encodeURIComponent(runId) + "/remove", { confirm: true });
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
