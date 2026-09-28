// The Settings view: who plays each role, what each is told, and how the roles work together. Read with the
// revision it was read at, changed here, and applied in one go to the operator's own settings, which reach
// the runs started after it and never a run already started. Each setting is named by its JSON Pointer:
// the change the page sends, and the refusal the server answers with, both name it that way.

import { api } from "./api.js";
import { $, code, confirmAction, el, report, score } from "./ui.js";

// The last read, the flows there are, and the changes made here since, by the pointer of the setting each
// changes: its new value, its removal, or its revert to what lies below the operator's own settings.
let shown = null;
let flows = [];
const staged = new Map();
const NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const ACCESS = { write: "Writes in the run's worktree.", read: "Reads only: its agent runs read-only." };
const RESET = ["agents", "roles", "stage_skills", "review_rounds", "max_rounds", "default_flow"];

export const settingsUnsent = () => staged.size > 0;

function pointer(...keys) {
  return keys.map((key) => "/" + String(key).replaceAll("~", "~0").replaceAll("/", "~1")).join("");
}

function keysOf(text) {
  return text.slice(1).split("/").map((key) => key.replaceAll("~1", "/").replaceAll("~0", "~"));
}

function at(document, keys) {
  return keys.reduce((node, key) => (node !== null && typeof node === "object" && key in node ? node[key] : undefined),
    document);
}

function same(one, other) {
  return JSON.stringify(one) === JSON.stringify(other);
}

// The settings as they will be once applied: what was read, with each change made here.
function pending(excluding = null) {
  const settings = structuredClone(shown.settings);
  for (const change of staged.values()) {
    if (excluding && (change.pointer === excluding || change.pointer.startsWith(excluding + "/"))) continue;
    const keys = keysOf(change.pointer);
    let parent = settings;
    for (const key of keys.slice(0, -1)) {
      if (parent[key] === null || typeof parent[key] !== "object") parent[key] = {};
      parent = parent[key];
    }
    const last = keys.at(-1);
    const below = change.revert ? at(shown.shared, keys) : undefined;
    if (change.remove || (change.revert && below === undefined)) delete parent[last];
    else parent[last] = structuredClone(change.revert ? below : change.value);
  }
  return settings;
}

// ---- changes made here ------------------------------------------------------------------------

// A change drops any made below the setting it changes, and one that leaves a setting as it was read is none.
// The field it came from, when given, shows at once whether it holds a change.
function stage(text, change, control) {
  for (const other of [...staged.keys()]) if (other.startsWith(text + "/")) staged.delete(other);
  const keys = keysOf(text);
  const read = at(pending(text), keys);
  const below = at(shown.shared, keys);
  if ((change.remove && read === undefined) || (change.revert && same(read, below)) ||
      ("value" in change && same(read, change.value))) staged.delete(text);
  else staged.set(text, Object.assign({ pointer: text }, change));
  if (control) control.toggleAttribute("data-staged", hasStaged(text));
  noteChanges();
}

function hasStaged(text) {
  return [...staged.keys()].some((part) => part === text || part.startsWith(text + "/") || text.startsWith(part + "/"));
}

function overridden(text) {
  if ([...staged.values()].some((change) => change.revert && text.startsWith(change.pointer + "/"))) return false;
  return at(shown.overrides, keysOf(text)) !== undefined;
}

function kinds() {
  return Object.fromEntries(shown.kinds.map((kind) => [kind.kind, kind]));
}

function kindName(kind) {
  const found = kinds()[kind];
  return found && found.name ? found.name : kind;
}

// What a skill named `name` is typed as in a stage's prompt by the kind `kind`.
function invocation(kind, name) {
  const found = kinds()[kind];
  if (!found || !found.skill) return el("span", kindName(kind) + " takes no skill.");
  if (!name) return "";
  const said = el("span", "Invoked as ");
  said.append(code(found.skill.replace("{name}", name)));
  return said;
}

