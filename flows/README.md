# Flows

The order a run's stages take, one file per flow, named for it. A run starts on one — the
Workbench's Flow list, `--flow` on the command line, or `default_flow` in `policy.json` when none is
named — and keeps its steps whatever this folder says afterwards. Each step is `role:action`; the
actions, and the rules a flow keeps, are [the architecture's D13](../docs/architecture/structure.md),
and a flow that breaks one is refused with the rule it broke. A flow's name is its file's without
`.json`: letters, digits, `.`, `_` and `-`, starting with a letter or a digit.

| flow | file |
|---|---|
| the engineer starts, from the code: plan, assessment, your approval, build, verification, the merge | [engineer-code.json](engineer-code.json) |
| the architect starts, researching: its brief, your approval, then as `engineer-code` | [architect-research.json](architect-research.json) |
