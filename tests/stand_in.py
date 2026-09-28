"""A kind of agent that exists only in the suite, planted on the adapters' search path by the test that
uses it and gone when that test ends: no production file is edited and nothing is written into the
checkout, so a kind is proven to be its module alone.

Its name, `stand-in`, is not its program's, `stand-in-agent`, so a test can tell which of the two a caller
looked up. Its program is `fake_cli.py stand-in`: flags, a session and a turn-end signal of its own — the
payload on the sink's stdin, labelled `finished`.
"""
import importlib
import os
import shutil
import sys
import tempfile

KIND = "stand-in"
MODULE = "stand_in"
PROGRAM = "stand-in-agent"

SOURCE = '''\
"""The suite's own kind of agent."""
import json
import os

NAME = "Stand-in"
EXECUTABLE = "stand-in-agent"
ACCESS = ("read", "write")
OPTIONS = ("model",)
SKILL = "@{name}"
SESSION_MARKERS = ("STAND_IN_SESSION",)
SESSION_MARKER_PREFIXES = ("STAND_IN_TURN_",)
LOST_SESSION = ("no such thread",)
OLD_BRAIN = None


def validate(profile):
    # It takes a model, of any spelling: none of its values reach a shell.
    return [(key, "the stand-in takes a model, and nothing else") for key in profile if key not in ("kind",) + OPTIONS]


def command(role, resume_id, traced=None):
    argv = [EXECUTABLE, "--access", role["workspace_access"]]
    if role.get("model"):
        argv += ["--model", role["model"]]
    return argv + (["--thread", resume_id] if resume_id else []), None


def host(argv):
    return list(argv)


def session_in(argv):
    return argv[argv.index("--thread") + 1] if "--thread" in argv else None


def wire(argv, events, sink):
    return list(argv) + ["--on-finish", json.dumps(sink("finished", "stdin"))]


def completion(events, prompt, session):
    for event in events:
        if event.get("_hook") != "finished" or (event.get("prompt") or "").strip() != prompt.strip():
            continue
        if session and event.get("thread") != session:
            continue
        return True, event.get("answer") or "", event.get("thread")
    return None


def output(message, session):
    return json.dumps({"thread": session, "answer": message}) + "\\n"


def _field(out, key):
    for line in out.splitlines():
        try:
            return json.loads(line)[key]
        except (ValueError, KeyError, TypeError):
            continue
    return None


def session(out, minted):
    return _field(out, "thread") or minted


def final_message(out):
    return _field(out, "answer") or ""


def message_of(event):
    return event.get("answer") if isinstance(event, dict) else None


def skill_folders(name, repo):
    return [os.path.join(root, name) for root in skill_roots(repo)]

def skill_roots(repo):
    return [os.path.join(repo, ".stand-in", "skills")]
'''


def plant(test, modules=None):
    """Put `modules` — {module name: source}, the stand-in alone by default — on the adapters' search path
    for `test`, and take them off again when it ends. Returns the folder they are in."""
    from app.agents import adapters
    modules = {MODULE: SOURCE} if modules is None else modules
    folder = tempfile.mkdtemp(prefix="orchestra-kinds-")
    for name, source in modules.items():
        with open(os.path.join(folder, name + ".py"), "w", encoding="utf-8") as fh:
            fh.write(source)
    adapters.__path__.append(folder)
    importlib.invalidate_caches()

    def unplant():
        adapters.__path__.remove(folder)
        for name in modules:
            sys.modules.pop("%s.%s" % (adapters.__name__, name), None)
        shutil.rmtree(folder, ignore_errors=True)
        importlib.invalidate_caches()
    test.addCleanup(unplant)
    return folder


def variant(**changes):
    """The stand-in's source with some of its definitions replaced: {name: source of the new definition,
    or None to remove it}. Each is found as the line that starts it and the lines indented under it."""
    lines = SOURCE.splitlines(keepends=True)
    for name, replacement in changes.items():
        start = next(index for index, line in enumerate(lines)
                     if line.startswith(("def %s(" % name, "%s = " % name)))
        end = start + 1
        while end < len(lines) and (lines[end].startswith((" ", "\t")) or not lines[end].strip()):
            end += 1
        # Keep the blank lines that separate it from the next definition.
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        lines[start:end] = [] if replacement is None else [replacement.rstrip("\n") + "\n"]
    return "".join(lines)
