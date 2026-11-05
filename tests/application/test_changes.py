"""A run's change, live, as its host's worker feeds it to the page: the files its worktree holds against the base
its run stands on now, sent again only when they move, and every way it cannot be read said, never guessed.

Every repository is a throwaway one; the run's status is a stand-in for its workflow's own.
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

from app.application import changes  # noqa: E402
from app.workspace import worktrees as W  # noqa: E402
import folders  # noqa: E402

TARGET = "windows" if sys.platform.startswith("win") else "wsl"


def git(path, *args):
    return subprocess.run(["git", "-C", path] + list(args), capture_output=True, text=True, check=True).stdout


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


class Feed(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="orchestra-change-"))
        self.addCleanup(folders.remove, self.tmp)
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(repo)
        git(repo, "init", "-q", "-b", "develop")
        for key, value in (("user.name", "t"), ("user.email", "t@t"), ("commit.gpgsign", "false"),
                           ("core.autocrlf", "false")):
            git(repo, "config", key, value)
        write(os.path.join(repo, "app.txt"), "one\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "base")
        self.base = git(repo, "rev-parse", "HEAD").strip()
        self.path = W.create(repo, "develop", os.path.join(self.tmp, "worktrees"), "run1", TARGET)
        # The run's status as its workflow answers it; a test changes it, or makes it unreadable.
        self.state = {"target": TARGET, "worktree_path": self.path, "base_tip": self.base}
        self.asked = []
        self.feed = changes.ChangeFeed(TARGET, state=self.status)

    def status(self, run_id):
        self.asked.append(run_id)
        if isinstance(self.state, Exception):
            raise self.state
        return self.state

    def look(self, memo):
        return self.feed.poll("run1", memo)

    def test_the_files_are_sent_as_a_snapshot_then_again_only_when_they_move(self):
        memo = {}
        write(os.path.join(self.path, "new.txt"), "drafted\n")
        sent, wait = self.look(memo)
        self.assertEqual([(each["path"], each["status"]) for each in sent["files"]], [("new.txt", "A")])
        self.assertEqual((sent["base"], sent["files_total"]), (self.base, 1), "against the base the run stands on")
        self.assertNotIn("tree", sent, "a summary, which writes no tree: a file opened is read as the change now")
        self.assertGreaterEqual(wait, changes.FASTEST)
        self.assertEqual(self.look(memo)[0], None, "nothing moved, so nothing is sent")
        write(os.path.join(self.path, "app.txt"), "one\ntwo\n")
        sent, _ = self.look(memo)
        self.assertEqual(sorted(each["path"] for each in sent["files"]), ["app.txt", "new.txt"])

    def test_the_base_is_the_one_the_run_stands_on_now(self):
        # A reconcile moves the run's base: what is shown is the change against the base it now names.
        memo = {}
        self.look(memo)
        git(self.path, "commit", "--allow-empty", "-q", "-m", "the base moved, brought in")
        self.state = dict(self.state, base_tip=git(self.path, "rev-parse", "HEAD").strip())
        memo["asked"] = 0
        sent, _ = self.look(memo)
        self.assertEqual(sent["base"], self.state["base_tip"], "sent again, though no file moved: its base did")

    def test_a_worktree_not_made_yet_is_said_once_and_watched_on(self):
        self.state = dict(self.state, worktree_path=None)
        memo = {}
        said, wait = self.look(memo)
        self.assertEqual(said, {"waiting": "the run has no worktree yet"})
        self.assertIsNotNone(wait, "it is made in a moment: the watch goes on")
        memo["asked"] = 0
        self.assertEqual(self.look(memo)[0], None, "said once, not at every look")

    def test_a_worktree_that_is_gone_ends_the_watch_saying_so(self):
        memo = {}
        self.look(memo)
        folders.remove(self.path)
        said, wait = self.look(memo)
        self.assertIn("gone", said)
        self.assertIsNone(wait)

    def test_a_run_of_another_host_or_none_at_all_is_not_read_here(self):
        self.state = dict(self.state, target="elsewhere")
        said, wait = self.look({})
        self.assertEqual((said, wait), ({"gone": "run run1 works on the elsewhere host, not this one"}, None))
        self.state = None
        said, wait = self.look({})
        self.assertEqual((said, wait), ({"gone": "Temporal holds no run run1"}, None))

    def test_a_status_that_cannot_be_read_is_said_and_asked_again(self):
        self.state = TimeoutError("no worker answered")
        memo = {}
        said, wait = self.look(memo)
        self.assertEqual(said, {"error": "the run's status cannot be read now: no worker answered"})
        self.assertEqual(wait, changes.RETRY)
        self.state = {"target": TARGET, "worktree_path": self.path, "base_tip": self.base}
        self.assertIn("files", self.look(memo)[0], "asked again at the next look, not after the usual while")

    def test_a_look_that_reads_again_after_one_that_could_not_says_so_though_nothing_moved(self):
        # The watcher was told it is not current: the first look that reads again must say what it read.
        memo = {}
        self.assertIn("files", self.look(memo)[0])
        self.state = TimeoutError("no worker answered")
        memo["asked"] = 0
        self.assertIn("error", self.look(memo)[0])
        self.state = {"target": TARGET, "worktree_path": self.path, "base_tip": self.base}
        self.assertIn("files", self.look(memo)[0], "after a status that could not be read")
        broken = dict(memo, path=os.path.join(self.tmp, "not-a-worktree"))
        os.makedirs(broken["path"])
        self.assertIn("error", self.look(broken)[0])
        broken["path"] = self.path
        self.assertIn("files", self.look(broken)[0], "after a worktree that could not be read")

    def test_its_git_runs_as_a_read_that_ends_with_the_worker(self):
        # A look's git must never outlive the worker: it runs through `launch.read`, which ends it with the worker.
        seen = []
        real = changes.launch.read

        def read(argv, timeout):
            seen.append(argv[3:5])
            return real(argv, timeout)
        changes.launch.read = read
        self.addCleanup(setattr, changes.launch, "read", real)
        write(os.path.join(self.path, "new.txt"), "drafted\n")
        self.assertIn("files", self.look({})[0])
        self.assertIn(["--no-optional-locks", "status"], seen, "the fingerprint")
        self.assertIn(["--no-optional-locks", "diff"], seen, "the summary")

    def test_a_slow_look_is_asked_less_often_within_its_bounds(self):
        self.assertEqual(changes.paced(0.1), changes.FASTEST)
        self.assertEqual(changes.paced(1.0), 5.0, "a look takes at most a sixth of the time")
        self.assertEqual(changes.paced(60), changes.SLOWEST)

    def test_the_status_is_asked_now_and_then_not_at_every_look(self):
        memo = {}
        for _ in range(3):
            self.look(memo)
        self.assertEqual(self.asked, ["run1"])

    def test_a_feed_not_yet_bound_to_its_worker_says_so(self):
        said, wait = changes.ChangeFeed(TARGET).poll("run1", {})
        self.assertEqual(said, {"error": "this host's worker is still starting"})
        self.assertEqual(wait, changes.RETRY)


if __name__ == "__main__":
    unittest.main()
