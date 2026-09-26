// One run, in the order it needs the operator: what it is and does now, the decision it waits for with its
// evidence, its own controls, what it kept, its terminals, its history and its change. The terminals and
// the change reader are their own owners; this module asks them, and never redraws their nodes.

import { api } from "./api.js";
import { $, PARTS, at, blockedBy, clock, code, confirmAction, copyButton, decisionTitle, doing, el, headline,
  outcome, report, score, unchanged, wrote } from "./ui.js";
import { stackButton, stackReading } from "./stack.js";
import { showTerminals, updateTerminals } from "./terminals.js";
import { placeChange, readOnceFor, showChangeFor } from "./change.js";
import { removeKept } from "./worktrees.js";

// How an answer is shown. Which answers a stop takes comes with the stop, and whether one is accepted is
// the workflow's; an action named here only by the stop still gets its button.
const LABELS = { approve: "Approve", revise: "Revise", "revise:engineer": "Revise (engineer)",
  "revise:architect": "Revise (architect)", guide: "Guide", continue: "Continue", merge: "Merge",
  discard: "Discard" };
// The answer that moves the run on is the primary one; discard is the dangerous one.
const PRIMARY = new Set(["approve", "merge", "guide", "continue"]);
const DANGER = new Set(["discard"]);
// The answers the operator's note is sent with — its label names them, and a refusal of one is shown at
// the note. Whether an answer needs words is the workflow's to refuse, never the page's.
const WORDED = { revise: "Revise", "revise:engineer": "Revise", "revise:architect": "Revise", guide: "Guide" };
const WORDLESS = new Set(["approve", "continue", "merge", "discard"]);
// A second look before an answer that lands or removes the work.
const ASK = {
  merge: { title: "Merge the verified change into the base branch?", confirm: "Merge" },
  discard: { title: "Discard this run's work?", confirm: "Discard", danger: true,
    body: "Discard deletes the worktree and its branch, with the change in them." },
};
// A run's lifecycle, after its decision: Stop ends it from whatever it is doing and keeps its work; force
// terminate is for a run a Stop cannot finish, and says what it cannot stop.
const LIFECYCLE = {
  stop: { title: "Stop this run?", body: "Its worktree and branch stay as they are.", confirm: "Stop run",
    danger: true, said: "stopping" },
  terminate: { title: "Force terminate this run?", confirm: "Force terminate", danger: true, said: "terminated",
    body: "Force terminate closes the run at once, with no cleanup, but cannot stop what its host is already " +
      "doing. An agent at work ends at its turn's next heartbeat; a worktree's creation, a merge or a discard " +
      "already running goes on, and may still change the repository afterwards. The run's terminals stay " +
      "until its host's worker restarts.", sent: { confirm: true } },
};
const GATES = { approval: "your approval", blocker: "your guidance", exhausted: "your guidance" };

let selected = null;
let shownStop = null;
// What the operator has typed for each stop and not yet sent: another run opened and this one again, the
// note is still there.
const drafts = new Map();
$("stop-note").addEventListener("input", () => {
  if (shownStop) drafts.set(shownStop, $("stop-note").value);
});

// Whether words the operator typed for a stop have not been sent.
export const unsent = () => [...drafts.values()].some((text) => text.trim());
// The texts the decision shows, which the history then keeps closed, marked as shown above.
let shownAbove = new Set();

// The run `runId` on the page, or none.
export function show(runId) {
  if (selected === runId) return;
  selected = runId;
  shownStop = null;
  shownAbove = new Set();
  // Nothing of the run shown before stays under this one's title, even while this one cannot be read.
  for (const id of ["run-facts", "run-score", "run-now", "run-blocked", "run-kept", "timeline", "lines"]) {
    delete $(id).dataset.drew;
  }
  for (const id of ["run-task", "run-now", "lines"]) $(id).textContent = "";
  for (const id of ["run-facts", "run-score", "timeline"]) $(id).replaceChildren();
  for (const id of ["stop", "run-blocked", "run-kept", "run-controls"]) $(id).hidden = true;
  for (const id of ["run-control-result", "run-kept-result", "run-blocked-result"]) report($(id), "");
  showTerminals(null);
  showChangeFor(runId);
  placeChange("none");
  if (runId) refreshRun();
}

