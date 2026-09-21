# application

Where the concerns are composed into the things a run actually does.

| concern | owner |
|---|---|
| current architecture | [docs/architecture/README.md](docs/architecture/README.md) |

Nothing here is started directly. The worker in [interfaces](../interfaces/README.md) registers the activities; the command line and the page both drive runs through `client`.
