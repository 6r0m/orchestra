#!/usr/bin/env bash
# The process mechanics of the Orchestra stack, one component at a time, for the stack owner
# (app/application/stack.py), which orders them and proves each outcome: `make up|down|check`, the
# command line and the Workbench all go through it. And the Workbench's own systemd user service,
# which only the Make targets manage — the Workbench never manages itself.
#   bash workers.sh temporal start|stop|status
#   bash workers.sh wsl|windows start|stop|status|sweep <name> [the pid a sweep knows is gone]
#   bash workers.sh workbench install|uninstall|start|stop|restart|status
# <name> is the worker's name on this machine (stack.worker_name): its pid file and log in
# tmp/orchestration, and its systemd scope. ORCH_POLICY, when set, is the policy the WSL worker runs.
# The Windows side is workers.ps1. Invoke through `bash`: the Windows drive mounts without execute bits.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME="$HERE/tmp/orchestration"
UNIT="orchestra-workbench.service"
COMPONENT="${1:-}" ACTION="${2:-}" NAME="${3:-}" GONE="${4:-}"
mkdir -p "$RUNTIME"

usage() {
    echo "usage: bash workers.sh temporal start|stop|status" >&2
    echo "       bash workers.sh wsl|windows start|stop|status|sweep <name> [pid]" >&2
    echo "       bash workers.sh workbench install|uninstall|start|stop|restart|status" >&2
    exit 2
}

environment() {
    # This checkout's uv-managed environment on this host (app/foundation/envpath.py).
    UV_PROJECT_ENVIRONMENT="$(uv run --no-project --managed-python --python 3.13 python "$HERE/app/foundation/envpath.py" "$HERE")"
    export UV_PROJECT_ENVIRONMENT
}

temporal() {
    local compose=(docker compose -f "$HERE/temporal/compose.yaml") running
    # The stack reads its own settings — the database password among them — from this checkout's .env.
    [ -f "$HERE/.env" ] && compose+=(--env-file "$HERE/.env")
    case "$ACTION" in
        start) "${compose[@]}" up -d ;;
        stop) "${compose[@]}" stop ;;
        status)
            running="$("${compose[@]}" ps --status running --services | tr '\n' ' ')"
            echo "${running:-none running}" ;;
        *) usage ;;
    esac
}

wsl_pid() {
    # The pid its file names while that process is still this worker: the file outlives a killed
    # worker, and pids are reused. A zombie's command line is empty.
    local file="$RUNTIME/$NAME.pid" pid
    [ -f "$file" ] || return 1
    pid="$(cat "$file")"
    tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null | grep -q -- "-m app.interfaces.worker wsl" || return 1
    echo "$pid"
}

wsl_worker() {
    local pid scope="orchestra-$NAME.scope"
    case "$ACTION" in
        status)
            if pid="$(wsl_pid)"; then echo "running $pid"; else echo "stopped"; fi ;;
        start)
            if pid="$(wsl_pid)"; then echo "running $pid"; return; fi
            environment
            uv --project "$HERE" sync --locked --quiet
            # In a systemd scope of its own: the Workbench's service, which may start it, takes every
            # process of its unit with it when it stops or restarts, and must never take a worker. One
            # temporary directory for the worker and for the sweep after it, whoever starts either.
            # Every stream redirected and the shell replaced: nothing holds this script's output open.
            (cd "$HERE" && TMPDIR=/tmp exec setsid nohup systemd-run --user --scope --quiet --collect --unit="$scope" \
                uv --project "$HERE" run --locked --no-sync python -m app.interfaces.worker wsl \
                >>"$RUNTIME/$NAME.log" 2>&1 </dev/null) >/dev/null 2>&1 </dev/null &
            echo "started; log: $RUNTIME/$NAME.log" ;;
        stop)
            if pid="$(wsl_pid)"; then
                # SIGINT lets it shut down — its activities cancelled, its turns' agents ended, its pid
                # file removed. One still there after 10 s is killed, and its reapers end its agents.
                kill -INT "$pid" 2>/dev/null || true
                for _ in $(seq 20); do wsl_pid >/dev/null || break; sleep 0.5; done
                if wsl_pid >/dev/null; then kill -KILL "$pid" 2>/dev/null || true; fi
                for _ in $(seq 10); do wsl_pid >/dev/null || break; sleep 0.5; done
                if pid="$(wsl_pid)"; then echo "still running $pid" >&2; exit 1; fi
            fi
            # Its scope ends once the reapers it left have ended its agents' scopes.
            for _ in $(seq 20); do systemctl --user is-active --quiet "$scope" || break; sleep 0.5; done
            if systemctl --user is-active --quiet "$scope"; then echo "its scope $scope still runs" >&2; exit 1; fi
            rm -f "$RUNTIME/$NAME.pid"
            echo "stopped" ;;
        sweep)
            environment
            cd "$HERE"
            # shellcheck disable=SC2086 # the pid, when there is one, is one more argument
            TMPDIR=/tmp uv --project "$HERE" run --locked --no-sync python -m app.interfaces.worker sweep $GONE ;;
        *) usage ;;
    esac
}

windows_worker() {
    # workers.ps1 through powershell.exe by its path: the Workbench's service has no Windows PATH.
    local powershell out code=0
    powershell="$(wslpath -u 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe')"
    # Into a file, never a pipe: a worker it starts would inherit the pipe and hold it open.
    out="$(mktemp "$RUNTIME/windows.XXXXXX")"
    "$powershell" -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w "$HERE/workers.ps1")" "$ACTION" "$NAME" \
        ${GONE:+"$GONE"} >"$out" 2>&1 </dev/null || code=$?
    tr -d '\r' <"$out"
    rm -f "$out"
    return "$code"
}

workbench_service() {
    local units="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
    case "$ACTION" in
        install)
            environment
            uv --project "$HERE" sync --locked --quiet
            mkdir -p "$units"
            # This checkout and its environment, which only this machine knows, are rendered in here.
            sed -e "s|@CHECKOUT@|$HERE|g" -e "s|@ENVIRONMENT@|$UV_PROJECT_ENVIRONMENT|g" \
                "$HERE/app/interfaces/workbench/$UNIT" >"$units/$UNIT"
            systemctl --user daemon-reload
            # The user manager, and the Workbench with it, outlives the last WSL terminal only while lingering is on.
            if [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != yes ]; then
                echo "warning: lingering is off for $USER, so the Workbench stops when your last WSL terminal" \
                     "closes; turn it on with: sudo loginctl enable-linger $USER" >&2
            fi
            systemctl --user enable "$UNIT"
            # Restarted, not only started: installing again is how this checkout's new code loads.
            systemctl --user restart "$UNIT"
            systemctl --user --no-pager --lines=0 status "$UNIT" ;;
        uninstall)
            systemctl --user disable --now "$UNIT" 2>/dev/null || true
            rm -f "$units/$UNIT"
            systemctl --user daemon-reload ;;
        start|stop|restart) systemctl --user "$ACTION" "$UNIT" ;;
        status) systemctl --user --no-pager status "$UNIT" ;;
        *) usage ;;
    esac
}

case "$COMPONENT" in
    temporal) temporal ;;
    wsl) [ -n "$NAME" ] || usage; wsl_worker ;;
    windows) [ -n "$NAME" ] || usage; windows_worker ;;
    workbench) workbench_service ;;
    *) usage ;;
esac
