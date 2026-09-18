"""Emit one complete work item to the trace UI without calling any model.

Iterating on what the operator sees should cost seconds, not a twenty-minute real run.
This drives the **real** workflow, activities and telemetry module on Temporal's
time-skipping test server, through the same fake seams the suite uses, so what lands in
Langfuse is produced by the code production uses. A fixture that emitted spans directly
would validate the fixture and nothing else.

Not a test, and deliberately not named like one: it writes to whatever Langfuse
`telemetry.resolve()` finds, so it must never run inside the hermetic suite. Its rows are
filed under the environment `fixture`, so synthetic work never counts in a real view or on
the dashboard.

    uv run --locked python tools/ui_fixture.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = os.path.dirname(HERE)
sys.path[:0] = [ORCH, os.path.join(ORCH, "tests")]

import repos  # noqa: E402
import telemetry as T  # noqa: E402
import temporal_env as E  # noqa: E402
from fakes import FakeWorktrees, codex_review_first, codex_review_resumed  # noqa: E402

TASK = ("Rename the flaky retry helper in nodes.py and cover it "
        "with a regression test that fails before the change")

# The shape a real run takes: a round sent back, a lost session rehydrated, a blocker the
# operator answers with guidance, the approval with its summary, a build attempt that fails
# and is continued, then the verified build. An operator judging the UI needs to see every
# kind of stop and failure, not a happy path.
_A1, _ = codex_review_first(
    "PATCH", "Required finding - the plan renames the helper but not its mention in "
             "README.md, so the docs would name a function that no longer exists. "
             "Smallest safe fix: update the README in the same change.")
_B1 = codex_review_resumed(
    "BLOCKER", "The task conflicts with an outside caller: tools/replay.py imports the "
               "helper by its current name, and renaming it breaks that script. This is "
               "the operator's call: keep the old name as an alias, or change the script too.")
_A2 = codex_review_resumed(
    "PASS", "Direction: rename the helper in place and keep the old name as an alias.\n"
            "Decision: add the regression test first, because the flake lives in "
            "the helper itself.\n"
            "Blast radius: nodes.py and README.md; tools/replay.py keeps working through the alias.\n"
            "Reused: the retry loop. New: one regression test and a short note in docs/.")
_A3 = codex_review_resumed(
    "PASS", "The build matches the plan: the helper is renamed, the old name stays as "
            "an alias, the README and a docs note say so, and the new test fails on the "
            "pre-change commit.")
GUIDANCE = "Keep the old name as an alias; do not change tools/replay.py."

SCRIPT = [("plan-e1-1", 0, "plan drafted\n"),
          ("assess-e1-1", 0, _A1),
          # The engineer's session is gone when round 2 resumes it: the stage starts a fresh
          # one, is marked WARNING, and the round still succeeds.
          ("plan-e1-2", 1, "Error: No conversation found with session ID: 00000000-dead\n"),
          ("plan-e1-2-rehydrated", 0, "plan revised\n"),
          ("assess-e1-2", 0, _B1),
          ("plan-e2-1", 0, "plan revised to keep the alias\n"),
          ("assess-e2-1", 0, _A2),
          # The first build attempt dies: the stage is an ERROR, and the run stops until
          # it is continued.
          ("build-e3-1", 1, "the agent exited before finishing\n"),
          ("build-e3-1", 0, "built\n"),
          ("verify-e3-1", 0, _A3)]


class FixtureWorktrees(FakeWorktrees):
    """A throwaway git repository standing in for the run's worktree, holding the change the fake agents describe.

    `final_diff` reads the worktree with git, so a fixture handing it a path that does not
    exist proves nothing about the artifact an operator actually reviews.
    """

    def __init__(self, base_dir):
        super().__init__()
        self.base_dir = base_dir

    def create(self, repo, base, root, run_id, target, lfs_pointers=False):
        path = os.path.join(self.base_dir, run_id)
        os.makedirs(path, exist_ok=True)

        def git(*args):
            subprocess.run(["git", "-C", path] + list(args), capture_output=True, text=True)

        def write(name, content):
            full = os.path.join(path, name)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as fh:
                fh.write(content)

        git("init", "-q")
        git("config", "user.email", "fixture@local")
        git("config", "user.name", "fixture")
        helper = ("def %s(call, attempts=3):\n    for _ in range(attempts):\n"
                  "        if call():\n            return True\n    return False\n")
        write("README.md", "# fixture\n\n`flaky_retry` in nodes.py retries a failed call.\n")
        write("nodes.py", helper % "flaky_retry")
        write(".gitignore", "*.log\n")
        git("add", "-A")
        git("commit", "-q", "-m", "base")
        # The change the fake agents describe: the rename with its alias, the README, a
        # regression test, and a docs note whose name has a space.
        write("README.md", "# fixture\n\n`retry_with_backoff` in nodes.py retries a failed call.\n")
        write("nodes.py", helper % "retry_with_backoff"
              + "\n\n# The old name stays for tools/replay.py.\nflaky_retry = retry_with_backoff\n")
        write("test_retry_helper.py", "from nodes import flaky_retry, retry_with_backoff\n\n\n"
              "def test_the_old_name_still_works():\n    assert flaky_retry is retry_with_backoff\n")
        write(os.path.join("docs", "retry helper.md"),
              "The retry helper is `retry_with_backoff`; `flaky_retry` stays as an alias.\n")
        write("debug.log", "ignored\n")
        return path


def _gdiff_s(path, scratch):
    """What `gdiff -s` copies for this worktree, by running its commands on a copy.

    The browser acceptance compares the UI's copy button against this, so it is computed
    without `telemetry`: an oracle built from the code under test would agree with any
    mistake in it.
    """
    copy = os.path.join(scratch, "gdiff-copy")
    shutil.copytree(path, copy)
    subprocess.run(["git", "-C", copy, "add", "-A"], check=True)
    return subprocess.run(["git", "-C", copy, "diff", "--no-ext-diff", "--no-textconv", "--cached"],
                          check=True, capture_output=True).stdout


def main():
    # Synthetic work is filed apart from real runs, whatever the shell exports.
    os.environ["LANGFUSE_TRACING_ENVIRONMENT"] = "fixture"
    tele = T.resolve()
    if tele is None:
        print("no Langfuse keys (secrets/langfuse.env) - nothing to emit", file=sys.stderr)
        return 1
    # A fixture has no agent transcripts: its fake architect writes no rollout, so an upload
    # would only mark every architect step as missing its turns.
    T.upload_codex_session = lambda *args, **kwargs: None

    tmp = tempfile.mkdtemp(prefix="ui-fixture-")
    try:
        E.host(SCRIPT, git=FixtureWorktrees(os.path.join(tmp, "worktrees")), telemetry=tele)
        run = E.Run(task=TASK)
        stops = [run.stop["reason"]]
        for answer in (GUIDANCE, "yes", "continue"):
            run.answer(answer)
            stops.append(run.stop["reason"])
        T.flush(tele)
        if stops != ["blocker", "approval", "failed", "final"]:
            print("expected the stops blocker, approval, failed, final; got %s" % stops, file=sys.stderr)
            return 1

        out_dir = os.path.join(repos.REPO, "tmp", "ui-fixture")
        os.makedirs(out_dir, exist_ok=True)
        expected = os.path.join(out_dir, "%s.expected.patch" % run.run_id)
        with open(expected, "wb") as fh:
            fh.write(_gdiff_s(os.path.join(tmp, "worktrees", run.run_id), tmp))
        with open(os.path.join(out_dir, "last.json"), "w", encoding="utf-8") as fh:
            json.dump({"run_id": run.run_id, "trace_id": run.state.get("trace_id"),
                       "environment": os.environ["LANGFUSE_TRACING_ENVIRONMENT"],
                       "expected_patch": expected}, fh)
        print("run id:   %s" % run.run_id)
        print("trace:    %s" % T.trace_url(tele, run.state.get("trace_id")))
        print("expected: %s" % expected)
        run.cleanup()
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
