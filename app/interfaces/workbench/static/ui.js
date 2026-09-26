// What every part of the page draws with, and the words it says a run's state in. Agent and run text is
// only ever set as text, never as markup.

export const $ = (id) => document.getElementById(id);

export function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}

// An identifier, a path or a name that is not prose: never translated, and in the code face.
export function code(text) {
  const node = el("code", text);
  node.translate = false;
  return node;
}

// The stack's parts by name: Temporal, and each host's worker.
export const PARTS = { temporal: "Temporal", wsl: "WSL worker", windows: "Windows worker" };

// Whether `node` last drew `value`: a part is drawn again only when what it shows has changed, so a
// selection, focus, an open disclosure and a scroll position survive a read that brought nothing new.
export function unchanged(node, value) {
  const drawn = JSON.stringify(value);
  if (node.dataset.drew === drawn) return true;
  node.dataset.drew = drawn;
  return false;
}

// The rest of the page reads again after one of its writes.
export function wrote() {
  document.dispatchEvent(new Event("workbench:wrote"));
}

// ---- times, each in the reader's own locale ---------------------------------------------------

const lasting = typeof Intl.DurationFormat === "function"
  ? new Intl.DurationFormat(undefined, { style: "short" }) : null;
const relative = new Intl.RelativeTimeFormat(undefined, { numeric: "auto", style: "short" });
const hourMinute = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" });
const dayHourMinute = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "2-digit",
  minute: "2-digit" });

function seconds(iso) {
  return Math.max(0, Math.floor((Date.now() - Date.parse(iso)) / 1000));
}

// How long since `iso`: "42 sec", "12 min", "1 hr, 5 min".
export function duration(iso) {
  const s = seconds(iso);
  if (Number.isNaN(s)) return "";
  const parts = s < 60 ? { seconds: Math.max(1, s) } : s < 3600 ? { minutes: Math.floor(s / 60) }
    : { hours: Math.floor(s / 3600), minutes: Math.floor(s / 60) % 60 };
  if (lasting) return lasting.format(parts);
  return Object.entries(parts).map(([unit, n]) => n + " " + unit.slice(0, 3)).join(" ");
}

// When `iso` was, from now: "4 hr. ago".
export function ago(iso) {
  const s = seconds(iso);
  if (Number.isNaN(s)) return "";
  if (s < 60) return relative.format(-s, "second");
  if (s < 3600) return relative.format(-Math.floor(s / 60), "minute");
  if (s < 86400) return relative.format(-Math.floor(s / 3600), "hour");
  return relative.format(-Math.floor(s / 86400), "day");
}

// The clock time of `iso`, with its day when that is not today.
export function at(iso) {
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "";
  return (when.toDateString() === new Date().toDateString() ? hourMinute : dayHourMinute).format(when);
}

// A time the page keeps current itself: `tick` rewrites its text, and no part is drawn again for it.
export function clock(iso, mode) {
  const node = el("span", mode === "ago" ? ago(iso) : duration(iso), "clock");
  node.dataset.since = iso;
  node.dataset.clock = mode || "for";
  return node;
}

export function tick() {
  for (const node of document.querySelectorAll("[data-since]")) {
    node.textContent = node.dataset.clock === "ago" ? ago(node.dataset.since) : duration(node.dataset.since);
  }
}

// ---- small controls ---------------------------------------------------------------------------

// The result of the operator's own action: said in its status line, or — refused — as an alert beside it.
export function report(line, text, refused) {
  let alert = line.nextElementSibling;
  if (!(alert && alert.getAttribute("role") === "alert")) {
    alert = el("p", null, "alert");
    alert.setAttribute("role", "alert");
    line.after(alert);
  }
  line.textContent = refused ? "" : text;
  alert.textContent = refused ? text : "";
}

// Puts `text` on the clipboard; `what` names it for a screen reader.
export function copyButton(text, what) {
  const button = el("button", "Copy", "copy");
  button.type = "button";
  button.setAttribute("aria-label", "Copy " + what);
  button.onclick = async () => {
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = "Copied";
    } catch (error) {
      button.textContent = "Copy failed";
    }
    setTimeout(() => { button.textContent = "Copy"; }, 1500);
  };
  return button;
}