export async function refreshRun() {
  if (!selected) return;
  const runId = selected;
  let status;
  try {
    status = await api("/api/runs/" + encodeURIComponent(runId));
  } catch (error) {
    if (runId !== selected) return;
    if (!$("run-task").textContent) $("run-task").textContent = runId;
    $("run-now").textContent = "It cannot be read: " + error.message;
    delete $("run-now").dataset.drew;
    return;
  }
  if (runId !== selected) return;
  const view = status.view;
  const state = status.state;
  // With its worker down the run is shown from its listing alone: what it last said stays on the page.
  if (!status.unreadable || !$("run-task").textContent) $("run-task").textContent = view.goal || runId;
  if (!status.unreadable || !$("run-facts").children.length) {
    renderFacts(runId, view, state, status.links, status.timeline);
  }
  renderScore(view);
  renderNow(view, status);
  renderBlocked(view);
  renderControls(view);
  if (status.unreadable) return;
  renderStop(status.stop, status.timeline);
  renderKept(runId, view);
  renderChange(view, status.stop, status.timeline);
  renderHistory(view, status.timeline);
  if (!unchanged($("lines"), status.lines)) $("lines").textContent = status.lines.join("\n");
  showTerminals(runId, state.target);
  // A failed step's terminal is where its failure shows.
  const failedRole = view.state === "failed" && state.current ? state.current.role : null;
  updateTerminals(view.state !== "closed", view.role || failedRole || null);
}

// ---- what the run is --------------------------------------------------------------------------

function renderFacts(runId, view, state, links, timeline) {
  const planned = Boolean(state.plan) && timeline.some((entry) => entry.stage === "plan");
  const facts = [
    ["Repository", view.repo && code(view.repo)],
    ["Host", view.host && code(view.host)],
    ["Flow", view.flow && (view.flow.name ? code(view.flow.name) : "the order from before flows")],
    ["Run and branch", [code(runId), copyButton(runId, "the run's id")]],
    ["Worktree", view.worktree && [code(view.worktree), copyButton(view.worktree, "the worktree's path")]],
    ["Plan", planned && [code(state.plan), copyButton(state.todo_path || state.plan, "the plan's path")]],
    ["Started", view.started && at(view.started)],
    ["Open in", openIn(links)],
  ];
  const list = $("run-facts");
  if (unchanged(list, [runId, view.repo, view.host, view.flow && view.flow.name, view.worktree, planned,
    state.plan, view.started, links])) return;
  list.replaceChildren(...facts.filter(([, value]) => value).map(([term, value]) => {
    const pair = el("div");
    const shown = el("dd");
    shown.append(...[].concat(value));
    pair.append(el("dt", term), shown);
    return pair;
  }));
}

function openIn(links) {
  if (!links) return null;
  const found = [["Temporal", links.temporal], ["Langfuse", links.trace]].filter(([, href]) => href);
  if (!found.length) return null;
  return found.map(([name, href]) => {
    const link = el("a", name);
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener";
    return link;
  });
}

function renderScore(view) {
  const list = $("run-score");
  if (unchanged(list, [view.flow, view.step, view.state, view.status])) return;
  list.hidden = !view.flow;
  if (!view.flow) return list.replaceChildren();
  const closed = view.state === "closed";
  score(list, view.flow.steps, view.step, closed ? (["MERGED", "DONE"].includes(view.status) ? "done" : "stopped") : null,
    view.state === "running");
  list.setAttribute("aria-label", "Its flow, " + (view.flow.name || "the order from before flows"));
}

