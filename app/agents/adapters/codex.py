"""Codex, OpenAI's CLI, as a kind of agent.

A turn is `codex` started again in the role's terminal: a new session, whose thread its first turn completes
in, or that thread resumed by id (`codex resume <thread>`). It runs under its own sandbox — read-only for a
read-only role, workspace-write otherwise — and never asks for approval. Live web search is on, and its
reasoning summaries are asked for, since they make a verdict legible; both through its validated config, so
a vendor rename fails loudly. On Windows it runs its unelevated sandbox: the elevated one starts its helper
through an administrator prompt, which a worker outside the interactive desktop can never show, and every
command the agent ran would fail with error 1223.

Its turn ends on its own hooks, each given its event on stdin: the `Stop` of a turn that its `UserPromptSubmit`
began with our prompt, or with any prompt submitted after it, in the expected thread. Its catch-up summaries
and other turns of its own run in threads of their own and never end the turn. Its answer is the turn's last
agent message. Never its `notify`: that event carries every input of the thread so far and is given as the
program's last argument, which on a long thread outgrew Windows' command line — measured, `os error 206`, the
event never written and the turn never ended. The hooks are one definition on every turn — the turn's events
file named in the environment, which Codex passes on to them (measured) — since Codex runs a hook only once it
has trusted that exact definition (`hooks_trust`); a start its review of hooks still holds is read off its screen
(`held`).

Its trust record: `[projects.'<repo>'] trust_level = "trusted"` in `~/.codex/config.toml`, or in the root
`CODEX_HOME` names — only ever appended, never with a key it already holds, since two tables of one key are
not valid TOML and would break the CLI; an explicit `untrusted` is the operator's own decision and left alone.

Its tracing: its own uploader, the Langfuse plugin's, run after a turn with the turn's rollout — not a Stop
hook: a hook that uploaded would upload every turn a second time, beside the plugin's own. The uploader built with the parent-trace and turn-lifecycle changes
nests its turns under their step; a build lacking either is reported. Its reasoning summaries
are read from the rollout, after the last `task_started`.
"""
import glob
import json
import os
import re
import sys
import time

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
# Its hooks, the events a turn's end is read from; and a part of a hook's command that needs no quoting in the
# shell Codex runs it with, on either host.
HOOK_EVENTS = ("UserPromptSubmit", "Stop")
PLAIN_PART = re.compile(r"[A-Za-z0-9_./:@%+=,-]+")
# Its review of hooks new or changed, as its interface draws it (measured, 0.159): how many wait, its answer that
# trusts them — the second of its choices, which trusts every hook waiting, whoever's — and its composer, drawn
# once it is ready; a dialog comes within a moment of the composer. Its config keys a hook's trust by the event in
# snake case.
HOOK_DIALOG = re.compile(r"(\d+)\s*hooks?\b.{0,16}?new\s*or\s*changed", re.I | re.S)
HOOK_READY = re.compile(r"Ask Codex to do anything|for shortcuts", re.I)
# Its question whether to trust the folder it starts in, drawn before anything else where the folder's repository
# is not trusted (measured, 0.166) — words run together as its interface draws them.
FOLDER_DIALOG = re.compile(r"Trust\s*this\s*folder\?", re.I)
TRUST_ALL = b"2\r"
STARTED_ALONE = ["-c", "check_for_update_on_startup=false"]
HOOK_KEYS = {"UserPromptSubmit": "user_prompt_submit", "Stop": "stop"}
TRUST_SECONDS = 45
DIALOG_SECONDS = 4
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
    # Drawn inline, as Claude is: on its default alternate screen it keeps no scrollback and takes every mouse
    # event, so its terminal on the page could not be scrolled back through the session (measured on both hosts).
    parts += ["--no-alt-screen"]
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


def hook_flags(sink):
    """Its hooks for a turn, as `-c` overrides: each event given on stdin to `turn_hook.py`, whose events file is
    `-` — the turn's, named in the environment — so the definition is the same on every turn."""
    flags = []
    for label in HOOK_EVENTS:
        command = " ".join(part if PLAIN_PART.fullmatch(part) else json.dumps(part)
                           for part in sink(label, "stdin", events="-"))
        flags += ["-c", "hooks.%s=[{hooks=[{type=\"command\",command=%s}]}]" % (label, json.dumps(command))]
    return flags


