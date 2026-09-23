# interfaces

What a human or a process manager starts. Nothing imports this package.

| concern | owner |
|---|---|
| durable documentation: the architecture, its structure and its views | [docs/README.md](docs/README.md) |

```bash
python -m app.interfaces.cli "fix X in Y"        # or: make feature TASK="fix X in Y"
python -m app.interfaces.worker wsl | windows | sweep [pid ...]
python -m app.interfaces.workbench.server
```

`workers.sh` and `workers.ps1` start a worker as a module from the checkout, and so does the Workbench's systemd unit, [orchestra-workbench.service](workbench/orchestra-workbench.service), which `make workbench-install` renders for this checkout: the checkout is what puts `app` on the path.
