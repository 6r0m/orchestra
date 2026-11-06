"""Append one agent event to a turn's events file. Called by the agents themselves, never by us.

    python app/agents/turn_hook.py <events-file> <label> stdin               (the payload on stdin)
    python app/agents/turn_hook.py <events-file> <label> argument <payload>  (the payload its last argument)

The label is recorded with the payload, as `_hook`: which of an agent's events it was. Where the payload
comes from is the agent's own way of calling a program, which its kind's adapter wires. An events file given as
`-` is the one `ORCHESTRA_TURN_EVENTS` names in the environment the agent passes on.

It always exits 0 and prints nothing, so it can never block, fail or steer the agent's turn.
"""
import json
import os
import sys
import time


def main(args):
    try:
        # `-`: the turn's file as its environment names it, so one hook definition serves every turn.
        events, label, source = os.environ["ORCHESTRA_TURN_EVENTS"] if args[0] == "-" else args[0], args[1], args[2]
        # The payload is UTF-8 whatever this process's locale would decode stdin as.
        payload = json.loads(args[-1]) if source == "argument" else json.loads(sys.stdin.buffer.read().decode("utf-8"))
        # What a dialog says and what a tool read or wrote stay out of the record: only its session and a
        # notification's kind are kept.
        if label in ("Notification", "PostToolUse", "PostToolUseFailure"):
            payload = {key: payload[key] for key in ("session_id", "notification_type") if key in payload}
        # When it was recorded, as `_at`: two roles' answers are told apart by when each came, never by when
        # their records last changed — a record gains events that answer no one.
        payload["_hook"], payload["_at"] = label, time.time()
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