// What the run is doing now, in one sentence, with how long it has been so.
function renderNow(view, status) {
  const line = $("run-now");
  if (unchanged(line, [status.unreadable, view.state, view.stage, view.role, view.since, view.closed, view.status,
    view.execution, status.state && status.state.refusal])) return;
  line.replaceChildren(...nowSaid(view, status));
}

function since(iso) {
  return iso ? [" for ", clock(iso), " (since " + at(iso) + ")"] : [];
}

function nowSaid(view, status) {
  if (status.unreadable) return ["Its status cannot be read now: " + status.unreadable.replace(/^its status cannot be read now: /, "")];
  if (view.state === "waiting" || view.state === "failed") return ["Waiting for your answer", ...since(view.since)];
  if (view.state === "stopping") {
    return ["Stopping", ...since(view.since), view.stage ? "; its " + view.stage + " runs to its end first." : ""];
  }
  if (view.state === "running") {
    if (!view.role) return [headline(view).text, ...since(view.since)];
    const who = el("span", "The " + view.role, "who " + view.role);
    return [who, " is " + doing(view.stage), ...since(view.since)];
  }
  const said = [outcome(view)];
  if (view.closed) said.push(" ", clock(view.closed, "ago"));
  const refusal = status.state && status.state.refusal;
  if (view.status === "REFUSED" && refusal) said.push(": " + refusal);
  return said;
}

// A run held up by a host whose worker is down says so, with that worker's Start when its owner reads it
// down and startable — never for a part whose state cannot be read.
function renderBlocked(view) {
  const box = $("run-blocked");
  const reading = stackReading();
  const parts = reading ? reading.components : [];
  const startable = view.blocked_by.filter((host) =>
    parts.some((part) => part.name === host && part.managed && part.startable && part.state === "down"));
  box.hidden = !view.blocked_by.length;
  if (unchanged(box, [view.blocked_by, startable])) return;
  $("run-blocked-said").textContent = view.blocked_by.length
    ? "Blocked: " + blockedBy(view).join(", ") + ", so this run cannot move." : "";
  $("run-blocked-actions").replaceChildren(...startable.map((host) =>
    stackButton("start", host, "Start the " + PARTS[host], $("run-blocked-result"))));
}

// The run's own controls, after its decision: while it is open and not stopping, Stop run then Force
// terminate; while it is stopping, Force terminate alone; once closed, neither.
function renderControls(view) {
  const stopping = view.state === "stopping";
  $("run-controls").hidden = view.state === "closed";
  $("run-stop").hidden = stopping;
  $("run-controls-hint").textContent = stopping
    ? "The Stop waits for what the run's host is already doing; Force terminate closes the run at once." : "";
}

async function lifecycle(kind, button) {
  const control = LIFECYCLE[kind];
  // The run asked about is the run the answer goes to, whatever the page opens meanwhile.
  const runId = selected;
  if (!(await confirmAction({ ...control, returnTo: button })) || runId !== selected) return;
  report($("run-control-result"), "sending…");
  try {
    await api("/api/runs/" + encodeURIComponent(runId) + "/" + kind, control.sent || {});
    report($("run-control-result"), control.said);
  } catch (error) {
    report($("run-control-result"), "not accepted: " + error.message, true);
    return;
  }
  wrote();
}
$("run-stop").onclick = () => lifecycle("stop", $("run-stop"));
$("run-terminate").onclick = () => lifecycle("terminate", $("run-terminate"));

// What a closed run kept — its worktree and branch, unmerged — until the operator removes them.
function renderKept(runId, view) {
  $("run-kept").hidden = !view.kept;
  if (!view.kept || unchanged($("run-kept"), [runId, view.worktree, view.repo])) return;
  $("run-kept-text").replaceChildren("It keeps its worktree ", code(view.worktree), " and its branch ", code(runId),
    ". Read its change, then remove them once you are done with them.");
  $("run-kept-show").href = "#worktrees=" + encodeURIComponent(view.repo);
  $("run-remove").onclick = () => removeKept(runId, $("run-kept-result"), refreshRun, $("run-remove"));
}

