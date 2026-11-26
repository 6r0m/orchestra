# Flows

The order a run's stages take, one file per flow, named for it. A run starts on one — the
Workbench's Flow list, `--flow` on the command line, or `default_flow` in
`.orchestra/settings.json` when none is named — and keeps its steps whatever this folder says
afterwards. Each step is `role:action`; the
actions, and the rules a flow keeps, are [the architecture's D13](../docs/architecture/structure.md),
and a flow that breaks one is refused with the rule it broke. A flow's name is its file's without
`.json`: letters, digits, `.`, `_` and `-`, starting with a letter or a digit.

| flow | file |
|---|---|
| the architect writes a planning brief, then the engineer plans and the roles continue after reviews pass. You decide whether to merge | [architect-plan.json](architect-plan.json) |
| the engineer plans from the code. You approve the assessed plan before the build | [engineer-plan.json](engineer-plan.json) |
| the architect starts with a brief. You approve the brief and the assessed implementation plan | [architect-research.json](architect-research.json) |

Saved settings and CLI commands may still use the former names `architect-auto` and `engineer-code`.
If their original files are absent, they resolve to `architect-plan` and `engineer-plan` respectively.

A flow that builds closes out before its merge: one without `engineer:closeout` is listed as broken
and starts no run. Only the runs started before closeouts follow such steps, to their end.
