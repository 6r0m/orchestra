"""Does a repository recorded by `trust.py` still raise no dialog in a worktree of it?

    python tools/trust_probe.py claude "$(command -v claude)" --model haiku
    python tools/trust_probe.py codex  "$(command -v codex)" --sandbox read-only --ask-for-approval never

Run it on a host after either CLI is upgraded: the vendors own that dialog and could change which
path it is keyed by, and the cost of not noticing is a turn that waits at a dialog nobody sees.

It makes a throwaway repository and one worktree of it under this repository's own `tmp/`, records
the repository exactly as a run's `prepare` does, starts the real CLI in the worktree, reports
whether the dialog appeared and whether the agent answered — then removes the worktree, the files
and the trust records it made, so a probe leaves nothing on the host.
"""
import os, re, shutil, subprocess, sys, tempfile, time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)))

HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path.insert(0, ORCH)
import launch  # noqa: E402
import trust  # noqa: E402

CLEAN = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
ASKED = ("Accessing workspace", "Do you trust", "trust this folder", "Yes, continue")
# The terminal draws the prompt as well as the answer, so the answer is not in the prompt.
PROMPT = "Reverse the text KOEBORP and reply with only the result."
ANSWER = "PROBEOK"


def git(path, *args):
    subprocess.run(["git", "-C", path] + list(args), check=True, capture_output=True)


def main(brain, argv):
    scratch = os.path.join(os.path.dirname(ORCH), os.pardir, "tmp", "trust-probe")
    os.makedirs(scratch, exist_ok=True)
    root = tempfile.mkdtemp(prefix="trustprobe-", dir=scratch)
    repo, tree = os.path.join(root, "repo"), os.path.join(root, "wt", "run1")
    try:
        os.makedirs(repo)
        git(repo, "init", "-q", "-b", "main")
        for key, value in (("user.email", "t@t"), ("user.name", "t"), ("commit.gpgsign", "false")):
            git(repo, "config", key, value)
        open(os.path.join(repo, "README.md"), "w").write("probe\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "init")
        git(repo, "worktree", "add", "-q", "-b", "run1", tree)

        print("recorded:", trust.ensure(repo, [brain]) or "nothing (already known)")
        out = os.path.join(root, "out.txt")
        text = ""
        # Through the same containment a run uses: this probe starts a real agent, and must not
        # leave one behind any more than a role turn may.
        contained = launch._Tree()
        with open(out, "wb") as sink:
            # An interactive CLI does not exit: watch what it draws, then end its whole tree.
            agent = contained.start([sys.executable, os.path.join(ORCH, "ptyhost.py"), "160", "48", "--"]
                                    + argv + ["--", PROMPT],
                                    tree, subprocess.DEVNULL, sink, subprocess.STDOUT, dict(os.environ))
            try:
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    time.sleep(2)
                    try:
                        with open(out, encoding="utf-8", errors="replace") as fh:
                            text = CLEAN.sub("", fh.read())
                    except OSError:
                        continue            # a file being written on a Windows drive can read short

                    if any(phrase in text for phrase in ASKED) or ANSWER in text:
                        break
            finally:
                if agent.poll() is None:
                    contained.stop(agent)
                contained.kill()
                contained.close()
        asked = [phrase for phrase in ASKED if phrase in text]
        print("%s in a worktree of a recorded repository: %s" %
              (brain, "ASKED " + str(asked) if asked else "no dialog"))
        answered = ANSWER in text
        print("answered %s:" % ANSWER, answered)
        if not answered:
            # What it drew instead, so a failure says why rather than only that.
            print("   last of what it showed:", " ".join(text.split())[-220:])
    finally:
        # Whatever happened, this probe leaves nothing behind - its worktree, its files, and the
        # trust records it made for a repository that is about to stop existing.
        # Windows can still hold the directory the agent ran in; the removal below is what matters.
        subprocess.run(["git", "-C", repo, "worktree", "remove", "--force", tree], capture_output=True)
        shutil.rmtree(root, ignore_errors=True)
        print("probe directory removed:", not os.path.exists(root))
        print("records removed:", trust.forget(repo, [brain]) or "none")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
