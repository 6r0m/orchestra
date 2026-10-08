#!/usr/bin/env bash
# Invoke through `bash` — the Windows drive mounts with fmask=0133, so this
# file can never carry an execute bit from WSL.
# The suite runs in this checkout's own uv-managed environment, which lives on
# the host's own disk (app/foundation/envpath.py); `uv sync --locked` creates or updates it.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$HERE"
# Each test class in a process of its own, a few at a time (tests/runner.py); named tests — modules,
# classes or single tests, as unittest names them — run alone.
if git -C "$HERE" rev-parse --git-dir >/dev/null 2>&1; then
    UV_PROJECT_ENVIRONMENT="$(uv run --no-project --managed-python --python 3.13 python "$HERE/app/foundation/envpath.py" "$REPO")"
    export UV_PROJECT_ENVIRONMENT
    uv --project "$HERE" sync --locked --quiet
    cd "$HERE"
    exec uv --project "$HERE" run --locked --no-sync python -m tests --parallel "$@"
fi
# A checkout this host's git does not read is another host's: a run's worktree, made by that host's git
# and removed there with the environment that host built for it. One kept for it here would outlive it,
# so the tests run in an environment of their own, which goes when they end — however they end: a signal
# sent to this shell is handed on to them, and they are waited for.
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
export UV_PROJECT_ENVIRONMENT="$scratch/environment"
uv --project "$HERE" sync --locked --quiet
cd "$HERE"
uv --project "$HERE" run --locked --no-sync python -m tests --parallel "$@" &
tests=$!
trap 'kill -s TERM "$tests" 2>/dev/null || true' TERM INT HUP
code=0
wait "$tests" || code=$?
if kill -0 "$tests" 2>/dev/null; then
    wait "$tests" || code=$?
fi
exit "$code"
