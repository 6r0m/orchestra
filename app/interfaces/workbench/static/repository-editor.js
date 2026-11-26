import { api, CONFIG } from "./api.js";
import { $, confirmAction, el, report, showReading } from "./ui.js";
import { chooseRepository, closeRepositoryPicker, refreshRepositoryChoice, reloadRepos } from "./picker.js";

const dialog = $("repository-editor");
const form = $("repository-form");
const remove = $("repository-remove");
const save = $("repository-save");
const cancel = $("repository-cancel");
const nameInput = $("repository-name");
const basics = { path: $("repository-path"), target: $("repository-target"), base_branch: $("repository-base") };
const groups = [
  { title: "Git and execution", fields: [["remote", "Remote", "Local base"],
    ["worktree_root", "Worktree root", "Detect automatically"], ["lfs_pointers", "Git LFS pointers"]] },
  { title: "Todo lifecycle", className: "repository-todo", hint: "Blank fields use the defaults shown.",
    fields: [["todo_dir", "Active"],
    ["todo_parked_dir", "Parked", "", "Disable parked destination"],
    ["todo_backlog_dir", "Backlog", "", "Disable backlog destination"],
    ["todo_done_dir", "Completed", "", "Delete completed todo files"], ["todo_name", "Todo filename pattern"]] },
  { title: "Closeout permissions", fields: [["closeout_docs", "Additional document paths",
    "No additional documents permitted"]] },
];
let current = null;

function option(value, label) {
  const element = el("option", label);
  element.value = value;
  return element;
}

function advancedField(group, entry, kind, [key, title, placeholder, disabledLabel]) {
  const field = el("div", null, "field");
  const label = el("label", title);
  const input = el(kind === "flag" ? "select" : kind === "paths" ? "textarea" : "input");
  input.id = "repository-field-" + key;
  input.name = key;
  label.htmlFor = input.id;
  if (kind === "flag") input.append(option("", "Use default"), option("true", "Yes"), option("false", "No"));
  else {
    if (kind !== "paths") input.type = "text";
    input.spellcheck = false;
    if (placeholder) input.placeholder = placeholder;
  }
  const value = entry[key];
  input.value = kind === "paths" ? (value || []).join("\n") : value ?? "";
  const initial = input.value;
  field.append(label, input);
  let disable = null;
  if (kind === "nullable") {
    disable = el("input");
    disable.type = "checkbox";
    disable.id = input.id + "-disabled";
    disable.checked = value === null;
    input.disabled = disable.checked;
    disable.onchange = () => { input.disabled = disable.checked; };
    const control = el("label", null, "check");
    control.htmlFor = disable.id;
    control.append(disable, disabledLabel);
    field.append(control);
  } else if (kind === "paths") {
    const hint = el("p", "Files the engineer may update during closeout. Enter one Git path pattern per line.", "hint");
    hint.id = input.id + "-hint";
    input.setAttribute("aria-describedby", hint.id);
    field.append(hint);
  }
  group.append(field);
  return (draft) => {
    if (disable?.checked) draft[key] = null;
    else if (input.value !== initial || value === null) {
      const raw = input.value.trim();
      if (raw) draft[key] = kind === "flag" ? raw === "true" :
        kind === "paths" ? raw.split("\n").map((line) => line.trim()).filter(Boolean) : raw;
      else delete draft[key];
    }
  };
}

function advancedFields(fields, entry) {
  const updates = [];
  for (const { title, fields: specs, className, hint } of groups) {
    const group = el("fieldset", null, "field repository-fieldset");
    if (className) group.classList.add(className);
    group.append(el("legend", title));
    if (hint) group.append(el("p", hint, "hint"));
    for (const spec of specs) {
      const kind = fields[spec[0]];
      if (kind) updates.push(advancedField(group, entry, kind, spec));
    }
    $("repository-fields").append(group);
  }
  return updates;
}

function draftEntry(session) {
  const entry = { ...session.entry };
  for (const [key, input] of Object.entries(basics)) {
    if (input.value === (entry[key] ?? "")) continue;
    if (input.value.trim()) entry[key] = input.value.trim();
    else delete entry[key];
  }
  for (const update of session.advanced) update(entry);
  return entry;
}

function updateDismissal() {
  const dirty = current?.entry && (nameInput.value !== (current.original || "") ||
    JSON.stringify(draftEntry(current)) !== JSON.stringify(current.entry));
  dialog.setAttribute("closedby", current?.saving || dirty ? "closerequest" : "any");
}

function updateHints() {
  if (!current?.entry) return;
  const { entry, automaticTarget, detectedBranch, defaults, todoChildren } = current;
  const samePath = basics.path.value === entry.path;
  const target = samePath && automaticTarget;
  basics.target.options[0].textContent = target ? "Automatic (" + target + ")" : "Automatic";
  const sameBaseSource = samePath && basics.target.value === (entry.target || "") &&
    ($("repository-field-remote")?.value || "") === (entry.remote || "");
  basics.base_branch.placeholder = sameBaseSource && detectedBranch ? "Automatic (" + detectedBranch + ")" : "Automatic";
  const active = $("repository-field-todo_dir")?.value.trim() || defaults.todo_dir;
  if (active) {
    for (const [key, leaf] of Object.entries(todoChildren)) {
      $("repository-field-" + key).placeholder = active.replace(/\/+$/, "") + "/" + leaf;
    }
  }
}

