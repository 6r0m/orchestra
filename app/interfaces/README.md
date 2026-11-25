# interfaces

What a human or a process manager starts. Nothing imports this package.

| concern | owner |
|---|---|
| Command-line entry point | [cli.py](cli.py) |
| Worker entry point | [worker.py](worker.py) |
| Browser interface and service | [Workbench](workbench/README.md) |
| Interface architecture | [docs/README.md](docs/README.md) |

```bash
python -m app.interfaces.cli --name fix-helper "fix X in Y"
# Or: make feature NAME=fix-helper TASK="fix X in Y"
python -m app.interfaces.worker wsl | windows | sweep [pid ...]
python -m app.interfaces.workbench.server
```
