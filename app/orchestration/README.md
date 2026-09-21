# orchestration

The run itself: its stages, the routes between them, the stops it waits at and the final gate.

| concern | owner |
|---|---|
| durable documentation: the architecture, its structure and its views | [docs/README.md](docs/README.md) |

Nothing here is started directly. Temporal runs `workflow.FeatureRun`; the worker that registers it is [interfaces](../interfaces/README.md).
