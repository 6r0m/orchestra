"""Kinds of agent, one module each, behind one contract — and the loader that finds them.

A kind is the agent system a role runs: its CLI, how a turn of it starts, ends and resumes, how it
runs read-only, how it takes a skill, what its sessions leave in an environment, and — for the kinds
that have them — its trust records and its tracing. Everything that differs between agents lives in
its kind's module and nowhere else; every other module takes a kind as data and asks its module.

A kind's module is named from the kind by one rule: the settings' grammar for a kind's name
(`app.foundation.policy.NAME`), each hyphen an underscore — `claude-code` is `claude_code.py`. Nothing
lists the kinds: `available()` finds them among this package's public modules, so a new kind is its
module alone.

What a kind's module holds, each named below by what it answers:

- `NAME`: how the page shows it. `EXECUTABLE`: the one program its turn runs, which its launch
  starts and a run's preparation looks for.
- `ACCESS`: the access it can run with, of `read` and `write`. `OPTIONS`: the settings a profile of
  it takes beyond its kind. `SKILL`: how a stage's skill leads its prompt, `{name}` in it, or None.
- `SESSION_MARKERS`, `SESSION_MARKER_PREFIXES`: the variables a session of its vendor leaves in an
  environment, which no agent of any kind inherits. `LOST_SESSION`: how its output says the session
  it was to resume is gone. `OLD_BRAIN`: the name the old shape of a run's policy gave it.
- `validate(profile)`: what is wrong with a profile's own settings, as (key, reason) pairs.
- `command(role, resume_id, traced)`: its interactive CLI for one turn, and the session it minted.
- `host(argv)`: that command as this host must launch it.
- `session_in(argv)`: the session a command resumes or mints.
- `wire(argv, events, sink)`: the command with its turn's end wired to the sink, which writes each
  event into the turn's own file.
- `completion(events, prompt, session)`: the turn's end, as (ok, message, session), or None yet.
- `output(message, session)`: what a finished turn leaves for the role-run to read.
- `session(out, minted)`: the session a new turn began. `final_message(out)`: its answer.
- `message_of(event)`: an agent message inside one JSON line of its output, or None.
- `skill_folders(name, repo)`: where a skill of that name would be found for it.
- optional — `trust_ensure(repo, home)`, `trust_forget(repo, home)`; `trace_env(context)`,
  `trace_settings(context, private)`, `reasoning(session)`, `upload(session, context)`;
  `waiting(events)`: whether its turn's events end on a dialog waiting in its terminal, for a kind that
  reports one.

Importing a kind's module only defines it: anything that touches the host happens in its answers,
so the kinds can be listed on a host that has none of their CLIs.
"""
import importlib
import os
import pkgutil

from app.foundation import policy as P

ACCESSES = ("read", "write")
REQUIRED = ("NAME", "EXECUTABLE", "ACCESS", "OPTIONS", "SKILL", "SESSION_MARKERS", "SESSION_MARKER_PREFIXES",
            "LOST_SESSION", "OLD_BRAIN", "validate", "command", "host", "session_in", "wire", "completion",
            "output", "session", "final_message", "message_of", "skill_folders", "skill_roots")
CALLABLE = ("validate", "command", "host", "session_in", "wire", "completion", "output", "session",
            "final_message", "message_of", "skill_folders", "skill_roots")
OPTIONAL = ("trust_ensure", "trust_forget", "trace_env", "trace_settings", "reasoning", "upload", "waiting")


class Refused(ValueError):
    """A kind that is not one, or whose module cannot be loaded or does not keep the contract."""


def module_name(kind):
    """`claude-code` → `claude_code`: the one rule between a kind and its module."""
    if not isinstance(kind, str) or not P.NAME.fullmatch(kind):
        raise Refused("%r is not a kind's name: lowercase letters and digits, words joined by single "
                      "hyphens" % (kind,))
    return kind.replace("-", "_")


def kind_of(module):
    """The kind a module of this package is, by the same rule; None when its name is not one."""
    kind = module.replace("_", "-")
    return kind if P.NAME.fullmatch(kind) and module_name(kind) == module else None


