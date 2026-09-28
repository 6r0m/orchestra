"""The settings: their files, their shape, and every configuration invariant that needs no agent's module.

- Two roles (D2): engineer (write) plans and builds; architect (read-only) researches, assesses and
  verifies — the judge of the plan verifies its execution. A role's access is its contract, never a
  setting (`ROLE_ACCESS`).
- Agents are profiles: a name for a kind of agent and that kind's own values. Which profile a role runs
  is configuration, and so is whether both roles run the same model (D9); whether a kind's values are
  valid, and whether it can run with its role's access, is its adapter's to say, composed in
  `app.application.settings`, since nothing here loads an adapter.
- review_rounds (D5): normal and extended architect review attempts per phase; max_rounds is retained for
  old settings and run policies.
- Git authority: all-false — agents never commit or push (D11).

Identifiers are data: binding an agent, editing a role's persona or naming the default flow is
configuration; a new stage is a change to the code (D13).

The effective settings come from the file `ORCHESTRA_SETTINGS` names, taken alone — a stack of its own,
the demo's or the acceptance run's — else from this checkout's `.orchestra/settings.json`, shared and
committed, with `.orchestra/settings.local.json` over it: the operator's own, ignored by git, a JSON
Merge Patch (RFC 7396) that the Workbench's Settings view writes. The result is validated whole, and its
origin is always the file below the patch, so no patch makes the deployment another stack. A path inside
the settings resolves from the checkout's root. A refusal names the setting it is about by its JSON
Pointer (RFC 6901), when it is about one.

An edit of the patch is sparse: it touches only the settings it is given, so a member the page does not
show survives, an unchanged shared value is never copied in, and a value equal to the one below leaves
the patch. Each read carries a revision of both files, which an edit is checked against.
"""
import copy
import hashlib
import json
import os
import re
import tempfile

from app.foundation import flows
from app.foundation import paths
from app.foundation import stages

# Names a settings file of a stack's own, taken alone.
VARIABLE = "ORCHESTRA_SETTINGS"
SETTINGS_FILE = os.path.join(paths.REPO, ".orchestra", "settings.json")
LOCAL_FILE = os.path.join(paths.REPO, ".orchestra", "settings.local.json")
# What an absent file contributes to a revision: never the bytes of a file that exists.
ABSENT = b"\0absent"

ROLES = ("engineer", "architect")
# Each role's access is its contract: the engineer writes, and the architect only reads (D2, D10). No
# other value is valid, so no setting holds it; a run's policy carries it from its start.
ROLE_ACCESS = {"engineer": "write", "architect": "read"}
# A kind's name and a profile's: lowercase letters and digits, in words joined by single hyphens.
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
# A skill is named by the Agent Skills specification's rule: that grammar, and at most 64 characters.
SKILL_NAME_MAX = 64
# A persona crosses to the role's host inside every turn's input, and Temporal's converter escapes each
# character it does not keep as ASCII: at this bound, a turn's input stays under Temporal's 256 KiB payload
# warning for any text (measured on the real wire, `tests/application/test_settings.py`).
MAX_PERSONA_BYTES = 16 * 1024
# Strict schemas: an unknown key is a typo, and a typo that silently does
# nothing is the worst failure mode for a config-driven system.
ROLE_KEYS = {"agent", "persona_file", "persona"}
PLAIN_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")
TOP_KEYS = {"agents", "roles", "max_rounds", "review_rounds", "auto_proceed", "timeout_seconds", "heartbeat_seconds",
            "stop_cleanup_seconds", "targets", "target_repo", "workbench_port", "stage_skills",
            "workflow_queue", "default_flow", "_policy_path"}
