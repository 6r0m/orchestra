# orchestration

The run itself: its stages, the routes between them, the stops it waits at and the final gate.

| concern | owner |
|---|---|
| current architecture | [docs/architecture/README.md](docs/architecture/README.md) |

Nothing here is started directly. Temporal runs `workflow.FeatureRun`; the worker that registers it is [interfaces](../interfaces/README.md).
