"""Codex, OpenAI's CLI, as a kind of agent.

A turn is `codex` started again in the role's terminal: a new session, whose thread its first turn completes
in, or that thread resumed by id (`codex resume <thread>`). It runs under its own sandbox — read-only for a
read-only role, workspace-write otherwise — and never asks for approval. Live web search is on, and its
reasoning summaries are asked for, since they make a verdict legible; both through its validated config, so
a vendor rename fails loudly. On Windows it runs its unelevated sandbox: the elevated one starts its helper
through an administrator prompt, which a worker outside the interactive desktop can never show, and every
command the agent ran would fail with error 1223.

Its turn ends on its `notify` program: the first `agent-turn-complete` in the expected thread whose inputs —
the thread's prompts so far — include ours. Its title turn runs in a thread of its own, whose input only
quotes the prompt, and never ends the turn. Its answer is the turn's last agent message.

Its trust record: `[projects.'<repo>'] trust_level = "trusted"` in `~/.codex/config.toml`, or in the root
`CODEX_HOME` names — only ever appended, never with a key it already holds, since two tables of one key are
not valid TOML and would break the CLI; an explicit `untrusted` is the operator's own decision and left alone.

Its tracing: its own uploader, the Langfuse plugin's, run after a turn with the turn's rollout — Codex's Stop
hook cannot do it (measured: it does not pass its environment to hook subprocesses), and a hook that did
would upload every turn a second time. The uploader built with the parent-trace and turn-lifecycle changes
nests its turns under their step; a build lacking either is reported. Its reasoning summaries
are read from the rollout, after the last `task_started`.
"""
import glob
import json
import os
import re
import sys

from app.agents.adapters import _files

NAME = "Codex"
EXECUTABLE = "codex"
ACCESS = ("read", "write")
# Its own sandbox, which the operating system enforces on everything a turn runs. Measured on both hosts
# with `codex sandbox`, no model in it, in a linked worktree: read-only wrote nowhere; workspace-write wrote
# in the worktree and the temporary folder and nowhere else, and neither could stage — a linked worktree's
# index lies outside it. So does a tool's cache or environment kept outside the worktree: one that needs it
# does not start.
BOUNDARY = {
    "read": "Enforced by Codex's own sandbox: nothing it runs can write anywhere.",
    "write": "Enforced by Codex's own sandbox: nothing it runs can write outside the worktree and the "
             "temporary folder, or stage in git. A tool that keeps its cache or environment elsewhere "
             "cannot run in its turn.",
}
OPTIONS = ("model", "effort")
SKILL = "${name}"
SESSION_MARKERS = ()
SESSION_MARKER_PREFIXES = ()
LOST_SESSION = ("no saved session found with id",)
OLD_BRAIN = "codex"
WINDOWS = sys.platform.startswith("win")
WINDOWS_FLAGS = ["-c", 'windows.sandbox="unelevated"']
PLAIN_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")
CONFIG_FILE = os.path.join(".codex", "config.toml")
TRUSTED = 'trust_level = "trusted"'
# Where a table begins: a header at the start of a line. Only removal uses this; what the config already
# holds is read by the TOML parser itself.
_HEADER = re.compile(r"^\[[^\n\]]*\]", re.M)
_UNPARSED = object()
# The plugin's uploader, built with the changes the trace needs and kept under the orchestration's own
# folder on each host, since Codex restores its plugin cache whenever it starts. None: that folder's.
PLUGIN = None
ROLLOUTS = "~/.codex/sessions/*/*/*/rollout-*-%s.jsonl"
UPLOAD_SECONDS = 60
# What the trace needs of the plugin's build: a name each change adds to the bundle, and what goes wrong
# without it. The first is the documented input; the second, the option the turn-lifecycle change adds.
PLUGIN_NEEDS = (
    ("LANGFUSE_CODEX_TRACEPARENT", "its turns will not nest under their stage"),
    ("finalizeTurnId", "empty duplicate turns will appear under later stages"),
)


def validate(profile):
    problems = []
    for key, value in profile.items():
        if key == "kind":
            continue
        if key not in OPTIONS:
            problems.append((key, "Codex takes %s, not %r" % (" and ".join(OPTIONS), key)))
        elif not (isinstance(value, str) and PLAIN_TOKEN.fullmatch(value)):
            problems.append((key, "must be a plain token"))
    return problems


def command(role, resume_id, traced=None):
    sandbox = "read-only" if role["workspace_access"] == "read" else "workspace-write"
    parts = [EXECUTABLE, "resume", resume_id] if resume_id else [EXECUTABLE]
    # Both through its validated config, so a vendor rename fails loudly: its reasoning summaries, off by
    # default for this account (measured) and what makes a verdict legible; and live web search, since the
    # roles prefer current practice over folklore and the architect may challenge the task itself (D15).
    parts += ["-c", 'model_reasoning_summary="detailed"']
    parts += ["-c", 'web_search="live"', "--sandbox", sandbox, "--ask-for-approval", "never"]
    if role.get("model"):
        parts += ["--model", role["model"]]
    if role.get("effort"):
        # No flag for this; the documented config key is validated strictly, so a vendor rename fails loudly.
        parts += ["-c", 'model_reasoning_effort="%s"' % role["effort"]]
    return parts, None