REPO_KEYS = {"commit_allowed", "push_allowed", "merge_allowed"}
# A Stop's cleanup waits this long at most, so a host whose worker is gone never holds a Stop; a policy's
# `stop_cleanup_seconds` may only shorten it.
STOP_CLEANUP_SECONDS = 60
# Where a run's agents can execute. Each host has its own task queue, polled only by
# that host's worker, so a role never runs on the wrong OS.
TARGETS = ("wsl", "windows")
# Each host's worker serves its live terminals on its own local port; the two hosts share one
# localhost, so the ports differ.
TARGET_KEYS = {"host", "worktree_root", "terminal_port"}
# What refuses settings of the shape they had before agent profiles, which only a run started then still
# carries: those runs are read, never such a file.
OLD_SHAPE = ("these settings have the shape they had before agent profiles: `agents` now maps a profile's "
             "name to its `kind` and that kind's `model` and `effort`, each role names its profile as `agent` "
             "and its persona as `persona_file`, a role's access is its own, never a setting, and a stage's "
             "skill is its name — see .orchestra/settings.json")


class InvalidPolicy(ValueError):
    """Settings that break a rule; `pointer` is the JSON Pointer of the setting it is about, or None."""

    def __init__(self, reason, pointer=None):
        super().__init__("%s: %s" % (pointer, reason) if pointer else reason)
        self.reason, self.pointer = reason, pointer


def pointer(*parts):
    """The JSON Pointer (RFC 6901) of a setting, from the keys that lead to it."""
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def sources(path=None, root=paths.REPO, environ=os.environ):
    """The files settings are read from: (the file below, the local patch or None when there is none to
    apply). `path`, or the file `ORCHESTRA_SETTINGS` names, is taken alone; else the checkout's shared
    settings, with its local patch over them."""
    named = path or environ.get(VARIABLE)
    if named:
        return named, None
    folder = os.path.join(root, ".orchestra")
    return os.path.join(folder, "settings.json"), os.path.join(folder, "settings.local.json")


def read_settings(path):
    """A settings file's object, unvalidated."""
    return _json(path)


def _json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            value = json.load(fh)
    except ValueError as exc:
        raise InvalidPolicy("%s is not JSON: %s" % (path, exc)) from exc
    if not isinstance(value, dict):
        raise InvalidPolicy("%s must hold an object of settings" % path)
    return value


def read_patch(local):
    """The local patch, or None when there is none. One that cannot be read stops the load, naming it."""
    if local is None or not os.path.exists(local):
        return None
    try:
        return _json(local)
    except OSError as exc:
        raise InvalidPolicy("%s cannot be read: %s" % (local, exc)) from exc


def merge(target, patch):
    """`patch` applied to `target` by RFC 7396: an object merges member by member, `null` removes a
    member, and any other value — a list included — replaces."""
    if not isinstance(patch, dict):
        return copy.deepcopy(patch)
    result = copy.deepcopy(target) if isinstance(target, dict) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = merge(result.get(key), value)
    return result


def load(path=None, root=paths.REPO, environ=os.environ):
    """The effective settings: `path`, or the file `ORCHESTRA_SETTINGS` names, alone; else the checkout's
    shared settings with its local patch over them.

    Validated for everything that needs no agent's module; `app.application.settings` loads through
    this and adds each kind's own checks, and is what everything else loads. A local patch that does not
    load, or makes the settings invalid, stops the load, naming its file.
    """
    below, local = sources(path, root, environ)
    raw = _json(below)
    patch = read_patch(local)
    if patch is None:
        return validate(dict(raw, _policy_path=origin(below, root)))
    try:
        return validate(dict(merge(raw, patch), _policy_path=origin(below, root)))
    except InvalidPolicy as exc:
        validate(dict(raw, _policy_path=origin(below, root)))
        raise InvalidPolicy("%s, over %s: %s" % (local, below, exc.reason), exc.pointer) from exc


def revision(below, local):
    """A revision of the settings as their files hold them now: a hash of both files' bytes, an absent one
    included."""
    digest = hashlib.sha256()
    for path in (below, local):
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except (FileNotFoundError, TypeError):
            data = ABSENT
        digest.update(b"%d:" % len(data) + data)
    return digest.hexdigest()


