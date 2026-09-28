"""Claude Code, Anthropic's CLI, as a kind of agent.

A turn is `claude` started again in the role's terminal: a new session under an id minted here
(`--session-id`), a resumed one by that id (`--resume`). A read-only role runs in plan mode; a writing one in
`dontAsk` mode with edits allowed inside its worktree, so a turn never waits on a permission prompt — what is
not allowed is denied and the agent works on. The host's skills folder is added for reading, where the
skills a stage invokes keep their references.

Its turn ends on its own hooks: `Stop` for a prompt id that `UserPromptSubmit` reported for our prompt, or
for any prompt submitted after it in the session, while no background task of it still runs; `StopFailure`
fails the turn. The hooks go in its settings — the file a traced turn already has, since Claude takes one
`--settings`, or its own. Its answer is the turn's final message.

A worker started from inside a Claude Code session inherits that session's markers, and a Claude agent
carrying them runs as that session's child: measured, it keeps no transcript, so its session cannot be
resumed by id. So no agent of any kind inherits them.

Its trust record: `projects["<repo>"].hasTrustDialogAccepted` in `~/.claude.json`, or the `.claude.json` in
the folder `CLAUDE_CONFIG_DIR` names — read, changed in memory and replaced whole, and on Windows keyed by
the repository's path in forward slashes, the spelling it reads (measured).

Its tracing: the Langfuse plugin, installed for the user but switched off there, is switched on for a traced
turn only, through that turn's own settings file, which holds both of the trace store's keys and lives in the
turn's private folder; the step's traceparent reaches it through the environment, so its turns nest under
the step. Its persisted thinking is an empty block and a signature, so it has no reasoning to read back.
"""
import json
import os
import re
import sys
import uuid

from app.agents.adapters import _files

NAME = "Claude Code"
EXECUTABLE = "claude"
ACCESS = ("read", "write")
OPTIONS = ("model", "effort")
SKILL = "/{name}"
SESSION_MARKERS = ("CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT", "CLAUDE_AGENT_SDK_VERSION")
SESSION_MARKER_PREFIXES = ("CLAUDE_CODE_",)
# Its terminal says so before it exits without any work (measured on the installed CLI).
LOST_SESSION = ("no conversation found with session id",)
OLD_BRAIN = "claude"
HOOKS = ("UserPromptSubmit", "Stop", "StopFailure")
WINDOWS = sys.platform.startswith("win")
# Model and effort reach the command line, so each is a plain token.
PLAIN_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")
CONFIG_FILE = ".claude.json"
PLUGIN = "langfuse-observability@langfuse-observability"
SETTINGS_FILE = "claude-settings.json"


def validate(profile):
    problems = []
    for key, value in profile.items():
        if key == "kind":
            continue
        if key not in OPTIONS:
            problems.append((key, "Claude Code takes %s, not %r" % (" and ".join(OPTIONS), key)))
        elif not (isinstance(value, str) and PLAIN_TOKEN.fullmatch(value)):
            problems.append((key, "must be a plain token"))
    return problems


def command(role, resume_id, traced=None):
    """Its CLI for one turn, and the session id minted for a new one."""
    parts = [EXECUTABLE]
    if traced:
        parts += ["--settings", traced]
    minted = None
    if resume_id:
        parts += ["--resume", resume_id]
    else:
        minted = str(uuid.uuid4())
        parts += ["--session-id", minted]
    if role.get("model"):
        parts += ["--model", role["model"]]
    if role.get("effort"):
        parts += ["--effort", role["effort"]]
    if role["workspace_access"] == "read":
        parts += ["--permission-mode", "plan"]
    else:
        # A role turn never waits on a permission prompt: what is not allowed is denied and the agent works on,
        # as a run with no one to ask always did. Edits in the worktree are allowed; an Edit rule also governs
        # writes.
        parts += ["--permission-mode", "dontAsk", "--allowedTools", "Edit(./**)"]
    return parts, minted


def host(argv, windows=WINDOWS, skills=None):
    """The skills a stage invokes read their references from this host's skills folder, outside the
    worktree; added as a working directory, it needs no approval to read."""
    skills = skills or os.path.join(os.path.expanduser("~"), ".claude", "skills")
    if os.path.isdir(skills):
        return list(argv) + ["--add-dir", os.path.realpath(skills)]
    return list(argv)


def session_in(argv):
    for flag in ("--session-id", "--resume"):
        if flag in argv:
            return argv[argv.index(flag) + 1]
    return None


def _hook(sink):
    return " ".join('"%s"' % part if index < 3 else part for index, part in enumerate(sink))