// ---- the decision ---------------------------------------------------------------------------

// What the decision shows the operator to judge by: the brief, the review, the failure, the verification.
function evidenceOf(stop, timeline) {
  if (stop.reason === "final") {
    const verified = [...timeline].reverse().find((entry) => entry.stage === "verify");
    return [verified && { label: "The architect's verification", verdict: verified.verdict, text: verified.feedback },
      { label: "The merge was refused", text: stop.feedback, code: true }].filter((part) => part && part.text);
  }
  const label = stop.reason === "approval"
    ? { research: "The architect's brief", plan: "The architect's assessment",
      build: "The architect's verification" }[stop.phase] || "The review"
    : { blocker: "The blocker", exhausted: "The last finding", failed: "What failed" }[stop.reason] || "Its words";
  return stop.feedback ? [{ label: label, text: stop.feedback, code: stop.reason === "failed" }] : [];
}

function evidencePart(part) {
  const box = el("div", null, "evidence-part");
  const label = el("div", null, "evidence-label");
  label.appendChild(el("span", part.label));
  if (part.verdict) label.appendChild(el("span", part.verdict, "verdict " + part.verdict));
  if (part.code) label.appendChild(copyButton(part.text, part.label.toLowerCase()));
  box.append(label, el(part.code ? "pre" : "div", part.text, part.code ? "code" : "prose"));
  return box;
}

function renderStop(stop, timeline) {
  const card = $("stop");
  // A stop the run has left takes its draft with it.
  for (const key of [...drafts.keys()]) {
    if (key.startsWith(selected + ":") && (!stop || key !== stop.id)) drafts.delete(key);
  }
  if (!stop) {
    card.hidden = true;
    shownStop = null;
    shownAbove = new Set();
    return;
  }
  card.hidden = false;
  // The same stop keeps what the operator has typed and what the page last said of it.
  if (shownStop === stop.id) return;
  shownStop = stop.id;
  card.classList.toggle("failed", stop.reason === "failed");
  $("stop-title").textContent = decisionTitle(stop.reason, stop.phase);
  $("stop-hint").textContent = stop.hint || "";
  const evidence = evidenceOf(stop, timeline);
  shownAbove = new Set(evidence.map((part) => part.text));
  $("stop-evidence").replaceChildren(...evidence.map(evidencePart));
  const actions = stop.actions || [];
  const worded = [...new Set(actions.filter((action) => WORDED[action]).map((action) => WORDED[action]))];
  $("stop-note-field").hidden = actions.every((action) => WORDLESS.has(action));
  $("stop-note-label").textContent = worded.length
    ? (worded.includes("Guide") ? "Your guidance, sent with Guide" : "Your note, sent with Revise") : "Your note";
  $("stop-note").placeholder = worded.includes("Guide") ? "How should the run go on…"
    : worded.length ? "What should change, and why…" : "";
  $("stop-note").value = drafts.get(stop.id) || "";
  for (const id of ["stop-note-alert", "stop-alert", "stop-result"]) $(id).textContent = "";
  $("stop-actions").replaceChildren(...actions.map((action) => {
    const button = el("button", LABELS[action] || action,
      PRIMARY.has(action) ? "primary" : DANGER.has(action) ? "danger" : "");
    button.type = "button";
    button.onclick = () => answer(stop, action, button);
    return button;
  }));
}