def parse_pointer(text):
    """The keys a JSON Pointer (RFC 6901) leads through."""
    if not isinstance(text, str) or not text.startswith("/"):
        raise InvalidPolicy("%r is not a JSON Pointer" % (text,))
    return [part.replace("~1", "/").replace("~0", "~") for part in text[1:].split("/")]


_MISSING = object()


def _at(document, keys):
    for key in keys:
        if not isinstance(document, dict) or key not in document:
            return _MISSING
        document = document[key]
    return document


def _difference(below, wanted):
    """The smallest patch that turns `below` into `wanted`."""
    if not (isinstance(below, dict) and isinstance(wanted, dict)):
        return copy.deepcopy(wanted)
    patch = {key: None for key in below if key not in wanted}
    patch.update({key: _difference(below.get(key), value) for key, value in wanted.items()
                  if below.get(key, _MISSING) != value})
    return patch


def _put(patch, keys, value):
    for key in keys[:-1]:
        if not isinstance(patch.get(key), dict):
            patch[key] = {}
        patch = patch[key]
    patch[keys[-1]] = value


def _drop(patch, keys):
    """Remove the member at `keys`, and every object that leaves empty."""
    trail = [patch]
    for key in keys[:-1]:
        if not isinstance(trail[-1].get(key), dict):
            return
        trail.append(trail[-1][key])
    trail[-1].pop(keys[-1], None)
    for depth in range(len(keys) - 1, 0, -1):
        if trail[depth]:
            break
        trail[depth - 1].pop(keys[depth - 1])


def edited(below, patch, changes):
    """The patch over `below` after `changes`, each `{"pointer", "value"}`, `{"pointer", "remove": true}` or
    `{"pointer", "revert": true}` — touching only the members they point at."""
    patch = copy.deepcopy(patch or {})
    for change in changes:
        keys = parse_pointer(change.get("pointer"))
        under = _at(below, keys)
        if change.get("revert"):
            _drop(patch, keys)
        elif change.get("remove"):
            if under is _MISSING:
                _drop(patch, keys)
            else:
                _put(patch, keys, None)
        elif "value" in change:
            if under is not _MISSING and change["value"] == under:
                _drop(patch, keys)
            else:
                _put(patch, keys, _difference(None if under is _MISSING else under, change["value"]))
        else:
            raise InvalidPolicy("a change sets a value, removes or reverts", change.get("pointer"))
    return patch


