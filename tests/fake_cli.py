"""A stand-in for the interactive `claude` and `codex` CLIs in a terminal, for `test_terminal.py`, and
for the program of the suite's own kind of agent (`stand_in.py`).

    fake_cli.py claude|codex|stand-in <the argv the real program would get>

It reads the turn's completion wiring exactly as the vendor does — Claude's hooks from its
`--settings`, Codex's `notify` from `-c`, the stand-in's `--on-finish` — and its last argument is the
prompt. What it does is named by a word in the prompt:

    complete     report the prompt submitted, draw a line, complete it
    foreign      first complete something else: another prompt, another session or thread
    failure      Claude only: end the turn with StopFailure
    exit         exit 3 without completing
    hang         never complete
    interrupt    wait for Esc, draw "Interrupted" and complete nothing; a typed line is a new prompt,
                 which completes — under its own prompt id for Claude, with every input so far for Codex,
                 and as the interrupted prompt's answer for the stand-in
    background   Claude only: first a Stop while a background task still runs, then the real one
    lost         say the session to resume does not exist, as each CLI does, and exit 1
    detach:<file>  start a detached process that writes its pid to <file>, then complete

After completing it stays running, echoing typed lines, as a live CLI does.
"""
import json
import os
import re
import subprocess
import sys
import time
import uuid

WINDOWS = sys.platform.startswith("win")


def settings_hooks(argv):
    if "--settings" not in argv:
        return {}
    value = argv[argv.index("--settings") + 1]
    if value.lstrip().startswith("{"):
        settings = json.loads(value)
    else:
        with open(value, encoding="utf-8") as fh:
            settings = json.load(fh)
    return settings.get("hooks") or {}


def claude_emit(hooks, event, payload):
    for group in hooks.get(event, []):
        for hook in group["hooks"]:
            subprocess.run(hook["command"], shell=True, input=json.dumps(payload).encode("utf-8"))


def codex_hooks(argv):
    """Codex's hooks as its `-c hooks.<event>=<TOML>` overrides give them: event -> its matcher groups."""
    import tomllib
    hooks = {}
    for index, value in enumerate(argv[:-1]):
        if value == "-c" and argv[index + 1].startswith("hooks."):
            key, _, toml = argv[index + 1].partition("=")
            hooks[key[len("hooks."):]] = tomllib.loads("v = " + toml)["v"]
    return hooks


def codex_emit(hooks, event, payload):
    # As Codex runs a hook: its command through the shell, the event on stdin.
    for group in hooks.get(event, []):
        for hook in group["hooks"]:
            subprocess.run(hook["command"], shell=True, input=json.dumps(payload).encode("utf-8"))


def on_finish(argv, payload):
    # A program given nowhere to say its turn ended says nothing, and runs on.
    if "--on-finish" in argv:
        command = json.loads(argv[argv.index("--on-finish") + 1])
        subprocess.run(command, input=json.dumps(payload).encode("utf-8"))


def draw(text):
    sys.stdout.write(text + "\r\n")
    sys.stdout.flush()


def read_key():
    if WINDOWS:
        import msvcrt
        return msvcrt.getwch()
    return os.read(0, 1).decode("utf-8", "replace")


def raw_input_mode():
    if not WINDOWS:
        import tty
        tty.setraw(0)


