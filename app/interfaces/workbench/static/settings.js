// The Settings view: who plays each role, what each is told, and how the roles work together. Read with the
// revision it was read at, changed here, and applied in one go to the operator's own settings, which reach
// the runs started after it and never a run already started. Each setting is named by its JSON Pointer:
// the change the page sends, and the refusal the server answers with, both name it that way.

import { api } from "./api.js";
import { $, code, confirmAction, el, listedFlowName, report, score, setDialogDismissal, showReading } from "./ui.js";

// The last read, the flows there are, and the changes made here since, by the pointer of the setting each
// changes: its new value, its removal, or its revert to what lies below the operator's own settings.
let shown = null;
let flows = [];
let selectedRole = null;
const staged = new Map();
const profilesDialog = $("settings-profiles-dialog");
const instructionsDialog = $("settings-instructions");
const NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const ACCESS = { write: "Writes in the run's worktree.", read: "Reads only: its agent runs read-only." };
const SHARED_PROFILE = "Changes to this profile apply to both roles on new runs.";
const SECTIONS = {
  roles: ["agents", "roles", "stage_skills", "review_prompts"],
  workflow: ["review_rounds", "default_flow", "timeout_seconds"],
};
const PROFILE_FIELDS = {
  model: "Model", effort: "Reasoning effort", provider: "Provider override", launcher: "Launcher",
};
const INSTRUCTIONS = [
  { key: "persona", title: "Role instructions",
    hint: "Sent when this role starts an agent session." },
  { key: "after_normal", title: "After normal rounds",
    hint: "Used on the first turn after the normal budget is exhausted, when extra review rounds are available." },
  { key: "at_limit", title: "Final round",
    hint: "Used on the final budgeted turn. If the review runs out of rounds, you receive the architect’s feedback." },
];

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

function canRevert(section, settings) {
  return SECTIONS[section].some((key) => {
    const root = pointer(key);
    const touched = [...staged.values()].some((change) => change.pointer === root
      || change.pointer.startsWith(root + "/"));
    if (!touched) return at(shown.overrides, [key]) !== undefined;
    return !same(settings[key], shown.shared[key]);
  });
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
  if ([...staged.values()].some((change) => change.revert &&
    (text === change.pointer || text.startsWith(change.pointer + "/")))) return false;
  return at(shown.overrides, keysOf(text)) !== undefined;
}

function kinds() {
  return Object.fromEntries(shown.kinds.map((kind) => [kind.kind, kind]));
}

function kindName(kind) {
  const found = kinds()[kind];
  return found && found.name ? found.name : kind;
}

// ---- drawing ------------------------------------------------------------------------------------

