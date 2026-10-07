// One run, in the order it needs the operator: what it is and does now, the decision it waits for with its
// evidence, its own controls, what it kept, its terminals, its history and its change. The terminals and
// the change reader are their own owners; this module asks them, and never redraws their nodes.

import { api } from "./api.js";
import { $, PARTS, at, blockedBy, clock, code, confirmAction, copyButton, decisionTitle, doing, el, headline,
  lasted, outcome, report, score, unchanged, wrote } from "./ui.js";
import { stackButton, stackReading } from "./stack.js";
import { showTerminals, updateTerminals } from "./terminals.js";
import { placeChange, readOnceFor, showChangeFor } from "./change.js";
import { chevron, fileList } from "./diff.js";
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
const STAGE_ROLES = { research: "architect", plan: "engineer", assess: "architect", build: "engineer",
  verify: "architect", closeout: "engineer" };

let selected = null;
let shownStop = null;
// Where the shown run's merge lands when its base is a remote's — `origin/main` — which its confirmation says.
let landsOn = null;
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
  record = { key: null, turns: [], answers: [], said: "" };
  drawn = { view: null, timeline: [] };
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
  landsOn = state && state.remote ? state.remote + "/" + state.base_branch : null;
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
  renderHistory(view, status.timeline, status.stop);
  if (!unchanged($("lines"), status.lines)) $("lines").textContent = status.lines.join("\n");
  showTerminals(runId, state.target);
  // A failed step's terminal is where its failure shows.
  const failedRole = view.state === "failed" && state.current ? state.current.role : null;
  updateTerminals({ open: view.state !== "closed", shown: view.role || failedRole || null, working: view.role || null,
    since: view.since || null });
}

// ---- what the run is --------------------------------------------------------------------------