// A setting the operator's own settings hold says so, with a way back to what lies below it. `what` names the
// setting in words, for whoever cannot see beside what the Revert sits.
function yours(text, redraw, what) {
  const marks = el("span", null, "marks");
  if (hasStaged(text)) marks.append(el("span", "changed", "yours"));
  else if (overridden(text)) {
    marks.append(el("span", "yours", "yours"));
    const back = el("button", "Revert", "quiet");
    back.type = "button";
    back.setAttribute("aria-label", "Revert " + what + " to the shared settings");
    back.onclick = () => {
      stage(text, { revert: true });
      redraw();
    };
    marks.append(back);
  }
  return marks;
}

// ---- drawing ------------------------------------------------------------------------------------

function field(labelText, control, text, extra, what, target = control) {
  const wrap = el("div", null, "field");
  const label = el("label", labelText);
  label.htmlFor = target.id;
  const head = el("div", null, "field-head");
  head.append(label, yours(text, draw, what || labelText));
  target.name = keysOf(text).join(".");
  target.dataset.pointer = text;
  if (hasStaged(text)) target.dataset.staged = "";
  const alert = el("p", null, "alert");
  alert.setAttribute("role", "alert");
  wrap.append(head, control, ...(extra || []), alert);
  return wrap;
}

function textInput(id, value, placeholder) {
  const input = el("input");
  input.type = "text";
  input.id = id;
  input.spellcheck = false;
  input.value = value || "";
  if (placeholder) input.placeholder = placeholder;
  return input;
}

