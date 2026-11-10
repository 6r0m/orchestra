// A read-only view of Temporal time and Langfuse cost. Its requests never hold up run controls.
import { api } from "./api.js";
import { $, el, lasted, unchanged } from "./ui.js";
import { setRunTitle } from "./rail.js";

let selected = null;
let value = null;
let view = null;
let pending = false;
let failure = "";
let lastRead = 0;
const usd = new Intl.NumberFormat(undefined, { style: "currency", currency: "USD",
  minimumFractionDigits: 2, maximumFractionDigits: 6 });
const number = new Intl.NumberFormat();

export function money(cost) {
  if (!cost || cost.usd === null || cost.usd === undefined) return "Cost unavailable";
  const amount = cost.usd > 0 && cost.usd < 0.000001 ? "<" + usd.format(0.000001) : usd.format(cost.usd);
  return (cost.provenance === "estimated" ? "≈" : "") + amount +
    (cost.api_equivalent ? " API-equivalent" : "") + (cost.unpriced || cost.partial ? " partial" : "");
}

export function showAccounting(runId) {
  selected = runId;
  value = view = null;
  failure = "";
  lastRead = 0;
  $("run-accounting").hidden = !runId;
  for (const id of ["accounting-summary", "accounting-roles", "accounting-attempts"]) {
    $(id).replaceChildren();
    delete $(id).dataset.drew;
  }
  $("accounting-note").textContent = runId ? "Reading recorded time and cost…" : "";
  $("accounting-details").open = false;
  setRunTitle("");
  refresh();
}

export function updateAccounting(next) {
  view = next;
  render();
  refresh();
}

async function refresh() {
  if (!selected || pending || Date.now() - lastRead < 10000) return;
  const runId = selected;
  pending = true;
  try {
    const read = await api("/api/runs/" + encodeURIComponent(runId) + "/accounting");
    if (selected !== runId) return;
    value = read;
    failure = "";
    lastRead = Date.now();
  } catch (error) {
    if (selected !== runId) return;
    failure = "Time and cost cannot be refreshed; retrying. " + error.message;
    lastRead = Date.now();
  } finally {
    pending = false;
    if (selected === runId) render();
  }
}

function elapsed(row) {
  if (!row.started) return "Start not recorded";
  if (row.ended) return Date.parse(row.ended) === Date.parse(row.started) ? "0 sec" : lasted(row.started, row.ended);
  return row.status === "running" ? lasted(row.started, new Date().toISOString()) : "End not recorded";
}

function roleTime(attempts) {
  if (!attempts.length) return "No recorded attempts";
  let milliseconds = 0;
  let unknown = false;
  let known = false;
  for (const row of attempts) {
    if (!row.started || (!row.ended && row.status !== "running")) { unknown = true; continue; }
    known = true;
    milliseconds += Math.max(0, Date.parse(row.ended || new Date().toISOString()) - Date.parse(row.started));
  }
  if (!known) return "Unavailable";
  return (unknown ? "≥ " : "") + (milliseconds === 0 ? "0 sec" :
    lasted(new Date(0).toISOString(), new Date(milliseconds).toISOString()));
}

function pair(label, text) {
  const node = el("div");
  node.append(el("span", label, "hint"), el("strong", text));
  return node;
}

function render() {
  if (!selected) return;
  const cost = value && value.cost;
  const total = cost && cost.available ? cost.total : null;
  const attempts = value ? value.attempts : [];
  const start = value && value.started || view && view.started;
  const end = value && value.closed || view && view.closed;
  const wall = start ? lasted(start, end || new Date().toISOString()) : "Unavailable";
  const summary = $("accounting-summary");
  if (!unchanged(summary, [wall, attempts.map(elapsed), total])) {
    summary.replaceChildren(pair("Run elapsed", wall), pair("Role time", value ? roleTime(attempts) : "Unavailable"),
      pair("Recorded USD", money(total)));
  }
  const note = [failure, cost && cost.stale ? "Cost data is stale; retrying." : "",
    cost && !cost.available ? cost.reason : "",
    cost && cost.truncated ? "Only part of the trace has been read." : "",
    cost && cost.incomplete_steps ? number.format(cost.incomplete_steps) + " role steps reported incomplete telemetry." : "",
    total && total.api_equivalent ? "Includes Standard API-equivalent costs; subscription charges are not measured." : "",
    total ? (!total.requests ? "No recorded model requests yet." : total.usd === null ? "No priced requests." :
      total.provenance === "provider_reported" ? "Provider-reported subtotal." : "Estimated from recorded requests.") +
      " Coverage unknown; unrecorded requests and extra charges may be missing." +
      (total.unpriced ? " " + number.format(total.unpriced) + " recorded requests have no verified price." : "") : ""]
    .filter(Boolean).join(" ");
  const noteText = note || "Reading recorded time and cost…";
  if ($("accounting-note").textContent !== noteText) $("accounting-note").textContent = noteText;
  const roles = $("accounting-roles");
  const roleNames = new Set([...attempts.map((row) => row.role), ...Object.keys(cost && cost.roles || {})]);
  const descriptions = [...roleNames].filter(Boolean).map((role) => {
    const rows = attempts.filter((row) => row.role === role);
    return [role, rows.length, roleTime(rows), money(cost && cost.roles && cost.roles[role])];
  });
  if (!unchanged(roles, descriptions)) roles.replaceChildren(...descriptions.map(([role, count, time, amount]) => {
    const node = el("p");
    node.append(el("strong", role, "role " + role), document.createTextNode(" · " + count + " attempts · " + time + " · " + amount));
    return node;
  }));
  const table = $("accounting-attempts");
  if (!unchanged(table, [attempts.map((row) => [row, elapsed(row)]), cost])) {
    table.replaceChildren(...attempts.map((row) => {
      const tr = el("tr");
      const identity = el("th", null, "accounting-identity");
      identity.scope = "row";
      identity.append(el("span", row.role || "Role unavailable", "role " + row.role),
        el("span", row.stage + " · episode " + row.episode + " · round " + row.round, "hint"));
      const amount = cost && cost.activities && cost.activities[row.activity_id];
      const tokens = amount && amount.tokens_unknown ? (amount.tokens ? "≥" + number.format(amount.tokens) : "Unknown")
        : amount ? number.format(amount.tokens) : "Unavailable";
      const timing = el("td");
      timing.append(el("span", elapsed(row)), el("span", row.status.replaceAll("_", " "), "hint"));
      tr.append(identity, timing, el("td", money(amount)),
        el("td", amount ? number.format(amount.requests) + " / " + tokens : "Unavailable"));
      return tr;
    }));
  }
  for (const node of document.querySelectorAll("[data-turn-cost]")) {
    node.textContent = money(cost && cost.turns && cost.turns[node.dataset.turnCost]);
    node.title = "Recorded request subtotal; billing coverage is unknown";
  }
  const now = view && (view.role || view.stage || view.state) || "Run";
  setRunTitle(money(total) + (failure || cost && cost.stale ? " stale" : "") + " | Run " + wall + " · " + now +
    " | " + ($("run-task").textContent || selected).slice(0, 60));
}

setInterval(() => { render(); refresh(); }, 5000);
