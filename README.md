# Orchestra

**A local workbench for running and reviewing changes made by coding agents.**

Give an engineer a task, let an architect review its plan and implementation, and decide what lands.
Watch the agents in their own terminals and inspect the change at the final gate. Orchestra uses the
native Claude Code, Codex and Pi CLIs and records the run in Temporal.

```text
Engineer plans → Architect reviews → You approve
Engineer builds → Architect verifies → Engineer closes out → You decide whether to merge
```

[Set up your first run](docs/using.md#first-run) · [Use the Workbench](docs/using.md#the-page) ·
[Read the trust model](docs/architecture/structure.md#risks-and-technical-debt)

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