// The action as the stop published it, and the note: what an answer needs is the workflow's to refuse.
async function answer(stop, action, button) {
  const runId = selected;
  const text = $("stop-note").value.trim();
  const body = { stop: stop.id, action: action };
  // Only words you wrote: an empty note must reach the workflow empty, for it to refuse.
  if (text) body.text = text;
  if (ASK[action]) {
    if (!(await confirmAction({ ...ASK[action], returnTo: button })) || runId !== selected) return;
    body.confirm = true;
  }
  for (const id of ["stop-note-alert", "stop-alert"]) $(id).textContent = "";
  for (const each of $("stop-actions").children) each.disabled = true;
  $("stop-result").textContent = "sending…";
  try {
    await api("/api/runs/" + encodeURIComponent(runId) + "/answer", body);
    drafts.delete(stop.id);
    $("stop-result").textContent = "answered: " + action;
  } catch (error) {
    $("stop-result").textContent = "";
    // A refusal is said beside what it concerns: at the note for an answer the note is sent with.
    if (WORDED[action]) {
      $("stop-note-alert").textContent = "not accepted: " + error.message;
      $("stop-note").focus();
    } else {
      $("stop-alert").textContent = "not accepted: " + error.message;
    }
    for (const each of $("stop-actions").children) each.disabled = false;
    return;
  }
  wrote();
}

// ---- the change and the history ---------------------------------------------------------------

// The change sits under the decision when the decision judges it — at a plan's or a build's approval and
// at the final gate, read at once — after the history once a plan exists, and nowhere before.
function renderChange(view, stop, timeline) {
  const judged = stop && ((stop.reason === "approval" && ["plan", "build"].includes(stop.phase)) || stop.reason === "final");
  const exists = view.worktree && (view.state === "closed" ? view.kept
    : judged || timeline.some((entry) => entry.stage === "plan"));
  placeChange(!exists ? "none" : judged ? "evidence" : "later");
  if (judged) readOnceFor(stop);
}

function renderHistory(view, timeline) {
  const root = $("timeline");
  if (unchanged(root, [timeline, [...shownAbove]])) return;
  const steps = view.flow ? view.flow.steps : [];
  const roleOf = (stage) => (steps.find((step) => step.endsWith(":" + stage)) || "").split(":")[0];
  root.replaceChildren();
  // A run's phases are its flow's work stages, in the order it took them.
  for (const phase of [...new Set(timeline.map((entry) => entry.phase))]) {
    const box = el("section", null, "phase");
    box.appendChild(el("h3", phase.charAt(0).toUpperCase() + phase.slice(1)));
    let episode = null;
    for (const entry of timeline.filter((each) => each.phase === phase)) {
      // A new episode of a phase starts with the operator's answer — a revise, or guidance.
      box.appendChild(historyEntry(entry, roleOf(entry.stage), episode !== null && entry.episode !== episode));
      episode = entry.episode;
    }
    root.appendChild(box);
  }
  if (!root.children.length) root.appendChild(el("p", "No step has finished yet.", "hint"));
}

// One round: who did what, its verdict, where it stopped for you, and its words — kept whole, and closed
// when the decision above already shows them.
function historyEntry(entry, role, answered) {
  const row = el("div", null, "entry");
  const head = el("div", null, "entry-head");
  const what = el("span");
  if (role) what.append(el("span", role, "role " + role), " ");
  what.append(entry.stage);
  head.append(what, el("span", "round " + entry.round + (answered ? ", after your answer" : ""), "hint"));
  if (entry.verdict) head.appendChild(el("span", entry.verdict, "verdict " + entry.verdict));
  if (entry.gate) head.appendChild(el("span", "stopped for " + (GATES[entry.gate] || entry.gate), "hint"));
  const time = el("time", at(entry.at));
  time.dateTime = entry.at || "";
  head.appendChild(time);
  row.appendChild(head);
  const text = entry.brief || entry.feedback;
  if (text) {
    const more = el("details");
    more.open = !shownAbove.has(text);
    more.append(el("summary", shownAbove.has(text) ? "Shown above, in the decision"
      : entry.brief ? "The brief" : "The review"), el("div", text, "prose"));
    row.appendChild(more);
  }
  return row;
}