def write_patch(local, patch):
    """Replace the local patch in one step, or remove it when it holds nothing. Raises OSError when either
    cannot be done, and then the file is as it was."""
    if not patch:
        if os.path.exists(local):
            os.remove(local)
        return
    folder = os.path.dirname(local)
    handle, temporary = tempfile.mkstemp(dir=folder, prefix=".settings-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(patch, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(temporary, local)
    except BaseException:
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise


def origin(path, root=paths.REPO):
    """Where settings came from, in a form that survives the crossing to the other host.

    The hosts spell one checkout differently (`/mnt/e/...` and `E:\\...`), so a file inside
    the checkout is named relative to it, with forward slashes, and each host reads that
    against its own checkout. A file outside the checkout keeps its absolute path, which
    only the host that loaded it can read.
    """
    absolute = os.path.abspath(path)
    try:
        relative = os.path.relpath(absolute, root)
    except ValueError:
        # Another drive than the checkout's, on Windows.
        return absolute
    if relative.split(os.sep)[0] == os.pardir:
        return absolute
    return relative.replace(os.sep, "/")


# An absolute path in either host's spelling: a drive, a UNC share or a POSIX root. One that
# is not absolute to *this* host was written by the other.
ABSOLUTE_ANYWHERE = re.compile(r"[A-Za-z]:[\\/]|[\\/]")


def prompt_path(policy, role_name):
    """The role's persona file as *this* host sees it. The one resolver.

    Settings name it `persona_file`, from the checkout's root, and the host starting a run reads it there
    (`persona`). A run started before agent profiles names it `prompt`, which the host running the role
    resolves against where that run's policy was loaded: its origin read against this checkout when it
    came from inside one, and as it stands when that is an absolute path on this host. An origin written
    by the other host is refused rather than guessed at, and so is a persona file that is not there: a
    role never runs on a persona other than the one its policy names.
    """
    role = policy["roles"][role_name]
    if "persona_file" in role:
        named, base, where = role["persona_file"], paths.REPO, pointer("roles", role_name, "persona_file")
    else:
        named, origin_path, where = role["prompt"], policy.get("_policy_path"), None
        if not origin_path:
            base = paths.REPO
        elif os.path.isabs(origin_path):
            base = os.path.dirname(origin_path)
        elif ABSOLUTE_ANYWHERE.match(origin_path):
            raise InvalidPolicy("role %r: the run's policy was loaded from %s, outside the checkout and on the "
                                "other host, so this host cannot read its persona files" % (role_name, origin_path))
        else:
            base = os.path.join(paths.REPO, *origin_path.split("/")[:-1])
    # A path is written with forward slashes, as JSON; normalised, the one answer reads the same in a
    # refusal on either host.
    resolved = named if os.path.isabs(named) else os.path.normpath(os.path.join(base, named))
    if not os.path.isfile(resolved):
        raise InvalidPolicy("role %r: persona file missing: %s" % (role_name, resolved), where)
    return resolved


def persona(settings, role_name):
    """The role's persona in effect — its `persona` text when given, else its `persona_file`'s — refused,
    naming the role, one byte of UTF-8 past `MAX_PERSONA_BYTES`."""
    role = settings["roles"][role_name]
    if "persona" in role:
        text, where = role["persona"], pointer("roles", role_name, "persona")
    else:
        path, where = prompt_path(settings, role_name), pointer("roles", role_name, "persona_file")
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, ValueError) as exc:
            raise InvalidPolicy("role %r: persona file %s cannot be read: %s" % (role_name, path, exc), where)
    size = len(text.encode("utf-8"))
    if size > MAX_PERSONA_BYTES:
        raise InvalidPolicy("role %r: its persona is %d bytes of UTF-8, over the %d a run carries"
                            % (role_name, size, MAX_PERSONA_BYTES), where)
    return text


def skill_name(value):
    """Whether `value` names a skill by the Agent Skills specification's rule."""
    return isinstance(value, str) and len(value) <= SKILL_NAME_MAX and NAME.fullmatch(value) is not None


def _old_shape(raw):
    roles = raw.get("roles")
    return "agents" not in raw or (isinstance(roles, dict) and any(
        isinstance(role, dict) and {"brain", "prompt"} & set(role) for role in roles.values()))