def load(kind):
    """The module of `kind`, checked against the contract; Refused, saying why, when it is not one."""
    name = module_name(kind)
    try:
        module = importlib.import_module("%s.%s" % (__name__, name))
    except ModuleNotFoundError as exc:
        if exc.name == "%s.%s" % (__name__, name):
            raise Refused("no kind %r: no module %s.py in %s" % (kind, name, __name__)) from exc
        raise Refused("kind %r cannot be loaded: %s" % (kind, exc)) from exc
    except Exception as exc:                        # noqa: BLE001 - said, never hidden
        raise Refused("kind %r cannot be loaded: %s: %s" % (kind, type(exc).__name__, exc)) from exc
    lacking = [part for part in REQUIRED if not hasattr(module, part)]
    lacking += [part for part in CALLABLE if hasattr(module, part) and not callable(getattr(module, part))]
    if lacking:
        raise Refused("kind %r lacks what every kind holds: %s" % (kind, ", ".join(lacking)))
    unknown = [access for access in module.ACCESS if access not in ACCESSES]
    if not module.ACCESS or unknown:
        raise Refused("kind %r: ACCESS must hold %s, not %s" % (kind, " or ".join(ACCESSES), unknown or "nothing"))
    return module


def capabilities(module):
    """What the page shows of a kind: its name, the access it can run with, its settings, its skills."""
    return {"name": module.NAME, "access": list(module.ACCESS), "options": list(module.OPTIONS),
            "skill": module.SKILL}


def available():
    """Every kind this package holds, each module answered on its own: its capabilities, or why it is
    refused. One module that fails never hides the rest."""
    found = []
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda info: info.name):
        if info.ispkg or info.name.startswith("_"):
            continue
        kind = kind_of(info.name)
        if kind is None:
            found.append({"kind": info.name, "refused": "%s.py is not named for a kind" % info.name})
            continue
        try:
            found.append(dict(capabilities(load(kind)), kind=kind, refused=None))
        except Refused as exc:
            found.append({"kind": kind, "refused": str(exc)})
    return found


def skill_names(repo):
    """Discovered skill names for each usable kind, using only the roots its adapter owns."""
    found = {}
    for entry in available():
        if entry["refused"]:
            continue
        module = load(entry["kind"])
        names = set()
        for root in module.skill_roots(repo):
            try:
                with os.scandir(root) as children:
                    names.update(child.name for child in children
                                 if P.skill_name(child.name) and child.is_dir(follow_symlinks=True) and
                                 os.path.isfile(os.path.join(child.path, "SKILL.md")))
            except OSError:
                # Discovery helps fill a setting; prepare still checks a binding on the worker that will use it.
                continue
        found[entry["kind"]] = sorted(names)
    return found


def usable():
    """The modules of every kind that loads."""
    return [load(entry["kind"]) for entry in available() if entry["refused"] is None]


def for_brain(brain):
    """The kind an old run's policy named as its `brain`, by the old name each kind declares."""
    for module in usable():
        if module.OLD_BRAIN and module.OLD_BRAIN == brain:
            return module
    raise Refused("no kind answers to the brain %r" % (brain,))


def kind_name(module):
    return kind_of(module.__name__.rsplit(".", 1)[-1])


def for_role(role):
    """The module a role of a run's policy runs: its `kind`, or the kind its old `brain` names."""
    if role.get("kind"):
        return load(role["kind"])
    return for_brain(role.get("brain"))


def view(role):
    """What a kind reads of a role of a run's policy, whichever shape it has: its access, and each value the
    kind takes — for a run started before agent profiles, its `reasoning_effort` as its effort."""
    values = {option: role.get(option) for option in for_role(role).OPTIONS}
    if values.get("effort") is None and "effort" in values:
        values["effort"] = role.get("reasoning_effort")
    return dict(values, workspace_access=role["workspace_access"])


def session_markers():
    """Every name, and every prefix, that a session of any kind leaves: no agent inherits any of them."""
    names, prefixes = set(), set()
    for module in usable():
        names.update(module.SESSION_MARKERS)
        prefixes.update(module.SESSION_MARKER_PREFIXES)
    return names, tuple(sorted(prefixes))


def waiting(events):
    """Whether a turn's events end on a dialog waiting in its terminal, by the kinds that report one; each
    reads only its own events, and a kind that reports none never waits here."""
    return any(module.waiting(events) for module in usable() if hasattr(module, "waiting"))


def skill(module, name):
    """A stage's skill as `module`'s kind invokes it, or None when that kind takes none."""
    return module.SKILL.format(name=name) if module.SKILL and name else None
