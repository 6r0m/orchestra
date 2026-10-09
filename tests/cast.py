"""A scripted scenario's cast: who plays each role, named by the profile the settings define.

The settings own what a profile is — its kind, its model and its effort — and which profile each role
runs by default. A scenario's scripted turns speak one kind's contract, so it says who plays it, by a
profile's name, and takes everything else from the settings: it names no model and no effort of its own,
and a default bound to another profile changes no scenario.
"""
import atexit
import json
import os
import shutil
import tempfile

from app.application import settings as S

# The scripted turns speak Claude's engineer contract and Codex's review contract.
ROLES = {"engineer": "claude-engineer", "architect": "codex-architect"}
_files = {}


def settings(**roles):
    """The shipped settings, each role run by the profile named for it here — this cast's where none is."""
    made = json.loads(json.dumps(S.load()))
    for role, profile in dict(ROLES, **roles).items():
        if profile not in made["agents"]:
            raise AssertionError("the settings define no profile %r for the %s to run" % (profile, role))
        made["roles"][role]["agent"] = profile
    S.check(made)
    return made


def policy(**roles):
    """The policy a run started on that cast is handed."""
    return S.run_policy(settings(**roles))


def file(**roles):
    """That cast as a settings file, for an entry point that loads its settings itself: the client's start,
    a Workbench, the command line. One file per cast in a process, removed when the process ends."""
    key = tuple(sorted(dict(ROLES, **roles).items()))
    if key not in _files:
        if not _files:
            folder = tempfile.mkdtemp(prefix="orchestra-cast-")
            atexit.register(shutil.rmtree, folder, True)
            _files[None] = folder
        path = os.path.join(_files[None], "settings-%d.json" % len(_files))
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({name: value for name, value in settings(**roles).items() if not name.startswith("_")}, fh)
        _files[key] = path
    return _files[key]
