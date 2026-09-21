# Main view

Orchestra's parts at its own level — one box per concern under `app/`, each linked to its own
architecture — and the participants outside it. Which process each part runs in is
[the processes view](processes.md); the stops a run can reach are [the stops view](stops.md).
Nothing inside a part is drawn here; that belongs to the part's own main view.

```mermaid
flowchart TD
    subgraph orchestra["Orchestra (app/)"]
        interfaces["interfaces<br/><i>cli · worker · workbench</i>"]
        application["application<br/><i>activities · client</i>"]
        orchestration["orchestration<br/><i>workflow · routing</i>"]
        agents["agents<br/><i>terminal · launch · nodes · trust</i>"]
        workspace["workspace<br/><i>repos · worktrees</i>"]
        observability["observability<br/><i>telemetry</i>"]
        foundation["foundation<br/><i>paths · envpath · policy · stages</i>"]
    end

    operator([operator]) -->|"a browser on 127.0.0.1, or a terminal"| interfaces
    interfaces -->|"the shared client"| application
    application -->|"an activity the workflow named"| orchestration
    application -->|"a role turn"| agents
    application -->|"the run's worktree"| workspace
    application -->|"trace rows for a run"| observability

    orchestration -->|"the stage contract"| foundation
    agents -->|"the stage's ask, and the policy"| foundation
    workspace -->|"the checkout root"| foundation
    observability -->|"the checkout root, and the policy"| foundation

    orchestration <-->|"workflow tasks, Updates, the status query"| temporal[("Temporal server")]
    application <-->|"start · answer · status"| temporal
    workspace -->|"the target host's git"| git[("the run's repository")]
    agents -->|"argv, a PTY, and the vendor's completion hook"| clis[("claude · codex")]
    observability -.->|"trace rows, never read back"| langfuse[("Langfuse")]
```

Every arrow between two parts inside the box is an import the boundary check enforces; the table
it enforces is in [structure.md](../structure.md#relationships-and-dependency-direction), and
`tests/test_architecture.py` fails on an import this picture does not show.

| part | its own architecture |
|---|---|
| foundation | [app/foundation](../../../app/foundation/docs/architecture/README.md) |
| orchestration | [app/orchestration](../../../app/orchestration/docs/architecture/README.md) |
| workspace | [app/workspace](../../../app/workspace/docs/architecture/README.md) |
| agents | [app/agents](../../../app/agents/docs/architecture/README.md) |
| observability | [app/observability](../../../app/observability/docs/architecture/README.md) |
| application | [app/application](../../../app/application/docs/architecture/README.md) |
| interfaces | [app/interfaces](../../../app/interfaces/docs/architecture/README.md) |
