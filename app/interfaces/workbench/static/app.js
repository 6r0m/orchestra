// The workbench page's entry: the view the URL's fragment names, the reads every few seconds, and the
// times kept current. Each part of the page is its own module and owns what it draws.

import { $, tick } from "./ui.js";
import { noteRuns, refreshStack } from "./stack.js";
import { reloadRepos } from "./picker.js";
import { reloadFlows } from "./start.js";
import { refreshRuns, runsListed, runsRead, select } from "./rail.js";
import { refreshRun, show, unsent } from "./run.js";
import { openWorktrees } from "./worktrees.js";

const VIEWS = { empty: "view-empty", new: "view-new", worktrees: "view-worktrees", run: "run" };

// A fragment that is not well encoded names nothing, rather than stopping the page.
function decoded(text) {
  try {
    return decodeURIComponent(text);
  } catch (error) {
    return null;
  }
}

// `#run=<id>`, `#new`, `#worktrees` or `#worktrees=<repo>`: the fragment is the browser's, so a reload
// keeps it, a link opens it in a new tab, and it never reaches the server.
function route(event) {
  if ($("confirm").open) $("confirm").close();
  const hash = location.hash;
  let view = "empty";
  let runId = null;
  let match = hash.match(/^#run=(.+)$/);
  if (match) {
    view = "run";
    runId = decoded(match[1]);
  } else if (hash === "#new") {
    view = "new";
  } else if ((match = hash.match(/^#worktrees(?:=(.+))?$/))) {
    view = "worktrees";
    openWorktrees(match[1] ? decoded(match[1]) : null);
  }
  for (const [name, id] of Object.entries(VIEWS)) $(id).hidden = name !== view;
  for (const [id, name] of [["nav-new", "new"], ["nav-worktrees", "worktrees"]]) {
    if (view === name) $(id).setAttribute("aria-current", "page");
    else $(id).removeAttribute("aria-current");
  }
  show(runId);
  select(runId);
  showEmpty();
  // Asked for by the operator, the form takes the typing at once.
  if (event && view === "new") $("start-task").focus();
}

// With runs listed and none open, a small word on what waits; with none at all, the form to start one.
function showEmpty() {
  if (!runsRead()) return;
  const runs = runsListed();
  if (!location.hash && !runs.length) {
    history.replaceState(null, "", "#new");
    route();
    return;
  }
  const waiting = runs.filter((run) => run.state === "waiting" || run.state === "failed").length;
  $("empty-said").textContent = waiting === 1 ? "One run waits for you: it is first in the list."
    : waiting ? waiting + " runs wait for you: they are first in the list."
      : runs.length ? "Nothing waits for you. Open a run to watch it, or start one with New run."
        : "No runs yet.";
}

$("skip").onclick = (event) => {
  // The skip link moves focus without changing the fragment, which names the view.
  event.preventDefault();
  $("main").focus();
};

window.addEventListener("hashchange", route);
// Leaving the page asks first while a task or a note is typed and not sent.
window.addEventListener("beforeunload", (event) => {
  if ($("start-task").value.trim() || unsent()) event.preventDefault();
});
// After a write of the page's own, what it changed is read at once.
document.addEventListener("workbench:wrote", () => {
  refreshRuns();
  refreshRun();
});
document.addEventListener("workbench:runs", () => {
  noteRuns(runsListed());
  showEmpty();
});

route();
reloadRepos();
reloadFlows();
refreshStack();
refreshRuns();
setInterval(refreshStack, 5000);
setInterval(refreshRuns, 5000);
setInterval(refreshRun, 2500);
setInterval(tick, 5000);
