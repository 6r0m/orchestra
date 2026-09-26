// Starting a run: its task, its repository — from repos.json or a path — the flow it follows, and whether
// it skips the flow's approvals.

import { api } from "./api.js";
import { $, el, report, score, wrote } from "./ui.js";
import { sourceChoice } from "./picker.js";

const chosenRepo = sourceChoice("start");
// The flows as last shown, so an unchanged answer leaves an open list as it is.
let shownFlows = "";
let listedFlows = [];

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
  // The flow chosen, else the policy's default; "" when the policy names none.
  const chosen = select.value || answer.default || "";
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
$("start-flow").onchange = showFlowSteps;

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
    $("start-task").value = "";
    wrote();
    if (location.hash === from) location.hash = "#run=" + encodeURIComponent(started.run_id);
  } catch (error) {
    report($("start-result"), "refused: " + error.message, true);
  } finally {
    button.disabled = false;
  }
};
