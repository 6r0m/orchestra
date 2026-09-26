// The repositories of repos.json, each list a menu of their owners: a name that carries its owners —
// `work/platform/service` — is found under `work`, then `platform`, each opening to the right as it is
// hovered or reached with Tab. A list stays the <select> its form reads, behind the button that opens it.

import { api } from "./api.js";
import { $, el } from "./ui.js";

const LISTS = ["start-repo", "worktrees-repo"];
// The repositories as last shown, so an unchanged answer leaves an open menu as it is.
let shownRepos = "";

function repoTree(listed) {
  const root = { owners: new Map(), repos: [] };
  for (const repo of listed) {
    let node = root;
    for (const owner of repo.id.split("/").slice(0, -1)) {
      if (!node.owners.has(owner)) node.owners.set(owner, { owners: new Map(), repos: [] });
      node = node.owners.get(owner);
    }
    node.repos.push(repo);
  }
  return root;
}

function repoMenu(node, choose) {
  const list = el("ul", null, "menu");
  for (const [name, owned] of node.owners) {
    const item = el("li", null, "owner");
    const button = el("button", name);
    button.type = "button";
    item.append(button, repoMenu(owned, choose));
    list.appendChild(item);
  }
  for (const repo of node.repos) {
    const button = el("button", repo.id.split("/").pop() + " (" + repo.target + ")");
    button.type = "button";
    button.translate = false;
    button.onclick = () => choose(repo.id);
    const item = el("li");
    item.appendChild(button);
    list.appendChild(item);
  }
  return list;
}

function picker(select) {
  if (select.nextElementSibling && select.nextElementSibling.classList.contains("picker")) {
    return select.nextElementSibling;
  }
  const box = el("div", null, "picker");
  const button = el("button", "none", "picker-button");
  button.type = "button";
  // Opening reads repos.json again, so an entry added to it shows without reloading the page.
  button.onclick = () => {
    const menu = box.querySelector(".menu");
    menu.hidden = !menu.hidden;
    if (!menu.hidden) reloadRepos();
  };
  box.onkeydown = (event) => {
    if (event.key !== "Escape") return;
    box.querySelector(".menu").hidden = true;
    button.focus();
  };
  box.append(button, el("ul", null, "menu"));
  box.lastChild.hidden = true;
  select.hidden = true;
  select.after(box);
  return box;
}

export function setRepo(select, id) {
  select.value = id;
  const chosen = select.selectedOptions[0];
  const button = picker(select).querySelector(".picker-button");
  button.textContent = chosen ? chosen.textContent : "none";
  button.setAttribute("aria-label", "Repository: " + button.textContent);
}

// A repository comes from one of two places, `<prefix>-repo` or `<prefix>-path`: only the one chosen is
// shown, and only it is read — the returned function says which repository is chosen now.
export function sourceChoice(prefix) {
  const box = $(prefix + "-source");
  const byPath = () => box.querySelector("input[name='" + prefix + "-source']:checked").value === "path";
  const shown = () => {
    box.querySelector(".source-listed").hidden = byPath();
    box.querySelector(".source-path").hidden = !byPath();
    $(prefix + "-path").required = byPath();
  };
  for (const radio of box.querySelectorAll("input[name='" + prefix + "-source']")) radio.onchange = shown;
  shown();
  // None when nothing is chosen: an empty repository would read as none, which the server takes as its
  // own checkout.
  return () => (byPath() ? $(prefix + "-path").value.trim() : $(prefix + "-repo").value) || null;
}

// Chooses the listed repository `id`.
export function chooseListed(prefix, id) {
  const listed = $(prefix + "-source").querySelector("input[value='listed']");
  listed.checked = true;
  listed.onchange();
  setRepo($(prefix + "-repo"), id);
}

async function loadRepos() {
  const listed = await api("/api/repos");
  const shown = JSON.stringify(listed);
  if (shown === shownRepos) return;
  shownRepos = shown;
  const tree = repoTree(listed);
  for (const id of LISTS) {
    const select = $(id);
    const chosen = select.value;
    select.replaceChildren(...listed.map((repo) => {
      const option = el("option", repo.id + " (" + repo.target + ")");
      option.value = repo.id;
      return option;
    }));
    const box = picker(select);
    const menu = repoMenu(tree, (repo) => {
      setRepo(select, repo);
      box.querySelector(".menu").hidden = true;
      select.dispatchEvent(new Event("change"));
    });
    if (!listed.length) menu.appendChild(el("li", "None in repos.json: choose A path", "muted"));
    const open = box.querySelector(".menu");
    menu.hidden = open.hidden;
    open.replaceWith(menu);
    setRepo(select, listed.some((repo) => repo.id === chosen) ? chosen : select.value);
  }
}

export const reloadRepos = () => {
  const reading = loadRepos().catch((error) => { $("start-result").textContent = error.message; });
  firstRead = firstRead || reading;
  return reading;
};
// The repositories' first read: a view the URL opens on a repository waits for it before choosing one.
let firstRead = null;
export const reposRead = () => firstRead || reloadRepos();

// A click anywhere but in a repository menu closes it.
document.addEventListener("click", (event) => {
  for (const menu of document.querySelectorAll(".picker > .menu")) {
    if (!menu.parentElement.contains(event.target)) menu.hidden = true;
  }
});
