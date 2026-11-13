// A typing aid for operator-authored instructions; selections never answer a stop or change the workflow.
import { api } from "./api.js";
import { $, el } from "./ui.js";

let generation = 0;
export async function pickSkills({ repo, run, input, stages = [] }) {
  const request = ++generation;
  const dialog = $("instruction-skills"), options = $("instruction-skills-options");
  const target = $("instruction-skills-stage"), search = $("instruction-skills-search");
  const status = $("instruction-skills-status"), add = $("instruction-skills-add");
  const selected = new Map();
  let rows = [], catalog;
  target.replaceChildren();
  for (const stage of ["This request", ...new Set(stages)]) {
    const option = el("option", stage.replace(":", " · "));
    option.value = stage;
    target.append(option);
  }
  const render = () => {
    options.replaceChildren();
    const role = target.value.split(":")[0], kind = catalog.roles[role];
    const kinds = kind ? [kind] : [...new Set(Object.values(catalog.roles))];
    const unique = new Map();
    for (const agent of kinds) for (const row of catalog.skills[agent] || []) {
      if (!unique.has(row.reference)) unique.set(row.reference, { ...row, agent });
    }
    rows = [...unique.values()];
    for (const row of rows.filter((row) => (row.name + " " + row.scope + " " + row.agent).toLowerCase().includes(search.value.toLowerCase()))) {
      const label = el("label", null, "skill-choice");
      const box = el("input");
      box.type = "checkbox";
      box.name = "skill_reference";
      box.value = row.reference;
      box.checked = selected.has(row.reference);
      box.onchange = () => { if (box.checked) selected.set(row.reference, row); else selected.delete(row.reference); };
      label.append(box, el("span", row.name + " · " + row.scope + " · " + row.agent));
      options.append(label);
    }
    const bound = catalog.stage_skills[target.value.split(":")[1]];
    status.textContent = rows.length + " available skills." + (bound ? " Stage default: " + bound + "." : "");
  };
  search.value = "";
  options.replaceChildren();
  status.textContent = "Reading repository and global skills on the execution host…";
  add.disabled = true;
  $("instruction-skills-cancel").onclick = () => dialog.close();
  dialog.showModal();
  try {
    if (!run && !repo) throw new Error("Choose a repository first.");
    catalog = await api("/api/skills?" + new URLSearchParams(run ? { run } : { repo }));
    if (!dialog.open || request !== generation) return;
    if (catalog.version !== 1) throw new Error("Reload the Workbench and target worker to use skill discovery.");
    search.oninput = render;
    target.onchange = () => { selected.clear(); render(); };
    render();
    add.disabled = false;
    add.onclick = () => {
      if (!dialog.open || request !== generation) return;
      if (!selected.size) { status.textContent = "Select at least one skill."; return; }
      const method = [...selected.values()].map((row) => "- " + row.name + ": " + row.reference.replaceAll("\\", "/")).join("\n");
      const when = target.value === "This request" ? "this request" : target.selectedOptions[0].textContent;
      input.value += (input.value.trim() ? "\n\n" : "") + "Use these skills for " + when + ". Read each SKILL.md and follow its applicable instructions within the current stage contract:\n" + method;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      dialog.close();
      input.focus();
    };
  } catch (error) {
    if (dialog.open && request === generation) status.textContent = "Skills unavailable: " + error.message + " Close and retry after the worker is available.";
  }
}