function field(labelText, control, text, extra = [], target = control) {
  const wrap = el("div", null, "field");
  const label = el("label", labelText);
  label.htmlFor = target.id;
  const head = el("div", null, "field-head");
  head.append(label);
  target.name = text ? keysOf(text).join(".") : target.id;
  if (text) {
    target.dataset.pointer = text;
    if (hasStaged(text)) target.dataset.staged = "";
  }
  const alert = el("p", null, "alert");
  alert.setAttribute("role", "alert");
  wrap.append(head, control, ...extra, alert);
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

function profileGroups(entries) {
  const groups = new Map();
  for (const entry of entries) {
    const runtime = entry[1].kind;
    if (!groups.has(runtime)) groups.set(runtime, []);
    groups.get(runtime).push(entry);
  }
  return groups;
}

function canServe(kind, role) {
  return !kind?.refused && kind?.access?.includes(shown.roles[role].access);
}

function profileDescription(profile) {
  return [profile.model, profile.effort && profile.effort + " effort"].filter(Boolean).join(" · ");
}

function profileName(name, role) {
  return name.endsWith("-" + role) ? name.slice(0, -(role.length + 1)) : name;
}

function profileLabel(name, profile, role) {
  const short = profileName(name, role);
  const description = profileDescription(profile);
  const repeated = short !== name && [profile.kind, profile.model].some((value) =>
    value === short || value?.startsWith(short + "-"));
  return [description && repeated ? "" : short, description].filter(Boolean).join(" · ");
}

function roleProfile(settings, role, name) {
  if (settings.roles[role].agent === name) return true;
  const suggested = Object.keys(settings.roles).find((role) => name.endsWith("-" + role));
  return (suggested ?? assignedRoles(settings, name)[0] ?? role) === role;
}

function chooseProfile(role, name) {
  const text = pointer("roles", role, "agent");
  stage(text, { value: name });
  draw();
  focusSetting(text);
}

function selectRole(role, settings = pending()) {
  selectedRole = role;
  for (const panel of $("settings-roles").children) panel.hidden = panel.dataset.role !== role;
  for (const choice of $("settings-role-options").querySelectorAll("input")) choice.checked = choice.value === role;
  const place = $("settings-profile-for-" + role);
  const previous = $("settings-role-profile");
  if (place && previous?.parentElement === place) return;
  previous?.remove();
  if (place) {
    const editor = el("div", null, "profile-fields");
    editor.id = "settings-role-profile";
    editor.append(...profileFields(settings, settings.roles[role].agent));
    place.append(editor);
  }
}

function drawRoles(settings) {
  const roles = Object.entries(shown.roles);
  const runtimes = kinds();
  const profiles = profileGroups(Object.entries(settings.agents));
  $("settings-role-options").replaceChildren(...roles.map(([role]) => {
    const option = el("div", null, "settings-role-option");
    const choice = el("input", null, "visually-hidden settings-role-choice");
    choice.type = "radio";
    choice.name = "settings-role";
    choice.id = "settings-role-choice-" + role;
    choice.value = role;
    choice.setAttribute("aria-controls", "settings-role-panel-" + role);
    choice.onchange = () => {
      selectRole(role);
      markSettingsSection($("settings-roles-title"));
    };
    const label = el("label");
    label.htmlFor = choice.id;
    const name = settings.roles[role].agent;
    const runtime = settings.agents[name]?.kind;
    label.append(el("span", role, "role " + role), el("span", kindName(runtime), "hint"));
    option.append(choice, label);
    return option;
  }));

  $("settings-roles").replaceChildren(...roles.map(([role, contract]) => {
    const block = el("section", null, "cast-role");
    block.id = "settings-role-panel-" + role;
    block.dataset.role = role;
    const title = el("h3", role, "visually-hidden");
    title.id = "settings-role-" + role;
    block.setAttribute("aria-labelledby", title.id);
    const bound = settings.roles[role].agent;
    const agent = el("select");
    agent.id = "settings-agent-" + role;
    for (const [runtime, entries] of profiles) {
      const compatible = canServe(runtimes[runtime], role);
      const group = el("optgroup");
      group.label = (runtimes[runtime]?.name || runtime) + (compatible ? "" : " (unavailable)");
      for (const [name, each] of entries) {
        if (name !== bound && (!compatible || !roleProfile(settings, role, name))) continue;
        const short = profileName(name, role);
        const runtimeName = kindName(runtime);
        const agentName = runtime === short || runtime.startsWith(short + "-") ? runtimeName : runtimeName + " · " + short;
        const option = el("option", name === bound ? agentName : profileLabel(name, each, role));
        option.value = name;
        option.translate = false;
        option.disabled = !compatible;
        group.append(option);
      }
      if (group.children.length) agent.append(group);
    }
    const hasOtherProfiles = [...Object.keys(settings.agents), ...Object.keys(shown.shared.agents)].some((name) => name !== bound);
    if (hasOtherProfiles) agent.add(new Option("Browse other profiles…", "#browse"));
    agent.value = bound;
    const agentPointer = pointer("roles", role, "agent");
    agent.onchange = () => {
      if (agent.value === "#browse") {
        agent.value = bound;
        openProfiles("browse");
      } else chooseProfile(role, agent.value);
    };
    const profilePlace = el("div", null, "settings-profile-values");
    profilePlace.id = "settings-profile-for-" + role;
    const profile = el("div", null, "cast-profile");
    const picker = el("div", null, "settings-profile-picker");
    const add = el("button", "+", "settings-profile-action");
    add.type = "button";
    add.title = "Add profile";
    add.setAttribute("aria-label", add.title);
    add.disabled = !shown.writable;
    add.onclick = () => openProfiles("add");
    const options = el("button", "Edit", "settings-profile-action settings-edit-profile");
    options.type = "button";
    options.title = shown.writable ? "Edit profile" : "View profile";
    options.textContent = shown.writable ? "Edit" : "View";
    options.setAttribute("aria-label", options.title);
    options.classList.add("settings-view-button");
    options.onclick = () => openProfiles("edit");
    picker.append(agent, add, options);
    profile.append(field("Agent profile", picker, agentPointer, [], agent), profilePlace);
    const runtime = runtimes[settings.agents[bound]?.kind];
    const access = el("details", null, "settings-detail settings-role-access");
    access.append(el("summary", "Workspace access"), el("p", [ACCESS[contract.access], runtime?.boundary?.[contract.access]]
      .filter(Boolean).join(" "), "hint"));
    block.append(title, profile);
    if (assignedRoles(settings, bound).length > 1) block.append(el("p", SHARED_PROFILE, "hint settings-shared-profile"));
    block.append(access, stageSkills(settings, role, contract.stages, runtime), instructionPreviews(role));
    return block;
  }));
  selectRole(Object.hasOwn(shown.roles, selectedRole) ? selectedRole : roles[0]?.[0], settings);
}

function skillStack(value) {
  return Array.isArray(value) ? value : value ? [value] : [];
}

function skillBinding(names) {
  return names.length ? { value: names.length === 1 ? names[0] : names } : { remove: true };
}

function stageSkills(settings, role, stages, runtime) {
  const skills = el("section", null, "settings-role-section skills");
  skills.id = "settings-skills-" + role;
  const picker = el("div", null, "stage-skill-fields");
  const available = runtime?.skill ? shown.skills[runtime.kind] || [] : [];
  const hint = runtime?.skill ? "Skills apply on each turn of the stage. The first skill leads."
    : "This runtime has no explicit skill binding.";
  skills.append(el("h4", "Stage skills"), el("p", hint, "hint"), picker);
  for (const stage_ of stages) {
    const title = stage_ === "research" ? "Plan" : stage_[0].toUpperCase() + stage_.slice(1);
    const text = pointer("stage_skills", stage_);
    const fieldset = el("fieldset", null, "field stage-skill");
    fieldset.id = "settings-skill-" + stage_;
    fieldset.tabIndex = -1;
    fieldset.dataset.pointer = text;
    fieldset.append(el("legend", title, "visually-hidden"));
    const current = skillStack(settings.stage_skills?.[stage_]);
    const stageHead = el("div", null, "settings-skill-head");
    stageHead.append(el("span", title));
    if (current.length) stageHead.append(el("span", current.length === 1 ? "1 skill" : current.length + " skills",
      "hint settings-skill-count"));
    fieldset.append(stageHead);
    const tags = el("div", null, "skill-tags");
    const manual = el("div", null, "skill-manual");
    manual.hidden = true;
    const input = textInput(fieldset.id + "-name", "", "Skill name…");
    input.maxLength = 64;
    input.setAttribute("aria-label", "Skill name for " + title);
    const add = el("button", "Add", "quiet");
    add.type = "button";
    manual.append(input, add);
    const alert = el("p", null, "alert");
    alert.setAttribute("role", "alert");
    const save = (next) => {
      stage(text, skillBinding(next));
      draw();
      $(fieldset.id).focus({ preventScroll: true });
    };
    for (const name of current) {
      const tag = el("button", name + (shown.writable ? " ×" : ""), "skill-tag");
      tag.type = "button";
      tag.disabled = !shown.writable;
      tag.setAttribute("aria-label", shown.writable ? "Remove " + name + " from " + title : name);
      tag.onclick = () => save(current.filter((skill) => skill !== name));
      tags.append(tag);
    }
    if (!current.length) tags.append(el("span", "Built-in instructions", "hint"));
    fieldset.append(el("p", "In use", "hint"), tags);
    if (runtime?.skill) {
      const candidates = available.filter((name) => !current.includes(name));
      const choices = el("div", null, "skill-available");
      for (const name of candidates) {
        const choice = el("button", "+ " + name, "skill-tag");
        choice.type = "button";
        choice.disabled = !shown.writable;
        choice.setAttribute("aria-label", "Add " + name + " to " + title);
        choice.onclick = () => save([...current, name]);
        choices.append(choice);
      }
      if (!candidates.length) choices.append(el("span", available.length ? "All installed skills are in use."
        : "No installed skills found.", "hint"));
      fieldset.append(el("p", "Available skills", "hint"), choices);
      if (shown.writable) {
        const enter = el("button", "Enter a skill name…", "quiet skill-name-entry");
        enter.type = "button";
        enter.onclick = () => {
          manual.hidden = false;
          enter.hidden = true;
          input.focus();
        };
        fieldset.append(enter, manual);
      }
    }
    add.onclick = () => {
      const name = input.value.trim();
      if (!NAME.test(name) || name.length > 64 || current.includes(name)) {
        alert.textContent = current.includes(name) ? "This skill is already selected."
          : "Use lowercase letters and digits with single hyphens between words.";
        input.focus();
        return;
      }
      save([...current, name]);
    };
    input.onkeydown = (event) => { if (event.key === "Enter") { event.preventDefault(); add.click(); } };
    fieldset.append(alert);
    picker.append(fieldset);
  }
  return skills;
}

function assignedRoles(settings, name) {
  return Object.keys(settings.roles).filter((role) => settings.roles[role].agent === name);
}

function primaryProfileOption(option) {
  return option === "model" || option === "effort";
}

function profileOption(option, id, value, path) {
  const input = textInput(id, value, "Runtime default");
  input.defaultValue = input.value;
  input.disabled = !shown.writable;
  const help = [];
  if (option === "provider" || option === "launcher") {
    const hint = el("p", null, "hint");
    hint.id = input.id + "-hint";
    input.setAttribute("aria-describedby", hint.id);
    const describe = () => {
      hint.textContent = option === "launcher" ? "Optional launcher executable on the worker. Leave blank for the runtime default."
        : input.value.trim() === "deepseek" ? "DeepSeek needs a model and DEEPSEEK_API_KEY on the worker."
        : "Leave blank to use the runtime's configured model provider.";
    };
    describe();
    input.oninput = describe;
    help.push(hint);
  }
  return { input, row: field(PROFILE_FIELDS[option] || option, input, path, help) };
}

function profileFields(settings, name, save) {
  const profile = settings.agents[name];
  if (!profile) return [];
  const options = kinds()[profile.kind]?.options || [];
  const prefix = save ? "settings-edit-" : "settings-";
  return options.filter((option) => save || primaryProfileOption(option) || option === "launcher")
    .map((option) => {
      const path = pointer("agents", name, option);
      const { input, row } = profileOption(option, prefix + option + "-" + name, profile[option], path);
      const update = () => {
        const value = input.value.trim();
        stage(path, value ? { value } : { remove: true }, input);
      };
      if (save) {
        const original = input.value;
        save.push(() => { if (input.value !== original) update(); });
      } else input.onchange = update;
      return row;
    });
}

function openProfiles(mode, name) {
  const role = selectedRole;
  const settings = pending();
  const body = $("settings-profiles-body");
  const form = $("settings-profile-form");
  const done = $("settings-profile-done");
  const adding = mode === "add";
  const browsing = mode === "browse";
  const bound = settings.roles[role].agent;
  let dirty = () => false;
  const updateDismissal = () => setDialogDismissal(profilesDialog, dirty());
  const close = profilesDialog.querySelector("footer [data-close-settings-dialog]");
  $("settings-profiles-title").textContent = adding ? "Add profile" : browsing ? "Choose a profile"
    : shown.writable ? "Edit profile" : "Profile details";
  const intro = $("settings-profiles-intro");
  intro.textContent = adding ? "Create a reusable profile and select it for this role." : "";
  intro.hidden = !adding;
  done.textContent = adding ? "Add and select" : "Save";
  done.title = mode === "edit" ? "Apply in Settings saves these changes for new runs." : "";
  done.hidden = browsing || !shown.writable;
  close.textContent = done.hidden ? "Close" : "Cancel";
  body.replaceChildren();
  if (browsing) {
    const runtimes = kinds();
    const entries = Object.entries(settings.agents).filter(([profile]) => profile !== bound);
    entries.push(...Object.entries(shown.shared.agents).filter(([profile]) => !Object.hasOwn(settings.agents, profile)));
    const list = el("ul", null, "profile-list");
    for (const [profile, details] of entries) {
      const row = el("li", null, "profile-row");
      const info = el("div");
      info.append(code(profileName(profile, role)), el("p", [kindName(details.kind), profileDescription(details)]
        .filter(Boolean).join(" · "), "hint"));
      const buttons = el("div", null, "actions");
      const removed = !Object.hasOwn(settings.agents, profile);
      if (removed) {
        info.append(el("p", "Removed", "hint"));
        const restore = el("button", "Restore", "quiet");
        restore.type = "button";
        restore.disabled = !shown.writable;
        restore.setAttribute("aria-label", "Restore the profile " + profile);
        restore.onclick = () => {
          stage(pointer("agents", profile), { revert: true });
          draw();
          openProfiles("browse");
        };
        buttons.append(restore);
      } else if (canServe(runtimes[details.kind], role)) {
        const use = el("button", "Select profile", "quiet");
        use.type = "button";
        use.disabled = !shown.writable;
        use.setAttribute("aria-label", "Select " + profile);
        use.onclick = () => {
          profilesDialog.close();
          chooseProfile(role, profile);
        };
        buttons.append(use);
      }
      if (!removed) {
        const edit = el("button", shown.writable ? "Edit" : "View", "quiet");
        edit.type = "button";
        edit.setAttribute("aria-label", (shown.writable ? "Edit" : "View") + " the profile " + profile);
        edit.onclick = () => openProfiles("edit", profile);
        buttons.append(edit);
      }
      if (!removed && !assignedRoles(settings, profile).length && shown.writable) {
        const remove = el("button", "Remove", "quiet danger");
        remove.type = "button";
        remove.setAttribute("aria-label", "Remove the profile " + profile);
        remove.onclick = async () => {
          if (!await confirmAction({ title: "Remove " + profile + "?", body: "Apply saves this removal.",
            confirm: "Remove", danger: true })) return;
          stage(pointer("agents", profile), { remove: true });
          draw();
          openProfiles("browse");
        };
        buttons.append(remove);
      }
      row.append(info, buttons);
      list.append(row);
    }
    body.append(entries.length ? list : el("p", "No other profiles.", "hint"));
    form.onsubmit = (event) => event.preventDefault();
  } else if (adding) {
    const profile = textInput("settings-add-name", "", "review-fast…");
    const runtime = el("select");
    runtime.id = "settings-add-kind";
    const runtimes = shown.kinds.filter((kind) => canServe(kind, role));
    for (const kind of runtimes) {
      runtime.add(new Option(kind.name, kind.kind));
    }
    runtime.value = settings.agents[bound]?.kind;
    if (runtime.selectedIndex < 0) runtime.selectedIndex = 0;
    const initialKind = runtime.value;
    const basics = el("div", null, "profile-form-fields");
    const nameField = field("Profile name", profile);
    basics.append(nameField, field("Runtime", runtime));
    const options = el("div", null, "profile-form-fields");
    const advanced = el("details", null, "settings-profile-advanced");
    const advancedFields = el("div", null, "profile-form-fields");
    advanced.append(el("summary", "Advanced profile options"), advancedFields);
    body.append(basics, options, advanced);
    const runtimeFields = new Map();
    dirty = () => profile.value !== "" || runtime.value !== initialKind || [...runtimeFields.values()]
      .some((fields) => fields.some(([, field]) => field.input.value !== ""));
    const drawOptions = () => {
      const kind = runtimes.find((item) => item.kind === runtime.value);
      if (!runtimeFields.has(runtime.value)) {
        runtimeFields.set(runtime.value, (kind?.options || []).map((option) =>
          [option, profileOption(option, "settings-add-" + option)]));
      }
      const fields = runtimeFields.get(runtime.value);
      options.replaceChildren(...fields.filter(([option]) => primaryProfileOption(option)).map(([, field]) => field.row));
      advancedFields.replaceChildren(...fields.filter(([option]) => !primaryProfileOption(option)).map(([, field]) => field.row));
      advanced.hidden = !advancedFields.children.length;
      advanced.open = false;
    };
    drawOptions();
    runtime.onchange = drawOptions;
    profile.autofocus = true;
    form.onsubmit = (event) => {
      event.preventDefault();
      if (!shown.writable) return;
      const name = profile.value.trim();
      const alert = nameField.querySelector(".alert");
      if (!NAME.test(name) || Object.hasOwn(settings.agents, name) || !runtime.value) {
        alert.textContent = !NAME.test(name) ? "Use lowercase letters and digits joined by single hyphens."
          : Object.hasOwn(settings.agents, name) ? "This profile name is already in use." : "Choose a runtime.";
        profile.focus();
        return;
      }
      const value = { kind: runtime.value };
      for (const [option, { input }] of runtimeFields.get(runtime.value)) {
        if (input.value.trim()) value[option] = input.value.trim();
      }
      stage(pointer("agents", name), { value });
      profilesDialog.close();
      chooseProfile(role, name);
    };
  } else {
    const editing = name || bound;
    const shared = shown.shared.agents[editing];
    const profilePointer = pointer("agents", editing);
    let save = [];
    let useShared = false;
    intro.textContent = kindName(settings.agents[editing].kind) + " · " + editing;
    intro.hidden = false;
    const fields = profileFields(settings, editing, save);
    const controls = el("div", null, "profile-form-fields");
    dirty = () => useShared || [...controls.querySelectorAll("input")].some((input) => input.value !== input.defaultValue);
    if (fields.length) {
      controls.append(...fields);
      body.append(controls);
    } else {
      body.append(el("p", "This runtime uses its own settings.", "hint"));
      done.hidden = true;
      close.textContent = "Close";
    }
    if (shown.writable && shared && (!same(shared, settings.agents[editing]) || overridden(profilePointer))) {
      const revert = el("button", "Use shared profile values", "quiet");
      revert.type = "button";
      revert.id = "settings-revert-profile";
      revert.onclick = () => {
        useShared = true;
        save = [];
        controls.replaceChildren(...profileFields(shown.shared, editing, save));
        intro.textContent = kindName(shared.kind) + " · " + editing;
        revert.disabled = true;
        updateDismissal();
        controls.querySelector("input")?.focus();
      };
      body.append(revert);
    }
    if (assignedRoles(settings, editing).length > 1) body.append(el("p", SHARED_PROFILE, "hint"));
    form.onsubmit = (event) => {
      event.preventDefault();
      if (!shown.writable) return;
      if (useShared) stage(profilePointer, { revert: true });
      save.forEach((update) => update());
      profilesDialog.close();
      draw();
      focusSetting(pointer("roles", role, "agent"));
    };
  }
  profilesDialog.oninput = profilesDialog.onchange = updateDismissal;
  updateDismissal();
  if (!profilesDialog.open) profilesDialog.showModal();
}

function drawWorkflow(settings) {
  const timeout = el("input");
  timeout.id = "settings-turn-hours";
  timeout.type = "number";
  timeout.name = "timeout_seconds";
  timeout.min = "0";
  timeout.step = "any";
  timeout.value = settings.timeout_seconds / 3600;
  timeout.dataset.pointer = "/timeout_seconds";
  timeout.toggleAttribute("data-staged", hasStaged(timeout.dataset.pointer));
  timeout.setAttribute("aria-describedby", "settings-turn-unit settings-turn-hint");
  timeout.onchange = () => stage("/timeout_seconds", { value: Math.round(Number(timeout.value) * 3600) }, timeout);
  const unit = el("span", "hours");
  unit.id = "settings-turn-unit";
  const duration = el("div", null, "workflow-duration");
  duration.append(timeout, unit);
  const controls = el("div", null, "workflow-turn-controls");
  controls.append(duration);
  const alert = el("p", null, "alert");
  alert.setAttribute("role", "alert");
  $("settings-timeout").replaceChildren(controls, alert);
  const rounds = settings.review_rounds || Object.fromEntries(shown.phases.map((phase) =>
    [phase, { normal: settings.max_rounds[phase], extended: 0 }]));
  $("settings-rounds").replaceChildren(...shown.phases.map((phase) => {
    const row = el("tr");
    const title = phase[0].toUpperCase() + phase.slice(1);
    const heading = el("th", title);
    heading.scope = "row";
    row.append(heading);
    for (const threshold of ["normal", "extended"]) {
      const text = pointer("review_rounds", phase, threshold);
      const input = el("input");
      input.type = "number";
      input.min = threshold === "normal" ? "1" : "0";
      input.step = "1";
      input.id = "settings-rounds-" + phase + "-" + threshold;
      input.value = rounds[phase][threshold];
      input.onchange = () => stage(text, { value: Number(input.value) }, input);
      input.oninput = () => updateReviewMaximum(phase);
      const when = threshold === "normal" ? "normal rounds" : "rounds after reflection";
      const wrap = field(title + " " + when, input, text);
      wrap.querySelector("label").classList.add("visually-hidden");
      wrap.classList.add("review-count");
      row.insertCell().append(wrap);
    }
    const maximum = el("output");
    maximum.id = "settings-rounds-" + phase + "-maximum";
    maximum.htmlFor = "settings-rounds-" + phase + "-normal settings-rounds-" + phase + "-extended";
    row.insertCell().append(maximum);
    return row;
  }));
  shown.phases.forEach(updateReviewMaximum);
  const select = $("settings-flow");
  select.name = "default_flow";
  const choosing = listedFlowName(flows, settings.default_flow || "");
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
  if (!choosing) {
    const placeholder = el("option", "Choose a default flow");
    placeholder.value = "";
    placeholder.disabled = true;
    options.unshift(placeholder);
  }
  select.replaceChildren(...options);
  select.value = choosing;
  if (staged.has("/default_flow")) select.dataset.staged = "";
  else delete select.dataset.staged;
  const steps = () => {
    const flow = flows.find((each) => each.name === select.value);
    $("settings-workflow-flow").textContent = select.value ? select.selectedOptions[0].textContent : "No default selected";
    $("settings-flow-steps").hidden = !(flow && flow.steps);
    if (flow && flow.steps) score($("settings-flow-steps"), flow.steps);
  };
  steps();
  select.onchange = () => {
    if (select.value) stage("/default_flow", { value: select.value }, select);
    steps();
  };
}

function updateReviewMaximum(phase) {
  const normal = $("settings-rounds-" + phase + "-normal");
  const extended = $("settings-rounds-" + phase + "-extended");
  const maximum = $("settings-rounds-" + phase + "-maximum");
  if (!normal || !extended || !maximum) return;
  const counts = [normal, extended];
  const valid = counts.every((input) => input.value !== "" && Number.isInteger(Number(input.value))
    && Number(input.value) >= Number(input.min));
  const total = valid ? counts.reduce((sum, input) => sum + Number(input.value), 0) : null;
  maximum.textContent = total === null ? "—" : total + (total === 1 ? " round" : " rounds");
  maximum.setAttribute("aria-label", total === null ? "Maximum " + phase + " iterations pending valid values"
    : "Maximum " + phase + " iterations: " + total);
}

function instructionPreviews(role) {
  const block = el("section", null, "settings-role-section settings-instruction-links");
  const heading = el("h4", "Instructions");
  heading.id = "settings-instruction-links-" + role;
  block.setAttribute("aria-labelledby", heading.id);
  const list = el("ul", null, "settings-instruction-list");
  for (const { key, title, hint } of INSTRUCTIONS) {
    const row = el("li");
    const help = el("span", null, "round-help instruction-help");
    const question = el("button", "?");
    question.type = "button";
    question.setAttribute("aria-label", "When " + title + " applies");
    const answer = el("span", hint);
    answer.id = "settings-instruction-help-" + key + "-" + role;
    answer.setAttribute("role", "tooltip");
    question.setAttribute("aria-describedby", answer.id);
    help.onpointerenter = question.onfocus = () => delete help.dataset.dismissed;
    question.onclick = () => {
      delete help.dataset.dismissed;
      question.focus();
    };
    question.onkeydown = (event) => {
      if (event.key === "Escape") help.dataset.dismissed = "";
    };
    help.append(question, answer);
    const preview = el("button", "Preview", "settings-view-button");
    preview.type = "button";
    preview.id = "settings-edit-" + (key === "persona" ? "instructions" : key) + "-" + role;
    preview.setAttribute("aria-label", "Preview " + title);
    preview.onclick = () => openInstructions(role, key);
    row.append(el("span", title), help, preview);
    list.append(row);
  }
  block.append(heading, list);
  return block;
}

function openInstructions(role, target = "persona") {
  const settings = pending();
  const configured = settings.roles[role];
  const saved = shown.settings.roles[role];
  const body = $("settings-instructions-body");
  const tabs = $("settings-instructions-nav");
  tabs.querySelectorAll(".settings-role-option").forEach((option) => option.remove());
  body.replaceChildren();
  const save = [];
  const dirty = [];
  const updateDismissal = () => setDialogDismissal(instructionsDialog, dirty.some((changed) => changed()));
  const view = (section) => {
    for (const panel of body.children) panel.hidden = panel.dataset.section !== section;
    for (const choice of tabs.querySelectorAll("input")) choice.checked = choice.value === section;
  };
  for (const event of INSTRUCTIONS) {
    const persona = event.key === "persona";
    const id = persona ? "settings-persona-" + role : "settings-prompt-" + event.key + "-" + role;
    const text = persona ? pointer("roles", role, "persona") : pointer("review_prompts", event.key, role);
    let useFile = false;
    const willReadDefault = persona && !("persona" in configured) && "persona" in saved;
    const old = persona ? configured.persona ?? (willReadDefault ? "" : shown.personas[role] ?? "")
      : at(settings, keysOf(text)) || "";
    const panel = el("section", null, "settings-instruction-panel");
    panel.id = id + "-panel";
    panel.dataset.section = event.key;
    const input = el("textarea");
    input.id = id;
    input.value = old;
    input.spellcheck = false;
    input.readOnly = !shown.writable;
    dirty.push(() => useFile || input.value !== old);
    const hint = el("p", persona ? (willReadDefault ? "The default instructions will be read when you apply."
      : event.hint)
      : event.hint + " Plan and Build share these additions. Up to "
        + shown.max_review_prompt_bytes.toLocaleString() + " UTF-8 bytes across both roles.", "hint");
    hint.id = id + "-hint";
    input.setAttribute("aria-describedby", hint.id);
    const editor = field(persona ? event.title : "Additional guidance (optional)", input, text);
    panel.append(hint);
    if (persona) {
      editor.querySelector("label").classList.add("visually-hidden");
      panel.append(editor);
      if (shown.writable && configured.persona_file && "persona" in configured) {
        const restore = el("button", "Use persona file", "quiet");
        restore.type = "button";
        restore.id = "settings-use-persona-file-" + role;
        let custom;
        restore.onclick = () => {
          useFile = !useFile;
          if (useFile) custom = input.value;
          input.value = useFile ? "" : custom;
          input.readOnly = useFile;
          hint.textContent = useFile ? "Apply will load " + configured.persona_file + "." : event.hint;
          restore.textContent = useFile ? "Keep custom instructions" : "Use persona file";
          updateDismissal();
        };
        panel.append(restore);
      }
    } else {
      input.placeholder = "Add guidance for this round…";
      const panes = el("div", null, "settings-review-panes");
      const builtIn = el("section", null, "prompt-built-in");
      const heading = el("h3", "Built-in instructions");
      heading.id = id + "-built-in-title";
      const instructions = el("pre", shown.code_owned_review_guidance?.[event.key]?.[role] ?? "Built-in guidance is unavailable.");
      instructions.tabIndex = 0;
      instructions.setAttribute("aria-labelledby", heading.id);
      builtIn.append(heading, instructions);
      panes.append(builtIn, editor);
      panel.append(panes);
    }
    save.push(() => {
      if (useFile) {
        stage(text, { remove: true });
        return;
      }
      if (input.value === old) return;
      if (persona && !("persona" in saved) && input.value === shown.personas[role]) staged.delete(text);
      else stage(text, persona || input.value.trim() ? { value: input.value } : { remove: true });
    });
    const tab = el("div", null, "settings-role-option");
    const choice = el("input", null, "visually-hidden");
    choice.type = "radio";
    choice.name = "instructions-tab";
    choice.id = id + "-tab";
    choice.value = event.key;
    choice.setAttribute("aria-controls", panel.id);
    choice.onchange = () => view(event.key);
    const label = el("label", event.title);
    label.htmlFor = choice.id;
    tab.append(choice, label);
    tabs.append(tab);
    body.append(panel);
  }
  $("settings-instructions-title").textContent = role[0].toUpperCase() + role.slice(1) + " instructions";
  $("settings-instructions-done").hidden = !shown.writable;
  $("settings-instructions-form").onsubmit = (event) => {
    event.preventDefault();
    if (!shown.writable) return;
    save.forEach((update) => update());
    instructionsDialog.close();
    noteChanges();
  };
  view(target);
  instructionsDialog.oninput = instructionsDialog.onchange = updateDismissal;
  updateDismissal();
  if (!instructionsDialog.open) instructionsDialog.showModal();
}

function noteChanges() {
  const settings = pending();
  for (const section of Object.keys(SECTIONS)) {
    $("settings-revert-" + section).disabled = !shown.writable || !canRevert(section, settings);
  }
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
  drawWorkflow(settings);
  form.hidden = false;
  $("settings-flow").disabled = !shown.writable;
  if (!shown.writable) {
    for (const control of form.querySelectorAll(
      "input:not(.settings-role-choice), select, textarea, button:not(.settings-view-button, .round-help button)"
    )) {
      control.disabled = true;
    }
  }
  noteChanges();
}

function revealSetting(control) {
  const rolePanel = control.closest(".cast-role");
  if (rolePanel) selectRole(rolePanel.dataset.role);
  const section = control.closest(".settings-part, .settings-disclosure");
  if (section) markSettingsSection($(section.id === "settings-workflow-details" ? "settings-workflow-title" : "settings-roles-title"));
  for (let parent = control.parentElement; parent; parent = parent.parentElement) {
    if (parent.tagName === "DETAILS") parent.open = true;
    if (parent.id === "settings-form") break;
  }
  control.focus();
}

function settingControl(text) {
  const match = '[data-pointer="' + CSS.escape(text) + '"]';
  const find = () => document.querySelector('#view-settings ' + match + ', .settings-editor[open] ' + match
    + ', .settings-instructions[open] ' + match);
  const visible = find();
  if (visible) return visible;
  const [group, name, field] = keysOf(text);
  if ((group === "roles" && ["persona", "persona_file"].includes(field)) || (group === "review_prompts" && field)) {
    const role = group === "roles" ? name : field;
    selectRole(role);
    openInstructions(role, group === "roles" ? "persona" : name);
    return field === "persona_file" ? $("settings-persona-" + role) : find();
  }
  if (group !== "agents" || !name) return null;
  const settings = pending();
  if (!Object.hasOwn(settings.agents, name)) return null;
  const roles = assignedRoles(settings, name);
  if (roles.length) {
    selectRole(roles.includes(selectedRole) ? selectedRole : roles[0], settings);
    const input = find();
    if (input) return input;
  }
  openProfiles("edit", name);
  return find();
}

function focusSetting(text) {
  const found = settingControl(text);
  if (found) revealSetting(found);
}

// A refusal said beside the setting its pointer names, or the nearest one shown, else at the Apply.
function refuse(text, reason) {
  for (const alert of document.querySelectorAll("#settings-form .alert, .settings-editor .alert, .settings-instructions .alert")) {
    alert.textContent = "";
  }
  let keys = text ? keysOf(text) : [];
  while (keys.length) {
    const found = settingControl(pointer(...keys));
    if (found) {
      const holder = found.closest(".field, td, details") || found.parentElement;
      const alert = holder.querySelector(".alert");
      if (alert) {
        alert.textContent = reason;
        revealSetting(found);
        return true;
      }
    }
    keys = keys.slice(0, -1);
  }
  return false;
}

// ---- reading and applying -----------------------------------------------------------------------

export function settingsSection(hash) {
  if (["#settings-review-prompt-summary", "#settings-profile-summary"].includes(hash)) return $("settings-roles-title");
  const link = [...$("settings-jumps").querySelectorAll("a")].find((link) => link.hash === hash);
  return link ? $(hash.slice(1)) : null;
}

function markSettingsSection(target) {
  const active = target.id;
  for (const link of $("settings-jumps").querySelectorAll("a")) {
    if (link.hash === "#" + active) link.setAttribute("aria-current", "location");
    else link.removeAttribute("aria-current");
  }
  const current = $("settings-form").querySelector("[data-settings-current]");
  const section = target.closest(".settings-part, .settings-disclosure");
  if (current !== section) {
    current?.removeAttribute("data-settings-current");
    section?.setAttribute("data-settings-current", "");
  }
}

export function jumpToSettingsSection(target) {
  if ($("view-settings").hidden || $("settings-form").hidden || $("settings-form").inert) return false;
  markSettingsSection(target || $("settings-roles-title"));
  if (!target) return false;
  if (target.parentElement.tagName === "DETAILS") target.parentElement.open = true;
  target.focus({ preventScroll: true });
  target.scrollIntoView({ block: "start" });
  if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
    target.animate([{ opacity: 0.55 }, { opacity: 1 }], 240);
  }
  return true;
}

