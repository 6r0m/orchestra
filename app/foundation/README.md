# foundation

The host and deployment facts every other package reads, and their validation.

| concern | owner |
|---|---|
| current architecture | [docs/architecture/README.md](docs/architecture/README.md) |

Nothing here starts a process. `app/foundation/envpath.py` is the one file run directly — `python app/foundation/envpath.py <checkout>` prints that checkout's environment path, and the shell wrappers call it before any environment exists.
