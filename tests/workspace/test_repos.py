"""The repository a run targets: descriptor over detection, and every refusal before any work."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

# The suite's own folder, reached from this concern's folder inside it, and the
# checkout above both: the shared harness and the fixtures live at the suite root.
HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

from app.foundation import paths  # noqa: E402
from app.workspace import repos  # noqa: E402
import folders  # noqa: E402

WINDOWS = sys.platform.startswith("win")


def git(path, *args):
    return subprocess.run(["git", "-C", path] + list(args), capture_output=True, text=True, check=True).stdout


class Layout(unittest.TestCase):
    """`<tmp>/Projects/<name>` beside a worktree root holding `projects`."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="orchestra-repos-"))
        self.addCleanup(folders.remove, self.tmp)
        self.repo = os.path.join(self.tmp, "Projects", "tool")
        os.makedirs(self.repo)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "base")
        self.root = os.path.join(self.tmp, "worktrees")
        os.makedirs(os.path.join(self.root, "projects"))
        self.selected = {"id": "tool", "path": self.repo, "target": "windows" if WINDOWS else "wsl"}

    def resolve(self, selected=None, which=shutil.which):
        return repos.resolve(selected or self.selected, self.root, which=which)

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

    def test_a_missing_git_refuses_before_git_is_read(self):
        """Git is the repository's one tool; whether a run's agents can run on the host is asked before
        this, by the run's preparation."""
        self.branch("develop")
        asked = []

        def which(tool):
            asked.append(tool)
            return None if tool == "git" else "/bin/" + tool
        with self.assertRaisesRegex(repos.Refused, "git is not installed on the %s host" % self.selected["target"]):
            self.resolve(which=which)
        self.assertEqual(asked, ["git"], "no agent's program is looked for here")

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

    def test_a_base_that_lives_on_a_remote_is_the_entrys_to_name_and_never_assumed(self):
        self.branch("develop")
        git(self.repo, "remote", "add", "upstream", os.path.join(self.tmp, "upstream.git"))
        self.assertIsNone(self.resolve()["remote"],
                          "the repository has a remote, and no entry names it: nothing leaves the machine")
        named = dict(self.selected, remote="upstream", base_branch="develop")
        self.assertEqual(self.resolve(named)["remote"], "upstream")
        with self.assertRaisesRegex(repos.Refused, "has no remote 'origin'"):
            self.resolve(dict(named, remote="origin"))

    def test_a_remotes_base_is_named_never_found_and_needs_no_branch_of_this_repositorys_own(self):
        self.branch("develop")
        git(self.repo, "remote", "add", "origin", os.path.join(self.tmp, "origin.git"))
        with self.assertRaisesRegex(repos.Refused, "base_branch"):
            self.resolve(dict(self.selected, remote="origin"))      # the branch a run is pushed to is never guessed
        resolved = self.resolve(dict(self.selected, remote="origin", base_branch="release"))
        self.assertEqual((resolved["base_branch"], resolved["remote"]), ("release", "origin"),
                         "the remote's branch is the base: this repository has no branch of that name")
        with self.assertRaisesRegex(repos.Refused, "no local branch 'release'"):
            self.resolve(dict(self.selected, base_branch="release"))  # control: a local base must be there

    def test_the_documents_a_closeout_may_change_are_the_ones_an_entry_names_and_no_others(self):
        self.branch("develop")
        self.assertEqual(self.resolve()["closeout_docs"], [],
                         "no entry names any: a closeout has the todo alone, and no file is a document by its name")
        self.assertEqual(self.resolve(dict(self.selected, closeout_docs=["README.md", "handbook/"]))["closeout_docs"],
                         ["README.md", "handbook/"])
        self.assertEqual(self.resolve(dict(self.selected, closeout_docs=[]))["closeout_docs"], [])