$("settings-jumps").onclick = (event) => {
  const link = event.target.closest("a");
  if (!link || link.hash !== location.hash || event.button || event.ctrlKey || event.metaKey ||
      event.shiftKey || event.altKey) return;
  event.preventDefault();
  jumpToSettingsSection(settingsSection(link.hash));
};

$("settings-workflow-title").onclick = (event) => markSettingsSection(event.currentTarget.parentElement.open
  ? $("settings-roles-title") : event.currentTarget);

for (const button of document.querySelectorAll("[data-close-settings-dialog]")) {
  button.onclick = () => button.closest("dialog").close();
}
window.addEventListener("hashchange", () => {
  if (!location.hash.startsWith("#settings")) {
    if (profilesDialog.open) profilesDialog.close();
    if (instructionsDialog.open) instructionsDialog.close();
  }
});

export async function openSettings() {
  if (!$("settings-reading").hidden) return;
  const form = $("settings-form");
  const retry = $("settings-reread");
  const before = shown && shown.revision;
  showReading("settings-reading", true);
  form.inert = true;
  retry.disabled = true;
  try {
    const read = await api("/api/settings");
    // The flows' default is read from the settings, so settings that do not load list none: their
    // refusal, and where to fix it, is what the view shows.
    flows = read.refused ? [] : (await api("/api/flows")).flows;
    shown = read;
    if (staged.size && before !== shown.revision) {
      staged.clear();
      report($("settings-result"), "The settings changed since you last saw them, so the changes you had made "
        + "here are gone. Make them again.", true);
    }
    draw();
  } catch (error) {
    const notice = $("settings-notice");
    notice.classList.add("bad");
    $("settings-notice-said").textContent = "The settings cannot be read: " + error.message;
    notice.hidden = false;
  } finally {
    form.inert = false;
    retry.disabled = false;
    showReading("settings-reading", false);
  }
  jumpToSettingsSection(settingsSection(location.hash));
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

for (const [section, keys] of Object.entries(SECTIONS)) {
  $("settings-revert-" + section).onclick = () => {
    for (const key of keys) stage(pointer(key), { revert: true });
    draw();
    report($("settings-result"), "Section reset in the draft. Apply to save it.");
  };
}

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
