// The repository dialog shared by New run and Worktrees. Each form keeps its own choice and path draft.

import { api } from "./api.js";
import { $, el, showReading } from "./ui.js";

const dialog = $("repo-picker");
const search = $("repo-search");
const results = $("repo-results");
const fields = new Map();
let listed = [];
let loaded = false;
let reading = null;
let active = null;
let focusBack = null;

function platform(target) {
  const badge = el("span", target === "windows" ? "Windows" : "WSL", "repo-platform");
  badge.dataset.target = target;
  return badge;
}

function showChoice(field) {
  const choice = field.recorded || (field.pathField.hidden && listed.find((repo) => repo.id === field.id));
  const label = choice?.id || (field.pathField.hidden ? "Choose a repository" : "Repository path");
  const text = el("span", label, "repo-label");
  text.translate = !choice || !field.pathField.hidden;
  field.button.replaceChildren(text);
  if (choice?.target) field.button.append(platform(choice.target));
}

function tell(field) {
  field.source.dispatchEvent(new Event("change", { bubbles: true }));
}

export const refreshRepositoryChoice = (prefix) => tell(fields.get(prefix));

export function sourceChoice(prefix) {
  const field = { prefix, source: $(prefix + "-source"), button: $(prefix + "-repo"), path: $(prefix + "-path"),
    pathField: $(prefix + "-path-field"), id: null };
  fields.set(prefix, field);
  field.button.onclick = () => {
    active = field;
    focusBack = field.button;
    search.value = "";
    render();
    dialog.showModal();
    search.focus();
    reloadRepos();
  };
  return () => field.pathField.hidden ? field.id : field.path.value.trim() || null;
}

export const isRepositoryPath = (prefix) => !fields.get(prefix).pathField.hidden;
export const isSavedRepository = (prefix) => {
  const field = fields.get(prefix);
  return !field.recorded && field.pathField.hidden && !!field.id;
};

export function showRecordedRepository(prefix, id, target) {
  const field = fields.get(prefix);
  const hidden = field.recorded?.hidden ?? field.pathField.hidden;
  field.recorded = { id, target, hidden };
  field.pathField.hidden = true;
  field.path.required = false;
  showChoice(field);
}

export function clearRecordedRepository(prefix) {
  const field = fields.get(prefix);
  if (!field.recorded) return;
  field.pathField.hidden = field.recorded.hidden;
  field.path.required = !field.pathField.hidden;
  field.recorded = null;
  showChoice(field);
}

function setPath(field, path) {
  field.recorded = null;
  field.pathField.hidden = false;
  field.path.required = true;
  if (path !== undefined) field.path.value = path;
  showChoice(field);
}

function setListed(field, id) {
  field.recorded = null;
  field.id = id;
  field.pathField.hidden = true;
  field.path.required = false;
  showChoice(field);
}

export function chooseRepository(prefix, repo, notify = false) {
  const field = fields.get(prefix);
  if (listed.some((choice) => choice.id === repo)) setListed(field, repo);
  else setPath(field, repo);
  if (notify) tell(field);
}

export function closeRepositoryPicker() {
  const prefix = active?.prefix;
  dialog.close();
  return prefix;
}

function render() {
  const focused = results.contains(document.activeElement) ? document.activeElement.title : null;
  const term = search.value.trim().toLowerCase();
  const groups = new Map();
  for (const repo of listed) {
    const split = repo.id.lastIndexOf("/");
    const group = split < 0 ? "" : repo.id.slice(0, split);
    if (!groups.has(group)) groups.set(group, []);
    if (repo.id.toLowerCase().includes(term)) groups.get(group).push(repo);
  }
  results.replaceChildren();
  let index = 0;
  for (const [group, repos] of groups) {
    const position = index++;
    if (!repos.length) continue;
    const section = el("div", null, "repo-group");
    if (group) {
      const title = el("h3", group);
      title.id = "repo-group-" + position;
      title.dataset.accent = position % 3;
      title.translate = false;
      section.setAttribute("role", "group");
      section.setAttribute("aria-labelledby", title.id);
      section.append(title);
    }
    for (const repo of repos) {
      const label = el("span", repo.id.slice(group ? group.length + 1 : 0), "repo-label");
      label.translate = false;
      const option = el("button", null, "repo-choice");
      option.type = "button";
      option.title = repo.id;
      option.setAttribute("aria-label", repo.id + (repo.target === "windows" ? " (Windows)" : " (WSL)"));
      if (active && isSavedRepository(active.prefix) && active.id === repo.id) option.setAttribute("aria-current", "true");
      option.onclick = () => {
        const field = active;
        setListed(field, repo.id);
        dialog.close();
        tell(field);
      };
      option.append(label, platform(repo.target));
      section.append(option);
    }
    results.append(section);
  }
  if (!results.children.length && loaded) results.append(el("p", term ? "No matching repositories." : "No saved repositories.", "hint"));
  if (focused) ([...results.querySelectorAll("button")].find((option) => option.title === focused) || search).focus();
}

search.addEventListener("input", render);
dialog.addEventListener("keydown", (event) => {
  if (!["ArrowUp", "ArrowDown"].includes(event.key)) return;
  const options = [...results.querySelectorAll("button"), ...dialog.querySelectorAll("footer button:not([hidden])")];
  const position = options.indexOf(document.activeElement);
  if (position < 0 && document.activeElement !== search) return;
  event.preventDefault();
  if (event.key === "ArrowUp" && position <= 0) search.focus();
  else options[Math.min(position + (event.key === "ArrowUp" ? -1 : 1), options.length - 1)].focus();
});
$("repo-enter-path").onclick = () => {
  const field = active;
  setPath(field);
  focusBack = field.path;
  dialog.close();
  tell(field);
};
$("repo-picker-close").onclick = () => dialog.close();
dialog.addEventListener("close", () => {
  if (dialog.open) return;
  if (focusBack?.offsetParent) focusBack.focus();
  active = null;
  focusBack = null;
});

async function loadRepos() {
  const notice = $("repo-picker-status");
  notice.textContent = loaded ? "" : "Reading saved repositories…";
  showReading("repo-picker-reading", !loaded);
  try {
    const next = await api("/api/repos");
    if (loaded && JSON.stringify(next) === JSON.stringify(listed)) return true;
    listed = next;
    for (const field of fields.values()) {
      if (!loaded) field.id = listed[0]?.id || null;
      const removed = field.id && !listed.some((repo) => repo.id === field.id);
      if (removed) field.id = null;
      showChoice(field);
      if (removed && !field.recorded && field.pathField.hidden) tell(field);
    }
    loaded = true;
    if (dialog.open) render();
    notice.textContent = "";
    return true;
  } catch (error) {
    notice.textContent = "Saved repositories unavailable. " + error.message;
    return false;
  } finally {
    showReading("repo-picker-reading", false);
  }
}

export async function reloadRepos(fresh = false) {
  if (fresh && reading) await reading;
  reading ||= loadRepos().finally(() => { reading = null; });
  return reading;
}

export const reposRead = () => loaded ? Promise.resolve() : reloadRepos();
