#!/usr/bin/env bash
# Start, check or stop what a run needs: the Temporal stack, the WSL and Windows workers, and the workbench.
#   bash workers.sh up | check | down
# Invoke through `bash`: the Windows drive mounts without execute bits. Each worker
# runs in its host's own uv-managed environment (app/foundation/envpath.py) and records its pid in
# tmp/orchestration/worker-<host>.pid; the Windows side is workers.ps1.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$HERE"
RUNTIME="$REPO/tmp/orchestration"
PID="$RUNTIME/worker-wsl.pid"
WORKBENCH_PORT="$(sed -n 's/.*"workbench_port": *\([0-9]*\).*/\1/p' "$HERE/policy.json")"
# One pid file per port: a workbench on another port is its own instance, and stopping this one
# must never stop that one.
WORKBENCH_PID="$RUNTIME/workbench-$WORKBENCH_PORT.pid"
WORKBENCH_URL="http://127.0.0.1:$WORKBENCH_PORT"
# The stack reads its own settings — the database password among them — from this checkout's .env.
COMPOSE_ENV=""
[ -f "$REPO/.env" ] && COMPOSE_ENV="--env-file $REPO/.env"
mkdir -p "$RUNTIME"

UV_PROJECT_ENVIRONMENT="$(uv run --no-project --managed-python --python 3.13 python "$HERE/app/foundation/envpath.py" "$REPO")"
export UV_PROJECT_ENVIRONMENT

windows() {
    # Into a file, never a pipe: the worker it starts inherits the pipe and would hold it open.
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w "$HERE/workers.ps1")" "$1" \
        >"$RUNTIME/workers-windows.out" 2>&1 </dev/null
    tr -d '\r' <"$RUNTIME/workers-windows.out"
}

wsl_alive() {
    [ -f "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null
}

workbench_alive() {
    [ -f "$WORKBENCH_PID" ] && kill -0 "$(cat "$WORKBENCH_PID")" 2>/dev/null
}

check() {
    (cd "$HERE" && uv --project "$HERE" run --locked --no-sync python -m app.interfaces.worker check) || return 1
    if workbench_alive && curl -fsS -o /dev/null "$WORKBENCH_URL/"; then
        echo "workbench              $WORKBENCH_URL"
    else
        echo "workbench              NOT SERVING"
        return 1
    fi
}

stop_pid() {
    # SIGINT lets the process shut down and remove its pid file; a worker does not end on SIGTERM.
    local file="$1" name="$2" pid
    pid="$(cat "$file")"
    kill -INT "$pid"
    for _ in $(seq 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
    kill -0 "$pid" 2>/dev/null && kill -KILL "$pid"
    rm -f "$file"
    echo "$name stopped"
}

case "${1:-}" in
    up)
        docker compose $COMPOSE_ENV -f "$HERE/temporal/compose.yaml" up -d
        uv --project "$HERE" sync --locked --quiet
        if wsl_alive; then
            echo "wsl worker already running (pid $(cat "$PID"))"
        else
            # Every stream redirected and the shell replaced: nothing is left holding this script's output open.
            (cd "$HERE" && exec setsid nohup uv --project "$HERE" run --locked --no-sync python -m app.interfaces.worker wsl \
                >>"$RUNTIME/worker-wsl.log" 2>&1 </dev/null) >/dev/null 2>&1 </dev/null &
            echo "wsl worker started; log: $RUNTIME/worker-wsl.log"
        fi
        windows up
        if workbench_alive; then
            echo "workbench already running (pid $(cat "$WORKBENCH_PID"))"
        else
            (cd "$HERE" && exec setsid nohup uv --project "$HERE" run --locked --no-sync python -m app.interfaces.workbench.server \
                >>"$RUNTIME/workbench.log" 2>&1 </dev/null) >/dev/null 2>&1 </dev/null &
            echo "workbench started; log: $RUNTIME/workbench.log"
        fi
        # Workers take a few seconds to connect and poll; the workbench records its pid once it serves.
        for _ in $(seq 30); do
            check >/dev/null 2>&1 && break
            sleep 2
        done
        check
        ;;
    check)
        check
        ;;
    down)
        if workbench_alive; then
            stop_pid "$WORKBENCH_PID" "workbench"
        fi
        if wsl_alive; then
            stop_pid "$PID" "wsl worker"
        fi
        windows down
        docker compose $COMPOSE_ENV -f "$HERE/temporal/compose.yaml" stop
        ;;
    *)
        echo "usage: bash workers.sh up|check|down" >&2
        exit 2
        ;;
esac
