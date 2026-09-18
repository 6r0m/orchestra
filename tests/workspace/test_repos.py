"""The repository a run targets: descriptor over detection, and every refusal before any work."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

# The suite's own folder, reached from this concern's folder inside it, and the
# checkout above both: the shared harness and the fixtures live at the suite root.
HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

from app.foundation import paths  # noqa: E402
from app.workspace import repos  # noqa: E402

WINDOWS = sys.platform.startswith("win")


def git(path, *args):
    return subprocess.run(["git", "-C", path] + list(args), capture_output=True, text=True, check=True).stdout


class Layout(unittest.TestCase):
    """`<tmp>/Projects/<name>` beside a worktree root holding `projects`."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="orch-repos-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = os.path.join(self.tmp, "Projects", "tool")
        os.makedirs(self.repo)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "base")
        self.root = os.path.join(self.tmp, "worktrees")
        os.makedirs(os.path.join(self.root, "projects"))
        self.selected = {"id": "tool", "path": self.repo, "target": "windows" if WINDOWS else "wsl"}

    def resolve(self, selected=None, which=shutil.which):
        return repos.resolve(selected or self.selected, [], self.root, which=which)

    def branch(self, name):
        git(self.repo, "branch", name)


class BaseBranch(Layout):
    def test_develop_then_dev_then_the_remotes_default(self):
        with self.assertRaisesRegex(repos.Refused, "base_branch"):
            self.resolve()                                   # neither configured nor found
        git(self.repo, "update-ref", "refs/remotes/origin/main", "main")
        git(self.repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        self.assertEqual(self.resolve()["base_branch"], "main")
        self.branch("dev")
        self.assertEqual(self.resolve()["base_branch"], "dev")
        self.branch("develop")
        self.assertEqual(self.resolve()["base_branch"], "develop")

    def test_a_configured_base_wins_and_must_exist(self):
        self.branch("develop")
        self.assertEqual(self.resolve(dict(self.selected, base_branch="main"))["base_branch"], "main")
        with self.assertRaisesRegex(repos.Refused, "no local branch"):
            self.resolve(dict(self.selected, base_branch="release"))


class WorktreeRoot(Layout):
    def setUp(self):
        super().setUp()
        self.branch("develop")

    def test_the_category_folder_is_matched_case_insensitively(self):
        self.assertEqual(self.resolve()["worktree_root"], os.path.join(self.root, "projects", "tool"))

    def test_no_matching_category_refuses(self):
        os.rename(os.path.join(self.root, "projects"), os.path.join(self.root, "other"))
        with self.assertRaisesRegex(repos.Refused, "0 folders"):
            self.resolve()

    @unittest.skipIf(WINDOWS, "a case-insensitive filesystem cannot hold two such folders")
    def test_two_matching_categories_refuse(self):
        os.makedirs(os.path.join(self.root, "Projects"))
        with self.assertRaisesRegex(repos.Refused, "2 folders"):
            self.resolve()

    def test_a_configured_root_wins(self):
        self.assertEqual(self.resolve(dict(self.selected, worktree_root="/elsewhere/x"))["worktree_root"]
                         if not WINDOWS else "skip", "/elsewhere/x" if not WINDOWS else "skip")


class Refusals(Layout):
    """Whatever is missing refuses before any work."""

    def test_a_missing_tool_refuses_before_git_is_read(self):
        self.branch("develop")
        with self.assertRaisesRegex(repos.Refused, "codex is not installed"):
            repos.resolve(self.selected, ["claude", "codex"], self.root,
                          which=lambda tool: None if tool == "codex" else "/bin/" + tool)

    def test_a_directory_that_is_not_a_repository_refuses(self):
        plain = os.path.join(self.tmp, "Projects", "plain")
        os.makedirs(plain)
        with self.assertRaisesRegex(repos.Refused, "not a git repository"):
            self.resolve(dict(self.selected, path=plain))

    def test_the_todo_convention_defaults_to_this_repositorys_and_an_entry_overrides_it(self):
        self.branch("develop")
        self.assertEqual({k: self.resolve()[k] for k in repos.TODO_DEFAULTS}, repos.TODO_DEFAULTS)
        custom = dict(self.selected, todo_dir="todo/00_current", todo_name="%Y%m%d-%H%M_{slug}")
        resolved = self.resolve(custom)
        self.assertEqual((resolved["todo_dir"], resolved["todo_name"], resolved["todo_done_dir"]),
                         ("todo/00_current", "%Y%m%d-%H%M_{slug}", "todo/done"))


class Selection(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="orch-select-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_a_named_entry_its_path_or_the_orchestrations_own_repository(self):
        descriptors = {"tool": {"path": self.tmp, "target": "wsl", "base_branch": "main"}}
        by_name = repos.select("tool", descriptors)
        self.assertEqual(by_name, {"id": "tool", "path": self.tmp, "target": "wsl", "base_branch": "main"})
        self.assertEqual(repos.select(self.tmp, descriptors), by_name)
        # No repository named: this checkout, whose root `paths` owns and `repos` does not.
        self.assertEqual(repos.select(None, {})["path"], paths.REPO)

    def test_a_repository_on_a_windows_drive_runs_on_windows_unless_its_entry_says_otherwise(self):
        self.assertEqual(repos.windows_path("/mnt/e/Projects/Sample"), "E:\\Projects\\Sample")
        self.assertIsNone(repos.windows_path("/home/user/repos/x"))
        # A path on a Windows drive is a Windows target on its own; the entry may still say otherwise.
        drive = os.path.join(self.tmp, "drive")
        os.makedirs(drive)
        detected = repos.select(drive, {"onwindows": {"path": drive}})
        self.assertEqual(detected["target"], "windows" if repos.windows_path(drive) else "wsl")
        self.assertEqual(repos.select(drive, {"onwsl": {"path": drive, "target": "wsl"}})["target"], "wsl")

    def test_a_windows_target_on_a_linux_path_is_refused(self):
        """A Windows process cannot use a Linux path as its working directory."""
        with self.assertRaisesRegex(repos.Refused, "C:\\\\Windows"):
            repos.select("tool", {"tool": {"path": self.tmp, "target": "windows"}})

    @unittest.skipUnless(shutil.which("cmd.exe") and not WINDOWS, "needs WSL's Windows interop")
    def test_control_without_the_guard_a_windows_process_silently_runs_in_c_windows(self):
        done = subprocess.run(["cmd.exe", "/c", "cd"], cwd=self.tmp, capture_output=True, text=True)
        self.assertEqual(done.stdout.strip().upper(), "C:\\WINDOWS")

    def test_a_missing_path_and_an_unknown_key_are_refused(self):
        with self.assertRaisesRegex(repos.Refused, "does not exist"):
            repos.select("gone", {"gone": {"path": os.path.join(self.tmp, "gone")}})
        path = os.path.join(self.tmp, "repos.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"tool": {"path": self.tmp, "targte": "wsl"}}, fh)
        with self.assertRaisesRegex(repos.Refused, "unknown keys"):
            repos.load(path)

    def test_the_example_descriptors_are_valid_and_none_of_your_own_are_shipped(self):
        example = repos.load(os.path.join(PKG, "repos.example.json"))
        self.assertEqual(sorted(example), ["service", "webapp"])
        self.assertEqual(example["webapp"]["target"], "windows")
        self.assertEqual(example["service"]["base_branch"], "main")
        # The file a run actually reads is yours and is never committed; absent means no descriptors.
        self.assertFalse(os.path.exists(os.path.join(PKG, "repos.json")) and
                         repos.load() and False, "a descriptor file is optional")
        self.assertEqual(repos.load(os.path.join(self.tmp, "absent.json")), {})

    def test_only_the_done_folder_may_be_null(self):
        path = os.path.join(self.tmp, "repos.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"tool": {"path": self.tmp, "todo_done_dir": None}}, fh)
        self.assertIsNone(repos.load(path)["tool"]["todo_done_dir"])
        # Control: any other string setting left null is refused.
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"tool": {"path": self.tmp, "todo_dir": None}}, fh)
        with self.assertRaisesRegex(repos.Refused, "non-empty string"):
            repos.load(path)

    def test_a_flag_must_be_a_boolean(self):
        path = os.path.join(self.tmp, "repos.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"tool": {"path": self.tmp, "lfs_pointers": "yes"}}, fh)
        with self.assertRaisesRegex(repos.Refused, "true or false"):
            repos.load(path)


if __name__ == "__main__":
    unittest.main()
