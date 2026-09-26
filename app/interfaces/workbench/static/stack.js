// The stack: its reading as chips in the top bar, its start, stop and restart in a popover under them, and
// a banner for each part that holds runs up — all as the stack's one owner reads and does them.

import { api } from "./api.js";
import { $, PARTS, confirmAction, el, report, unchanged, wrote } from "./ui.js";

const VERBS = { start: "Start", stop: "Stop", restart: "Restart" };
// What stopping a part interrupts, said before the operator confirms it; a restart stops it first.
const INTERRUPTS = {
  temporal: "Stopping Temporal pauses every run until it starts again. An agent at work goes on, but if " +
    "Temporal stays down longer than a role's heartbeat interval, its stage fails and waits for you to continue it.",
  wsl: "Stopping the WSL worker ends any agent at work on it — its stage then waits for you to continue it — " +
    "and pauses every run until it starts again. A merge or discard it is running may be cut off; its run " +
    "then waits at that step until the step fails or times out, and Force terminate ends it sooner.",
  windows: "Stopping the Windows worker ends any agent at work on it — its stage then waits for you to " +
    "continue it — and pauses the Windows runs until it starts again. A merge or discard it is running is " +
    "cut off; its run then waits at that step until the step times out, and Force terminate ends it sooner.",
  stack: "Stopping the stack stops both workers, then Temporal: every agent at work ends — its stage then " +
    "waits for you to continue it — a merge or discard running may be cut off, and every run pauses until " +
    "it starts again.",
};
// The stack's last reading, and how many open runs each host's down worker holds up.
let reading = null;
let holding = {};

export const stackReading = () => reading;

export async function refreshStack() {
  try {
    reading = await api("/api/health");
  } catch (error) {
    return;
  }
  render(reading);
}

// The runs as the rail last read them: how many each down worker holds up, said in its banner.
export function noteRuns(runs) {
  const counted = {};
  for (const run of runs) {
    for (const host of run.blocked_by || []) counted[host] = (counted[host] || 0) + 1;
  }
  holding = counted;
  if (reading) renderBanners(reading);
}

function named(part) {
  return part === "temporal" ? "Temporal" : part ? "the " + PARTS[part] : "the stack";
}

function render(health) {
  renderChips(health);
  renderPanel(health);
  renderBanners(health);
}

// Each part's state at a glance: a dot, and its state in words whenever it is not up.
function renderChips(health) {
  const chips = $("stack-chips");
  if (unchanged(chips, health.components.map((part) => [part.name, part.state]))) return;
  chips.replaceChildren(...health.components.map((part) => {
    const chip = el("span", null, "chip");
    chip.dataset.state = part.state;
    const dot = el("span", null, "dot");
    dot.setAttribute("aria-hidden", "true");
    chip.append(dot, PARTS[part.name] || part.name,
      el("span", " " + part.state, part.state === "up" ? "state visually-hidden" : "state"));
    return chip;
  }));
}

// What a part offers, as its owner reads it: a part down, its Start; any other, its Restart and Stop —
// Start and Restart only where the owner says this side can start it.
function partActions(part) {
  const actions = part.state === "down" ? ["start"] : ["restart", "stop"];
  return actions.filter((action) => part.startable || action === "stop");
}

// The whole stack's Start and Restart act on every managed part — its owner starts each, whatever the page
// read of it — so each is offered only while every part is in a state safe for it. Stopping is safe in any.
function wholeActions(health) {
  const managed = health.components.filter((part) => part.managed);
  if (managed.length < 2) return [];
  const safe = (part) => ["up", "running"].includes(part.state) || (part.state === "down" && part.startable);
  const actions = [];
  if (managed.some((part) => part.state === "down" && part.startable) && managed.every(safe)) actions.push("start");
  if (!managed.some((part) => part.state === "unknown")) actions.push("restart");
  actions.push("stop");
  return actions;
}

