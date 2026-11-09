"""Claude Code, Anthropic's CLI, as a kind of agent.

A turn is `claude` started again in the role's terminal: a new session under an id minted here
(`--session-id`), a resumed one by that id (`--resume`). A read-only role runs in plan mode; a writing one in
`dontAsk` mode with edits allowed inside its worktree, so a turn never waits on a permission prompt — what is
not allowed is denied and the agent works on. Neither is offered the vendor's question tools, nor a way into
or out of plan mode that would wait on a dialog. The host's skills folder is added for reading, where the
skills a stage invokes keep their references.

Its turn ends on its own hooks: `Stop` for a prompt id that `UserPromptSubmit` reported for our prompt, or
for any prompt submitted after it in the session, while no background task of it still runs; `StopFailure`
fails the turn. The hooks go in its settings — the file a traced turn already has, since Claude takes one
`--settings`, or its own — with its auto-compact on, whatever the operator's own setting: a session that fills
its context with it off stops there and fires no hook. A stop like that all the same — compaction off by the
environment, or given up — is read off its screen once the turn goes quiet (`halted`). Its answer is the turn's
final message.

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
from app.agents import launch
from app.foundation import localenv

NAME = "Claude Code"
EXECUTABLE = "claude"
ACCESS = ("read", "write")
# Its own permission rules, with no operating-system boundary under them: its sandbox covers shell commands
# on Linux and WSL2 only, and is not turned on here. Measured on WSL, started as `command` starts a writing
# role: its file tool was refused outside the worktree, and a command its shell ran wrote there.
BOUNDARY = {
    "read": "Held by Claude Code's plan mode: a rule of its own, with no operating-system boundary under it.",
    "write": "Claude Code's own rules hold its file edits to the worktree. The commands it runs are not "
             "confined by the operating system: what they reach is what this host's Claude settings allow.",
}
OPTIONS = ("model", "effort", "provider")
SKILL = "/{name}"
SESSION_MARKERS = ("CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT", "CLAUDE_AGENT_SDK_VERSION")
SESSION_MARKER_PREFIXES = ("CLAUDE_CODE_",)
# Its terminal says so before it exits without any work (measured on the installed CLI).
LOST_SESSION = ("no conversation found with session id",)
OLD_BRAIN = "claude"
HOOKS = ("UserPromptSubmit", "Stop", "StopFailure", "PostToolUse", "PostToolUseFailure")
# The notifications that mean a dialog waits in its terminal for someone to answer it: each its own hook
# matcher, since a `|` between them is a command separator to the Windows `.cmd` shim.
DIALOGS = ("permission_prompt", "elicitation_dialog", "elicitation_url_dialog")
# What a turn's own settings say besides its hooks. A role's session spans every turn of the role, and one that
# fills its context with auto-compact off stops at *Context limit reached · /compact or /clear to continue*
# firing no hook, so the turn waits out its limit (measured: the operator's build, its session through nine plan
# rounds, the operator's own setting off). A turn's `--settings` outrank the user's. Compaction can still stop:
# `DISABLE_AUTO_COMPACT` or `DISABLE_COMPACT` in the worker's environment turns it off (documented; neither host
# sets either), and Claude gives up auto-compacting when the context refills at once after each summary
# (documented, *Autocompact is thrashing: …*) — such a stop is read off its screen (`halted`).
TURN_SETTINGS = {"autoCompactEnabled": True}
# Those stops as its interface draws them — the first measured, its words spaced or run together; the second as
# its docs spell it — and what it draws while it works, below anything it said before.
CONTEXT_STOPPED = re.compile(r"Context\s*limit\s*reached\W{0,5}/compact\s*or\s*/clear|Autocompact\s*is\s*thrashing",
                             re.I)
WORKING = re.compile(r"esc\s*to\s*interrupt", re.I)
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
        elif key == "provider":
            if value != "deepseek":
                problems.append((key, "must be deepseek, or omitted to use the CLI's existing configuration"))
        elif not (isinstance(value, str) and PLAIN_TOKEN.fullmatch(value)):
            problems.append((key, "must be a plain token"))
    if profile.get("provider") == "deepseek" and profile.get("model") not in ("deepseek-flash", "deepseek-v4-pro"):
        problems.append(("model", "DeepSeek requires deepseek-flash or deepseek-v4-pro"))
    return problems


def environment(role, env):
    """Overrides for the selected provider; empty values clear competing authentication and cloud routes."""
    if role.get("provider") != "deepseek":
        return {}
    key = env.get("DEEPSEEK_API_KEY")
    if not key:
        try:
            key = localenv.read().get("DEEPSEEK_API_KEY")
        except (OSError, UnicodeError) as exc:
            raise launch.ExecutorError("cannot read DeepSeek credentials from .env: %s" % type(exc).__name__) from None
    if not key or not key.strip():
        raise launch.ExecutorError("the DeepSeek profile requires DEEPSEEK_API_KEY in .env or this host's worker environment")
    model = role["model"]
    kept = dict.fromkeys(("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK",
                          "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY", "CLAUDE_CODE_USE_MANTLE",
                          "CLAUDE_CODE_USE_ANTHROPIC_AWS"), "")
    kept.update(ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic", ANTHROPIC_AUTH_TOKEN=key,
                ANTHROPIC_MODEL=model + "[1m]", CLAUDE_CODE_SUBAGENT_MODEL=model,
                CLAUDE_CODE_EFFORT_LEVEL=role.get("effort") or "max",
                CLAUDE_CODE_AUTO_COMPACT_WINDOW="786432", CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1")
    for size in ("OPUS", "SONNET", "HAIKU", "FABLE"):
        kept["ANTHROPIC_DEFAULT_%s_MODEL" % size] = model
    return kept


def configure(role, env, traced, private):
    """Provider routing in the private CLI settings, whose env outranks user and project settings."""
    values = environment(role, env)
    if not values:
        return env, traced
    settings = {}
    if traced:
        with open(traced, encoding="utf-8") as fh:
            settings = json.load(fh)
    settings.setdefault("env", {}).update(values)
    if traced:
        with open(traced, "w", encoding="utf-8") as fh:
            json.dump(settings, fh)
    else:
        traced = _files.private_file(private, "claude-provider.json", json.dumps(settings))
    return dict(env, **values), traced


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
        parts += ["--model", role["model"] + ("[1m]" if role.get("provider") == "deepseek" else "")]
    if role.get("effort"):
        parts += ["--effort", role["effort"]]
    if role["workspace_access"] == "read":
        parts += ["--permission-mode", "plan", "--disallowedTools", "AskUserQuestion", "ExitPlanMode"]
    else:
        # A role turn never waits on a permission prompt: what is not allowed is denied and the agent works on,
        # as a run with no one to ask always did. Edits in the worktree are allowed; an Edit rule also governs
        # writes. Not `bypassPermissions`: it skips the protected-path and working-directory checks, and nothing
        # here isolates the filesystem in their place.
        parts += ["--permission-mode", "dontAsk", "--allowedTools", "Edit(./**)",
                  "--disallowedTools", "AskUserQuestion", "EnterPlanMode"]
    return parts, minted


def host(argv, windows=WINDOWS, skills=None):
    """The skills a stage invokes read their references from this host's skills folder, outside the
    worktree; added as a working directory, it needs no approval to read."""
    skills = skills or os.path.join(os.path.expanduser("~"), ".claude", "skills")
    if os.path.isdir(skills):
        return list(argv) + ["--add-dir", os.path.realpath(skills)]
    return list(argv)


def readable(argv, folders):
    """The command with `folders` outside the worktree — a turn's attached prompt parts — readable unasked, and
    only readable: a rule allowing reads under each, never a working directory. Measured with `--add-dir`: a
    `cd` into a working directory is kept, so the agent's shell stayed in the folder, and its edit rule, `./**`,
    then refused the worktree; with the rule, its shell went back to the worktree after the command."""
    return list(argv) + [part for folder in folders
                         for part in ("--allowedTools", read_rule(os.path.realpath(folder)))]


def read_rule(path):
    """Claude's rule allowing reads under the absolute `path`. `//` starts an absolute path in its rules, and on
    Windows it matches a path in POSIX form: `C:\\Users\\alice` as `/c/Users/alice`."""
    drive = re.match(r"([A-Za-z]):[\\/]", path)
    if drive:
        path = "/%s/%s" % (drive.group(1).lower(), path[3:])
    return "Read(/%s/**)" % path.replace("\\", "/").rstrip("/")


def session_in(argv):
    for flag in ("--session-id", "--resume"):
        if flag in argv:
            return argv[argv.index(flag) + 1]
    return None


def _hook(sink):
    return " ".join('"%s"' % part if index < 3 else part for index, part in enumerate(sink))


def wire(argv, events, sink):
    """Its hooks in its settings — the file it names, or its own — and its auto-compact on (`TURN_SETTINGS`)."""
    hooks = {event: [{"hooks": [{"type": "command", "command": _hook(sink(event, "stdin"))}]}] for event in HOOKS}
    hooks["Notification"] = [
        {"matcher": kind, "hooks": [{"type": "command", "command": _hook(sink("Notification", "stdin"))}]}
        for kind in DIALOGS]
    argv = list(argv)
    if "--settings" in argv:
        path = argv[argv.index("--settings") + 1]
        with open(path, encoding="utf-8") as fh:
            settings = json.load(fh)
        settings.update(TURN_SETTINGS, hooks=hooks)
        # The file is the turn's private one; it keeps holding what it held.
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(settings, fh)
        return argv
    return argv[:1] + ["--settings", json.dumps(dict(TURN_SETTINGS, hooks=hooks))] + argv[1:]


def halted(text, events):
    """Why what it drew holds a turn gone silent — stopped at its context limit, waiting for `/compact` or
    `/clear`, which fires no hook — or None: only where that stop is the last of its kind it drew, its working line
    nowhere after it, and it had not ended its answer — after a `Stop`, while a background task of it runs, it is
    idle as it should be, whatever its answer quoted."""
    if events and events[-1].get("_hook") in ("Stop", "StopFailure"):
        return None
    stops = list(CONTEXT_STOPPED.finditer(text))
    if not stops or WORKING.search(text, stops[-1].end()):
        return None
    return ("Claude stopped at its context limit and waits for /compact or /clear, which fires no hook (it said: "
            "%s). Continue the run; if it stops there again, type /compact in the role's terminal within two minutes "
            "— with a focus on what to keep, when it says auto-compact is thrashing" % stops[-1].group(0))


def waiting(events):
    """Whether its turn's events end on a dialog still waiting in its terminal: a dialog's notification that
    no tool's end, prompt or end of the turn has followed yet."""
    for event in reversed(events):
        hook = event.get("_hook")
        if hook == "Notification" and event.get("notification_type") in DIALOGS:
            return True
        if hook in HOOKS:
            return False
    return False


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


def reply(events, prompt, session):
    """Its last answer in `session` to a prompt typed into its terminal other than the turn's — never the turn's
    own answer, which words typed during the turn may also have led to — with when its hook recorded it (`_at`,
    None in a record older than that)."""
    wanted = prompt.strip()
    done = completion(events, prompt, session)
    turn = done[1] if done and done[0] else None
    asked = {}
    said = None
    for event in events:
        if event.get("session_id") != session:
            continue
        if event.get("_hook") == "UserPromptSubmit":
            asked[event.get("prompt_id")] = (event.get("prompt") or "").strip()
        elif event.get("_hook") == "Stop":
            message = event.get("last_assistant_message") or ""
            if asked.get(event.get("prompt_id"), wanted) != wanted and message and message != turn:
                said = (message, event.get("_at"))
    return said


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
