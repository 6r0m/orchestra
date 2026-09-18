#!/usr/bin/env bash
# Invoke through `bash` — the Windows drive mounts with fmask=0133, so this
# file can never carry an execute bit from WSL.
# The suite runs in this checkout's own uv-managed environment, which lives on
# the host's own disk (app/foundation/envpath.py); `uv sync --locked` creates or updates it.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$HERE"
UV_PROJECT_ENVIRONMENT="$(uv run --no-project --managed-python --python 3.13 python "$HERE/app/foundation/envpath.py" "$REPO")"
export UV_PROJECT_ENVIRONMENT
uv --project "$HERE" sync --locked --quiet
cd "$HERE"
exec uv --project "$HERE" run --locked --no-sync python -m unittest discover -s tests -p "test_*.py" -t . "$@"