function drawRoles(settings) {
  $("settings-roles").replaceChildren(...Object.entries(shown.roles).map(([role, contract]) => {
    const block = el("section", null, "cast-role");
    block.dataset.role = role;
    const title = el("h3", role, "role " + role);
    title.id = "settings-role-" + role;
    block.setAttribute("aria-labelledby", title.id);
    const bound = settings.roles[role].agent;
    const profile = settings.agents[bound] || {};

    const agent = el("select");
    agent.id = "settings-agent-" + role;
    for (const [name, each] of Object.entries(settings.agents)) {
      const option = el("option", name + " (" + kindName(each.kind) + ")");
      option.value = name;
      option.translate = false;
      agent.append(option);
    }
    agent.value = bound;
    const agentPointer = pointer("roles", role, "agent");
    agent.onchange = () => {
      stage(agentPointer, { value: agent.value });
      draw();
      focusSetting(agentPointer);
    };
    const facts = el("p", ACCESS[contract.access], "hint");

    // Its persona: the text the run carries from its start — its file's, or the operator's own.
    const personaPointer = pointer("roles", role, "persona");
    const change = staged.get(personaPointer);
    const mine = change ? "value" in change : overridden(personaPointer);
    const read = change ? (mine ? change.value : null) : shown.personas[role];
    const persona = el("details", null, "persona");
    const summary = el("summary");
    const size = el("span", null, "bytes");
    const source = el("span", null, mine ? "yours" : "hint");
    if (mine) source.textContent = "yours";
    else if ("persona" in settings.roles[role]) source.textContent = "from the shared settings";
    else source.append("from ", code(settings.roles[role].persona_file));
    summary.append(el("span", "Persona", "label"), " ", source, " ", size);
    const text = el("textarea");
    text.id = "settings-persona-" + role;
    text.name = keysOf(personaPointer).join(".");
    text.rows = 12;
    text.spellcheck = false;
    text.dataset.pointer = personaPointer;
    if (staged.has(personaPointer)) text.dataset.staged = "";
    const measure = () => {
      const bytes = new TextEncoder().encode(text.value).length;
      size.textContent = bytes.toLocaleString() + " of " + shown.max_persona_bytes.toLocaleString() + " bytes";
      size.classList.toggle("over", bytes > shown.max_persona_bytes);
    };
    if (read === null) {
      text.value = "";
      text.placeholder = "The text of " + settings.roles[role].persona_file + ", once applied.";
      size.textContent = "";
    } else {
      text.value = read;
      measure();
    }
    text.oninput = measure;
    text.onchange = () => {
      if (!("persona" in shown.settings.roles[role]) && text.value === shown.personas[role]) {
        staged.delete(personaPointer);
        text.removeAttribute("data-staged");
        noteChanges();
      } else stage(personaPointer, { value: text.value }, text);
    };
    const label = el("label", "What the " + role + " is told when its session begins", "visually-hidden");
    label.htmlFor = text.id;
    const personaAlert = el("p", null, "alert");
    personaAlert.setAttribute("role", "alert");
    const actions = el("div", null, "actions");
    if (mine || change) {
      const back = el("button", "Use ", "quiet");
      back.append(code(settings.roles[role].persona_file));
      back.type = "button";
      back.onclick = () => {
        stage(personaPointer, overridden(personaPointer) ? { revert: true } : { remove: true });
        draw();
      };
      actions.append(back);
    }
    persona.append(summary, label, text, personaAlert, actions);

    // The skill that leads each of its stages, as its bound kind invokes it.
    const skills = el("div", null, "skills");
    skills.append(el("h4", "Skills"));
    for (const stage_ of contract.stages) {
      const skillPointer = pointer("stage_skills", stage_);
      const input = textInput("settings-skill-" + stage_, at(settings, ["stage_skills", stage_]), "none");
      const row = el("div", null, "skill-input");
      const choose = el("button", "+ Skill", "quiet");
      choose.type = "button";
      choose.setAttribute("aria-label", "Choose an installed skill for " + stage_);
      choose.disabled = !(kinds()[profile.kind] || {}).skill;
      choose.onclick = () => openSkillPicker(input, profile.kind, stage_);
      row.append(input, choose);
      const said = el("p", null, "hint");
      const show = () => said.replaceChildren(input.value.trim()
        ? invocation(profile.kind, input.value.trim()) : el("span", "No stage skill is explicitly bound."));
      show();
      input.oninput = show;
      input.disabled = !(kinds()[profile.kind] || {}).skill;
      input.onchange = () => {
        const name = input.value.trim();
        stage(skillPointer, name ? { value: name } : { remove: true }, input);
      };
      skills.append(field(stage_, row, skillPointer, [said], "the " + stage_ + " stage's skill", input));
    }
    block.append(title, field("Agent", agent, agentPointer, [facts], "the " + role + "'s agent"), persona, skills);
    return block;
  }));
}

function openSkillPicker(input, kind, stage_) {
  const dialog = $("settings-skill-picker");
  const options = $("settings-skill-options");
  dialog.querySelector(".hint").textContent = "Choose an available skill for the " + stage_ + " stage.";
  const names = shown.skills[kind] || [];
  const controls = [];
  for (const name of names) {
    const option = el("button", name, "quiet skill-option");
    option.type = "button";
    option.translate = false;
    option.onclick = () => {
      input.value = name;
      input.dispatchEvent(new Event("input"));
      input.dispatchEvent(new Event("change"));
      dialog.close();
      input.focus();
    };
    controls.push(option);
  }
  const clear = el("button", "No explicit skill", "quiet skill-option");
  clear.type = "button";
  clear.onclick = () => {
    input.value = "";
    input.dispatchEvent(new Event("input"));
    input.dispatchEvent(new Event("change"));
    dialog.close();
    input.focus();
  };
  controls.push(clear);
  if (!names.length) controls.unshift(el("p", "No installed skills were discovered for this agent."));
  options.replaceChildren(...controls);
  dialog.showModal();
}