function renderPanel(health) {
  const parts = $("stack-parts");
  if (!unchanged(parts, health.components)) {
    parts.replaceChildren(...health.components.map((part) => {
      const row = el("div", null, "part");
      row.append(el("span", PARTS[part.name] || part.name, "name"), el("span", part.state, "state " + part.state));
      const actions = el("div", null, "actions");
      if (part.managed) for (const action of partActions(part)) actions.appendChild(stackButton(action, part.name));
      row.appendChild(actions);
      const detail = [part.pid && "pid " + part.pid, (part.detail || "").replace(/^\s*—\s*/, ""),
        !part.managed && "not this stack's to start or stop",
        part.managed && !part.startable && (part.state === "unknown" ? "its state cannot be read" : "cannot be started from here")]
        .filter(Boolean).join("; ");
      if (detail) row.appendChild(el("p", detail, "detail"));
      return row;
    }));
  }
  const all = $("stack-all");
  const whole = wholeActions(health);
  if (unchanged(all, whole)) return;
  all.replaceChildren();
  if (whole.length) all.append(el("span", "The whole stack", "label"), ...whole.map((action) => stackButton(action, null)));
}

// A banner for each part that holds runs up: what is wrong, what it holds up, and — only for a part its
// owner reads down and startable — the one-click Start. A part whose state cannot be read gets its reason
// and no Start: it is not proven down.
function renderBanners(health) {
  const box = $("banners");
  const wrong = health.components.filter((part) => part.state === "down" || part.state === "unknown");
  if (unchanged(box, [wrong, holding, health.error])) return;
  for (const old of box.querySelectorAll(".banner.stack")) old.remove();
  for (const part of wrong) box.appendChild(banner(part, health));
}

function banner(part, health) {
  const row = el("div", null, "banner stack " + (part.state === "down" ? "bad" : "warn"));
  const held = holding[part.name] || 0;
  let said;
  if (part.name === "temporal") {
    said = "Temporal is down: every run pauses until it starts again.";
  } else if (part.state === "unknown") {
    said = "The " + PARTS[part.name] + "'s state cannot be read, so it is not known to be up or down.";
  } else {
    said = "The " + PARTS[part.name] + " is down" + (held ? ": " + held + (held === 1 ? " run cannot" : " runs cannot") +
      " move until it starts." : ".");
  }
  row.appendChild(el("span", said));
  const why = !part.managed ? "This stack does not manage it."
    : part.name === "temporal" ? health.error : part.state === "unknown" ? part.detail
      : !part.startable ? "It cannot be started from here: " + (part.detail || "") : "";
  if (why) row.appendChild(el("span", why, "why"));
  if (part.managed && part.startable && part.state === "down") {
    row.appendChild(stackButton("start", part.name, "Start " + named(part.name)));
  }
  return row;
}

// A button for a start, stop or restart of `part`, or of the whole stack when it is null.
export function stackButton(action, part, label, line) {
  const button = el("button", label || VERBS[action] + " " + (part ? PARTS[part] : "stack"),
    action === "stop" ? "danger" : "");
  button.type = "button";
  button.onclick = () => stackAction(action, part, line || $("stack-result"), button);
  return button;
}

// A start, stop or restart of the stack or one part, as its one owner does it; what each part came to.
async function stackAction(action, part, line, button) {
  const which = part ? PARTS[part] : "the stack";
  if (action !== "start") {
    // A confirmation closes the popover it was asked from; focus then goes back to the chips that open it.
    const fromPanel = Boolean(button.closest("#stack-panel"));
    const go = await confirmAction({
      title: VERBS[action] + " " + named(part) + "?",
      body: INTERRUPTS[part || "stack"] + (action === "restart" ? " A restart stops it first, then starts it again." : ""),
      confirm: VERBS[action] + " " + (part ? PARTS[part] : "stack"),
      danger: true,
      returnTo: fromPanel ? $("stack-button") : button,
    });
    if (!go) return;
  }
  const focused = document.activeElement === button;
  const buttons = document.querySelectorAll("#stack-panel button, #banners button, #run-blocked button");
  for (const each of buttons) each.disabled = true;
  report(line, "sending…");
  try {
    const done = await api("/api/stack", { action: action, component: part });
    const failed = done.results.filter((result) => !result.ok);
    const said = (failed.length ? "failed: " : "done: ") + action + " " + which + " — " +
      done.results.map((result) => PARTS[result.component] + ": " + result.said).join("; ");
    report(line, said, failed.length > 0);
    if (!failed.length) setTimeout(() => { if (line.textContent === said) report(line, ""); }, 20000);
    reading = done.health;
    render(reading);
  } catch (error) {
    report(line, "not accepted: " + error.message, true);
  } finally {
    for (const each of buttons) each.disabled = false;
  }
  // A button the new reading drew again is gone: its focus goes to the chips, not to the page's start.
  if (focused && !button.isConnected) $("stack-button").focus();
  wrote();
}
