"""A stand-in for the interactive `claude` and `codex` CLIs in a terminal, for `test_terminal.py`.

    fake_cli.py claude|codex <the argv the real CLI would get>

It reads the turn's completion wiring exactly as the vendor does — Claude's hooks from its
`--settings`, Codex's `notify` from `-c` — and its last argument is the prompt. What it does
is named by a word in the prompt:

    complete     report the prompt submitted, draw a line, complete it
    foreign      first complete something else: another prompt, another session or thread
    failure      Claude only: end the turn with StopFailure
    exit         exit 3 without completing
    hang         never complete
    interrupt    wait for Esc, draw "Interrupted" and complete nothing; a typed line is a new prompt,
                 which completes — under its own prompt id for Claude, with every input so far for Codex
    background   Claude only: first a Stop while a background task still runs, then the real one
    lost         say the session to resume does not exist, as each CLI does, and exit 1
    detach:<file>  start a detached process that writes its pid to <file>, then complete

After completing it stays running, echoing typed lines, as a live CLI does.
"""
import json
import os
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


def codex_notify(argv, payload):
    for index, value in enumerate(argv):
        if value == "-c" and argv[index + 1].startswith("notify="):
            command = json.loads(argv[index + 1][len("notify="):])
            subprocess.run(command + [json.dumps(payload)])


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
        subprocess.Popen([sys.executable, "-c", code, pid_file], creationflags=0x00000008 | 0x00000200)
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
    else:
        resumed = len(argv) > 1 and argv[0] == "resume"
        thread = argv[1] if resumed else str(uuid.uuid4())
        # A resumed thread's inputs start with the prompts of its earlier turns.
        inputs = (["an earlier turn's prompt"] if resumed else []) + [prompt]

        def complete(message, failure=False, typed=None, running=False):
            if typed is not None:
                inputs.append(typed)
            codex_notify(argv, {"type": "agent-turn-complete", "thread-id": thread, "turn-id": str(uuid.uuid4()),
                                "input-messages": list(inputs), "last-assistant-message": message})

        # Codex's own title turn, in a thread of its own, always comes first.
        codex_notify(argv, {"type": "agent-turn-complete", "thread-id": str(uuid.uuid4()),
                            "turn-id": str(uuid.uuid4()), "input-messages": ["Generate a title for: " + prompt],
                            "last-assistant-message": '{"title":"x"}'})
        if foreign:
            codex_notify(argv, {"type": "agent-turn-complete", "thread-id": thread, "turn-id": str(uuid.uuid4()),
                                "input-messages": ["something the operator typed"],
                                "last-assistant-message": "someone else's turn"})
        return complete


def main():
    brain, argv = sys.argv[1], sys.argv[2:]
    # As both CLIs parse it: `--add-dir` takes every value up to the next option or `--`.
    if "--add-dir" in argv and "--" not in argv:
        sys.exit("no prompt: --add-dir took it as a directory")
    prompt = argv[-1]
    words = prompt.split()
    raw_input_mode()
    draw("fake %s ready" % brain)
    if "lost" in words:
        draw("No conversation found with session ID: x" if brain == "claude"
             else "ERROR: No saved session found with ID x. Run `codex resume` without an ID")
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
