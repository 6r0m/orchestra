# interfaces

What a human or a process manager starts. Nothing imports this package.

| concern | owner |
|---|---|
| current architecture | [docs/architecture/README.md](docs/architecture/README.md) |

```bash
python -m app.interfaces.cli "fix X in Y"        # or: make feature TASK="fix X in Y"
python -m app.interfaces.worker wsl | windows | check
python -m app.interfaces.workbench.server
```

`workers.sh` and `workers.ps1` start the worker and the page as modules from the checkout, which is what puts `app` on the path.