function drawProfiles(settings) {
  const bound = Object.fromEntries(Object.entries(settings.roles).map(([role, each]) => [each.agent, role]));
  $("settings-profiles").replaceChildren(...Object.entries(settings.agents).map(([name, profile]) => {
    const kind = kinds()[profile.kind] || { name: profile.kind, refused: "no module answers for this kind" };
    const row = el("tr");
    const who = el("td");
    who.append(code(name), yours(pointer("agents", name), draw, "the profile " + name));
    const what = el("td");
    what.append(kind.name || profile.kind, el("span", kind.refused ? "Unusable: " + kind.refused
      : (kind.access.includes("read") ? "Can review. " : "Cannot review. ")
        + (kind.access.includes("write") ? "Can build." : "Cannot build."), "gloss"));
    const cells = ["model", "effort"].map((option) => {
      const cell = el("td");
      const text = pointer("agents", name, option);
      if (!kind.options || !kind.options.includes(option)) {
        cell.append(el("span", "not taken", "gloss"));
        return cell;
      }
      const input = textInput("settings-" + option + "-" + name, profile[option]);
      input.name = keysOf(text).join(".");
      input.setAttribute("aria-label", name + "'s " + option);
      input.dataset.pointer = text;
      if (hasStaged(text)) input.dataset.staged = "";
      input.onchange = () => {
        const value = input.value.trim();
        stage(text, value ? { value } : { remove: true }, input);
      };
      const alert = el("p", null, "alert");
      alert.setAttribute("role", "alert");
      cell.append(input, yours(text, draw, "the profile " + name + "'s " + option), alert);
      return cell;
    });
    const act = el("td");
    const remove = el("button", "Remove", "danger quiet");
    remove.type = "button";
    remove.setAttribute("aria-label", "Remove the profile " + name);
    if (bound[name]) {
      remove.disabled = true;
      remove.title = "The " + bound[name] + " runs it";
    }
    remove.onclick = async () => {
      const go = await confirmAction({ title: "Remove the profile " + name + "?",
        body: "It is removed from your settings when you apply. The shared settings keep theirs.",
        confirm: "Remove", danger: true, returnTo: $("settings-add-name") });
      if (!go) return;
      stage(pointer("agents", name), { remove: true });
      draw();
    };
    act.append(remove);
    row.append(who, what, ...cells, act);
    return row;
  }), ...Object.entries(shown.overrides.agents || {}).filter(([name, value]) => value === null
    && !staged.has(pointer("agents", name))).map(([name]) => {
    const row = el("tr", null, "removed");
    const who = el("td");
    who.append(code(name));
    const said = el("td", "Removed in your settings; the shared settings still hold it.");
    said.colSpan = 3;
    const act = el("td");
    const restore = el("button", "Restore", "quiet");
    restore.type = "button";
    restore.setAttribute("aria-label", "Restore the profile " + name);
    restore.onclick = () => {
      stage(pointer("agents", name), { revert: true });
      draw();
    };
    act.append(restore);
    row.append(who, said, act);
    return row;
  }));
  const usable = shown.kinds.filter((kind) => !kind.refused);
  const choose = $("settings-add-kind");
  const chosen = choose.value;
  choose.replaceChildren(...usable.map((kind) => {
    const option = el("option", kind.name + " (" + kind.kind + ")");
    option.value = kind.kind;
    option.translate = false;
    return option;
  }));
  if (usable.some((kind) => kind.kind === chosen)) choose.value = chosen;
  $("settings-unusable").replaceChildren(...shown.kinds.filter((kind) => kind.refused).map((kind) => {
    const item = el("li");
    item.append(code(kind.kind), " cannot be used: " + kind.refused);
    return item;
  }));
}