class Selection(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="orchestra-select-"))
        self.addCleanup(folders.remove, self.tmp)

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

    def test_a_windows_drive_path_spelled_back_as_wsl_sees_it(self):
        for path in ("/mnt/e/Projects/Sample", "/mnt/c"):
            self.assertEqual(repos.wsl_path(repos.windows_path(path)), path)
        self.assertEqual(repos.wsl_path("E:\\Projects\\Sample\\"), "/mnt/e/Projects/Sample")
        self.assertIsNone(repos.wsl_path("/home/user/repos/x"))
        self.assertIsNone(repos.wsl_path("\\\\server\\share\\x"))

    def test_a_runs_repository_chosen_again_by_its_name_only_while_its_entry_is_still_that_repository(self):
        """What the Workbench's Worktrees view opens for a run: the repository the run chose, never another
        of its name."""
        listed = {"tool": {"path": self.tmp}}
        self.assertEqual(repos.selector("tool", self.tmp, "wsl", listed), "tool")
        # A repository given by its path is named for its folder, a name repos.json may give another, or none.
        elsewhere = os.path.join(self.tmp, "elsewhere", "tool")
        self.assertEqual(repos.selector("tool", elsewhere, "wsl", listed), elsewhere)
        self.assertEqual(repos.selector("tool", self.tmp, "wsl", {}), self.tmp)
        # A Windows run's path is in its host's spelling; `select` takes the client's.
        self.assertEqual(repos.selector("sample", "E:\\Projects\\Sample", "windows", {}), "/mnt/e/Projects/Sample")
        # A repos.json that cannot be read cannot vouch for the name; the path still names the repository.
        with unittest.mock.patch.object(repos, "load", side_effect=repos.Refused("repos.json is broken")):
            self.assertEqual(repos.selector("tool", self.tmp, "wsl"), self.tmp)

    @unittest.skipIf(WINDOWS, "the client, which chooses a run's repository, runs on WSL")
    def test_a_windows_runs_listed_repository_chosen_again_by_its_name(self):
        entry = {"sample": {"path": "/mnt/e/Projects/Sample"}}
        self.assertEqual(repos.selector("sample", "E:\\Projects\\Sample", "windows", entry), "sample")

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

    def test_the_example_descriptors_are_valid(self):
        example = repos.load(os.path.join(PKG, ".orchestra", "repos.example.json"))
        self.assertEqual(sorted(example), ["service", "work/webapp"])
        self.assertEqual(example["work/webapp"]["target"], "windows")
        self.assertEqual(example["service"]["base_branch"], "main")
        # A file named that is not there holds no descriptors.
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

    def test_a_closeouts_documents_are_paths_inside_the_repository(self):
        path = os.path.join(self.tmp, "repos.json")

        def loaded(value):
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"tool": {"path": self.tmp, "closeout_docs": value}}, fh)
            return repos.load(path)["tool"]["closeout_docs"]
        for held in (["README.md", "docs/", "**/README.md", "app/*/docs/**"], []):
            self.assertEqual(loaded(held), held)
            self.assertEqual(repos.select("tool", repos.load(path))["closeout_docs"], held,
                             "and the run's selection carries them to its host")
        # Not a list, not a path, a way out of the repository, or what git would read as something else.
        for refused in ("docs/", None, [""], [" "], [7], ["../other"], ["docs/../../other"], ["/etc"],
                        [":(top)docs"], [":!docs"], ["-x"], ["docs\\guide.md"]):
            with self.assertRaisesRegex(repos.Refused, "closeout_docs must list paths inside the repository",
                                        msg=repr(refused)):
                loaded(refused)

    def test_a_flag_must_be_a_boolean(self):
        path = os.path.join(self.tmp, "repos.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"tool": {"path": self.tmp, "lfs_pointers": "yes"}}, fh)
        with self.assertRaisesRegex(repos.Refused, "true or false"):
            repos.load(path)


class Source(unittest.TestCase):
    """The one file descriptors come from: the one `ORCHESTRA_REPOS` names, alone, else the checkout's
    `.orchestra/repos.json` — where a `repos.json` left at its root is refused, never read, never moved."""

    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="orchestra-source-"))
        self.addCleanup(folders.remove, self.root)
        os.makedirs(os.path.join(self.root, ".orchestra"))

    def write(self, relative, entries):
        path = os.path.join(self.root, *relative.split("/"))
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(entries, fh)
        return path

    def source(self, **environ):
        return repos.descriptor_file(self.root, environ)

    def test_without_the_variable_the_folder_s_file_and_one_left_at_the_root_is_refused_not_read(self):
        self.assertIsNone(self.source(), "neither there: no descriptors, as a fresh checkout has none")
        legacy = self.write("repos.json", {"old": {"path": self.root}})
        with self.assertRaisesRegex(repos.Refused, r"move it to .*\.orchestra.repos\.json"):
            self.source()
        with open(legacy, encoding="utf-8") as fh:
            self.assertIn("old", fh.read(), "left where it was, as it was")
        current = self.write(".orchestra/repos.json", {"new": {"path": self.root}})
        with self.assertRaisesRegex(repos.Refused, "both"):
            self.source()
        os.remove(legacy)
        self.assertEqual(self.source(), current)

    def test_the_variable_takes_its_file_alone_and_one_that_is_not_there_is_refused(self):
        self.write("repos.json", {"old": {"path": self.root}})
        self.write(".orchestra/repos.json", {"new": {"path": self.root}})
        named = self.write("mine.json", {"mine": {"path": self.root}})
        # Neither of the checkout's files is looked at, the one left at its root included.
        self.assertEqual(self.source(ORCHESTRA_REPOS=named), named)
        self.assertEqual(sorted(repos.load(named)), ["mine"])
        with self.assertRaisesRegex(repos.Refused, "does not exist"):
            self.source(ORCHESTRA_REPOS=os.path.join(self.root, "absent.json"))

    def test_the_suite_reads_descriptors_of_its_own_never_the_operator_s(self):
        named = os.environ.get("ORCHESTRA_REPOS")
        self.assertTrue(named, "the suite's harness names descriptors of its own")
        self.assertNotEqual(os.path.normcase(os.path.dirname(os.path.abspath(named))),
                            os.path.normcase(os.path.join(paths.REPO, ".orchestra")))
        self.assertEqual(os.path.abspath(repos.descriptor_file()), os.path.abspath(named))


if __name__ == "__main__":
    unittest.main()