def validate(raw):
    if _old_shape(raw):
        raise InvalidPolicy(OLD_SHAPE)
    unknown = sorted(set(raw) - TOP_KEYS)
    if unknown:
        raise InvalidPolicy("unknown setting", pointer(unknown[0]))
    agents = raw.get("agents")
    if not isinstance(agents, dict) or not agents:
        raise InvalidPolicy("must map each profile's name to its kind", pointer("agents"))
    for name, profile in agents.items():
        if not NAME.fullmatch(name):
            raise InvalidPolicy("a profile's name is lowercase letters and digits, words joined by single hyphens",
                                pointer("agents", name))
        if not isinstance(profile, dict):
            raise InvalidPolicy("must hold the profile's kind and its values", pointer("agents", name))
        # What a kind's other values may be is the kind's own to say (`app.application.settings`).
        if not (isinstance(profile.get("kind"), str) and NAME.fullmatch(profile["kind"])):
            raise InvalidPolicy("must name a kind: lowercase letters and digits, words joined by single hyphens",
                                pointer("agents", name, "kind"))
    # A stage may be led by a skill — its methodology, which this component does not own — named by the
    # skills' own rule; how a kind invokes it is the kind's. Unset means the prompt says everything itself.
    skills = raw.get("stage_skills") or {}
    if not isinstance(skills, dict):
        raise InvalidPolicy("must map a stage to the skill that leads its prompt", pointer("stage_skills"))
    for stage, skill in skills.items():
        if stage not in stages.STAGE_ROLE:
            raise InvalidPolicy("not a stage (%s)" % ", ".join(sorted(stages.STAGE_ROLE)),
                                pointer("stage_skills", stage))
        if not skill_name(skill):
            raise InvalidPolicy("a skill's name: lowercase letters and digits, words joined by single hyphens, "
                                "at most %d characters, such as investigate-change" % SKILL_NAME_MAX,
                                pointer("stage_skills", stage))
    roles = raw.get("roles")
    if not isinstance(roles, dict) or set(roles) != set(ROLES):
        raise InvalidPolicy("must define exactly %s" % " and ".join(ROLES), pointer("roles"))
    for name in ROLES:
        role = roles[name]
        if not isinstance(role, dict):
            raise InvalidPolicy("must hold the role's agent and persona", pointer("roles", name))
        unknown = sorted(set(role) - ROLE_KEYS)
        if unknown:
            raise InvalidPolicy("unknown setting: a role takes %s" % ", ".join(sorted(ROLE_KEYS)),
                                pointer("roles", name, unknown[0]))
        if role.get("agent") not in agents:
            raise InvalidPolicy("must name a profile in agents", pointer("roles", name, "agent"))
        if "persona" in role and not isinstance(role["persona"], str):
            raise InvalidPolicy("must be the persona's text", pointer("roles", name, "persona"))
        if "persona_file" in role and not (isinstance(role["persona_file"], str) and role["persona_file"]):
            raise InvalidPolicy("must be a file's path from the checkout's root", pointer("roles", name, "persona_file"))
        if "persona" not in role and "persona_file" not in role:
            raise InvalidPolicy("needs a persona_file, or its persona text", pointer("roles", name))
        # Read to prove it is there and within its bound; a run's start reads it again, into the run.
        persona(raw, name)

    legacy = raw.get("max_rounds")
    if "max_rounds" in raw:
        if not isinstance(legacy, dict) or set(legacy) != set(stages.PHASES):
            raise InvalidPolicy("must define exactly %s" % " and ".join(stages.PHASES), pointer("max_rounds"))
        for phase, n in legacy.items():
            if not isinstance(n, int) or isinstance(n, bool) or n < 1:
                raise InvalidPolicy("must be an int >= 1", pointer("max_rounds", phase))
    rounds = raw.get("review_rounds")
    if "review_rounds" in raw:
        if not isinstance(rounds, dict) or set(rounds) != set(stages.PHASES):
            raise InvalidPolicy("must define exactly %s" % " and ".join(stages.PHASES), pointer("review_rounds"))
        for phase, thresholds in rounds.items():
            if not isinstance(thresholds, dict) or set(thresholds) != {"normal", "extended"}:
                raise InvalidPolicy("must define exactly normal and extended", pointer("review_rounds", phase))
            for name, n in thresholds.items():
                minimum = 0 if name == "extended" else 1
                if not isinstance(n, int) or isinstance(n, bool) or n < minimum:
                    raise InvalidPolicy("must be an int >= %d" % minimum,
                                        pointer("review_rounds", phase, name))
    if "max_rounds" not in raw and "review_rounds" not in raw:
        raise InvalidPolicy("must define review_rounds", pointer("review_rounds"))

    repo = raw.get("target_repo")
    if not isinstance(repo, dict):
        raise InvalidPolicy("required", pointer("target_repo"))
    unknown = sorted(set(repo) - REPO_KEYS)
    if unknown:
        raise InvalidPolicy("unknown setting", pointer("target_repo", unknown[0]))
    for key in ("commit_allowed", "push_allowed", "merge_allowed"):
        if repo.get(key) is not False:
            raise InvalidPolicy("must be false — agents never commit or push (D11)", pointer("target_repo", key))
    timeout = raw.get("timeout_seconds")
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout < 1:
        raise InvalidPolicy("must be an int >= 1", pointer("timeout_seconds"))
    if not isinstance(raw.get("auto_proceed"), bool):
        raise InvalidPolicy("must be true or false", pointer("auto_proceed"))
    # The flow a run starts on when it names none, a file in `flows/`, read only at a run's start: named
    # by the flows' own grammar, so a name taken here can always be a file there.
    if "default_flow" in raw and not flows.is_name(raw["default_flow"]):
        raise InvalidPolicy("must name a flow in flows/, such as engineer-code", pointer("default_flow"))
    heartbeat = raw.get("heartbeat_seconds")
    if not isinstance(heartbeat, int) or isinstance(heartbeat, bool) or heartbeat < 1:
        raise InvalidPolicy("must be an int >= 1", pointer("heartbeat_seconds"))
    # Optional, and only ever shorter than the minute a Stop's cleanup waits at most.
    if "stop_cleanup_seconds" in raw:
        cleanup = raw["stop_cleanup_seconds"]
        if (not isinstance(cleanup, int) or isinstance(cleanup, bool)
                or not 1 <= cleanup <= STOP_CLEANUP_SECONDS):
            raise InvalidPolicy("must be an int from 1 to %d: it may only shorten a Stop's cleanup"
                                % STOP_CLEANUP_SECONDS, pointer("stop_cleanup_seconds"))
    # Required, so settings that forget it fail here rather than joining another stack's runs.
    if not (isinstance(raw.get("workflow_queue"), str) and PLAIN_TOKEN.fullmatch(raw["workflow_queue"])):
        raise InvalidPolicy("must be a plain token: the task queue these settings' runs are on",
                            pointer("workflow_queue"))
    targets = raw.get("targets")
    if not isinstance(targets, dict) or set(targets) != set(TARGETS):
        raise InvalidPolicy("must define exactly %s" % " and ".join(TARGETS), pointer("targets"))
    for name, target in targets.items():
        if not isinstance(target, dict) or set(target) != TARGET_KEYS:
            raise InvalidPolicy("must define exactly %s" % ", ".join(sorted(TARGET_KEYS)), pointer("targets", name))
        if not (isinstance(target["host"], str) and PLAIN_TOKEN.fullmatch(target["host"])):
            raise InvalidPolicy("must be a plain token", pointer("targets", name, "host"))
        if not (isinstance(target["worktree_root"], str) and target["worktree_root"]):
            raise InvalidPolicy("must be a path", pointer("targets", name, "worktree_root"))
    ports = [(pointer("workbench_port"), raw.get("workbench_port"))] + [
        (pointer("targets", name, "terminal_port"), target["terminal_port"]) for name, target in targets.items()]
    for where, port in ports:
        if not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535:
            raise InvalidPolicy("must be a port number", where)
    if len({port for _, port in ports}) != len(ports):
        raise InvalidPolicy("the Workbench's port and the terminal ports must all differ")
    return raw


def queue(policy, target):
    """The task queue of one target host: `target:<os>:<host>`."""
    return "target:%s:%s" % (target, policy["targets"][target]["host"])


def workflow_queue(policy):
    """The task queue these settings' runs — and the reads of their changes and worktrees — are on.

    The deployment's is `orchestration`, where every run Temporal retains is queried; another
    stack's, the demo's or the acceptance's, so its worker never takes another stack's workflow tasks.
    """
    return policy["workflow_queue"]