// The page's own confirmation: `title` asks, `body` says what follows, `confirm` names the button that
// goes ahead. Cancel is focused first when the action is dangerous; Escape cancels; focus then goes back
// to `returnTo` — a control, or the function that finds it — or else to what asked.
export function confirmAction({ title, body, confirm, danger, returnTo }) {
  const dialog = $("confirm");
  const yes = $("confirm-yes");
  $("confirm-title").textContent = title;
  $("confirm-body").textContent = body || "";
  $("confirm-body").hidden = !body;
  yes.textContent = confirm;
  yes.className = danger ? "danger" : "primary";
  const asked = document.activeElement;
  return new Promise((resolve) => {
    dialog.addEventListener("close", () => {
      resolve(dialog.returnValue === "confirm");
      const back = (typeof returnTo === "function" ? returnTo() : returnTo) || asked;
      if (back && back.isConnected && back.offsetParent !== null) back.focus();
    }, { once: true });
    dialog.returnValue = "";
    dialog.showModal();
    (danger ? $("confirm-no") : yes).focus();
  });
}

// ---- a run in words ---------------------------------------------------------------------------

const DOING = { research: "researching", plan: "planning", assess: "assessing the plan", build: "building",
  verify: "verifying the build" };
// What the run does in a step no role takes.
const HOLDING = { setup: "Setting up its worktree", merge: "Merging", discard: "Discarding",
  cleanup: "Cleaning up" };

export function doing(stage) {
  return DOING[stage] || stage;
}

// What a stop asks of the operator, by why it stopped and — for an approval — what it approves.
export function decisionTitle(reason, phase) {
  if (reason === "approval") {
    return { research: "Approve the research brief", plan: "Approve the plan", build: "Approve the build" }[phase]
      || "Approve";
  }
  return { blocker: "The architect raised a blocker", exhausted: "The review rounds are used up",
    failed: "A step failed", final: "Ready to merge" }[reason] || reason;
}

// How a closed run ended: the workflow's word, or Temporal's when it ended the run itself.
export function outcome(view) {
  if (view.execution === "TERMINATED") return "Force terminated";
  if (view.execution && !["COMPLETED", "CANCELED"].includes(view.execution)) {
    return "Ended: " + view.execution.toLowerCase().replace(/_/g, " ");
  }
  return { MERGED: "Merged", DISCARDED: "Discarded", STOPPED: "Stopped", DONE: "Done", REFUSED: "Refused",
    ABORTED: "Aborted" }[view.status] || (view.status ? view.status.toLowerCase() : "Closed");
}

// A run's state in a few words, and the voice it is said in: who is working, you, or trouble.
export function headline(view) {
  if (view.state === "waiting") return { text: decisionTitle(view.stop.reason, view.phase), tone: "you" };
  if (view.state === "failed") return { text: "A step failed", tone: "bad" };
  if (view.state === "stopping") return { text: "Stopping", tone: "quiet" };
  if (view.state === "running") {
    if (view.role) return { text: view.role + " " + doing(view.stage), tone: view.role };
    return { text: HOLDING[view.stage] || view.stage || "Starting", tone: "quiet" };
  }
  return { text: outcome(view), tone: "quiet" };
}

// The hosts whose down workers hold a run up.
export function blockedBy(view) {
  return view.blocked_by.map((host) => "the " + (PARTS[host] || host) + " is down");
}

// ---- a flow ---------------------------------------------------------------------------------

// A flow drawn as its line of cues into `list`: each step `role action`, those before `current` done and
// the one at `current` ringed; `ended` marks where a closed run stopped, or every step done.
export function score(list, steps, current, ended, moving) {
  list.replaceChildren(...steps.map((step, index) => {
    const [role, action] = step.split(":");
    const item = el("li");
    item.dataset.role = role;
    let state = "plain";
    if (ended === "done") state = "done";
    else if (current !== null && current !== undefined) {
      state = index < current ? "done" : index > current ? "next" : ended === "stopped" ? "stopped" : "current";
    }
    item.dataset.state = state;
    if (state === "current") {
      item.setAttribute("aria-current", "step");
      if (moving) item.dataset.moving = "";
    }
    const mark = el("span", null, "mark");
    mark.setAttribute("aria-hidden", "true");
    item.append(mark, el("span", role, "role-word"), " " + action);
    if (state !== "plain") item.title = { done: "done", current: "now", next: "to come", stopped: "where it stopped" }[state];
    return item;
  }));
}
