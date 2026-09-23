# application

Where the concerns are composed into the things a run actually does.

| concern | owner |
|---|---|
| durable documentation: the architecture, its structure and its views | [docs/README.md](docs/README.md) |

Nothing here is started directly. The worker in [interfaces](../interfaces/README.md) registers the activities; the command line and the page both drive runs through `client`, and the stack through `stack`.