def wire(argv, events, sink):
    return list(argv) + hook_flags(sink)


class HooksRefused(RuntimeError):
    """Its hooks could not be trusted here without trusting others: the operator reviews those first."""


def hooks_trust(sink, start, record, home=None):
    """Its hooks trusted on this host before a turn, so its review dialog never holds a turn: Codex runs a hook only
    once it has trusted that exact definition (`[hooks.state]` in its config, a hash only it computes). The
    definition is remembered in `record` with the hashes Codex wrote for it; while Codex still holds those, they
    are trusted. Otherwise its interface is started for a moment twice — `start(args)`, no prompt, no model. First
    without ours: a hook it asks to review then is another's — the operator's, a plugin's or the repository's — and
    fails the step, nothing answered. Then with ours, a moment later: all it can ask to review now is ours, so its
    *Trust all*, which trusts every hook waiting, is answered; its hashes are then remembered. Raises HooksRefused
    when other hooks wait for review, or when no trust can be read. True when it trusted them now."""
    flags = hook_flags(sink)
    definition = json.dumps(flags)
    # Keyed by the config the trust lives in too: two homes of Codex on one host — a demo's own — never share it.
    definition = config_path(home) + "\n" + definition
    remembered = _remembered(record).get(definition)
    if remembered and _hook_hashes(home) == remembered:
        return False
    _review(start(STARTED_ALONE), home, None)
    before = _all_hooks(home)
    answered = _review(start(STARTED_ALONE + flags), home, before)
    hashes = _hook_hashes(home)
    others = {key: value for key, value in _all_hooks(home).items() if key not in hashes and before.get(key) != value}
    if others:
        raise HooksRefused("trusting the orchestra's hooks also trusted %s on this host: review them with /hooks in "
                           "Codex" % ", ".join(sorted(others)))
    # What it remembers of a config that is gone — a demo's own home, removed with it — goes too.
    kept = {key: value for key, value in _remembered(record).items() if os.path.exists(key.split("\n", 1)[0])}
    _files.replace(record, json.dumps(dict(kept, **{definition: hashes}), indent=1) + "\n")
    return answered


def _review(cli, home, before):
    """Codex, started for a moment, read until it is ready, then ended. With `before` None it was started without
    our hooks, so any hook it asks to review is another's: refused, nothing answered. Otherwise with ours: its dialog
    answered *Trust all* — never for more hooks than ours — until it holds a trust for each of ours that its config
    did not hold `before`. True when it answered."""
    try:
        answered, ready_at = False, None
        deadline = time.monotonic() + TRUST_SECONDS
        while time.monotonic() < deadline:
            seen = cli.text()
            if FOLDER_DIALOG.search(seen):
                raise HooksRefused("Codex asks whether to trust this folder on this host, which a turn's repository "
                                   "is trusted for before it starts: start codex in it and answer, or check its "
                                   "trust record")
            dialog = HOOK_DIALOG.search(seen)
            if dialog and not answered:
                waiting = int(dialog.group(1))
                if before is None or waiting > len(HOOK_EVENTS):
                    raise HooksRefused(
                        "Codex on this host has hooks waiting for review that are not the orchestra's (%d) — yours, a "
                        "plugin's or the repository's — and its Trust all would trust them with the orchestra's: "
                        "review them with /hooks in Codex started in the run's worktree, then continue the run"
                        % (waiting if before is None else waiting - len(HOOK_EVENTS)))
                cli.write(TRUST_ALL)
                answered = True
            hashes = _hook_hashes(home)
            whole = before is None or (len(hashes) == len(HOOK_EVENTS) and all(hashes.values()))
            if answered and whole and hashes != _ours(before):
                return True
            if not answered and whole and HOOK_READY.search(seen):
                # Ready with no dialog: nothing waits — or, ours given, Codex trusts them already. A dialog drawn
                # after the composer comes within a moment of it, so ready is believed only once that moment passed.
                ready_at = ready_at or time.monotonic()
                if time.monotonic() - ready_at >= DIALOG_SECONDS:
                    return False
            time.sleep(0.2)
        raise HooksRefused("Codex's review of hooks could not be read on this host within %ds: start codex in the "
                           "run's worktree and review its hooks with /hooks" % TRUST_SECONDS)
    finally:
        cli.end()