export async function openRepositoryEditor(prefix, original = null, detection = null) {
  const returnTo = original ? $("repository-edit") :
    prefix === "worktrees" && document.activeElement === $("repository-add") ? $("repository-add") : $(prefix + "-repo");
  const session = { prefix, original, returnTo };
  current = session;
  form.reset();
  basics.target.options[0].textContent = "Automatic";
  basics.base_branch.placeholder = "Automatic";
  $("repository-fields").replaceChildren();
  $("repository-advanced").open = false;
  $("repository-editor-title").textContent = original ? "Edit repository" : "Add repository";
  save.textContent = original ? "Save changes" : "Save repository";
  save.disabled = true;
  remove.hidden = true;
  remove.disabled = false;
  cancel.disabled = false;
  for (const input of [nameInput, ...Object.values(basics)]) input.disabled = true;
  report($("repository-result"), "Reading repository settings…");
  showReading("repository-reading", true);
  updateDismissal();
  dialog.showModal();
  try {
    const snapshot = await api("/api/repos/editor" + (original ? "?name=" + encodeURIComponent(original) : ""));
    if (current !== session || !dialog.open) return;
    if (!snapshot.writable) throw new Error("This repository list is managed outside the Workbench.");
    if (original && !Object.hasOwn(snapshot.entries, original)) throw new Error("This repository was removed from the list.");
    const entry = original ? snapshot.entries[original] : {};
    const target = [...basics.target.options].find((option) => option.value === snapshot.automatic_target);
    Object.assign(session, { entry, revision: snapshot.revision, advanced: advancedFields(snapshot.fields, entry),
      defaults: snapshot.defaults || {}, todoChildren: snapshot.todo_children || {}, automaticTarget: target?.textContent,
      detectedBranch: !entry.base_branch && detection?.revision === snapshot.descriptor_revision ? detection?.branch : null });
    for (const [key, value] of Object.entries(session.defaults)) {
      $("repository-field-" + key).placeholder = value;
    }
    nameInput.value = original || "";
    for (const [key, input] of Object.entries(basics)) input.value = entry[key] ?? "";
    updateHints();
    for (const input of [nameInput, ...Object.values(basics)]) input.disabled = false;
    save.disabled = false;
    remove.hidden = !original;
    report($("repository-result"), "");
    nameInput.focus();
  } catch (error) {
    if (current === session && dialog.open) report($("repository-result"), error.message, true);
  } finally {
    if (current === session) showReading("repository-reading", false);
  }
}

async function apply(session, name, entry, confirm = false) {
  if (session !== current || session.saving || !dialog.open) return;
  session.saving = true;
  updateDismissal();
  save.disabled = remove.disabled = cancel.disabled = true;
  report($("repository-result"), name ? "Checking the repository on its execution host…" : "Removing from the list…");
  try {
    await api("/api/repos/editor", { original: session.original, name, entry, confirm, revision: session.revision });
    const refreshed = await reloadRepos(true);
    if (session === current && dialog.open) {
      if (name && refreshed) chooseRepository(session.prefix, name, true);
      if (!refreshed) {
        report($("repository-result"), "Change saved. Open the repository picker again to reload the list.", true);
        cancel.disabled = false;
        return;
      }
      dialog.close();
    }
    if (session.prefix !== "start") refreshRepositoryChoice("start");
  } catch (error) {
    if (session === current && dialog.open) {
      report($("repository-result"), error.message, true);
      save.disabled = remove.disabled = cancel.disabled = false;
    }
  } finally {
    session.saving = false;
    if (session === current && dialog.open) updateDismissal();
  }
}

function updateEditor() {
  updateHints();
  updateDismissal();
}

form.addEventListener("input", updateEditor);
form.addEventListener("change", updateEditor);
form.onsubmit = (event) => {
  event.preventDefault();
  const session = current;
  if (!session?.entry || save.disabled) return;
  const name = nameInput.value === session.original ? session.original : nameInput.value.trim();
  apply(session, name, draftEntry(session));
};
remove.onclick = async () => {
  const session = current;
  if (!session?.original || session.saving) return;
  const approved = await confirmAction({ title: "Remove this repository from the list?",
    body: "The entry for " + session.original + " will be removed. The repository, its files and its worktrees stay on disk.",
    confirm: "Remove from list", danger: true, returnTo: remove });
  if (approved) apply(session, null, null, true);
};
cancel.onclick = () => dialog.close();
dialog.addEventListener("cancel", (event) => { if (current?.saving) event.preventDefault(); });
dialog.addEventListener("close", () => {
  if (dialog.open) return;
  const returned = current?.returnTo;
  if (returned?.offsetParent) returned.focus();
  else if (current?.prefix) $(current.prefix + "-repo").focus();
  current = null;
});
$("repo-add").hidden = CONFIG.repositories_writable === false;
$("repo-add").onclick = () => openRepositoryEditor(closeRepositoryPicker());