function renderFacts(runId, view, state, links, timeline) {
  const planned = Boolean(state.plan) && timeline.some((entry) => entry.stage === "plan");
  const facts = [
    ["Repository", view.repo && code(view.repo)],
    ["Flow", view.flow && (view.flow.name ? code(view.flow.name) : "the order from before flows")],
    ["Host", view.host && code(view.host)],
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
    if (term === "Repository") pair.className = "repo-fact";
    if (term === "Flow") pair.className = "flow-fact";
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
  if (unchanged(line, [status.unreadable, view.state, view.agent_prompt, view.stage, view.role, view.since, view.closed, view.status,
    view.execution, status.state && status.state.refusal])) return;
  line.replaceChildren(...nowSaid(view, status));
}

function since(iso) {
  return iso ? [" for ", clock(iso), " (since " + at(iso) + ")"] : [];
}

function nowSaid(view, status) {
  if (status.unreadable) return ["Its status cannot be read now: " + status.unreadable.replace(/^its status cannot be read now: /, "")];
  if (view.agent_prompt) return ["The " + view.role + " is waiting for input in its live terminal. Open the terminal below to answer or interrupt."];
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

// The run's own controls, after its decision. While it waits for you nothing runs on its host, so a Stop ends it:
// Stop run alone, quiet, its consequence beside it. While it works, Stop run then Force terminate — a run whose
// status cannot be read shows as working, so a Stop its worker never reads can still be forced; while it is
// stopping, Force terminate alone; once closed, neither.
function renderControls(view) {
  const stopping = view.state === "stopping";
  const atStop = view.state === "waiting" || view.state === "failed";
  $("run-controls").hidden = view.state === "closed";
  $("run-stop").hidden = stopping;
  $("run-stop").classList.toggle("quiet", atStop);
  $("run-terminate").hidden = atStop;
  $("run-controls-hint").textContent = stopping
    ? "The Stop waits for what the run's host is already doing; Force terminate closes the run at once."
    : atStop ? "Ends the run here without merging; its worktree and branch stay." : "";
}

async function lifecycle(kind, button) {
  const control = LIFECYCLE[kind];
  // The run asked about is the run the answer goes to, whatever the page opens meanwhile, and the only run
  // its result is said on.
  const runId = selected;
  if (!(await confirmAction({ ...control, returnTo: button })) || runId !== selected) return;
  report($("run-control-result"), "sending…");
  try {
    await api("/api/runs/" + encodeURIComponent(runId) + "/" + kind, control.sent || {});
  } catch (error) {
    if (runId === selected) report($("run-control-result"), "not accepted: " + error.message, true);
    return;
  }
  if (runId === selected) report($("run-control-result"), control.said);
  wrote();
}
$("run-stop").onclick = () => lifecycle("stop", $("run-stop"));
$("run-terminate").onclick = () => lifecycle("terminate", $("run-terminate"));

// What a closed run kept — its worktree and branch, unmerged — until the operator removes them.
function renderKept(runId, view) {
  $("run-kept").hidden = !view.kept;
  if (!view.kept || unchanged($("run-kept"), [runId, view.worktree, view.worktrees_of])) return;
  $("run-kept-text").replaceChildren("It keeps its worktree ", code(view.worktree), " and its branch ", code(runId),
    ". Read its change, then remove them once you are done with them.");
  // Its repository as the Worktrees view takes it: its repos.json name, or its path.
  $("run-kept-show").href = "#worktrees=" + encodeURIComponent(view.worktrees_of);
  $("run-remove").onclick = () => removeKept(runId, $("run-kept-result"), refreshRun, $("run-remove"),
    () => runId === selected);
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
    // A merge that leaves the machine says where it goes before it is asked for.
    const asked = action === "merge" && landsOn
      ? { ...ASK.merge, title: "Merge the verified change into " + landsOn + "?",
        body: "It is pushed to the remote, forcing nothing: a remote that has moved takes nothing." }
      : ASK[action];
    if (!(await confirmAction({ ...asked, returnTo: button })) || runId !== selected) return;
    body.confirm = true;
  }
  for (const id of ["stop-note-alert", "stop-alert"]) $(id).textContent = "";
  for (const each of $("stop-actions").children) each.disabled = true;
  $("stop-result").textContent = "sending…";
  // What came of it is said only where it was asked — this run, at this stop — never on whatever the page
  // shows when the answer comes back.
  const here = () => runId === selected && shownStop === stop.id;
  try {
    await api("/api/runs/" + encodeURIComponent(runId) + "/answer", body);
  } catch (error) {
    if (!here()) return;
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
  drafts.delete(stop.id);
  if (here()) $("stop-result").textContent = "answered: " + action;
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

// What the run's Temporal history adds to its timeline — when each turn started, the tree each review judged, and
// your answers — read again whenever the timeline or the stop moves on.
let record = { key: null, turns: [], answers: [], said: "" };
let drawn = { view: null, timeline: [] };

function renderHistory(view, timeline, stop) {
  drawn = { view: view, timeline: timeline };
  const key = JSON.stringify([selected, timeline.length, stop && stop.id, view.state]);
  if (record.key !== key) {
    record.key = key;
    readRecord(selected, key);
  }
  drawHistory();
}

async function readRecord(runId, key) {
  try {
    const read = await api("/api/runs/" + encodeURIComponent(runId) + "/history");
    if (runId !== selected || record.key !== key) return;
    record = { key: key, turns: read.turns, answers: read.answers, said: "" };
  } catch (error) {
    if (runId !== selected || record.key !== key) return;
    // Read again at the page's next read of the run.
    record = { key: null, turns: record.turns, answers: record.answers,
      said: "Your answers and each round's change cannot be read now: " + error.message
        + ". The page tries again as it reads the run." };
  }
  drawHistory();
}

// One transcript in the run's order, by phase: each turn a row — who, which stage and round, its verdict, how long
// it took, when — opening to what it received and what it produced; your answers rows of their own between.
function drawHistory() {
  const { view, timeline } = drawn;
  const root = $("timeline");
  if (!view || unchanged(root, [timeline, record.turns, record.answers, record.said, [...shownAbove]])) return;
  const openDetails = new Set([...root.querySelectorAll("details[open][data-history-detail]")]
    .map((detail) => detail.dataset.historyDetail));
  // A completed turn's record does not change: one already read keeps what it shows, and what was opened in it.
  const bodies = new Map([...root.querySelectorAll("details.turn > .turn-body[data-loaded='yes']")]
    .map((body) => [body.parentElement.dataset.historyDetail, body]));
  const steps = view.flow ? view.flow.steps : [];
  const roleOf = (stage) => (steps.find((step) => step.endsWith(":" + stage)) || "").split(":")[0]
    || STAGE_ROLES[stage];
  const turns = new Map(record.turns.map((turn) => [turnKey(turn), turn]));
  // Your answers follow the turn the run's history says each came after, in the history's own order; one after a
  // turn the timeline does not show yet comes last.
  const following = new Map();
  for (const answer of record.answers) {
    following.set(answer.after || "", [...(following.get(answer.after || "") || []), answer]);
  }
  const answersAfter = (key) => {
    const found = following.get(key) || [];
    following.delete(key);
    return found.map((answer) => ({ answer: answer }));
  };
  const items = answersAfter("");
  for (const entry of timeline) items.push({ entry: entry }, ...answersAfter(historyKey(entry)));
  for (const key of [...following.keys()]) items.push(...answersAfter(key));

  const shown = [];
  if (record.said) shown.push(el("p", record.said, "hint"));
  let box = null;
  let phase = null;
  for (const item of items) {
    // An answer is in the phase of the step it answered, which may be one no completed turn shows — a failed one —
    // or none: an answer before any role's step is under its own heading.
    const itsPhase = item.entry ? item.entry.phase : item.answer.phase || null;
    if (!box || itsPhase !== phase) {
      phase = itsPhase;
      box = el("section", null, "phase");
      box.appendChild(el("h3", phase ? phase.charAt(0).toUpperCase() + phase.slice(1) : "Before any turn"));
      shown.push(box);
    }
    box.appendChild(item.entry
      ? turnRow(item.entry, roleOf(item.entry.stage), turns.get(turnKey(item.entry)), openDetails, bodies)
      : answerRow(item.answer, phase));
  }
  if (!items.length) shown.push(el("p", "No step has finished yet.", "hint"));
  root.replaceChildren(...shown);
}

function turnKey(turn) {
  return "turn:" + historyKey(turn);
}

// A turn as the run's history names it.
function historyKey(turn) {
  return turn.stage + ":" + turn.episode + ":" + turn.round;
}

// A turn the run's history names, said as its row says it: "build, round 2, at 16:31" — its time tells it from the
// same stage and round of another episode.
function turnSaid(key) {
  const [stage, , round] = key.split(":");
  const turn = record.turns.find((each) => historyKey(each) === key);
  return stage + ", round " + round + (turn && turn.ended ? ", at " + at(turn.ended) : "");
}

function firstLine(text) {
  return text.trim().split("\n")[0];
}

function turnRow(entry, role, turn, openDetails, bodies) {
  const key = turnKey(entry);
  const row = el("details", null, "turn");
  row.dataset.historyDetail = key;
  if (role) row.dataset.role = role;
  const head = el("span", null, "turn-head");
  head.appendChild(chevron());
  if (role) head.append(el("span", role, "role " + role));
  head.append(el("span", entry.stage + ", round " + entry.round, "turn-what"));
  if (entry.verdict) head.appendChild(el("span", entry.verdict, "verdict " + entry.verdict));
  if (entry.gate) head.appendChild(el("span", "stopped for " + (GATES[entry.gate] || entry.gate), "hint"));
  if (turn) head.appendChild(el("span", lasted(turn.started, turn.ended), "hint took"));
  const time = el("time", at(entry.at));
  time.dateTime = entry.at || "";
  head.appendChild(time);
  const summary = el("summary", null);
  summary.appendChild(head);
  const said = entry.brief || entry.feedback;
  if (said) summary.appendChild(el("span", shownAbove.has(said) ? "Shown above, in the decision" : firstLine(said),
    "turn-preview"));
  const body = bodies.get(key) || el("div", null, "turn-body");
  if (bodies.has(key)) refreshProduced(body, entry);
  row.append(summary, body);
  row.addEventListener("toggle", () => {
    if (row.open && !body.dataset.loaded) loadTurn(body, entry, role, selected);
  });
  row.open = openDetails.has(key);
  return row;
}

// How an answer reads in the transcript, by its action and the phase it was given in.
const APPROVED = { research: "approved the research brief", plan: "approved the plan", build: "approved the build" };

function answerSaid(answer, phase) {
  switch (answer.action) {
    case "approve": return APPROVED[phase] || "approved";
    case "revise": return answer.role ? "sent it back to the " + answer.role : "asked for a revision";
    case "guide": return "guided the run";
    case "continue": return "continued after the failure";
    case "merge": return "merged";
    case "discard": return "discarded the run's work";
    default: return answer.action;
  }
}

function answerRow(answer, phase) {
  const row = el("div", null, "answer");
  const head = el("div", null, "turn-head");
  head.append(el("span", "you", "role you"), el("span", answerSaid(answer, phase), "turn-what"));
  const time = el("time", at(answer.at));
  time.dateTime = answer.at || "";
  head.appendChild(time);
  row.appendChild(head);
  if (answer.text) row.appendChild(el("div", answer.text, "answer-words"));
  return row;
}

async function loadTurn(body, entry, role, runId) {
  body.dataset.loaded = "loading";
  body.replaceChildren(el("p", "Reading the turn…", "hint"));
  let read;
  try {
    read = await api("/api/runs/" + encodeURIComponent(runId) + "/turn?"
      + new URLSearchParams({ stage: entry.stage, episode: entry.episode, round: entry.round }));
  } catch (error) {
    if (body.isConnected && runId === selected) {
      delete body.dataset.loaded;
      readAgain(body, "The turn cannot be read: " + error.message, () => loadTurn(body, entry, role, runId));
    }
    return;
  }
  if (!body.isConnected || runId !== selected) return;
  const attempts = read.attempts;
  body.attempts = attempts;
  body.dataset.above = JSON.stringify([...shownAbove]);
  const shown = attempts.map((attempt, index) => {
    const box = el("section", null, "attempt");
    if (attempts.length > 1) box.appendChild(el("h4", index ? "Retried with a new session" : "First attempt"));
    box.append(received(attempt, role), produced(attempt, index === attempts.length - 1 ? entry : null, index));
    return box;
  });
  if (!attempts.length) {
    shown.push(el("p", "This turn's local record is unavailable: what it received is not known here.", "hint"));
    shown.push(produced({ input: null, output: null }, entry, 0));
  }
  if (role === "engineer") shown.push(roundChange(entry, runId));
  body.replaceChildren(...shown);
  body.dataset.loaded = "yes";
}

// A prompt's parts by plain names; the task and the persona are the run's own, as it started.
const PART_NAMES = { skill: "The stage's skill", task: "The task", persona: "The role's persona",
  instructions: "The stage's instructions", recheck: "Re-check your findings", brief: "The research brief to check",
  "previous-brief": "Its previous brief", guidance: "Your guidance", reflection: "A convergence reflection",
  "reflection-guidance": "Your reflection guidance", handoff: "The final-budget handoff",
  "handoff-guidance": "Your final-turn guidance" };

function partName(part, role) {
  if (part === "findings") return role === "architect" ? "Its findings to re-check" : "The findings to address";
  return PART_NAMES[part] || part;
}

// What the turn was given: its own new prompt — the vendor holds what came before — in the parts it was built
// from, a short one said in place; and the exact prompt, to copy.
function received(attempt, role) {
  const box = el("div", null, "received");
  box.appendChild(el("h4", "Received"));
  if (attempt.input === null) {
    box.appendChild(el("p", "No local record of its prompt.", "hint"));
    return box;
  }
  if (attempt.parts) {
    const list = el("ul", null, "prompt-parts");
    for (const part of attempt.parts) {
      const text = part.text.trim();
      const name = partName(part.part, role);
      const started = part.part === "task" || part.part === "persona" ? " — as the run started" : "";
      const item = el("li");
      if (!text.includes("\n") && text.length <= 100) {
        item.append(el("span", name + started + ": ", "part-name"), code(text));
      } else {
        const one = el("details", null, "prompt-part");
        const label = el("summary", name);
        if (started) label.appendChild(el("span", started, "hint"));
        one.append(label, el("div", text, "turn-prose"));
        item.appendChild(one);
      }
      list.appendChild(item);
    }
    box.appendChild(list);
  }
  const exact = el("details", null, "turn-prompt");
  exact.append(el("summary", attempt.parts ? "The exact prompt" : "Its prompt, as sent"),
    field(attempt.input, "the prompt sent to the agent"));
  box.appendChild(exact);
  return box;
}

// What a turn read before produced, said again for the decision now above: what it shows is pointed to, and
// what it no longer shows is said here again. The rest of the turn — and what was opened in it — stays.
function refreshProduced(body, entry) {
  const above = JSON.stringify([...shownAbove]);
  if (body.dataset.loaded !== "yes" || body.dataset.above === above) return;
  body.dataset.above = above;
  const attempts = body.attempts || [];
  for (const shown of body.querySelectorAll(":scope > .attempt > .produced, :scope > .produced")) {
    const index = Number(shown.dataset.attempt);
    const counted = !attempts.length || index === attempts.length - 1;
    const opened = { output: Boolean(shown.querySelector(":scope > details.turn-output[open]")),
      raw: Boolean(shown.querySelector(":scope > details.turn-raw[open]")) };
    shown.replaceWith(produced(attempts[index] || { input: null, output: null }, counted ? entry : null, index,
      opened));
  }
}

// What the turn gave back: the run's own record of it — the brief, the verdict and findings — for the attempt that
// counted, else what its record holds; said once, so the decision's evidence is pointed to, not repeated. Closed, as
// its prompt is, its verdict and first line in its summary; `opened` keeps it and its raw record open when it is drawn
// again.
function produced(attempt, entry, index, opened) {
  const box = el("div", null, "produced");
  box.dataset.attempt = index;
  box.appendChild(el("h4", "Produced"));
  const message = attempt.message ?? attempt.output;
  const review = entry && entry.verdict ? { verdict: entry.verdict, feedback: entry.feedback || "" }
    : reviewOutput(message);
  const text = review ? review.feedback : (entry && entry.brief) || message;
  if (text && shownAbove.has(text)) {
    box.appendChild(el("p", "Shown above, in the decision.", "hint"));
  } else if (text === null || text === undefined) {
    box.appendChild(el("p", "No local record of its answer.", "hint"));
  } else if (!text && !review) {
    box.appendChild(el("p", "The record holds no final message.", "hint"));
  } else {
    const output = el("details", null, "turn-output");
    const summary = el("summary");
    if (review) summary.append(el("span", review.verdict, "verdict " + review.verdict), " ");
    summary.appendChild(el("span", text ? firstLine(text) : "no findings", "first-line"));
    output.append(summary, field(review ? review.verdict + "\n\n" + text : text, "what it produced", text));
    output.open = Boolean(opened && opened.output);
    box.appendChild(output);
  }
  if (attempt.output !== null && attempt.output !== undefined && attempt.output !== message) {
    const raw = el("details", null, "turn-raw");
    raw.open = Boolean(opened && opened.raw);
    const record = el("pre", attempt.output, "code");
    record.translate = false;
    const inside = el("div", null, "turn-field");
    inside.append(copyButton(attempt.output, "the raw output record"), record);
    raw.append(el("summary", "Raw output record"), inside);
    box.appendChild(raw);
  }
  return box;
}

// Text kept whole, with its copy: `shown` when what is shown differs from what is copied.
function field(text, what, shown) {
  const box = el("div", null, "turn-field");
  box.append(copyButton(text, what), el("div", shown ?? text, "turn-prose"));
  return box;
}

function reviewOutput(message) {
  if (!message) return null;
  try {
    const parsed = JSON.parse(message);
    return parsed && ["PASS", "PATCH", "BLOCKER", "UNVERIFIED"].includes(parsed.verdict)
      && typeof parsed.feedback === "string" ? parsed : null;
  } catch (error) {
    return null;
  }
}

// An engineer turn's change as the run's history pairs it with the reviews around it (`client.history`). The worktree
// is live, so it is the change that review judged, not proof of who wrote each line.
function roundChange(entry, runId) {
  const box = el("details", null, "round-change");
  box.dataset.historyDetail = "change:" + turnKey(entry);
  const summary = el("summary", "Change since the previous review");
  const body = el("div", null, "round-change-body");
  box.append(summary, body);
  box.addEventListener("toggle", () => {
    if (box.open && !box.dataset.loaded) loadRoundChange(entry, runId, box, summary, body);
  });
  return box;
}

async function loadRoundChange(entry, runId, box, summary, body) {
  const turn = [...record.turns].reverse().find((each) => historyKey(each) === historyKey(entry));
  const change = turn && turn.change;
  const said = (text) => body.replaceChildren(el("p", text, "hint"));
  if (!change) {
    said(record.said || "The run's history is still being read; close this and open it again in a moment.");
  } else if (change.pending) {
    said("No review has judged this turn's change yet; Change reads the worktree as it is now.");
  } else if (change.unrecorded) {
    said("The review after this turn recorded no tree, so its change cannot be read back.");
  } else if (change.with) {
    said("Shown with " + turnSaid(change.with) + ": a review between them recorded no tree, so the two turns' "
      + "change cannot be told apart and is shown once, there.");
  } else {
    box.dataset.loaded = "loading";
    said("Reading the change…");
    const query = { tree: change.tree };
    if (change.base) query.base = change.base;
    try {
      const read = await api("/api/runs/" + encodeURIComponent(runId) + "/diff?" + new URLSearchParams(query));
      if (!box.isConnected || runId !== selected) return;
      summary.replaceChildren("Change since the previous review",
        el("span", read.files_total === 1 ? "1 file" : read.files_total + " files", "hint"));
      const together = change.turns.length > 1 ? [el("p", "The change of " + change.turns.map(turnSaid).join(" and ")
        + " together: a review between them recorded no tree, so they cannot be told apart.", "hint")] : [];
      body.replaceChildren(...together, read.files_total ? fileList(runId, read, read.files, read.files_total)
        : el("p", "No file changed between the two reviews.", "hint"));
      box.dataset.loaded = "yes";
    } catch (error) {
      if (!box.isConnected || runId !== selected) return;
      delete box.dataset.loaded;
      readAgain(body, "The change cannot be read: " + error.message,
        () => loadRoundChange(entry, runId, box, summary, body));
    }
  }
}

function readAgain(body, message, again) {
  const line = el("p", message, "alert");
  line.setAttribute("role", "alert");
  const retry = el("button", "Read again");
  retry.type = "button";
  retry.onclick = again;
  body.replaceChildren(line, retry);
}