def host(argv, windows=WINDOWS, skills=None):
    return list(argv) + WINDOWS_FLAGS if windows else list(argv)


def session_in(argv):
    return argv[argv.index("resume") + 1] if "resume" in argv[1:2] else None


def wire(argv, events, sink):
    return list(argv) + ["-c", "notify=%s" % json.dumps(sink("notify", "argument"))]


def completion(events, prompt, session):
    wanted = prompt.strip()
    for event in events:
        if event.get("_hook") != "notify" or event.get("type") != "agent-turn-complete":
            continue
        if wanted not in [text.strip() for text in event.get("input-messages") or []]:
            continue
        if session and event.get("thread-id") != session:
            continue
        return True, event.get("last-assistant-message") or "", event.get("thread-id")
    return None


def output(message, session):
    """The turn's thread and final message, as the events `codex exec --json` prints them."""
    return "\n".join(json.dumps(event) for event in (
        {"type": "thread.started", "thread_id": session},
        {"type": "item.completed", "item": {"type": "agent_message", "text": message}})) + "\n"


def session(out, minted):
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "thread.started" and event.get("thread_id"):
            return event["thread_id"]
    return None


def message_of(event):
    item = event.get("item") if isinstance(event, dict) else None
    if isinstance(item, dict) and item.get("type") == "agent_message":
        return item.get("text")
    return None


def final_message(out):
    """A turn's answer is its last agent message, and nothing else it printed is one."""
    said = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                said.append(message_of(json.loads(line)))
            except ValueError:
                pass
    said = [message for message in said if message]
    return said[-1] if said else ""


def _home():
    return os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")


def skill_folders(name, repo):
    return [os.path.join(root, name) for root in skill_roots(repo)]


def skill_roots(repo):
    return [os.path.join(_home(), "skills"),
            os.path.join(os.path.expanduser("~"), ".agents", "skills"),
            os.path.join(repo, ".agents", "skills")]


# ---- trust ----------------------------------------------------------------------------------

def config_path(home=None):
    """Its config file on this host. `CODEX_HOME` names the root that holds it."""
    if home:
        return os.path.join(home, CONFIG_FILE)
    named = os.environ.get("CODEX_HOME")
    if named:
        return os.path.join(named, "config.toml")
    return os.path.join(os.path.expanduser("~"), CONFIG_FILE)


def trust_key(repo):
    """The repository as a TOML key: a literal string, so a Windows path keeps its backslashes."""
    return "'%s'" % repo if "'" not in repo else json.dumps(repo)


def _tables(text):
    """`text` split where a table begins: what precedes the first one, then each table whole. A table runs
    to the next header, so a table that follows the one we remove is never part of it."""
    headers = list(_HEADER.finditer(text))
    if not headers:
        return [text]
    blocks = [text[:headers[0].start()]] if headers[0].start() else []
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        blocks.append(text[header.start():end])
    return blocks


def _state(text, repo):
    """What the config already says about `repo`: its `trust_level`, None when absent, or unreadable.

    Read by the TOML parser, never by matching text: the operator may write a table in any valid shape — a
    comment after the header, either kind of quoting — and a table we failed to see is a table we would
    append a second time, which is not valid TOML and would break the CLI.
    """
    try:
        import tomllib
        projects = tomllib.loads(text).get("projects") or {}
    except Exception:                               # noqa: BLE001 - unreadable: touch nothing
        return _UNPARSED
    wanted = _files.same(repo)
    for key, value in projects.items():
        if _files.same(key) == wanted:
            return (value or {}).get("trust_level") or ""
    return None


def trust_ensure(repo, home=None):
    path = config_path(home)
    text = _files.read(path)
    if _state(text, repo) is not None:
        # Already there — trusted, untrusted, or a shape we do not own. Never a second table.
        return False
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    # Appended, never rewritten: the file is the operator's, with their own comments and order.
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write("\n[projects.%s]\n%s\n" % (trust_key(repo), TRUSTED))
    return True


def trust_forget(repo, home=None):
    path = config_path(home)
    text = _files.read(path)
    if _state(text, repo) != "trusted":
        return False
    header = "[projects.%s]" % trust_key(repo)
    kept, removed = [], False
    for block in _tables(text):
        lines = block.splitlines()
        ours = lines and lines[0].strip() == header and [line.strip() for line in lines[1:] if line.strip()] == [TRUSTED]
        if ours:
            removed = True
            continue
        kept.append(block)
    if not removed:
        return False                                # trusted, but not in the shape we wrote it
    _files.replace(path, "".join(kept))
    return True