def wire(argv, events, sink):
    """Its hooks in its settings — the file it names, or its own."""
    hooks = {event: [{"hooks": [{"type": "command", "command": _hook(sink(event, "stdin"))}]}] for event in HOOKS}
    argv = list(argv)
    if "--settings" in argv:
        path = argv[argv.index("--settings") + 1]
        with open(path, encoding="utf-8") as fh:
            settings = json.load(fh)
        settings["hooks"] = hooks
        # The file is the turn's private one; it keeps holding what it held.
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(settings, fh)
        return argv
    return argv[:1] + ["--settings", json.dumps({"hooks": hooks})] + argv[1:]


def completion(events, prompt, session):
    wanted = prompt.strip()
    ids = set()
    for event in events:
        if event.get("session_id") != session:
            continue
        hook = event.get("_hook")
        if hook == "UserPromptSubmit":
            if ids or (event.get("prompt") or "").strip() == wanted:
                ids.add(event.get("prompt_id"))
        elif ids and event.get("prompt_id") in ids:
            if hook == "Stop" and not any(task.get("status") == "running"
                                          for task in event.get("background_tasks") or []):
                return True, event.get("last_assistant_message") or "", session
            if hook == "StopFailure":
                return False, json.dumps({key: value for key, value in event.items()
                                          if key not in ("transcript_path", "_hook")}), session
    return None


def output(message, session):
    return message


def session(out, minted):
    return minted


def final_message(out):
    return out


def message_of(event):
    return None


def skill_folders(name, repo):
    return [os.path.join(root, name) for root in skill_roots(repo)]


def skill_roots(repo):
    return [os.path.join(os.path.expanduser("~"), ".claude", "skills"),
            os.path.join(repo, ".claude", "skills")]


# ---- trust ----------------------------------------------------------------------------------

def config_path(home=None):
    """Its config file on this host, under `CLAUDE_CONFIG_DIR` when that names its home.

    Measured, not assumed: started with an empty directory named by that variable, the CLI created
    `.claude.json` inside it, beside its own `sessions/` and `cache/`.
    """
    if home:
        return os.path.join(home, CONFIG_FILE)
    return os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~"), CONFIG_FILE)


def trust_key(repo):
    """The spelling it looks a repository up by on this host: forward slashes on Windows (measured)."""
    return repo.replace("\\", "/") if WINDOWS else repo


def _config(home):
    path = config_path(home)
    try:
        with open(path, encoding="utf-8") as fh:
            config = json.load(fh)
    except FileNotFoundError:
        return path, {}
    except ValueError:
        return path, None                           # not the shape we know; leave it alone
    return path, config if isinstance(config, dict) else None


def trust_ensure(repo, home=None):
    path, config = _config(home)
    if config is None:
        return False
    projects = config.setdefault("projects", {})
    entry = projects.get(trust_key(repo))
    if isinstance(entry, dict) and entry.get("hasTrustDialogAccepted"):
        return False
    projects[trust_key(repo)] = dict(entry or {}, hasTrustDialogAccepted=True)
    _files.replace(path, json.dumps(config, indent=2))
    return True


def trust_forget(repo, home=None):
    path, config = _config(home)
    if config is None:
        return False
    projects = config.get("projects") or {}
    entry = projects.get(trust_key(repo))
    if not isinstance(entry, dict) or not entry.pop("hasTrustDialogAccepted", False):
        return False
    # What the CLI itself put in the entry is not ours to remove; an entry holding nothing else goes.
    if not any(value for value in entry.values()):
        projects.pop(trust_key(repo))
    _files.replace(path, json.dumps(config, indent=2))
    return True


# ---- tracing --------------------------------------------------------------------------------

def trace_env(context):
    """The step's traceparent, so its turns nest under the step, and the run's environment and release,
    which reach the plugin's own rows only through this process."""
    if not context or not context.get("traceparent"):
        return None
    env = {"CC_LANGFUSE_TRACEPARENT": context["traceparent"]}
    for name, key in (("LANGFUSE_TRACING_ENVIRONMENT", "environment"), ("LANGFUSE_RELEASE", "release")):
        if context.get(key):
            env[name] = context[key]
    return env


def trace_settings(context, private):
    """The turn's own settings file, switching the plugin on with both keys; None unless the step is traced
    and both keys are set, so a run with tracing off never switches it on."""
    if not context or not context.get("traceparent"):
        return None
    if not context.get("public_key") or not context.get("secret_key"):
        return None
    settings = {"enabledPlugins": {PLUGIN: True},
                "pluginConfigs": {PLUGIN: {"options": {"LANGFUSE_PUBLIC_KEY": context["public_key"],
                                                       "LANGFUSE_SECRET_KEY": context["secret_key"],
                                                       "LANGFUSE_BASE_URL": context["base_url"]}}}}
    return _files.private_file(private, SETTINGS_FILE, json.dumps(settings))
