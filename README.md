# Orchestra

**Automate software engineering without manually coordinating agents or losing control of the process.**

Orchestra is a local-first workbench for running coding agents through configurable, durable and independently reviewed engineering workflows.

Give it a task. An engineer plans and implements the change in a dedicated Git worktree, and an
architect reviews the plan and implementation in a separate session. The stages, review budgets and
approval gates you choose govern how the work progresses.

From one Workbench, follow both agents in their native terminals and inspect their decisions and
changes. Pause a turn to give guidance, request revisions, continue a failed step or approve the merge.

Temporal preserves workflow progress and decisions across interruptions. Orchestra manages Git
integration. Claude Code, Codex and Pi retain their native sessions across turns.

The supported setup is **Windows with WSL 2 and systemd**. The first-run guide covers Docker Compose,
uv and the agent CLI on the host that runs the task.

[Set up your first run](docs/using.md#first-run) · [Use the Workbench](docs/using.md#the-page) ·
[Read the trust model](docs/architecture/structure.md#risks-and-technical-debt)

The default [`architect-plan`](flows/architect-plan.json) flow starts with an architect brief. The
engineer drafts a plan for the architect to assess. When the plan passes, implementation starts
automatically. After verification and closeout, you decide whether to merge.

| Find | Go to |
|---|---|
| Setup, daily operation and troubleshooting | [Documentation](docs/README.md) |
| Production components and their owners | [Source](app/README.md) |
| How to contribute, test and verify a change | [Contributing](CONTRIBUTING.md) |
| Development and acceptance checks | [Tests](tests/README.md) |
| Local demo and repository checks | [Tools](tools/README.md) |
| Work in progress | [Todo](todo/README.md) |

## Configuration

- [Policy and first-run settings](docs/using.md#first-run)
- [Optional team skills](docs/using.md#optional-team-skills)
- [Repository descriptor example](.orchestra/repos.example.json)
- [Role definitions](roles/README.md)
- [Workflow definitions](flows/README.md)

## License

Orchestra is [MIT licensed](LICENSE). Third-party notice files accompany the
[Workbench's vendored assets](app/interfaces/workbench/static/vendor/).