function drawTogether(settings) {
  const rounds = settings.review_rounds || Object.fromEntries(shown.phases.map((phase) =>
    [phase, { normal: settings.max_rounds[phase], extended: 0 }]));
  $("settings-rounds").replaceChildren(...shown.phases.flatMap((phase) => {
    const group = el("section", null, "review-budget");
    group.append(el("h3", phase[0].toUpperCase() + phase.slice(1)));
    const fields = ["normal", "extended"].map((threshold) => {
      const text = pointer("review_rounds", phase, threshold);
      const input = el("input");
      input.type = "number";
      input.min = threshold === "normal" ? "1" : "0";
      input.step = "1";
      input.id = "settings-rounds-" + phase + "-" + threshold;
      input.name = keysOf(text).join(".");
      input.value = rounds[phase][threshold];
      input.onchange = () => stage(text, { value: Number(input.value) }, input);
      return field(threshold === "normal" ? "Normal" : "Extended", input, text, [],
                   "the " + phase + " " + threshold + " review budget");
    });
    group.append(...fields);
    return group;
  }));
  const select = $("settings-flow");
  select.name = "default_flow";
  const choosing = settings.default_flow || "";
  const options = flows.map((flow) => {
    const option = el("option", flow.error ? flow.name + " (refused)" : flow.name);
    option.value = flow.name;
    option.disabled = Boolean(flow.error);
    option.translate = false;
    return option;
  });
  if (choosing && !flows.some((flow) => flow.name === choosing)) {
    const missing = el("option", choosing + " (missing)");
    missing.value = choosing;
    options.unshift(missing);
  }
  const none = el("option", "none: the order runs took before flows");
  none.value = "";
  options.unshift(none);
  select.replaceChildren(...options);
  select.value = choosing;
  if (staged.has("/default_flow")) select.dataset.staged = "";
  else delete select.dataset.staged;
  const steps = () => {
    const flow = flows.find((each) => each.name === select.value);
    $("settings-flow-steps").hidden = !(flow && flow.steps);
    if (flow && flow.steps) score($("settings-flow-steps"), flow.steps);
  };
  steps();
  select.onchange = () => {
    stage("/default_flow", select.value ? { value: select.value } : { remove: true }, select);
    steps();
  };
}

function noteChanges() {
  const count = staged.size;
  $("settings-pending").textContent = !shown.writable ? "These settings take no changes here."
    : count ? count + (count === 1 ? " change" : " changes") + " to apply. Runs started from now on take them."
      : "No changes.";
  $("settings-apply").disabled = !shown.writable || !count;
  $("settings-discard").hidden = !count;
}

function draw() {
  const notice = $("settings-notice");
  const form = $("settings-form");
  if (shown.refused) {
    // Nothing is shown to change while the settings do not load: the reason, and where to fix it.
    notice.hidden = false;
    notice.classList.add("bad");
    $("settings-notice-said").textContent = "The settings do not load: " + shown.refused.reason.replace(/\.?\s*$/, ".")
      + " Fix the file it names, or delete your own settings file, then read them again.";
    form.hidden = true;
    return;
  }
  notice.classList.remove("bad");
  notice.hidden = shown.writable;
  if (!shown.writable) {
    $("settings-notice-said").textContent = "These settings are " + shown.source
      + ", which ORCHESTRA_SETTINGS names for a stack of its own. This page shows them and applies nothing.";
  }
  const settings = pending();
  drawRoles(settings);
  drawProfiles(settings);
  drawTogether(settings);
  form.hidden = false;
  for (const id of ["settings-add-name", "settings-add-kind", "settings-add", "settings-flow", "settings-reset"]) {
    $(id).disabled = !shown.writable;
  }
  if (!shown.writable) {
    for (const control of form.querySelectorAll("input, select, textarea, button")) control.disabled = true;
  }
  noteChanges();
}

function focusSetting(text) {
  const found = $("view-settings").querySelector('[data-pointer="' + CSS.escape(text) + '"]');
  if (found) found.focus();
}

