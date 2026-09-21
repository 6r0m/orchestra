"""Record the event histories the replay guard replays.

Rerun only when the workflow changes on purpose, and then behind `workflow.patched`,
so the histories recorded before the change still replay:
`python tests/record_histories.py [name ...]` — the named histories only, every one when none is
named. A new history is recorded by its name alone, so the ones older code wrote stay as they were.
"""
import base64
import json
import os
import re
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

import temporal_env as E  # noqa: E402
from fakes import FakeWorktrees, codex_review_first, codex_review_resumed  # noqa: E402

HISTORIES = os.path.join(HERE, "histories")
# Temporal stamps every event with the worker that wrote it — `<pid>@<hostname>`. These files are
# published, so the machine that recorded them is replaced by a fixed name; replay does not read it.
RECORDER = "recorder@orchestra"
# The same for where the recording ran: a checkout path and a home directory name the person who
# recorded it. They reach the history as activity inputs and results — some of them base64 — and as
# the file names in a failure's stack trace. Replay does not read them either; it compares the
# commands the workflow issues, and every occurrence is replaced consistently.
NEUTRAL = ((PKG, "/orchestra"), (os.path.expanduser("~"), "/home/user"))


def neutral(text):
    """`text` with every path of the recording machine replaced, inside base64 payloads as well."""
    for real, fixed in NEUTRAL:
        text = text.replace(real, fixed)

    def payload(match):
        blob = match.group(1)
        try:
            decoded = base64.b64decode(blob, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return match.group(0)
        clean = decoded
        for real, fixed in NEUTRAL:
            clean = clean.replace(real, fixed)
        if clean == decoded:
            return match.group(0)
        return '"data": "%s"' % base64.b64encode(clean.encode("utf-8")).decode()

    return re.sub(r'"data": "([A-Za-z0-9+/=]+)"', payload, text)


def anonymous(text):
    """The history with no trace of the machine that recorded it."""
    history = json.loads(text)
    replaced = 0

    def walk(node):
        nonlocal replaced
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "identity" and isinstance(value, str) and value:
                    node[key] = RECORDER
                    replaced += 1
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(history)
    return json.dumps(history, indent=2, sort_keys=True) + "\n", replaced


def save(name, run):
    history = E.run(run.handle.fetch_history())
    text, replaced = anonymous(history.to_json())
    text = neutral(text)
    with open(os.path.join(HISTORIES, name + ".json"), "w", encoding="utf-8") as fh:
        fh.write(text)
    run.cleanup()
    print("recorded %s: %d events, %d identities replaced" % (name, len(history.events), replaced))


def patch_loop_approval_merge():
    a1, _ = codex_review_first("PATCH", "fix A")
    E.host([("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, a1),
            ("plan-e1-2", 0, "p2\n"), ("assess-e1-2", 0, codex_review_resumed("PASS", "Direction: A.")),
            ("build-e2-1", 0, "b\n"), ("verify-e2-1", 0, codex_review_resumed("PASS"))])
    run = E.Run()
    run.answer("yes")
    run.answer("merge")
    return run


def blocker_guidance_failure_continue_discard():
    b1, _ = codex_review_first("BLOCKER", "premise wrong")
    E.host([("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, b1),
            ("plan-e2-1", 1, "usage limit\n"), ("plan-e2-1", 0, "p2\n"),
            ("assess-e2-1", 0, codex_review_resumed("PASS")),
            ("build-e3-1", 0, "b\n"), ("verify-e3-1", 0, codex_review_resumed("PASS"))])
    run = E.Run()
    run.answer("use approach B")
    run.answer("continue")
    run.answer("yes")
    run.answer("discard", confirm=True)
    return run


def final_revise_conflict_merge():
    a1, _ = codex_review_first("PASS")
    E.host([("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, a1),
            ("build-e2-1", 0, "b\n"), ("verify-e2-1", 0, codex_review_resumed("PASS")),
            ("verify-e3-1", 0, codex_review_resumed("PASS")),
            ("build-e4-1", 0, "resolved\n"), ("verify-e4-1", 0, codex_review_resumed("PASS"))],
           git=FakeWorktrees([{"result": "conflict", "files": ["app.txt"]}, {"result": "merged", "commit": "c1"}]))
    run = E.Run(auto=True)
    run.answer("revise architect re-check the error path")
    run.answer("merge")
    run.answer("merge")
    return run


def approval_stop():
    a1, _ = codex_review_first("PASS")
    E.host([("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, a1)])
    run = E.Run()
    E.run(run.handle.cancel())
    E.run(E.cli.follow(run.handle, answered=run.stop["id"]))
    return run


def final_merge_stop_lands():
    """A Stop while the merge runs: the run shows it, waits for the merge, and ends merged."""
    merging, land = threading.Event(), threading.Event()

    class Held(FakeWorktrees):
        def merge(self, *args):
            merging.set()
            land.wait(60)
            return super().merge(*args)
    a1, _ = codex_review_first("PASS")
    E.host([("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, a1),
            ("build-e2-1", 0, "b\n"), ("verify-e2-1", 0, codex_review_resumed("PASS"))], git=Held())
    run = E.Run(auto=True)
    E.run(E.cli.runs.answer(E.client(), run.run_id, {"stop": run.stop["id"], "action": "merge"}, check=False))
    merging.wait(30)
    E.run(run.handle.cancel())
    while E.run(run.handle.query("status"))["state"]["status"] != "STOPPING":
        time.sleep(0.2)
    land.set()
    E.run(E.cli.follow(run.handle, answered=run.stop["id"]))
    return run


RECORDINGS = (patch_loop_approval_merge, blocker_guidance_failure_continue_discard, final_revise_conflict_merge,
              approval_stop, final_merge_stop_lands)


def main(names):
    os.makedirs(HISTORIES, exist_ok=True)
    known = {record.__name__: record for record in RECORDINGS}
    unknown = [name for name in names if name not in known]
    if unknown:
        sys.exit("no such history: %s (known: %s)" % (", ".join(unknown), ", ".join(known)))
    for name in names or known:
        save(name, known[name]())


if __name__ == "__main__":
    main(sys.argv[1:])
