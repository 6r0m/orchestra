"""Append one agent event to a turn's events file. Called by the agents themselves, never by us.

    python turn_hook.py <events-file> UserPromptSubmit|Stop|StopFailure   (Claude hook: payload on stdin)
    python turn_hook.py <events-file> notify <payload>                    (Codex notify: payload as argument)

It always exits 0 and prints nothing, so it can never block, fail or steer the agent's turn.
"""
import json
import os
import sys


def main(args):
    try:
        events, kind = args[0], args[1]
        # The payload is UTF-8 whatever this process's locale would decode stdin as.
        payload = json.loads(args[-1]) if kind == "notify" else json.loads(sys.stdin.buffer.read().decode("utf-8"))
        payload["_hook"] = kind
        line = (json.dumps(payload) + "\n").encode("utf-8")
        # One write in append mode: concurrent hooks never interleave inside a line.
        fd = os.open(events, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
    except Exception:                               # noqa: BLE001 - a hook must never fail the agent
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