// A refusal said beside the setting its pointer names, or the nearest one shown, else at the Apply.
function refuse(text, reason) {
  for (const alert of $("settings-form").querySelectorAll(".alert")) alert.textContent = "";
  let keys = text ? keysOf(text) : [];
  while (keys.length) {
    const found = $("view-settings").querySelector('[data-pointer="' + CSS.escape(pointer(...keys)) + '"]');
    if (found) {
      const holder = found.closest(".field, td, details, .add-agent") || found.parentElement;
      const alert = holder.querySelector(".alert");
      if (alert) {
        alert.textContent = reason;
        if (found.closest("details")) found.closest("details").open = true;
        found.focus();
        return true;
      }
    }
    keys = keys.slice(0, -1);
  }
  return false;
}

// ---- reading and applying -----------------------------------------------------------------------

export async function openSettings() {
  const before = shown && shown.revision;
  let read;
  try {
    read = await api("/api/settings");
    // The flows' default is read from the settings, so settings that do not load list none: their
    // refusal, and where to fix it, is what the view shows.
    flows = read.refused ? [] : (await api("/api/flows")).flows;
  } catch (error) {
    report($("settings-result"), "The settings cannot be read: " + error.message + ". Read them again once "
      + "the Workbench answers.", true);
    return;
  }
  shown = read;
  if (staged.size && before !== shown.revision) {
    staged.clear();
    report($("settings-result"), "The settings changed since you last saw them, so the changes you had made "
      + "here are gone. Make them again.", true);
  }
  draw();
}

$("settings-reread").onclick = () => {
  staged.clear();
  report($("settings-result"), "");
  openSettings();
};

$("settings-discard").onclick = async () => {
  const go = await confirmAction({ title: "Discard your changes?",
    body: "The " + staged.size + (staged.size === 1 ? " change" : " changes") + " made here and not applied are "
      + "dropped. What is applied stays as it is.", confirm: "Discard", danger: true,
    returnTo: $("settings-apply") });
  if (!go) return;
  staged.clear();
  report($("settings-result"), "Changes discarded.");
  draw();
};

$("settings-reset").onclick = () => {
  for (const key of RESET) stage(pointer(key), { revert: true });
  draw();
  report($("settings-result"), staged.size ? "Reset staged. Apply to restore the shared defaults."
    : "The visible settings already match the shared defaults.");
};

$("settings-skill-picker-close").onclick = () => $("settings-skill-picker").close();

$("settings-add").onclick = () => {
  const name = $("settings-add-name").value.trim();
  const kind = $("settings-add-kind").value;
  const alert = $("settings-add-alert");
  const settings = pending();
  alert.textContent = !NAME.test(name) ? "A profile's name is lowercase letters and digits, words joined by "
    + "single hyphens." : settings.agents[name] ? "There is a profile named " + name + " already." : "";
  if (alert.textContent) $("settings-add-name").focus();
  if (alert.textContent || !kind) return;
  stage(pointer("agents", name), { value: { kind } });
  $("settings-add-name").value = "";
  draw();
  focusSetting(pointer("agents", name, "model"));
};

$("settings-form").onsubmit = async (event) => {
  event.preventDefault();
  const button = $("settings-apply");
  button.disabled = true;
  refuse(null);
  report($("settings-result"), "applying…");
  try {
    shown = await api("/api/settings", { revision: shown.revision, changes: [...staged.values()] });
    staged.clear();
    draw();
    // What else the page draws from the settings reads them again: the default flow a new run takes.
    document.dispatchEvent(new Event("workbench:settings"));
    report($("settings-result"), "Applied. Runs started from now on take these settings; a run already started "
      + "keeps its own.");
  } catch (error) {
    if (error.status === 409) {
      report($("settings-result"), "Not applied: the settings changed since this page read them. Read them "
        + "again, then make your changes on what is there now.", true);
      $("settings-notice-said").textContent = "The settings changed since this page read them.";
      $("settings-notice").hidden = false;
    } else {
      refuse(error.pointer, error.message);
      report($("settings-result"), "Not applied: " + (error.pointer ? error.pointer + ": " : "") + error.message, true);
    }
    noteChanges();
  }
};