# ---- tracing --------------------------------------------------------------------------------

def _plugin():
    if PLUGIN:
        return PLUGIN
    from app.foundation import envpath
    return os.path.join(envpath.environment_root(), "codex-observability-plugin", "dist", "index.mjs")


def _rollout(session_id):
    found = glob.glob(os.path.expanduser(ROLLOUTS % session_id))
    return found[-1] if found else None


def trace_env(context):
    # Deliberately nothing: enabling the vendor's hook from here would upload every turn a second time —
    # measured: one copy nested under the stage from the upload below, and one in its own trace. Ingested
    # observations are immutable, so the one uploader is the explicit one, which alone can carry the step's
    # parent context.
    return None


def reasoning(session_id):
    """The reasoning summaries of the session's most recent run, as readable text: one session spans every
    stage its role takes, and each run of it opens with a `task_started`. Raises OSError when its rollout
    cannot be read."""
    path = _rollout(session_id) if session_id else None
    if not path:
        return None
    current = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            payload = record.get("payload") or record
            if payload.get("type") == "task_started":
                current = []
            elif payload.get("type") == "reasoning":
                for item in payload.get("summary") or []:
                    text = (item.get("text") if isinstance(item, dict) else str(item)) or ""
                    if text.strip():
                        current.append(text.strip())
    return "\n\n".join(current) or None


def _last_turn(path):
    """The id of a rollout's most recent turn, as Codex's Stop hook reports it; None when it cannot be read."""
    last = None
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                payload = (record.get("payload") if isinstance(record, dict) else None) or {}
                if payload.get("type") == "task_started" and payload.get("turn_id"):
                    last = payload["turn_id"]
    except OSError:
        return None
    return last


def _missing(bundle):
    """What the installed plugin build lacks, as the consequence of each gap."""
    try:
        with open(bundle, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return [effect for _, effect in PLUGIN_NEEDS]
    return [effect for marker, effect in PLUGIN_NEEDS if marker not in text]


def upload(session_id, context):
    """The finished turn's transcript for the vendor's own uploader: the notes to report, and the uploader
    to run — its argv, the environment it adds, its input — or None when there is none to run."""
    if not session_id or not context:
        return None
    notes = []
    lost = "the %s's turns were not uploaded" % context["metadata"]["role"]
    uploader = sorted(glob.glob(os.path.expanduser(_plugin())))
    missing = _missing(uploader[-1]) if uploader else []
    if missing:
        # A plugin upgrade can replace a build that has these with one that lacks them. The upload still
        # works, but the trace quietly degrades in exactly the ways the build was changed to prevent.
        notes.append({"key": "codex plugin build",
                      "say": "plugin build at %s: %s (see tools/README.md, 'The Codex plugin must support a "
                             "parent trace')" % (uploader[-1], "; ".join(missing)),
                      "degraded": "codex plugin build: %s" % "; ".join(missing)})
    rollout = _rollout(session_id)
    if not uploader or not rollout:
        notes.append({"key": "codex upload",
                      "say": "no uploader (%d) or rollout (%d) for %s" % (len(uploader), int(bool(rollout)),
                                                                          session_id),
                      "degraded": "%s: no uploader (%d) or rollout (%d)" % (lost, len(uploader), int(bool(rollout)))})
        return {"notes": notes, "run": None}
    env = {"TRACE_TO_LANGFUSE": "true",
           # The plugin's own default host is Langfuse Cloud: name ours rather than rely on a user-level file.
           "LANGFUSE_CODEX_BASE_URL": context["base_url"],
           "PLUGIN_ROOT": os.path.dirname(os.path.dirname(uploader[-1])),
           "LANGFUSE_CODEX_TRACE_SEED": context["seed"],
           # Tags and metadata reach the plugin's rows only when it is not attached to a stage. The tags are
           # the few every row carries; the run's own values belong in the metadata.
           "LANGFUSE_CODEX_TAGS": ",".join(context["tags"]),
           # Its session cannot be renamed, so it carries the work item inside it instead.
           "LANGFUSE_CODEX_METADATA": json.dumps(context["metadata"])}
    if context.get("traceparent"):
        # Attach the turns to the step that caused them. A build without parent-context support ignores it
        # and degrades to a correlated separate session.
        env["LANGFUSE_CODEX_TRACEPARENT"] = context["traceparent"]
    payload = {"session_id": session_id, "transcript_path": rollout, "hook_event_name": "Stop",
               # Codex's own Stop hook names the turn that just ended, and the plugin finalizes only that one.
               # Without it, the empty record a resumed session writes before its next turn is exported as a
               # turn of its own, under every later stage.
               "turn_id": _last_turn(rollout)}
    return {"notes": notes,
            "run": {"argv": ["node", uploader[-1]], "env": env, "input": json.dumps(payload),
                    "timeout": UPLOAD_SECONDS,
                    "failed": lost}}