def held(text):
    """Why what Codex drew before its turn began holds the turn for the operator, or None: its review of hooks new or
    changed — another's, or ours once it no longer holds them trusted as remembered — or its question whether to
    trust the folder."""
    dialog = HOOK_DIALOG.search(text)
    if dialog:
        return ("Codex waits for hooks to be reviewed before it starts the turn (%s): review what /hooks lists in "
                "Codex started in the run's worktree on this host — nothing, when only the orchestra's own wait — "
                "then continue the run, which trusts the orchestra's own again" % dialog.group(1))
    if FOLDER_DIALOG.search(text):
        return ("Codex asks whether to trust this folder before it starts the turn: start codex in the run's worktree "
                "on this host and answer, then continue the run")
    return None


def _remembered(record):
    """The definitions trusted before, each with the hashes Codex wrote for it; empty when there are none."""
    try:
        known = json.loads(_files.read(record) or "{}")
    except ValueError:
        return {}
    return known if isinstance(known, dict) else {}


def _all_hooks(home=None):
    """Every hook its config records trust for: key -> trusted hash; empty when the config cannot be read."""
    try:
        import tomllib
        state = ((tomllib.loads(_files.read(config_path(home))).get("hooks") or {}).get("state") or {})
    except Exception:                               # noqa: BLE001 - unreadable: nothing is trusted
        return {}
    return {key: (value or {}).get("trusted_hash") for key, value in state.items() if isinstance(value, dict)}


def _ours(hooks):
    """Of a config's hook trust, what it holds for ours: given with `-c`, one per event, each the first of its
    group, keyed `<root>\\<session-flags>\\config.toml:<event>:0:0` (measured)."""
    wanted = {"%s:0:0" % HOOK_KEYS[label] for label in HOOK_EVENTS}
    return {key: value for key, value in hooks.items()
            if "<session-flags>" in key and ":".join(key.rsplit(":", 3)[1:]) in wanted}


def _hook_hashes(home=None):
    return _ours(_all_hooks(home))


def completion(events, prompt, session):
    """The `Stop` of a turn its `UserPromptSubmit` began with our prompt — or with a prompt submitted after it in
    this turn, the operator steering it — in the expected thread, or the thread our prompt began a turn in."""
    wanted = prompt.strip()
    thread, turns = session, set()
    for event in events:
        if thread and event.get("session_id") != thread:
            continue
        hook = event.get("_hook")
        if hook == "UserPromptSubmit":
            if turns or (event.get("prompt") or "").strip() == wanted:
                thread = thread or event.get("session_id")
                turns.add(event.get("turn_id"))
        elif hook == "Stop" and event.get("turn_id") in turns:
            return True, event.get("last_assistant_message") or "", thread
    return None


def reply(events, prompt, session):
    """Its last answer in its thread `session` to a prompt typed into its terminal other than the turn's, never the
    turn's own answer, with when its hook recorded it (`_at`, None in a record older than that). Its own
    catch-up summaries run in threads of their own. A turn recorded before its hooks were wired is read from its
    `notify` events: a completion whose newest input is not the prompt."""
    wanted = prompt.strip()
    done = completion(events, prompt, session)
    turn = done[1] if done and done[0] else None
    asked, said = {}, None
    for event in events:
        hook = event.get("_hook")
        if hook == "notify" and event.get("type") == "agent-turn-complete" and event.get("thread-id") == session:
            inputs = [text.strip() for text in event.get("input-messages") or [] if isinstance(text, str)]
            if inputs and inputs[-1] != wanted and event.get("last-assistant-message"):
                said = (event["last-assistant-message"], event.get("_at"))
        elif event.get("session_id") != session:
            continue
        elif hook == "UserPromptSubmit":
            asked[event.get("turn_id")] = (event.get("prompt") or "").strip()
        elif hook == "Stop":
            message = event.get("last_assistant_message") or ""
            if asked.get(event.get("turn_id"), wanted) != wanted and message and message != turn:
                said = (message, event.get("_at"))
    return said


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
