# foundation

The contract every other package reads: where this checkout and its environments are, the validated policy, and the stages of a run.

| concern | owner |
|---|---|
| durable documentation: the architecture, its structure and its views | [docs/README.md](docs/README.md) |

Nothing here starts a process. `app/foundation/envpath.py` is the one file run directly — `python app/foundation/envpath.py <checkout>` prints that checkout's environment path, and the shell wrappers call it before any environment exists.
