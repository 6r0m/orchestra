// The workbench page's entry: the view the URL's fragment names, the reads every few seconds, and the
// times kept current. Each part of the page is its own module and owns what it draws.

import { $, showReading, tick, unchanged } from "./ui.js";
import { noteRuns, refreshStack } from "./stack.js";
import { reloadRepos } from "./picker.js";
import { noteStarts, reloadFlows } from "./start.js";
import { prepareRuns, refreshRuns, runOverview, runsListed, select } from "./rail.js";
import { refreshRun, show, unsent } from "./run.js";
import { openWorktrees } from "./worktrees.js";
import { jumpToSettingsSection, openSettings, settingsSection, settingsUnsent } from "./settings.js";
import { noteTerminalRuns, showTerminalHistory } from "./terminals.js";

const VIEWS = { empty: "view-empty", new: "view-new", worktrees: "view-worktrees", settings: "view-settings",
  run: "run" };

// A fragment that is not well encoded names nothing, rather than stopping the page.
function decoded(text) {
  try {
    return decodeURIComponent(text);
  } catch (error) {
    return null;
  }
}

// `#run=<id>`, `#new`, `#worktrees`, `#worktrees=<repo>` or `#settings`: the fragment is the browser's, so a
// reload keeps it, a link opens it in a new tab, and it never reaches the server.
function route(event) {
  if ($("confirm").open) $("confirm").close();
  if ($("repo-picker").open) $("repo-picker").close();
  if ($("repository-editor").open) $("repository-editor").close();
  const hash = location.hash;
  const settingsAnchor = settingsSection(hash);
  let view = "empty";
  let runId = null;
  let worktreeRepo = null;
  let worktreeRun = null;
  let match = hash.match(/^#run=(.+)$/);
  if (match) {
    view = "run";
    runId = decoded(match[1]);
  } else if (hash === "#new") {
    view = "new";
  } else if ((match = hash.match(/^#worktrees(?:=(.+))?$/))) {
    view = "worktrees";
    worktreeRepo = match[1] ? decoded(match[1]) : null;
  } else if ((match = hash.match(/^#worktrees-run=(.+)$/))) {
    view = "worktrees";
    worktreeRun = decoded(match[1]);
  } else if (hash === "#settings" || settingsAnchor) {
    view = "settings";
    if ($("view-settings").hidden) openSettings();
  }
  for (const [name, id] of Object.entries(VIEWS)) $(id).hidden = name !== view;
  prepareRuns(Boolean(event) && view === "run");
  if (view === "worktrees") openWorktrees(worktreeRepo, worktreeRun);
  for (const [id, views] of [["nav-runs", ["empty", "run", "new"]],
    ["nav-worktrees", ["worktrees"]], ["nav-settings", ["settings"]]]) {
    if (views.includes(view)) $(id).setAttribute("aria-current", view === "new" ? "location" : "page");
    else $(id).removeAttribute("aria-current");
  }
  show(runId);
  select(runId);
  showEmpty();
  if (view === "settings" && jumpToSettingsSection(settingsAnchor)) return;
  if (event) {
    if (view === "new") {
      $("start-task").focus();
    } else {
      const heading = $(VIEWS[view]).querySelector("h1");
      heading.tabIndex = -1;
      heading.focus();
    }
  }
}

function showEmpty() {
  if ($("view-empty").hidden) return;
  const { groups, read, unavailable, more } = runOverview();
  const waiting = groups.waiting.length, running = groups.running.length;
  const next = groups.waiting[0] || groups.running[0];
  const state = unavailable ? "unavailable" : !read ? "loading" : next ? "active" : "idle";
  const panel = $("resting-state");
  const closed = groups.finished.length, rejected = groups.rejected.length;
  if (unchanged(panel, [state, waiting, running, next?.run_id, closed, rejected, more])) return;
  const copy = {
    loading: ["Reading runs…", ""],
    unavailable: ["Run list unavailable", "The Workbench will try again."],
    idle: ["You’re all caught up", "No active runs or pending decisions."],
    active: waiting ? [waiting + (waiting === 1 ? " run needs attention" : " runs need attention"), "Open the newest run waiting for you."]
      : ["Runs in progress", "Open the newest run to see its progress."],
  };
  const [title, detail] = copy[state];
  panel.dataset.state = state;
  showReading("home-reading", state === "loading");
  $("empty-title").textContent = title;
  const message = $("empty-said");
  message.textContent = detail;
  message.hidden = !detail;
  const action = $("empty-action");
  action.hidden = state !== "idle" && state !== "active";
  action.href = state === "active" ? "#run=" + encodeURIComponent(next.run_id) : "#new";
  action.textContent = state === "active" ? (waiting ? "Review run" : "Open run") : "New run";
  action.title = state === "active" ? "Open this run in the Workbench" : "Open the form that starts a run";
  const history = $("empty-counts");
  history.hidden = state !== "idle" || !(closed || rejected || more);
  history.textContent = closed + (closed === 1 ? " closed run" : " closed runs") + " · " + rejected + " rejected"
    + (more ? " · More history available" : "");
}

$("skip").onclick = (event) => {
  // The skip link moves focus without changing the fragment, which names the view.
  event.preventDefault();
  $("main").focus();
};

window.addEventListener("hashchange", route);
// Leaving the page asks first while a task or a note is typed and not sent, or settings changed and not applied.
window.addEventListener("beforeunload", (event) => {
  if ($("start-task").value.trim() || unsent() || settingsUnsent()) event.preventDefault();
});
// Settings applied: a new run's flow is read again, its default among them.
document.addEventListener("workbench:settings", reloadFlows);
// After a write of the page's own, what it changed is read at once.
document.addEventListener("workbench:wrote", () => {
  refreshRuns();
  refreshRun();
});
document.addEventListener("workbench:runs", () => {
  showEmpty();
  if (runOverview().unavailable) return;
  noteTerminalRuns(runsListed());
  noteRuns(runsListed());
  noteStarts(runsListed());
});

if (new URLSearchParams(location.search).has("terminal-history")) {
  showTerminalHistory(new URLSearchParams(location.search));
} else {
  route();
  reloadRepos();
  reloadFlows();
  refreshStack();
  refreshRuns();
  setInterval(refreshStack, 5000);
  setInterval(refreshRuns, 5000);
  setInterval(refreshRun, 2500);
  setInterval(tick, 5000);
}
