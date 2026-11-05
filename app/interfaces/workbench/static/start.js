// Starting a run: its task, its repository — from repos.json or a path — the flow it follows, and whether
// it skips the flow's approvals.

import { api } from "./api.js";
import { $, el, report, sayRefused, score, wrote } from "./ui.js";
import { sourceChoice } from "./picker.js";

const chosenRepo = sourceChoice("start");
// The runs started from this page, by id, with the repository each was started on, until the list reads them
// closed. Kept in memory, as an unsent note is: a reload forgets them.
const starting = new Map();

// Each run started here that the list now reads closed, its ending known: one refused — before any work, which
// is the only place a run is refused — says so in the page's window, in the refusal's own words, read from the
// run. One whose ending cannot be read yet is looked at again at the next read.
export async function noteStarts(runs) {
  for (const run of runs) {
    const started = starting.get(run.run_id);
    if (!started || run.state !== "closed" || !run.status) continue;
    starting.delete(run.run_id);
    if (run.status !== "REFUSED") continue;
    let reason = null;
    try {
      const status = await api("/api/runs/" + encodeURIComponent(run.run_id));
      reason = status.state && status.state.refusal;
    } catch (error) {
      reason = null;
    }
    sayRefused({ title: "The run was refused",
      said: "It was refused before any work: no worktree was made and no agent started.",
      reason: reason || "Its reason cannot be read now; the run's own page says it once it can.",
      what: (run.repo || started.repo) + " · " + run.run_id });
  }
}
// The flows as last shown, so an unchanged answer leaves an open list as it is.
let shownFlows = "";
let listedFlows = [];
// Whether the flow shown is one the operator chose, rather than the settings' default: a default applied in
// Settings is taken up, and a choice is kept.
let chosenFlow = false;

function showFlowSteps() {
  const chosen = listedFlows.find((flow) => flow.name === $("start-flow").value);
  const steps = $("start-flow-steps");
  steps.hidden = !(chosen && chosen.steps);
  if (chosen && chosen.steps) score(steps, chosen.steps);
}

async function loadFlows() {
  const answer = await api("/api/flows");
  const shown = JSON.stringify(answer);
  if (shown === shownFlows) return;
  shownFlows = shown;
  listedFlows = answer.flows;
  const select = $("start-flow");
  // The flow the operator chose, else the settings' default; "" when they name none.
  const chosen = chosenFlow ? select.value : answer.default || "";
  const options = answer.flows.map((flow) => {
    // A flow that breaks a rule is listed, never offered: its reason is what to fix in its file. The one
    // chosen stays chosen, so a start on it is refused with that reason, never made on another flow.
    const option = el("option", flow.error ? flow.name + " (refused)" : flow.name);
    option.value = flow.name;
    option.disabled = Boolean(flow.error) && flow.name !== chosen;
    if (flow.error) option.title = flow.error;
    return option;
  });
  if (chosen && !answer.flows.some((flow) => flow.name === chosen)) {
    // So does a flow chosen, or named the default, that has no file.
    const missing = el("option", chosen + " (missing)");
    missing.value = chosen;
    options.unshift(missing);
  }
  if (!answer.default) {
    // With no default in the policy a run names no flow, as the command line's does, and takes the
    // order runs took before flows.
    const none = el("option", "none — the order from before flows");
    none.value = "";
    options.unshift(none);
  }
  select.replaceChildren(...options);
  select.value = chosen;
  showFlowSteps();
}

// flows/ is read again each time the list is opened, so a flow added or edited there shows without a reload.
export const reloadFlows = () => loadFlows().catch((error) => report($("start-result"), error.message, true));
$("start-flow").onfocus = reloadFlows;
$("start-flow").onchange = () => {
  chosenFlow = true;
  showFlowSteps();
};

$("start").onsubmit = async (event) => {
  event.preventDefault();
  const button = event.submitter || $("start").querySelector("button[type=submit]");
  const repo = chosenRepo();
  if (!repo) {
    report($("start-result"), "Choose a repository, or give its path.", true);
    return;
  }
  // The run started opens only while the page is still where it was started from: an operator who moved
  // on meanwhile stays where they went, and finds it in the list.
  const from = location.hash;
  button.disabled = true;
  report($("start-result"), "starting…");
  try {
    const started = await api("/api/runs", { task: $("start-task").value, repo: repo,
      flow: $("start-flow").value, auto_proceed: $("start-auto").checked });
    report($("start-result"), "started " + started.run_id);
    starting.set(started.run_id, { repo: repo });
    $("start-task").value = "";
    wrote();
    if (location.hash === from) location.hash = "#run=" + encodeURIComponent(started.run_id);
  } catch (error) {
    // A 4xx is the Workbench's refusal before any run is made: it checks the request, the repository, the flow,
    // the settings and the workers before it starts one. Anything else — its own failure or timeout, which may
    // come after Temporal took the start, or no answer at all — leaves whether a run was made unknown here, and
    // the list of runs says; starting it again could start it twice.
    const refused = error.status >= 400 && error.status < 500;
    report($("start-result"), (refused ? "refused: " : "not confirmed: ") + error.message, true);
    sayRefused(refused
      ? { title: "The run was not started", said: "The Workbench refused it before making a run.",
        reason: error.message, what: repo }
      : { title: "The start was not confirmed", said: "Whether a run was made is not known: check the list of runs " +
        "before starting it again.", reason: error.message, what: repo });
  } finally {
    button.disabled = false;
  }
};