def detach(pid_file):
    """A process of its own session or group that writes its pid and outlives this one."""
    code = "import os, sys, time\nopen(sys.argv[1], 'w').write(str(os.getpid()))\ntime.sleep(600)\n"
    if WINDOWS:
        # Its own group, and a console of its own that has no window. With no console at all, the
        # interpreter a venv's python.exe launches would be given a new one — shown, and taking focus.
        subprocess.Popen([sys.executable, "-c", code, pid_file], creationflags=subprocess.CREATE_NO_WINDOW
                         | subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        subprocess.Popen([sys.executable, "-c", code, pid_file], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    while not os.path.exists(pid_file) or not open(pid_file).read():
        time.sleep(0.05)


def completer(brain, argv, prompt, foreign=False):
    """How a turn of this brain ends, wired as the vendor wires it: returns `complete(message, ...)`.

    Emits what the vendor emits before the completion itself — Claude's `UserPromptSubmit`, Codex's
    title turn in a thread of its own — so a caller only says how the turn ends. `foreign` first
    completes something that is not this turn: another prompt, another session or thread.
    """
    if brain == "claude":
        hooks = settings_hooks(argv)
        session = argv[argv.index("--session-id") + 1] if "--session-id" in argv else argv[argv.index("--resume") + 1]
        prompt_id = str(uuid.uuid4())
        state = {"prompt_id": prompt_id}

        def complete(message, failure=False, typed=None, running=False):
            if typed is not None:
                # A prompt the operator typed is a prompt of its own.
                state["prompt_id"] = str(uuid.uuid4())
                claude_emit(hooks, "UserPromptSubmit", {"session_id": session, "prompt_id": state["prompt_id"],
                                                        "prompt": typed})
            event = "StopFailure" if failure else "Stop"
            tasks = [{"id": "b1", "type": "shell", "status": "running"}] if running else []
            claude_emit(hooks, event, {"session_id": session, "prompt_id": state["prompt_id"], "hook_event_name": event,
                                       "last_assistant_message": message, "background_tasks": tasks,
                                       "error": "rate_limit" if failure else None})

        if foreign:
            claude_emit(hooks, "Stop", {"session_id": session, "prompt_id": str(uuid.uuid4()),
                                        "last_assistant_message": "someone else's turn"})
            claude_emit(hooks, "Stop", {"session_id": str(uuid.uuid4()), "prompt_id": prompt_id,
                                        "last_assistant_message": "another session"})
        claude_emit(hooks, "UserPromptSubmit", {"session_id": session, "prompt_id": prompt_id, "prompt": prompt})
        return complete
    elif brain == "stand-in":
        thread = argv[argv.index("--thread") + 1] if "--thread" in argv else str(uuid.uuid4())

        def complete(message, failure=False, typed=None, running=False):
            on_finish(argv, {"thread": thread, "prompt": prompt, "answer": message})

        if foreign:
            on_finish(argv, {"thread": thread, "prompt": "something else", "answer": "someone else's turn"})
        return complete
    else:
        resumed = len(argv) > 1 and argv[0] == "resume"
        thread = argv[1] if resumed else str(uuid.uuid4())
        hooks = codex_hooks(argv)
        state = {"turn": str(uuid.uuid4())}

        def complete(message, failure=False, typed=None, running=False):
            if typed is not None:
                # A prompt the operator typed begins a turn of its own.
                state["turn"] = str(uuid.uuid4())
                codex_emit(hooks, "UserPromptSubmit", {"session_id": thread, "turn_id": state["turn"],
                                                       "prompt": typed})
            codex_emit(hooks, "Stop", {"session_id": thread, "turn_id": state["turn"], "hook_event_name": "Stop",
                                       "stop_hook_active": False, "last_assistant_message": message})

        # Codex's own work — a catch-up summary — runs in a thread of its own and comes first.
        side, side_turn = str(uuid.uuid4()), str(uuid.uuid4())
        codex_emit(hooks, "UserPromptSubmit", {"session_id": side, "turn_id": side_turn,
                                               "prompt": "Write a brief catch-up for: " + prompt})
        codex_emit(hooks, "Stop", {"session_id": side, "turn_id": side_turn, "last_assistant_message": '{"x":1}'})
        if foreign:
            codex_emit(hooks, "Stop", {"session_id": thread, "turn_id": str(uuid.uuid4()),
                                       "last_assistant_message": "someone else's turn"})
        codex_emit(hooks, "UserPromptSubmit", {"session_id": thread, "turn_id": state["turn"], "prompt": prompt})
        return complete


def codex_hold(argv):
    """Codex's review of hooks, as measured on 0.159, drawn before anything else: each hook given with `-c`, or in
    the repository's `.codex/hooks.json`, that its config does not trust with its present definition — how many —
    and, on its second choice, every one of them trusted, recorded in `[hooks.state]` with a hash of its definition.
    Until a key is read, nothing else happens."""
    import hashlib
    import tomllib
    home = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    config = os.path.join(home, "config.toml")
    try:
        with open(config, encoding="utf-8") as fh:
            state = (tomllib.loads(fh.read()).get("hooks") or {}).get("state") or {}
    except FileNotFoundError:
        state = {}
    snake = lambda event: re.sub(r"(?<!^)(?=[A-Z])", "_", event).lower()   # noqa: E731
    root = "C:\\<session-flags>\\config.toml" if WINDOWS else "/<session-flags>/config.toml"
    given = {"%s:%s:0:0" % (root, snake(event)): groups for event, groups in codex_hooks(argv).items()}
    project = os.path.join(os.getcwd(), ".codex", "hooks.json")
    if os.path.exists(project):
        with open(project, encoding="utf-8") as fh:
            theirs = json.load(fh).get("hooks") or {}
        given.update({"%s:%s:0:0" % (project, snake(event)): groups for event, groups in theirs.items()})
    wanted = {key: "sha256:" + hashlib.sha256(json.dumps(groups, sort_keys=True).encode("utf-8")).hexdigest()
              for key, groups in given.items()}
    new = {key: value for key, value in wanted.items() if (state.get(key) or {}).get("trusted_hash") != value}
    if new:
        draw("Hooks need review %d %s new or changed." % (len(new), "hook is" if len(new) == 1 else "hooks are"))
        draw("1. Review hooks 2. Trust all and continue 3. Continue without trusting")
        if read_key() == "2":
            os.makedirs(home, exist_ok=True)
            with open(config, "a", encoding="utf-8") as fh:
                for key, value in new.items():
                    fh.write("\n[hooks.state.'%s']\ntrusted_hash = \"%s\"\n" % (key, value))


def codex_review(argv):
    """Codex started with no prompt: its review of hooks, then its composer, until it is ended."""
    codex_hold(argv)
    draw("Ask Codex to do anything")
    while True:
        read_key()


def main():
    brain, argv = sys.argv[1], sys.argv[2:]
    if brain == "codex" and "--" not in argv:
        return codex_review(argv)
    if brain == "codex":
        # Its prompt waits until its review of hooks is answered.
        codex_hold(argv)
    # As both CLIs parse it: `--add-dir` takes every value up to the next option or `--`.
    if "--add-dir" in argv and "--" not in argv:
        sys.exit("no prompt: --add-dir took it as a directory")
    prompt = argv[-1]
    words = prompt.split()
    raw_input_mode()
    draw("fake %s ready" % brain)
    if "lost" in words:
        draw({"claude": "No conversation found with session ID: x",
              "stand-in": "Error: no such thread x"}.get(
            brain, "ERROR: No saved session found with ID x. Run `codex resume` without an ID"))
        sys.exit(1)
    complete = completer(brain, argv, prompt, foreign="foreign" in words)
    time.sleep(0.3)
    if "exit" in words:
        draw("giving up")
        sys.exit(3)
    if "hang" in words:
        while True:
            time.sleep(1)
    if "failure" in words:
        complete("", failure=True)
    elif "background" in words:
        complete("Waiting for the command to complete...", running=True)
        time.sleep(1.5)
        complete("done background")
    elif "interrupt" in words:
        draw("working")
        while read_key() != "\x1b":
            pass
        draw("Interrupted")
        typed = ""
        while True:
            key = read_key()
            if key in ("\r", "\n"):
                break
            typed += key
        complete("resumed with " + typed, typed=typed)
    else:
        for word in words:
            if word.startswith("detach:"):
                detach(word[len("detach:"):])
        draw("answer for " + words[0])
        complete("done " + words[0])
    while True:
        key = read_key()
        if not key:
            return
        sys.stdout.write(key)
        sys.stdout.flush()


if __name__ == "__main__":
    main()
