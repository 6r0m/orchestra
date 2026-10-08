"""A run's git lifecycle against real repositories: create, guard, view, merge, conflict, discard, cleanup.

Covers the worktree view, the controller-only guard, git side effects adopted after an
ambiguous failure, and the approved merge with its environment cleanup and deletion
guards. Every repository is a throwaway one under a temporary directory.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

# The suite's own folder, reached from this concern's folder inside it, and the
# checkout above both: the shared harness and the fixtures live at the suite root.
HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

from app.application import activities as A  # noqa: E402
from app.foundation import envpath  # noqa: E402
from app.workspace import worktrees as W  # noqa: E402
import folders  # noqa: E402

WINDOWS = sys.platform.startswith("win")
TARGET = "windows" if WINDOWS else "wsl"


def git(path, *args, env=None):
    return subprocess.run(["git", "-C", path] + list(args), capture_output=True, text=True, check=True,
                          env=env).stdout


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


class Repo(unittest.TestCase):
    """A repository on `develop`, checked out in its main checkout, with its own worktree root."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="orchestra-git-"))
        self.addCleanup(folders.remove, self.tmp)
        self.repo = os.path.join(self.tmp, "repo")
        self.root = os.path.join(self.tmp, "worktrees")
        os.makedirs(self.repo)
        hooks = os.path.join(self.tmp, "no-hooks")
        os.makedirs(hooks)
        git(self.repo, "init", "-q", "-b", "develop")
        for key, value in (("user.name", "t"), ("user.email", "t@t"), ("commit.gpgsign", "false"),
                           ("core.hooksPath", hooks), ("core.autocrlf", "false")):
            git(self.repo, "config", key, value)
        write(os.path.join(self.repo, "app.txt"), "one\n")
        write(os.path.join(self.repo, "todo", "README.md"), "todos\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")
        # Environments land under this test's own cache root.
        self.cache = os.path.join(self.tmp, "cache")
        saved = {key: os.environ.get(key) for key in ("XDG_CACHE_HOME", "LOCALAPPDATA")}
        os.environ["LOCALAPPDATA" if WINDOWS else "XDG_CACHE_HOME"] = self.cache
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
                                 for k, v in saved.items()])

    def worktree(self, run_id, change=True):
        path = W.create(self.repo, "develop", self.root, run_id, TARGET)
        if change:
            write(os.path.join(path, "app.txt"), "one\n%s\n" % run_id)
            write(os.path.join(path, "todo", "2026-09-15_1200-%s.md" % run_id), "**Status:** DRAFT\nplan\n")
        return path

    def environment(self, checkout):
        path = envpath.environment_for(checkout)
        os.makedirs(path)
        write(os.path.join(path, "pyvenv.cfg"), "home = x\n")
        return path

    def merge(self, run_id, path):
        return W.merge(self.repo, path, run_id, "develop", W.work_tree(path),
                       os.path.join("todo", "2026-09-15_1200-%s.md" % run_id), os.path.join("todo", "done"),
                       "2026-09-15_1200-%s: the change" % run_id, "Merge 2026-09-15_1200-%s" % run_id)

    def merges_on_develop(self):
        return [line for line in git(self.repo, "log", "--first-parent", "--format=%s", "develop").splitlines()
                if line.startswith("Merge ")]


class Create(Repo):
    def test_a_worktree_lands_in_the_root_on_its_own_branch_and_is_adopted_when_made_again(self):
        path = self.worktree("run1", change=False)
        self.assertEqual(path, os.path.join(self.root, "run1"))
        self.assertEqual(git(path, "rev-parse", "--abbrev-ref", "HEAD").strip(), "run1")
        self.assertEqual(W.create(self.repo, "develop", self.root, "run1", TARGET), path,
                         "an existing worktree of this run is adopted, not created twice")
        # Control: git itself refuses to create it twice.
        again = subprocess.run(["git", "-C", self.repo, "worktree", "add", "-b", "run1", path, "develop"],
                               capture_output=True)
        self.assertNotEqual(again.returncode, 0)

    @unittest.skipUnless(shutil.which("git-lfs"), "needs Git LFS")
    def test_lfs_pointers_keep_assets_out_of_the_worktree(self):
        git(self.repo, "lfs", "install", "--local")
        git(self.repo, "lfs", "track", "*.bin")
        with open(os.path.join(self.repo, "asset.bin"), "wb") as fh:
            fh.write(b"\x00heavy asset content\x01" * 100)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "an asset")
        pointer = W.create(self.repo, "develop", self.root, "pointers", TARGET, lfs_pointers=True)
        with open(os.path.join(pointer, "asset.bin"), "rb") as fh:
            self.assertTrue(fh.read().startswith(b"version https://git-lfs"), "a pointer, not the asset")
        self.assertEqual(git(pointer, "status", "--porcelain").strip(), "", "and the worktree is clean")
        # Control: without the flag the asset's content is copied into the worktree.
        copied = W.create(self.repo, "develop", self.root, "copied", TARGET)
        with open(os.path.join(copied, "asset.bin"), "rb") as fh:
            self.assertTrue(fh.read().startswith(b"\x00heavy asset content"))

    def test_a_run_id_reads_as_its_task_and_is_a_valid_branch_folder_and_short(self):
        cases = {"Add a regression test for check-scripts-layout.py": "add-a-regression",
                 "Fix X": "fix-x",
                 "--delete ../../etc/passwd; rm -rf ~ `whoami`": "delete-etc",
                 "Überprüfe die Größe": "berprfe-die-gre",
                 "supercalifragilisticexpialidocious": "supercalifragili",
                 "日本語だけ": "run"}
        for task, words in cases.items():
            name = W.run_id(task)
            self.assertRegex(name, r"^%s-[0-9a-f]{8}$" % words, task)
            self.assertLessEqual(len(name), 25, "a Windows worktree path stays under 260 characters")
            self.assertEqual(subprocess.run(["git", "check-ref-format", "--branch", name],
                                            capture_output=True).returncode, 0, name)
        self.assertNotEqual(W.run_id("Fix X"), W.run_id("Fix X"), "two runs of one task stay apart")
        path = W.create(self.repo, "develop", self.root, W.run_id("--x ../y"), TARGET)
        self.assertTrue(os.path.isdir(path) and os.path.dirname(path) == self.root)

    def test_a_stale_branch_of_the_same_name_is_refused_and_one_at_the_base_is_adopted(self):
        git(self.repo, "branch", "stale", "develop")
        write(os.path.join(self.repo, "app.txt"), "moved\n")
        git(self.repo, "commit", "-q", "-am", "the base moves on")
        with self.assertRaises(W.GitError):
            W.create(self.repo, "develop", self.root, "stale", TARGET)
        self.assertFalse(os.path.exists(os.path.join(self.root, "stale")), "nothing is created")
        # Control: a branch still at the base, as a create that failed midway leaves it, is adopted.
        git(self.repo, "branch", "fresh", "develop")
        self.assertTrue(os.path.isdir(W.create(self.repo, "develop", self.root, "fresh", TARGET)))

    def _deep_file(self, length):
        """Commit a file whose repository path is exactly `length` characters."""
        parts, left = [], length
        while left > 60:
            parts.append("d" * 49)
            left -= 50
        parts.append("f" * left)
        write(os.path.join(self.repo, *parts), "x\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "a deep file")

    def test_a_windows_worktree_past_the_path_limit_is_refused_before_it_exists(self):
        run_id = "deep-0000"
        budget = W.WINDOWS_MAX_FILE - len(os.path.join(self.root, run_id)) - 1
        self._deep_file(budget + 1)
        with self.assertRaises(W.GitError) as raised:
            W.create(self.repo, "develop", self.root, run_id, "windows")
        self.assertIn("past", str(raised.exception))
        self.assertFalse(os.path.exists(os.path.join(self.root, run_id)))
        self.assertFalse(W.branch_exists(self.repo, run_id), "nothing is created")
        # Control: the same file one character shorter fits.
        git(self.repo, "rm", "-q", "-r", "d" * 49)
        git(self.repo, "commit", "-q", "-m", "gone")
        self._deep_file(budget)
        self.assertTrue(os.path.isdir(W.create(self.repo, "develop", self.root, run_id, "windows")))

    def test_a_path_holding_something_else_is_refused(self):
        os.makedirs(os.path.join(self.root, "run1"))
        with self.assertRaises(W.GitError):
            W.create(self.repo, "develop", self.root, "run1", TARGET)


class Guard(Repo):
    """What a role may not change is detected; what it may run changes nothing."""

    def test_reads_leave_the_guard_unchanged_and_staging_or_committing_changes_it(self):
        path = self.worktree("run1")
        before = W.guard(path, "run1")
        for args in (("status",), ("diff",), ("log", "-1"), ("status", "--porcelain")):
            git(path, *args)
        self.assertEqual(W.guard(path, "run1"), before, "git status, diff and log keep working")
        git(path, "add", "app.txt")
        staged = W.guard(path, "run1")
        self.assertNotEqual(staged, before, "git add is detected")
        git(path, "commit", "-q", "-m", "agent commit")
        self.assertNotEqual(W.guard(path, "run1"), staged, "git commit is detected")

    def test_an_edit_only_its_content_tells_is_in_the_tree_a_review_and_a_merge_are_held_to(self):
        """A file rewritten to the same size in the second its index was written looks unchanged by its stat.
        Git's own index knows to compare content then, and the private copy the tree is computed on must."""
        import time
        from unittest import mock
        path = self.worktree("run1", change=False)
        git(path, "config", "core.trustctime", "false")     # what ctime tells differs by host
        index = git(path, "rev-parse", "--path-format=absolute", "--git-path", "index").strip()
        app, then = os.path.join(path, "app.txt"), time.time() - 30
        os.utime(app, (then, then))
        git(path, "update-index", "--refresh")
        os.utime(index, (then, then))                        # written in the second its file was
        write(app, "two\n")                                  # the same four bytes long
        os.utime(app, (then, then))
        edit = git(path, "hash-object", "app.txt").strip()
        self.assertEqual(git(path, "rev-parse", W.work_tree(path) + ":app.txt").strip(), edit)
        # Control: a copy stamped when it was made trusts the stat, and the edit is not in its tree.
        with mock.patch.object(W.shutil, "copy2", shutil.copyfile):
            stale = git(path, "rev-parse", W.work_tree(path) + ":app.txt").strip()
        self.assertEqual(stale, git(path, "rev-parse", "HEAD:app.txt").strip())
        self.assertNotEqual(stale, edit)

    def test_a_role_that_stages_fails_its_stage(self):
        path = self.worktree("run1")

        def staging_agent(worktree, argv, rdir, name, prompt, timeout, env, *, kind):
            git(worktree, "add", "-A")
            return 0, "done\n"

        from app.application import settings as S
        host = A.Activities(runner=staging_agent, telemetry=None)
        state = {"run_id": "run1-guard", "task": "t", "phase": "plan", "round": 0, "episode": 1,
                 "worktree_path": path, "todo_path": os.path.join(path, "todo", "x.md"), "agent_sessions": {}}
        self.addCleanup(shutil.rmtree, A.run_dir("run1-guard"), ignore_errors=True)
        with self.assertRaises(Exception) as raised:
            host.run_role({"stage": "plan", "state": state, "policy": S.run_policy(S.load())})
        self.assertIn("git_violation", str(raised.exception))

    def test_an_agents_git_can_neither_push_nor_reach_a_remote(self):
        """Measured without pushing: the push URL is rewritten, and every transport is refused."""
        path = self.worktree("run1", change=False)
        bare = os.path.join(self.tmp, "remote.git")
        subprocess.run(["git", "init", "-q", "--bare", bare], check=True)
        git(self.repo, "remote", "add", "origin", bare)
        git(self.repo, "remote", "add", "withpush", bare)
        git(self.repo, "config", "remote.withpush.pushurl", bare)
        agent = A.agent_env({})
        plain = dict(os.environ)
        # Control: without the agent's git configuration both reach the remote.
        self.assertEqual(git(path, "remote", "get-url", "--push", "origin", env=plain).strip(), bare)
        self.assertEqual(subprocess.run(["git", "-C", path, "ls-remote", "withpush"], env=plain,
                                        capture_output=True).returncode, 0)
        self.assertEqual(git(path, "remote", "get-url", "--push", "origin", env=agent).strip(),
                         "orchestration-push-blocked:" + bare)
        refused = subprocess.run(["git", "-C", path, "ls-remote", "withpush"], env=agent, capture_output=True,
                                 text=True)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("not allowed", refused.stderr)
        self.assertNotIn("UV_PROJECT_ENVIRONMENT", A.agent_env({}) if "UV_PROJECT_ENVIRONMENT" in os.environ else {})

    def test_a_push_an_agent_actually_attempts_reaches_no_remote(self):
        """The attempt itself, not an inspection of the configuration — detecting a push is too late.

        Both remote shapes and the documented way to lift the transport refusal.
        """
        path = self.worktree("run1", change=False)
        bare = os.path.join(self.tmp, "remote.git")
        subprocess.run(["git", "init", "-q", "--bare", bare], check=True)
        git(self.repo, "remote", "add", "origin", bare)
        git(self.repo, "remote", "add", "withpush", bare)
        git(self.repo, "config", "remote.withpush.pushurl", bare)
        agent = A.agent_env({})

        def push(remote, ref, env, *ahead):
            return subprocess.run(["git", "-C", path] + list(ahead)
                                  + ["push", remote, "HEAD:refs/heads/" + ref],
                                  env=env, capture_output=True, text=True)

        for remote in ("origin", "withpush"):
            self.assertNotEqual(push(remote, "plain-" + remote, agent).returncode, 0,
                                "an agent's push to %s must fail" % remote)
            self.assertNotEqual(push(remote, "lifted-" + remote, agent,
                                     "-c", "protocol.allow=always").returncode, 0,
                                "a deliberate -c protocol.allow=always must not lift the refusal")
        self.assertEqual(git(bare, "for-each-ref", "--format=%(refname)").split(), [],
                         "no ref an agent pushed reached the remote")
        # Control: the same push without the agent's environment reaches the remote.
        plain = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.assertEqual(push("withpush", "control", plain).returncode, 0)
        self.assertEqual(git(bare, "for-each-ref", "--format=%(refname)").split(),
                         ["refs/heads/control"])


class View(Repo):
    """Every worktree git reports, marked against the local base branch, deleted by nothing."""

    def test_merged_and_unmerged_worktrees_are_told_apart_and_a_removed_one_disappears(self):
        merged = self.worktree("merged")
        git(merged, "add", "-A")
        git(merged, "commit", "-q", "-m", "merged work")
        git(self.repo, "merge", "-q", "--no-ff", "-m", "merge it", "merged")
        unmerged = self.worktree("unmerged")
        git(unmerged, "add", "-A")
        git(unmerged, "commit", "-q", "-m", "unmerged work")
        pending = self.worktree("pending")                       # a run's work, not yet committed
        rows = {row["branch"]: row for row in W.view(self.repo, "develop")}
        self.assertEqual((rows["merged"]["state"], rows["unmerged"]["state"], rows["develop"]["state"],
                          rows["pending"]["state"]), ("merged", "unmerged", "base", "uncommitted"),
                         "uncommitted work is never shown as merged")
        self.assertTrue(os.path.isdir(pending))
        self.assertTrue(os.path.isdir(merged) and os.path.isdir(unmerged), "the view deletes nothing")
        git(self.repo, "worktree", "remove", "--force", unmerged)
        self.assertNotIn("unmerged", {row["branch"] for row in W.view(self.repo, "develop")})


class ReviewDiff(Repo):
    """Reading a change: one snapshot named by its base and tree, each file by its exact path, every read of it
    the same bytes whatever the worktree or the repository's settings do."""

    DEEP = "src/a-rather-long-directory-name/and-another-one-below-it/2026-09-30_1627-audit_the_codex_adapter_s_output.md"

    def setUp(self):
        super().setUp()
        write(os.path.join(self.repo, "docs", "old name.md"), "".join("line %d of the guide\n" % n for n in range(1, 31)))
        write(os.path.join(self.repo, "gone.txt"), "about to go\n")
        write(os.path.join(self.repo, "long.txt"), "".join("line %d\n" % n for n in range(1, 41)))
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "more files")
        self.path = self.worktree("run1", change=False)

    def edit(self):
        """A change holding every kind of file a list must say: added deep down, spaced, renamed and edited,
        binary, deleted and modified."""
        write(os.path.join(self.path, *self.DEEP.split("/")), "new\n")
        write(os.path.join(self.path, "with space.txt"), "spaced\n")
        os.rename(os.path.join(self.path, "docs", "old name.md"), os.path.join(self.path, "docs", "new name.md"))
        with open(os.path.join(self.path, "docs", "new name.md"), "a", encoding="utf-8", newline="") as fh:
            fh.write("one more line\n")
        with open(os.path.join(self.path, "image.bin"), "wb") as fh:
            fh.write(b"\x00\x01binary\x00")
        os.remove(os.path.join(self.path, "gone.txt"))
        write(os.path.join(self.path, "long.txt"),
              "".join(("line %d\n" % n) if n != 20 else "changed 20\n" for n in range(1, 41)))

    def diff(self, *args):
        """git's own bytes of a diff, read by this test rather than the code under test."""
        return subprocess.run(["git", "-C", self.path, "diff"] + list(args), capture_output=True, check=True).stdout

    def test_each_changed_file_is_listed_by_its_exact_path(self):
        self.edit()
        read = W.review_diff(self.path)
        self.assertRegex(read["base"], r"^[0-9a-f]{40}$", "the worktree's HEAD, whole")
        self.assertEqual(read["base"], git(self.path, "rev-parse", "HEAD").strip())
        self.assertEqual(read["tree"], W.work_tree(self.path), "the tree `git add -A` makes, and nothing staged")
        self.assertEqual(git(self.path, "diff", "--cached", "--name-only"), "", "reading staged nothing")
        files = {entry["path"]: entry for entry in read["files"]}
        self.assertEqual(files, {
            self.DEEP: {"path": self.DEEP, "old": None, "status": "A", "added": 1, "removed": 0, "binary": False},
            "with space.txt": {"path": "with space.txt", "old": None, "status": "A", "added": 1, "removed": 0,
                               "binary": False},
            "docs/new name.md": {"path": "docs/new name.md", "old": "docs/old name.md", "status": "R", "added": 1,
                                 "removed": 0, "binary": False},
            "image.bin": {"path": "image.bin", "old": None, "status": "A", "added": None, "removed": None,
                          "binary": True},
            "gone.txt": {"path": "gone.txt", "old": None, "status": "D", "added": 0, "removed": 1, "binary": False},
            "long.txt": {"path": "long.txt", "old": None, "status": "M", "added": 1, "removed": 1, "binary": False}})
        self.assertEqual(read["files_total"], 6)
        # Control: git's stat, which the page showed, cuts the long path.
        self.assertNotIn(self.DEEP, read["summary"])
        self.assertIn("...", read["summary"])

    def test_a_file_is_read_whole_and_alone_or_its_changes_only_past_the_bound(self):
        self.edit()
        read = W.review_diff(self.path)
        one = W.review_diff(self.path, base=read["base"], tree=read["tree"], file="long.txt")
        self.assertEqual((one["base"], one["tree"], one["file"]["path"], one["whole"]),
                         (read["base"], read["tree"], "long.txt", True))
        lines = one["patch"].splitlines()
        self.assertEqual(sum(line.startswith("diff --git ") for line in lines), 1, "that file alone")
        self.assertEqual([line for line in lines if line.startswith("@@")], ["@@ -1,40 +1,40 @@"],
                         "the whole file, every unchanged line with it")
        renamed = W.review_diff(self.path, base=read["base"], tree=read["tree"], file="docs/new name.md")
        self.assertIn("rename from docs/old name.md", renamed["patch"], "a rename read by both its paths")
        self.assertIn("+one more line", renamed["patch"])
        # Whether a file is read whole is decided from its sizes before any diff runs: a large file with one
        # change never has its whole diff made, only to be thrown away.
        calls = []
        run = subprocess.run

        def recorded(argv, *args, **kwargs):
            calls.append(list(argv))
            return run(argv, *args, **kwargs)
        saved = W.FILE_LIMIT
        self.addCleanup(setattr, W, "FILE_LIMIT", saved)
        self.addCleanup(setattr, W.subprocess, "run", run)
        W.subprocess.run = recorded
        size = os.path.getsize(os.path.join(self.path, "long.txt"))
        W.FILE_LIMIT = size - 1
        short = W.review_diff(self.path, base=read["base"], tree=read["tree"], file="long.txt")
        self.assertFalse(short["whole"], "past the bound, its changes only, and said so")
        hunks = [line for line in short["patch"].splitlines() if line.startswith("@@")]
        self.assertEqual(len(hunks), 1)
        self.assertTrue(hunks[0].startswith("@@ -17,7 +17,7 @@"), hunks)
        self.assertFalse([argv for argv in calls if W.WHOLE in argv], "no whole diff of a file past the bound")
        calls.clear()
        W.FILE_LIMIT = saved
        self.assertTrue(W.review_diff(self.path, base=read["base"], tree=read["tree"], file="long.txt")["whole"])
        self.assertTrue([argv for argv in calls if W.WHOLE in argv], "control: one well under the bound is read whole")

    def test_a_list_too_long_for_one_read_goes_on_from_the_same_snapshot(self):
        self.edit()
        saved = W.FILES_LIMIT
        W.FILES_LIMIT = 4
        self.addCleanup(setattr, W, "FILES_LIMIT", saved)
        first = W.review_diff(self.path)
        self.assertEqual((len(first["files"]), first["files_total"]), (4, 6))
        write(os.path.join(self.path, "later.txt"), "after the list was read\n")
        rest = W.review_diff(self.path, base=first["base"], tree=first["tree"], files_from=4)
        self.assertEqual((rest["base"], rest["tree"], rest["files_total"], rest["files_from"]),
                         (first["base"], first["tree"], 6, 4))
        listed = [entry["path"] for entry in first["files"] + rest["files"]]
        self.assertEqual(sorted(listed), sorted([self.DEEP, "with space.txt", "docs/new name.md", "image.bin",
                                                 "gone.txt", "long.txt"]),
                         "every file of the snapshot once, the one written since in none")
        self.assertNotIn("patch", rest, "a page of the list is the list alone")

    def test_every_read_comes_from_the_snapshot_it_names_whatever_the_worktree_does(self):
        self.edit()
        # A character that spans several bytes, laid so that a part's edge falls inside one.
        write(os.path.join(self.path, "big.txt"), "".join("строка %d ✓\n" % number for number in range(4000)))
        first = W.review_diff(self.path)
        base, tree = first["base"], first["tree"]
        # The worktree moves on after the list was read: its terminals stay live.
        write(os.path.join(self.path, "long.txt"), "rewritten\n")
        write(os.path.join(self.path, "big.txt"), "gone\n")
        one = W.review_diff(self.path, base=base, tree=tree, file="long.txt")
        self.assertIn("+changed 20", one["patch"], "the file as it was listed")
        self.assertNotIn("rewritten", one["patch"])
        saved = W.PATCH_CHUNK
        W.PATCH_CHUNK = 1000
        self.addCleanup(setattr, W, "PATCH_CHUNK", saved)
        parts, offset = [], 0
        while True:
            read = W.review_diff(self.path, offset, base=base, tree=tree)
            self.assertLessEqual(len(read["patch"].encode("utf-8")), W.PATCH_CHUNK)
            self.assertEqual((read["base"], read["tree"]), (base, tree), "every part names its snapshot")
            parts.append(read["patch"])
            if read["next"] >= read["total"]:
                break
            self.assertGreater(read["next"], offset, "a part always moves forward")
            offset = read["next"]
        self.assertGreater(len(parts), 20, "the change is larger than one part")
        self.assertEqual("".join(parts).encode("utf-8"),
                         self.diff("--no-ext-diff", "--no-textconv", "--find-renames", "--no-color", base, tree),
                         "the parts are the snapshot's whole patch, byte for byte")
        self.assertNotEqual(W.review_diff(self.path)["tree"], tree, "control: read again, the change is new")

    def test_an_offset_inside_a_character_is_refused_not_mangled(self):
        write(os.path.join(self.path, "big.txt"), "строка\n" * 50)
        first = W.review_diff(self.path)
        whole = first["patch"].encode("utf-8")
        inside = next(i for i, byte in enumerate(whole) if byte & 0xC0 == 0x80)
        with self.assertRaises(RuntimeError) as caught:
            W.review_diff(self.path, inside, base=first["base"], tree=first["tree"])
        self.assertIn("inside a character", str(caught.exception))

    def test_only_a_file_of_the_snapshot_is_read_and_its_path_is_never_a_pattern(self):
        write(os.path.join(self.path, "[ab].txt"), "bracketed\n")
        write(os.path.join(self.path, "a.txt"), "plain\n")
        read = W.review_diff(self.path)
        self.assertEqual(sorted(entry["path"] for entry in read["files"]), ["[ab].txt", "a.txt"])
        one = W.review_diff(self.path, base=read["base"], tree=read["tree"], file="[ab].txt")
        self.assertIn("+bracketed", one["patch"])
        self.assertNotIn("plain", one["patch"], "`[ab].txt` named that file, never a pattern matching a.txt")
        for asked in ("nope.txt", ":(glob)*", "*.txt", "", "../app.txt"):
            with self.assertRaises(W.ChangeRefused, msg=asked) as caught:
                W.review_diff(self.path, base=read["base"], tree=read["tree"], file=asked)
            self.assertIn("is not a file of this change", str(caught.exception))

    def test_the_repositorys_settings_add_no_helper_or_colour_and_keep_renames_found(self):
        self.edit()
        write(os.path.join(self.path, ".gitattributes"), "*.md diff=shout\n")
        for key, value in (("diff.renames", "false"), ("color.ui", "always"),
                           ("diff.shout.textconv", "sed s/^/CONVERTED:/")):
            git(self.repo, "config", key, value)
        read = W.review_diff(self.path)
        renamed = [entry for entry in read["files"] if entry["path"] == "docs/new name.md"]
        self.assertEqual([(entry["status"], entry["old"]) for entry in renamed], [("R", "docs/old name.md")])
        one = W.review_diff(self.path, base=read["base"], tree=read["tree"], file="docs/new name.md")
        for text in (read["patch"], one["patch"]):
            self.assertNotIn("\x1b[", text, "no colour")
            self.assertNotIn("CONVERTED:", text, "no text conversion")
        # Control: the same reads without the explicit options follow the settings.
        names = self.diff("--no-color", "--name-status", "-z", read["base"], read["tree"]).split(b"\0")
        self.assertIn(b"docs/old name.md", names)
        self.assertFalse([name for name in names if name.startswith(b"R")])
        self.assertEqual(names[names.index(b"docs/old name.md") - 1], b"D", "a rename shown as a delete")
        plain = self.diff(read["base"], read["tree"])
        self.assertIn(b"\x1b[", plain)
        self.assertIn(b"CONVERTED:", plain)

    def test_a_tree_git_no_longer_holds_is_said_gone_and_a_name_that_is_no_object_refused(self):
        with self.assertRaises(W.ChangeRefused) as caught:
            W.review_diff(self.path, tree="0" * 40)
        self.assertIn("no longer holds", str(caught.exception))
        for asked in ("HEAD", "--output=x", "abc", "0" * 39):
            with self.assertRaises(W.ChangeRefused, msg=asked) as caught:
                W.review_diff(self.path, tree=asked)
            self.assertIn("is not an object name", str(caught.exception))
        head = git(self.path, "rev-parse", "HEAD").strip()
        self.assertEqual(W.review_diff(self.path, base=head, tree=W.work_tree(self.path))["files"], [],
                         "control: a pair git holds is read")


class Merge(Repo):
    """The approved merge — one work commit, an explicit merge commit, then everything the run owned goes."""

    def test_the_verified_change_is_committed_merged_and_cleaned_up(self):
        path = self.worktree("run1")
        env = self.environment(path)
        main_env = self.environment(self.repo)
        result = self.merge("run1", path)
        self.assertEqual(result["result"], "merged")
        self.assertEqual(git(self.repo, "log", "-1", "--format=%s", "develop").strip(), "Merge 2026-09-15_1200-run1")
        self.assertEqual(len(git(self.repo, "log", "-1", "--format=%P", "develop").split()), 2,
                         "an explicit merge commit, never a fast-forward")
        work = git(self.repo, "log", "-1", "--format=%s", "develop^2").strip()
        self.assertEqual(work, "2026-09-15_1200-run1: the change")
        tree = git(self.repo, "ls-tree", "-r", "--name-only", "develop").split()
        self.assertIn("todo/done/2026-09-15_1200-run1.md", tree)
        self.assertNotIn("todo/2026-09-15_1200-run1.md", tree)
        self.assertIn("**Status:** PASS (implementation)", git(self.repo, "show", "develop:todo/done/2026-09-15_1200-run1.md"))
        self.assertFalse(os.path.exists(path))
        self.assertNotIn("run1", git(self.repo, "branch", "--format=%(refname:short)").split())
        self.assertFalse(os.path.exists(env), "the worktree's environment went with it")
        self.assertTrue(os.path.exists(main_env), "the main checkout's environment is untouched")

    def test_a_repository_without_a_done_folder_has_the_plan_deleted_by_the_merge(self):
        path = self.worktree("run1")
        plan = os.path.join("todo", "2026-09-15_1200-run1.md")
        result = W.merge(self.repo, path, "run1", "develop", W.work_tree(path), plan, None,
                         "2026-09-15_1200-run1: the change", "Merge 2026-09-15_1200-run1")
        self.assertEqual(result["result"], "merged")
        tree = git(self.repo, "ls-tree", "-r", "--name-only", "develop").split()
        self.assertNotIn("todo/2026-09-15_1200-run1.md", tree, "the finished plan is gone")
        self.assertFalse([name for name in tree if name.startswith("todo/done/")], "and no done folder appears")
        self.assertEqual(git(self.repo, "show", "develop:app.txt"), "one\nrun1\n", "the change itself merged")

    def test_a_merge_whose_commit_failed_merges_when_continued(self):
        for done in (os.path.join("todo", "done"), None):
            with self.subTest(done_folder=done):
                run_id = "run-%s" % ("done" if done else "nodone")
                path = self.worktree(run_id)
                plan = os.path.join("todo", "2026-09-15_1200-%s.md" % run_id)
                # CRLF, so a restored plan that changed its line endings would not match.
                with open(os.path.join(path, plan), "wb") as fh:
                    fh.write(b"**Status:** DRAFT\r\nplan\r\n")
                verified = W.work_tree(path)
                # The first commit fails after the plan was finished and staged, as a missing identity does.
                hooks = git(self.repo, "config", "core.hooksPath").strip()
                marker = os.path.join(self.tmp, "failed-once-%s" % run_id)
                write(os.path.join(hooks, "pre-commit"),
                      "#!/bin/sh\n[ -e '%s' ] && exit 0\ntouch '%s'\nexit 1\n" % (marker.replace("\\", "/"),
                                                                                marker.replace("\\", "/")))
                os.chmod(os.path.join(hooks, "pre-commit"), 0o755)
                self.addCleanup(lambda: os.path.exists(os.path.join(hooks, "pre-commit"))
                                and os.remove(os.path.join(hooks, "pre-commit")))
                with self.assertRaises(W.GitError):
                    W.merge(self.repo, path, run_id, "develop", verified, plan, done, "%s: change" % run_id,
                            "Merge %s" % run_id)
                self.assertFalse(os.path.exists(os.path.join(path, plan)), "the failed attempt had finished the plan")
                result = W.merge(self.repo, path, run_id, "develop", verified, plan, done, "%s: change" % run_id,
                                 "Merge %s" % run_id)
                self.assertEqual(result["result"], "merged", "continuing the merge commits the verified change")
                os.remove(os.path.join(hooks, "pre-commit"))

    def test_a_change_made_after_verification_is_refused(self):
        path = self.worktree("run1")
        verified = W.work_tree(path)
        write(os.path.join(path, "app.txt"), "edited after the architect judged it\n")
        with self.assertRaises(W.MergeRefused):
            W.merge(self.repo, path, "run1", "develop", verified, "todo/x.md", "todo/done", "m", "Merge m")
        self.assertEqual(self.merges_on_develop(), [])

    def test_staged_changes_in_the_base_checkout_are_the_operators_and_refuse_the_merge(self):
        path = self.worktree("run1")
        write(os.path.join(self.repo, "operator.txt"), "mine\n")
        git(self.repo, "add", "operator.txt")
        with self.assertRaises(W.MergeRefused):
            self.merge("run1", path)
        self.assertEqual(git(self.repo, "diff", "--cached", "--name-only").split(), ["operator.txt"],
                         "the operator's staged content is exactly as it was")
        self.assertEqual(self.merges_on_develop(), [])

    def test_a_merge_refused_after_its_work_commit_merges_when_continued(self):
        for done in (os.path.join("todo", "done"), None):
            with self.subTest(done_folder=done):
                run_id = "run-%s" % ("done" if done else "nodone")
                path = self.worktree(run_id)
                plan = os.path.join("todo", "2026-09-15_1200-%s.md" % run_id)
                verified = W.work_tree(path)
                write(os.path.join(self.repo, "operator.txt"), "mine\n")
                git(self.repo, "add", "operator.txt")
                with self.assertRaises(W.MergeRefused):
                    W.merge(self.repo, path, run_id, "develop", verified, plan, done, "%s: change" % run_id,
                            "Merge %s" % run_id)
                git(self.repo, "restore", "--staged", "operator.txt")
                os.remove(os.path.join(self.repo, "operator.txt"))
                result = W.merge(self.repo, path, run_id, "develop", verified, plan, done, "%s: change" % run_id,
                                 "Merge %s" % run_id)
                self.assertEqual(result["result"], "merged", "the written work commit is merged, not undone")

    def test_a_base_not_checked_out_is_merged_without_touching_any_checkout(self):
        git(self.repo, "switch", "-q", "-c", "elsewhere")
        path = self.worktree("run1")
        self.assertEqual(self.merge("run1", path)["result"], "merged")
        self.assertEqual(git(self.repo, "log", "-1", "--format=%s", "develop").strip(), "Merge 2026-09-15_1200-run1")
        self.assertEqual(git(self.repo, "status", "--porcelain").strip(), "")

    def test_a_conflict_goes_back_into_the_run_and_merges_after_its_resolution(self):
        path = self.worktree("run1")
        write(os.path.join(self.repo, "app.txt"), "one\nthe base moved\n")
        git(self.repo, "commit", "-q", "-am", "base moved")
        base_before = git(self.repo, "rev-parse", "develop").strip()
        result = self.merge("run1", path)
        self.assertEqual((result["result"], result["files"]), ("conflict", ["app.txt"]))
        self.assertEqual(git(self.repo, "rev-parse", "develop").strip(), base_before, "the base is untouched")
        self.assertEqual(git(self.repo, "status", "--porcelain").strip(), "", "the base checkout is left clean")
        self.assertIn("<<<<<<<", open(os.path.join(path, "app.txt"), encoding="utf-8").read())
        # The engineer resolves the file; the architect verifies; the operator approves again.
        write(os.path.join(path, "app.txt"), "one\nthe base moved\nrun1\n")
        again = W.merge(self.repo, path, "run1", "develop", W.work_tree(path),
                        os.path.join("todo", "2026-09-15_1200-run1.md"), os.path.join("todo", "done"),
                        "2026-09-15_1200-run1: the change", "Merge 2026-09-15_1200-run1")
        self.assertEqual(again["result"], "merged")
        self.assertEqual(git(self.repo, "show", "develop:app.txt"), "one\nthe base moved\nrun1\n")
        history = git(self.repo, "log", "--format=%s", "develop").splitlines()
        self.assertIn("Merge develop into run1", history, "one reconciliation merge commit, no rebase")

    def test_a_conflict_handed_back_is_read_against_the_base_brought_in_never_its_own_commit(self):
        """A conflict leaves the run's change committed and the moved base merged into its worktree. What the
        operator then judges is what the run adds to that base — not the base's own commits arriving."""
        path = self.worktree("run1")
        write(os.path.join(self.repo, "app.txt"), "one\nthe base moved\n")
        for name in ("elsewhere.txt", "more.txt"):
            write(os.path.join(self.repo, name), "the base's own\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base moved")
        moved = git(self.repo, "rev-parse", "develop").strip()
        before = W.review_diff(path)
        self.assertEqual((before["base"], before["against"]), (git(path, "rev-parse", "HEAD").strip(), "commit"),
                         "no base brought in: against the worktree's own commit, as ever")
        self.assertEqual(self.merge("run1", path)["result"], "conflict")
        write(os.path.join(path, "app.txt"), "one\nthe base moved\nrun1\n")
        read = W.review_diff(path)
        self.assertEqual((read["base"], read["against"]), (moved, "merged"), "against the base as it was brought in")
        self.assertEqual(sorted(each["path"] for each in read["files"]),
                         ["app.txt", "todo/done/2026-09-15_1200-run1.md"], "the run's own change, and no more")
        self.assertEqual(W.review_diff(path, base=read["base"], tree=read["tree"], file="app.txt")["file"]["added"], 1,
                         "its resolved file adds the run's one line to the base's")
        # Control: against the run's own commit — what was read before — the base's files are the change.
        own = W.review_diff(path, base=git(path, "rev-parse", "HEAD").strip(), tree=read["tree"])
        self.assertEqual(sorted(each["path"] for each in own["files"]), ["app.txt", "elsewhere.txt", "more.txt"])


class Closeout(Repo):
    """A run whose engineer closed it out: what that closeout changed is read path by path, the tree it left is
    exactly what a merge commits, and a change sent back is the one the architect verified again."""

    PLAN = "todo/2026-09-15_1200-run1.md"
    DONE = "todo/done/2026-09-15_1200-run1.md"
    MESSAGES = ("2026-09-15_1200-run1: the change", "Merge 2026-09-15_1200-run1")

    def at(self, path, name):
        return os.path.join(path, *name.split("/"))

    def closed(self):
        """A run's worktree as its engineer's closeout left it — the todo moved to the done folder and cut, a
        document edited — with the tree the architect verified before it and the tree it left."""
        path = self.worktree("run1")
        write(self.at(path, "docs/guide.md"), "the guide\n")
        verified = W.work_tree(path)
        os.remove(self.at(path, self.PLAN))
        write(self.at(path, self.DONE), "**Status:** PASS 2026-09-15, as the engineer wrote it\nthe record\n")
        write(self.at(path, "docs/guide.md"), "the guide\nwhat stays true\n")
        return path, verified, W.work_tree(path)

    def merge_closed(self, path, tree):
        # No plan for the controller to finish: the closeout has.
        return W.merge(self.repo, path, "run1", "develop", tree, None, os.path.join("todo", "done"), *self.MESSAGES)

    def test_what_a_closeout_changed_is_read_path_by_path_a_move_as_its_two_ends(self):
        path, verified, closeout = self.closed()
        self.assertEqual(sorted(W.changed(path, verified, closeout)),
                         [("A", self.DONE), ("D", self.PLAN), ("M", "docs/guide.md")])
        self.assertEqual(W.changed(path, closeout, closeout), [], "control: a tree against itself changed nothing")

    def test_a_merge_commits_exactly_the_tree_the_closeout_left(self):
        path, _, closeout = self.closed()
        # What the operator reads at the final gate is that tree: the todo where its closeout put it.
        read = W.review_diff(path)
        self.assertEqual(read["tree"], closeout)
        self.assertEqual(sorted(entry["path"] for entry in read["files"]), ["app.txt", "docs/guide.md", self.DONE])
        self.assertEqual(self.merge_closed(path, closeout)["result"], "merged")
        self.assertEqual(git(self.repo, "rev-parse", "develop^2^{tree}").strip(), closeout,
                         "the work commit is the tree the operator reviewed, byte for byte")
        self.assertEqual(git(self.repo, "show", "develop:" + self.DONE),
                         "**Status:** PASS 2026-09-15, as the engineer wrote it\nthe record\n")
        self.assertNotIn(self.PLAN, git(self.repo, "ls-tree", "-r", "--name-only", "develop").split())
        self.assertFalse(os.path.exists(path), "and everything the run owned is gone, as after any merge")
        # Control: a run with no closeout has the controller finish its plan, so its commit is not the tree
        # the merge was handed.
        other = self.worktree("run2")
        handed = W.work_tree(other)
        self.assertEqual(self.merge("run2", other)["result"], "merged")
        self.assertNotEqual(git(self.repo, "rev-parse", "develop^2^{tree}").strip(), handed)

    def test_a_change_made_after_the_closeout_is_refused_and_nothing_is_committed_or_merged(self):
        path, _, closeout = self.closed()
        write(self.at(path, "app.txt"), "edited after the closeout\n")
        with self.assertRaisesRegex(W.MergeRefused, "no longer the change that was offered"):
            self.merge_closed(path, closeout)
        self.assertEqual(self.merges_on_develop(), [])
        self.assertEqual(git(self.repo, "rev-list", "--count", "develop..run1").strip(), "0", "no work commit either")
        self.assertEqual(git(path, "diff", "--cached", "--name-only").strip(), "", "and nothing was staged")
        with open(self.at(path, "app.txt"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "edited after the closeout\n", "the worktree is as it was found")

    def test_a_closed_out_merge_whose_commit_failed_merges_when_continued(self):
        path, _, closeout = self.closed()
        hooks = git(self.repo, "config", "core.hooksPath").strip()
        marker = os.path.join(self.tmp, "failed-once").replace("\\", "/")
        write(os.path.join(hooks, "pre-commit"), "#!/bin/sh\n[ -e '%s' ] && exit 0\ntouch '%s'\nexit 1\n"
              % (marker, marker))
        os.chmod(os.path.join(hooks, "pre-commit"), 0o755)
        with self.assertRaises(W.GitError):
            self.merge_closed(path, closeout)
        self.assertTrue(os.path.exists(self.at(path, self.DONE)), "the closed-out todo stays where its engineer put it")
        self.assertIn(self.DONE, git(path, "diff", "--cached", "--name-only").split(),
                      "the precondition: the failed attempt left the change staged")
        # Tried again on a worktree that moved meanwhile, it is refused with nothing left staged for a role to find.
        write(self.at(path, "app.txt"), "typed after the failed merge\n")
        with self.assertRaises(W.MergeRefused):
            self.merge_closed(path, closeout)
        self.assertEqual(git(path, "diff", "--cached", "--name-only").strip(), "")
        write(self.at(path, "app.txt"), "one\nrun1\n")
        self.assertEqual(self.merge_closed(path, closeout)["result"], "merged")
        self.assertEqual(git(self.repo, "rev-parse", "develop^2^{tree}").strip(), closeout)

    def test_a_conflict_is_reopened_with_its_todo_where_the_resolving_roles_are_asked_to_read_it(self):
        path, verified, closeout = self.closed()
        write(os.path.join(self.repo, "app.txt"), "one\nthe base moved\n")
        git(self.repo, "commit", "-q", "-am", "base moved")
        result = self.merge_closed(path, closeout)
        self.assertEqual((result["result"], result["files"]), ("conflict", ["app.txt"]))
        self.assertFalse(os.path.exists(self.at(path, self.PLAN)),
                         "the precondition: the todo is closed out in the run's commit, gone from its path")
        # Before the engineer's turn on the conflict.
        self.assertEqual(W.reopen(path, closeout, verified), [])
        with open(self.at(path, self.PLAN), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "**Status:** DRAFT\nplan\n", "the todo as the architect verified it")
        self.assertFalse(os.path.exists(self.at(path, self.DONE)))
        with open(self.at(path, "app.txt"), encoding="utf-8") as fh:
            self.assertIn("<<<<<<<", fh.read(), "the conflict is still the engineer's to resolve")
        self.assertTrue(git(path, "rev-parse", "--verify", "MERGE_HEAD").strip(), "and the merge is still under way")
        # Resolved, verified, closed out again and merged: one todo, where its repository keeps it finished.
        write(self.at(path, "app.txt"), "one\nthe base moved\nrun1\n")
        resolved = W.work_tree(path)
        os.remove(self.at(path, self.PLAN))
        write(self.at(path, self.DONE), "**Status:** PASS 2026-09-15\nthe record\n")
        final = W.work_tree(path)
        self.assertEqual(sorted(W.changed(path, resolved, final)), [("A", self.DONE), ("D", self.PLAN)])
        self.assertEqual(self.merge_closed(path, final)["result"], "merged")
        tree = git(self.repo, "ls-tree", "-r", "--name-only", "develop").split()
        self.assertIn(self.DONE, tree)
        self.assertNotIn(self.PLAN, tree)
        self.assertIn("Merge develop into run1", git(self.repo, "log", "--format=%s", "develop").splitlines())

    def test_a_todo_its_repository_deletes_comes_back_from_the_verified_tree_when_reopened(self):
        """Deleted by its closeout, it is in no folder and no commit: the tree the architect verified holds it."""
        path = self.worktree("run1")
        verified = W.work_tree(path)
        os.remove(self.at(path, self.PLAN))
        final = W.work_tree(path)
        self.assertEqual(W.holds(path, final, [self.PLAN]), [])
        self.assertEqual(W.reopen(path, final, verified), [])
        with open(self.at(path, self.PLAN), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "**Status:** DRAFT\nplan\n")
        self.assertEqual(W.work_tree(path), verified)

    def test_which_paths_lie_outside_the_todo_folders_and_a_repositorys_documents_is_gits_own_matching(self):
        path = self.worktree("run1")
        names = ("README.md", "app/part/README.md", "docs/guide.md", "app/part/docs/structure.md", "roles/engineer.md",
                 "skills/review/SKILL.md", "AGENTS.md", "app/part/main.py", "docs.md", "todo[1]/note.md")
        for name in names:
            write(self.at(path, name), "one\n")
        before = W.work_tree(path)
        for name in names:
            write(self.at(path, name), "two\n")
        os.remove(self.at(path, self.PLAN))
        write(self.at(path, self.DONE), "moved\n")
        after = W.work_tree(path)

        def outside(folders, patterns):
            return sorted(name for _, name in W.changed(path, before, after, folders, patterns))
        behaviour = ["AGENTS.md", "app/part/main.py", "docs.md", "roles/engineer.md", "skills/review/SKILL.md",
                     "todo[1]/note.md"]
        self.assertEqual(outside(("todo", "todo\\done"), ("**/README.md", "**/docs/**")), behaviour,
                         "a README and a docs folder wherever they are; a persona, a skill and code are neither")
        self.assertEqual(outside(("todo",), ("README.md", "docs/")),
                         sorted(behaviour + ["app/part/README.md", "app/part/docs/structure.md"]),
                         "a file and a folder named plainly are that file and that folder")
        self.assertEqual(outside(("todo[1]", None), ()),
                         sorted(set(names) - {"todo[1]/note.md"} | {self.PLAN, self.DONE}),
                         "a folder is taken literally, never as a pattern, and one a repository has not is none")
        self.assertEqual(W.holds(path, after, [self.PLAN, self.DONE, "todo[1]/note.md", "docs"]),
                         [self.DONE, "todo[1]/note.md"], "a file a tree holds, by its exact name")

    def test_a_reopened_change_is_the_tree_the_architect_verified_and_nothing_is_staged(self):
        path, verified, closeout = self.closed()
        self.assertEqual(W.reopen(path, closeout, verified), [])
        self.assertEqual(W.work_tree(path), verified)
        with open(self.at(path, self.PLAN), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "**Status:** DRAFT\nplan\n", "the todo is back where its roles read it")
        self.assertFalse(os.path.exists(self.at(path, self.DONE)))
        self.assertEqual(git(path, "diff", "--cached", "--name-only").strip(), "", "files are written, none staged")
        self.assertEqual(W.reopen(path, closeout, verified), [], "reopened again, it is found as it should be")
        self.assertEqual(W.work_tree(path), verified)

    def test_a_reopen_keeps_what_was_changed_again_after_the_closeout(self):
        path, verified, closeout = self.closed()
        write(self.at(path, "docs/guide.md"), "the guide\nwhat stays true\nand what was typed at the gate\n")
        write(self.at(path, "app.txt"), "typed at the gate too\n")
        self.assertEqual(W.reopen(path, closeout, verified), ["docs/guide.md"],
                         "a path changed again since is someone's later work, and is said")
        with open(self.at(path, "docs/guide.md"), encoding="utf-8") as fh:
            self.assertIn("typed at the gate", fh.read())
        with open(self.at(path, "app.txt"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "typed at the gate too\n", "what the closeout never touched is left alone")
        self.assertTrue(os.path.exists(self.at(path, self.PLAN)), "the todo is back all the same")
        self.assertFalse(os.path.exists(self.at(path, self.DONE)))

    def test_a_reopen_that_cannot_read_the_verified_tree_changes_nothing(self):
        path, _, closeout = self.closed()
        before = W.work_tree(path)
        with self.assertRaises(W.GitError):
            W.reopen(path, closeout, "0" * 40)
        self.assertEqual(W.work_tree(path), before, "a tree git does not hold is not a tree without the todo")


class Adopt(Repo):
    """A git side effect whose worker died before reporting is adopted, never applied twice."""

    def test_a_merge_already_written_is_found_and_not_merged_again(self):
        git(self.repo, "switch", "-q", "-c", "elsewhere")
        path = self.worktree("run1")
        self.environment(path)
        # The first attempt got as far as the merge commit, then its worker died.
        git(path, "add", "-A")
        git(path, "commit", "-q", "-m", "2026-09-15_1200-run1: the change")
        base = git(self.repo, "rev-parse", "develop").strip()
        tip = git(self.repo, "rev-parse", "run1").strip()
        tree = git(self.repo, "merge-tree", "--write-tree", base, tip).split()[0]
        commit = git(self.repo, "commit-tree", tree, "-p", base, "-p", tip, "-m", "Merge 2026-09-15_1200-run1").strip()
        git(self.repo, "update-ref", "refs/heads/develop", commit, base)

        result = self.merge("run1", path)
        self.assertEqual((result["result"], result["commit"]), ("merged", commit))
        self.assertEqual(self.merges_on_develop(), ["Merge 2026-09-15_1200-run1"])
        self.assertFalse(os.path.exists(path), "the adopted merge still cleans up")

        # Control: repeating the merge without reading git first writes a second merge commit.
        git(self.repo, "branch", "run1-again", tip)
        base = git(self.repo, "rev-parse", "develop").strip()
        tree = git(self.repo, "merge-tree", "--write-tree", base, tip).split()[0]
        second = git(self.repo, "commit-tree", tree, "-p", base, "-p", tip, "-m", "Merge 2026-09-15_1200-run1").strip()
        git(self.repo, "update-ref", "refs/heads/develop", second, base)
        self.assertEqual(len(self.merges_on_develop()), 2)

    def test_another_runs_merge_with_the_same_message_is_not_adopted(self):
        """Two runs can carry one subject; only the run's own tip identifies its merge."""
        git(self.repo, "switch", "-q", "-c", "elsewhere")
        message = "Merge the run's plan"                  # the same subject for both runs
        paths = {}
        for run_id in ("run1", "run2"):
            paths[run_id] = self.worktree(run_id, change=False)
            write(os.path.join(paths[run_id], run_id + ".txt"), "work of %s\n" % run_id)
            write(os.path.join(paths[run_id], "todo", "2026-09-15_1200-%s.md" % run_id), "**Status:** DRAFT\n")
        for run_id in ("run1", "run2"):
            result = W.merge(self.repo, paths[run_id], run_id, "develop", W.work_tree(paths[run_id]),
                             os.path.join("todo", "2026-09-15_1200-%s.md" % run_id),
                             os.path.join("todo", "done"), "%s: the change" % run_id, message)
            self.assertEqual(result["result"], "merged")
        tree = git(self.repo, "ls-tree", "-r", "--name-only", "develop").split()
        self.assertIn("run2.txt", tree, "the second run's work is merged, not mistaken for the first's")
        self.assertEqual(len(self.merges_on_develop()), 2)
        self.assertFalse(os.path.exists(paths["run2"]))

    def test_a_discard_already_done_is_adopted(self):
        path = self.worktree("run1")
        W.discard(self.repo, path, "run1")
        W.discard(self.repo, path, "run1")
        self.assertFalse(os.path.exists(path))
        # Control: git itself fails on the second removal.
        self.assertNotEqual(subprocess.run(["git", "-C", self.repo, "worktree", "remove", path],
                                           capture_output=True).returncode, 0)


class Cleanup(Repo):
    """Nothing a run owns is removed until the base is proven to hold its work."""

    def test_an_unmerged_branch_is_refused_and_nothing_is_removed(self):
        path = self.worktree("run1")
        git(path, "add", "-A")
        git(path, "commit", "-q", "-m", "work the base does not have")
        env = self.environment(path)
        with self.assertRaises(W.GitError):
            W.cleanup(self.repo, path, "run1", "develop")
        self.assertTrue(os.path.isdir(path), "the worktree is kept")
        self.assertIn("run1", git(self.repo, "branch", "--format=%(refname:short)").split())
        self.assertTrue(os.path.exists(env), "and so is its environment")


class EnvironmentRemoval(Repo):
    """The deletion guards: only exactly a worktree's own environment is ever removed."""

    def test_its_environment_is_removed_and_a_missing_one_is_already_removed(self):
        path = self.worktree("run1", change=False)
        env = self.environment(path)
        self.assertTrue(envpath.remove_environment(path))
        self.assertFalse(os.path.exists(env))
        self.assertFalse(envpath.remove_environment(path))

    def test_a_directory_without_pyvenv_cfg_is_refused(self):
        path = self.worktree("run1", change=False)
        env = envpath.environment_for(path)
        write(os.path.join(env, "precious.txt"), "not an environment\n")
        with self.assertRaises(envpath.UnsafeRemoval):
            envpath.remove_environment(path)
        self.assertTrue(os.path.exists(os.path.join(env, "precious.txt")))

    def test_a_derived_path_outside_the_root_is_refused(self):
        outside = os.path.join(self.tmp, "outside")
        write(os.path.join(outside, "pyvenv.cfg"), "home = x\n")
        original = envpath.environment_for
        envpath.environment_for = lambda checkout: outside
        try:
            with self.assertRaises(envpath.UnsafeRemoval):
                envpath.remove_environment(self.repo)
        finally:
            envpath.environment_for = original
        self.assertTrue(os.path.exists(os.path.join(outside, "pyvenv.cfg")))

    def test_a_link_escaping_the_root_is_refused(self):
        path = self.worktree("run1", change=False)
        outside = os.path.join(self.tmp, "outside")
        write(os.path.join(outside, "pyvenv.cfg"), "home = x\n")
        env = envpath.environment_for(path)
        os.makedirs(os.path.dirname(env), exist_ok=True)
        if WINDOWS:
            subprocess.run(["cmd", "/c", "mklink", "/J", env, outside], check=True, capture_output=True)
        else:
            os.symlink(outside, env)
        with self.assertRaises(envpath.UnsafeRemoval):
            envpath.remove_environment(path)
        self.assertTrue(os.path.exists(os.path.join(outside, "pyvenv.cfg")), "the link's target is untouched")
        # Control: removing what the link resolves to, unguarded, would delete the outside directory.
        self.assertEqual(os.path.realpath(env), os.path.realpath(outside))

    def test_a_root_that_is_a_link_is_refused(self):
        path = self.worktree("run1", change=False)
        real_root = os.path.join(self.tmp, "real-root")
        os.makedirs(real_root)
        root = envpath.environment_root()
        os.makedirs(os.path.dirname(root), exist_ok=True)
        if WINDOWS:
            subprocess.run(["cmd", "/c", "mklink", "/J", root, real_root], check=True, capture_output=True)
        else:
            os.symlink(real_root, root)
        env = envpath.environment_for(path)
        write(os.path.join(env, "pyvenv.cfg"), "home = x\n")
        with self.assertRaises(envpath.UnsafeRemoval):
            envpath.remove_environment(path)
        self.assertTrue(os.path.exists(os.path.join(env, "pyvenv.cfg")))

    def refusing(self, call, named):
        """`os.unlink` or `os.rmdir`, refusing — as a file some process holds is refused — whatever is `named`."""
        real = getattr(os, call)

        def refuse(path, *args, **kwargs):
            if os.path.basename(os.fspath(path)) == named:
                raise PermissionError(13, "held by a process", os.fspath(path))
            return real(path, *args, **kwargs)
        return mock.patch.object(os, call, refuse)

    def test_a_removal_that_stopped_is_finished_by_the_same_call(self):
        """`pyvenv.cfg` is what says the folder is an environment. Removed in the folder's own order it can go
        before the file a removal stops at — and the retry, a continued merge's, then refuses what is left."""
        path = self.worktree("run1", change=False)
        env = self.environment(path)
        # Folders added until the folder's own order holds one after pyvenv.cfg, whatever that order is on
        # this filesystem: a removal that takes them as they come has deleted pyvenv.cfg when it gets there.
        for letter in "abcdefghijklmnopqrstuvwxyz":
            write(os.path.join(env, letter + "-folder", "held-by-a-process.bin"), "a library\n")
            order = os.listdir(env)
            if order.index(letter + "-folder") > order.index("pyvenv.cfg"):
                break
        else:
            self.fail("no folder came after pyvenv.cfg in this filesystem's order")
        for name in os.listdir(env):
            if name not in ("pyvenv.cfg", letter + "-folder"):
                os.remove(os.path.join(env, name, "held-by-a-process.bin"))
        with self.refusing("unlink", "held-by-a-process.bin"):
            with self.assertRaises(PermissionError):
                envpath.remove_environment(path)
        self.assertTrue(os.path.isfile(os.path.join(env, "pyvenv.cfg")), "it outlives everything it speaks for")
        self.assertTrue(envpath.remove_environment(path), "the same removal, the file let go")
        self.assertFalse(os.path.exists(env))

    def test_a_removal_stopped_at_the_folder_itself_is_finished_too(self):
        """All of it gone but the folder: nothing is left in it to say what it was, and nothing to lose."""
        path = self.worktree("run1", change=False)
        env = self.environment(path)
        write(os.path.join(env, "Lib", "library.bin"), "a library\n")
        with self.refusing("rmdir", os.path.basename(env)):
            with self.assertRaises(PermissionError):
                envpath.remove_environment(path)
        self.assertEqual(os.listdir(env), [])
        self.assertTrue(envpath.remove_environment(path))
        self.assertFalse(os.path.exists(env))
        # Control: only an empty folder is taken without its pyvenv.cfg.
        write(os.path.join(env, "Lib", "precious.txt"), "not an environment's\n")
        with self.assertRaises(envpath.UnsafeRemoval):
            envpath.remove_environment(path)
        self.assertTrue(os.path.isfile(os.path.join(env, "Lib", "precious.txt")))

    def test_a_link_inside_is_removed_and_what_it_leads_to_is_kept(self):
        path = self.worktree("run1", change=False)
        env = self.environment(path)
        outside = os.path.join(self.tmp, "outside")
        write(os.path.join(outside, "precious.txt"), "not the environment's\n")
        os.makedirs(os.path.join(env, "Lib"))
        for link in (os.path.join(env, "linked"), os.path.join(env, "Lib", "linked")):
            if WINDOWS:
                subprocess.run(["cmd", "/c", "mklink", "/J", link, outside], check=True, capture_output=True)
            else:
                os.symlink(outside, link)
        self.assertTrue(envpath.remove_environment(path))
        self.assertFalse(os.path.exists(env))
        self.assertTrue(os.path.isfile(os.path.join(outside, "precious.txt")), "the links went, not their target")


@unittest.skipUnless(WINDOWS, "Windows deletes no name of a file a process has loaded; Linux unlinks it")
class EnvironmentsShareNoFile(Repo):
    """uv installs a package into every environment as hard links to one cached copy, unless told to copy
    (`link-mode`, pyproject.toml). A worker has its libraries loaded for as long as it runs, and Windows
    deletes no name of a loaded file: a run worktree's environment, linked to the same copies, could not be
    removed while a worker ran — the run merged, and its merge failed at the cleanup, again at every retry."""

    def test_a_library_of_this_environment_is_no_other_environments_file(self):
        """The environment these tests run in is the one this checkout's worker imports from."""
        packages = os.path.join(sys.prefix, "Lib", "site-packages")
        shared = [os.path.relpath(os.path.join(folder, name), packages)
                  for folder, _, names in os.walk(packages) for name in names
                  if name.lower().endswith((".pyd", ".dll")) and os.stat(os.path.join(folder, name)).st_nlink > 1]
        self.assertEqual(shared[:3], [], "%d libraries of this environment are other environments' files too: it "
                         "was built before pyproject.toml told uv to copy. Stop this checkout's Windows worker and "
                         "rebuild it once: uv sync --locked --reinstall" % len(shared))

    def test_control_a_library_shared_with_a_running_process_holds_the_environment_until_it_ends(self):
        """What a shared file costs: the removal stops at it for as long as any process has it loaded under
        any of its names, and completes — run again, as a continued merge runs it — once none has."""
        import importlib.util
        path = self.worktree("run1", change=False)
        env = self.environment(path)
        # One file under two names, as uv's cache and an environment hold a library: a process loads the one,
        # the environment holds the other.
        cached = os.path.join(self.tmp, "cached.dll")
        shutil.copyfile(importlib.util.find_spec("select").origin, cached)
        linked = os.path.join(env, "Lib", "site-packages", "package", "library.pyd")
        os.makedirs(os.path.dirname(linked))
        os.link(cached, linked)
        # It ends when its input does. An environment's python is a launcher of the real one, so ending the
        # process started here would leave the one that loaded the file running.
        holder = subprocess.Popen([sys.executable, "-c", "import ctypes, sys; ctypes.WinDLL(sys.argv[1]); "
                                   "print('loaded', flush=True); sys.stdin.read()", cached],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

        def ended():
            holder.stdin.close()
            holder.wait(timeout=30)
            holder.stdout.close()
        self.addCleanup(lambda: holder.poll() is None and ended())
        self.assertEqual(holder.stdout.readline().strip(), "loaded")
        with self.assertRaises(PermissionError):
            envpath.remove_environment(path)
        self.assertTrue(os.path.isfile(linked), "the name in the environment stays")
        ended()
        self.assertTrue(envpath.remove_environment(path), "the same removal, once nothing has the file loaded")
        self.assertFalse(os.path.exists(env))


class Landing(Repo):
    """A run that stands on a recorded tip of its base: the base brought into its worktree when it moved, and
    its final tree landed only while the base is still where the run was judged."""

    def stand(self, run_id):
        path = self.worktree(run_id)
        return path, W.started_from(path)

    def land(self, run_id, path, tip, tree=None):
        return W.merge(self.repo, path, run_id, "develop", tree or W.work_tree(path), None,
                       os.path.join("todo", "done"), "%s: the change" % run_id, "Merge %s" % run_id, tip)

    def move_base(self, files):
        for name, text in files.items():
            write(os.path.join(self.repo, name), text)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base moved")
        return git(self.repo, "rev-parse", "develop").strip()

    def subjects(self, *args):
        # A commit before its parents, whatever second each was made in.
        return git(self.repo, "log", "--topo-order", "--format=%s", *args).splitlines()

    def test_a_base_that_stands_takes_the_final_tree_as_one_commit_and_the_merge_named_for_the_run(self):
        path, tip = self.stand("run1")
        self.assertEqual(tip, git(self.repo, "rev-parse", "develop").strip(), "it began from the base's tip")
        self.assertEqual(W.reconcile(self.repo, path, "develop", tip), {"moved": False})
        final = W.work_tree(path)
        result = self.land("run1", path, tip)
        self.assertEqual(result["result"], "merged")
        self.assertEqual(git(self.repo, "rev-parse", "develop^{tree}").strip(), final, "the base holds the final tree")
        self.assertEqual(self.subjects("--first-parent", "develop"), ["Merge run1", "base"])
        merge, landing = git(self.repo, "rev-list", "--parents", "-n", "1", "develop").split()[1:]
        self.assertEqual((merge, git(self.repo, "rev-list", "--parents", "-n", "1", landing).split()[1:]),
                         (tip, [tip]), "the merge's first parent is the base's tip, and the change one commit on it")
        self.assertEqual(git(self.repo, "show", "develop:app.txt"), "one\nrun1\n")
        self.assertFalse(os.path.exists(path), "the worktree is gone")
        self.assertFalse(W.branch_exists(self.repo, "run1"))
        self.assertEqual(self.land("run1", path, tip, final), result, "tried again, the merge it made is adopted")

    def test_a_base_that_moved_since_the_gate_takes_the_change_as_git_merges_the_two(self):
        """Once the operator has said Merge, a base that moved on is git's to merge: the change the gate
        showed, on the base as it is. No role's turn is spent on a merge git makes without a conflict."""
        path, tip = self.stand("run1")
        moved = self.move_base({"elsewhere.txt": "the base's own\n"})
        final = W.work_tree(path)
        result = self.land("run1", path, tip)
        self.assertEqual(result, {"result": "merged", "commit": git(self.repo, "rev-parse", "develop").strip(),
                                  "onto": moved}, "it says what it was merged onto")
        merge, landing = git(self.repo, "rev-list", "--parents", "-n", "1", "develop").split()[1:]
        self.assertEqual((merge, git(self.repo, "rev-list", "--parents", "-n", "1", landing).split()[1:],
                          git(self.repo, "rev-parse", landing + "^{tree}").strip()), (moved, [tip], final),
                         "the merge's first parent is the base as it is; the change is one commit on the tip it "
                         "was judged on, its tree the one the gate showed")
        self.assertEqual((git(self.repo, "show", "develop:app.txt"), git(self.repo, "show", "develop:elsewhere.txt")),
                         ("one\nrun1\n", "the base's own\n"), "the base holds the run's change and its own")
        self.assertEqual(self.subjects("--first-parent", "develop"), ["Merge run1", "base moved", "base"],
                         "the base's own history is its first-parent line")
        self.assertEqual((git(self.repo, "status", "--porcelain").strip(),
                          open(os.path.join(self.repo, "app.txt"), encoding="utf-8").read()), ("", "one\nrun1\n"),
                         "and its checkout is in step")
        self.assertFalse(os.path.exists(path), "the worktree is gone")
        self.assertFalse(W.branch_exists(self.repo, "run1"))
        self.assertEqual(self.land("run1", path, tip, final), result, "tried again, the merge it made is adopted")

    def test_a_base_that_moved_into_conflict_since_the_gate_takes_nothing_and_nothing_is_written(self):
        """Where git cannot merge the two, nothing lands and the controller resolves nothing: the conflict is
        the run's roles' to meet, in the worktree."""
        path, tip = self.stand("run1")
        moved = self.move_base({"app.txt": "one\nthe base moved\n"})
        offered = W.work_tree(path)
        self.assertEqual(self.land("run1", path, tip), {"result": "moved"})
        self.assertEqual((git(self.repo, "rev-parse", "develop").strip(), git(self.repo, "rev-parse", "run1").strip(),
                          W.work_tree(path), git(self.repo, "status", "--porcelain").strip()),
                         (moved, tip, offered, ""), "nothing committed, nothing merged, no checkout touched")
        came = W.reconcile(self.repo, path, "develop", tip)
        self.assertEqual((came["base_tip"], came["files"]), (moved, ["app.txt"]), "brought in, markers and all")

    def test_a_base_that_already_holds_the_change_takes_no_empty_merge(self):
        path, tip = self.stand("run1")
        moved = self.move_base({"app.txt": "one\nrun1\n",
                                os.path.join("todo", "2026-09-15_1200-run1.md"): "**Status:** DRAFT\nplan\n"})
        with self.assertRaisesRegex(W.MergeRefused, "no change that develop lacks"):
            self.land("run1", path, tip)
        self.assertEqual(git(self.repo, "rev-parse", "develop").strip(), moved)

    def test_a_base_that_moved_before_the_gate_is_brought_in_and_the_change_is_read_against_it(self):
        """Before the gate the base comes into the worktree, so what is judged and shown stands on it."""
        path, tip = self.stand("run1")
        moved = self.move_base({"elsewhere.txt": "the base's own\n"})
        came = W.reconcile(self.repo, path, "develop", tip)
        self.assertEqual((came["moved"], came["base_tip"], came["files"]), (True, moved, []))
        self.assertEqual(came["tree"], W.work_tree(path), "the tree the worktree holds with the base in it")
        self.assertTrue(os.path.isfile(os.path.join(path, "elsewhere.txt")), "the base's file is in the worktree")
        self.assertEqual(W.reconcile(self.repo, path, "develop", moved), {"moved": False}, "it stands on that tip now")
        read = W.review_diff(path, base=moved)
        self.assertEqual((read["against"], sorted(each["path"] for each in read["files"])),
                         ("tip", ["app.txt", "todo/2026-09-15_1200-run1.md"]), "the change is the run's own")
        final = W.work_tree(path)
        self.assertEqual(self.land("run1", path, moved)["result"], "merged")
        self.assertEqual(git(self.repo, "rev-parse", "develop^{tree}").strip(), final)
        self.assertEqual(self.subjects("--first-parent", "develop"), ["Merge run1", "base moved", "base"],
                         "the base's own history is its first-parent line")
        self.assertEqual([each for each in self.subjects("develop") if "stood" in each or "into" in each], [],
                         "nothing the run's branch held as the base came in is reachable from the base")

    def test_a_conflict_is_met_in_the_worktree_and_its_resolution_lands_as_the_same_two_commits(self):
        path, tip = self.stand("run1")
        moved = self.move_base({"app.txt": "one\nthe base moved\n"})
        came = W.reconcile(self.repo, path, "develop", tip)
        self.assertEqual((came["moved"], came["base_tip"], came["files"]), (True, moved, ["app.txt"]))
        self.assertIn("<<<<<<<", open(os.path.join(path, "app.txt"), encoding="utf-8").read())
        self.assertEqual((git(self.repo, "rev-parse", "develop").strip(), git(self.repo, "status", "--porcelain").strip()),
                         (moved, ""), "the base and its checkout are untouched")
        # The engineer resolves in the files, staging nothing; the architect judges the whole.
        write(os.path.join(path, "app.txt"), "one\nthe base moved\nrun1\n")
        final = W.work_tree(path)
        self.assertEqual(self.land("run1", path, moved)["result"], "merged")
        self.assertEqual((git(self.repo, "rev-parse", "develop^{tree}").strip(), git(self.repo, "show", "develop:app.txt")),
                         (final, "one\nthe base moved\nrun1\n"))
        self.assertEqual(self.subjects("develop"), ["Merge run1", "run1: the change", "base moved", "base"],
                         "the change and its merge — no merge of the base into the run, nothing kept as it came in")

    def test_a_base_that_moves_again_is_brought_in_again_and_an_answer_that_was_lost_is_adopted(self):
        path, tip = self.stand("run1")
        first = self.move_base({"elsewhere.txt": "the base's own\n"})
        came = W.reconcile(self.repo, path, "develop", tip)
        self.assertEqual(W.reconcile(self.repo, path, "develop", tip), came,
                         "asked again with the tip it began from — its answer lost — the merge under way is adopted")
        self.assertEqual(self.subjects("run1").count("As it stood when develop moved"), 1, "its files kept once")
        second = self.move_base({"more.txt": "the base's own, later\n"})
        again = W.reconcile(self.repo, path, "develop", first)
        self.assertEqual((again["moved"], again["base_tip"], again["files"]), (True, second, []))
        self.assertTrue(all(os.path.isfile(os.path.join(path, name)) for name in ("elsewhere.txt", "more.txt")))
        final = W.work_tree(path)
        self.assertEqual(self.land("run1", path, second)["result"], "merged")
        self.assertEqual(git(self.repo, "rev-parse", "develop^{tree}").strip(), final)
        self.assertEqual(self.subjects("--first-parent", "develop"), ["Merge run1", "base moved", "base moved", "base"])

    def test_the_operators_own_edits_in_the_base_checkout_are_never_written_over(self):
        path, tip = self.stand("run1")
        write(os.path.join(self.repo, "app.txt"), "one\nthe operator's, not committed\n")
        with self.assertRaises(W.MergeRefused):
            self.land("run1", path, tip)
        self.assertEqual((git(self.repo, "rev-parse", "develop").strip(),
                          open(os.path.join(self.repo, "app.txt"), encoding="utf-8").read()),
                         (tip, "one\nthe operator's, not committed\n"), "a file the landing changes: refused, kept")
        git(self.repo, "checkout", "-q", "--", "app.txt")
        write(os.path.join(self.repo, "todo", "README.md"), "todos\nthe operator's, elsewhere\n")
        write(os.path.join(self.repo, "operator.txt"), "mine\n")
        git(self.repo, "add", "operator.txt")
        with self.assertRaises(W.MergeRefused):
            self.land("run1", path, tip)
        self.assertEqual(git(self.repo, "diff", "--cached", "--name-only").split(), ["operator.txt"],
                         "staged content is the operator's: refused, exactly as it was")
        git(self.repo, "restore", "--staged", "operator.txt")
        os.remove(os.path.join(self.repo, "operator.txt"))
        self.assertEqual(self.land("run1", path, tip)["result"], "merged", "the commit it had written is merged")
        self.assertEqual(open(os.path.join(self.repo, "todo", "README.md"), encoding="utf-8").read(),
                         "todos\nthe operator's, elsewhere\n", "an edit the landing does not touch stays")
        self.assertEqual(self.subjects("develop").count("run1: the change"), 1, "and written once")

    def test_a_landing_whose_commit_a_hook_refused_lands_when_continued(self):
        path, tip = self.stand("run1")
        moved = self.move_base({"app.txt": "one\nthe base moved\n"})
        W.reconcile(self.repo, path, "develop", tip)
        write(os.path.join(path, "app.txt"), "one\nthe base moved\nrun1\n")
        final = W.work_tree(path)
        hooks = git(self.repo, "config", "core.hooksPath").strip()
        marker = os.path.join(self.tmp, "failed-once").replace("\\", "/")
        write(os.path.join(hooks, "pre-commit"), "#!/bin/sh\n[ -e '%s' ] && exit 0\ntouch '%s'\nexit 1\n" % (marker, marker))
        os.chmod(os.path.join(hooks, "pre-commit"), 0o755)
        self.addCleanup(lambda: os.path.exists(os.path.join(hooks, "pre-commit"))
                        and os.remove(os.path.join(hooks, "pre-commit")))
        with self.assertRaises(W.GitError):
            self.land("run1", path, moved)
        self.assertEqual((git(self.repo, "rev-parse", "develop").strip(), W.work_tree(path)), (moved, final),
                         "the repository's own hook judged the commit that lands; refused, the base has nothing")
        self.assertEqual(self.land("run1", path, moved)["result"], "merged")
        self.assertEqual(git(self.repo, "rev-parse", "develop^{tree}").strip(), final)

    def test_a_base_rewound_under_a_run_is_brought_into_nothing(self):
        """A base that no longer holds the commit a run stands on dropped something on purpose. Git would call
        the rewound tip already merged, and the run would land what the base dropped."""
        began = git(self.repo, "rev-parse", "develop").strip()
        self.move_base({"dropped.txt": "what the base will drop\n"})
        path, tip = self.stand("run1")
        git(self.repo, "reset", "-q", "--hard", began)
        self.assertEqual(self.land("run1", path, tip), {"result": "moved"})
        with self.assertRaisesRegex(W.GitError, "rewound or rewritten"):
            W.reconcile(self.repo, path, "develop", tip)
        self.assertEqual((git(self.repo, "rev-parse", "develop").strip(), git(self.repo, "rev-parse", "run1").strip(),
                          W._merging(path)), (began, tip, False), "nothing kept, nothing brought in, the base untouched")

    def test_a_base_checked_out_nowhere_lands_by_its_ref_or_not_at_all(self):
        git(self.repo, "switch", "-q", "-c", "elsewhere")
        path, tip = self.stand("run1")
        other, other_tip = self.stand("run2")
        third = self.worktree("run3", change=False)
        write(os.path.join(third, "third.txt"), "run3\n")
        final = W.work_tree(path)
        self.assertEqual(self.land("run1", path, tip)["result"], "merged")
        self.assertEqual((git(self.repo, "rev-parse", "develop^{tree}").strip(), git(self.repo, "status", "--porcelain").strip()),
                         (final, ""), "landed, and no checkout touched")
        landed = git(self.repo, "rev-parse", "develop").strip()
        self.assertEqual(self.land("run2", other, other_tip), {"result": "moved"},
                         "the second changed the same lines on the old tip: a conflict, and nothing lands")
        self.assertEqual(git(self.repo, "rev-parse", "develop").strip(), landed)
        result = self.land("run3", third, other_tip)
        self.assertEqual((result["result"], result["onto"], git(self.repo, "rev-parse", "develop").strip(),
                          git(self.repo, "status", "--porcelain").strip()), ("merged", landed, result["commit"], ""),
                         "a third that git merges lands by the ref, from where the base is, and no checkout touched")
        self.assertEqual((git(self.repo, "show", "develop:app.txt"), git(self.repo, "show", "develop:third.txt")),
                         ("one\nrun1\n", "run3\n"))

    def test_a_run_with_nothing_the_base_lacks_is_refused(self):
        path = self.worktree("run1", change=False)
        tip = W.started_from(path)
        with self.assertRaises(W.MergeRefused):
            self.land("run1", path, tip)
        self.assertEqual(git(self.repo, "rev-parse", "develop").strip(), tip)

    def test_a_worktree_changed_after_it_was_offered_is_refused(self):
        path, tip = self.stand("run1")
        offered = W.work_tree(path)
        write(os.path.join(path, "app.txt"), "edited after the gate showed it\n")
        with self.assertRaises(W.MergeRefused):
            W.merge(self.repo, path, "run1", "develop", offered, None, os.path.join("todo", "done"), "m", "Merge m", tip)
        self.assertEqual((git(self.repo, "rev-parse", "develop").strip(), git(self.repo, "rev-parse", "run1").strip()),
                         (tip, tip))


class Remote(Repo):
    """A repository whose base is a remote's: a run begins from what the remote holds, and lands there by a
    push that forces nothing. This repository's own branch of that name is no destination."""

    def setUp(self):
        super().setUp()
        self.origin = os.path.join(self.tmp, "origin.git")
        git(self.tmp, "init", "-q", "--bare", "-b", "develop", self.origin)
        git(self.repo, "remote", "add", "origin", self.origin)
        git(self.repo, "push", "-q", "origin", "develop")
        self.local = git(self.repo, "rev-parse", "develop").strip()

    def elsewhere(self, files):
        """A commit pushed to the remote from another clone: the remote moves, this repository's branch does not."""
        clone = os.path.join(self.tmp, "clone-%d" % len(os.listdir(self.tmp)))
        git(self.tmp, "clone", "-q", "-c", "core.autocrlf=false", "-b", "develop", self.origin, clone)
        for key, value in (("user.name", "o"), ("user.email", "o@o"), ("commit.gpgsign", "false"),
                           ("core.autocrlf", "false")):
            git(clone, "config", key, value)
        for name, text in files.items():
            write(os.path.join(clone, name), text)
        git(clone, "add", "-A")
        git(clone, "commit", "-q", "-m", "pushed from elsewhere")
        git(clone, "push", "-q", "origin", "develop")
        return git(clone, "rev-parse", "HEAD").strip()

    def stand(self, run_id):
        # Where the remote leads, taken before any role runs: the run fetches from and pushes to nowhere else.
        self.pinned = W.remote_id(self.repo, "origin")
        # And what git runs before a push from here: the run pushes past nothing else.
        self.gate = W.prepush_id(self.repo)
        path = W.create(self.repo, "develop", self.root, run_id, TARGET, remote="origin", pinned=self.pinned)
        write(os.path.join(path, "app.txt"), "one\n%s\n" % run_id)
        return path, W.started_from(path)

    def land(self, run_id, path, tip, tree=None):
        return W.merge(self.repo, path, run_id, "develop", tree or W.work_tree(path), None,
                       os.path.join("todo", "done"), "%s: the change" % run_id, "Merge %s" % run_id, tip, "origin",
                       self.pinned, self.gate)

    def reconcile(self, path, tip):
        return W.reconcile(self.repo, path, "develop", tip, "origin", self.pinned)

    def remote_tip(self):
        return git(self.origin, "rev-parse", "develop").strip()

    def test_a_run_begins_from_what_the_remote_holds_and_lands_there_by_a_push(self):
        ahead = self.elsewhere({"elsewhere.txt": "pushed by another\n"})
        path, tip = self.stand("run1")
        self.assertEqual((tip, os.path.isfile(os.path.join(path, "elsewhere.txt"))), (ahead, True),
                         "from the remote's tip, which this repository's own branch is behind")
        self.assertNotEqual(subprocess.run(["git", "-C", self.repo, "config", "--get", "branch.run1.remote"],
                                           capture_output=True).returncode, 0, "its branch follows no upstream")
        final = W.work_tree(path)
        result = self.land("run1", path, tip)
        self.assertEqual((result["result"], self.remote_tip()), ("merged", result["commit"]), "the remote took it")
        self.assertEqual(git(self.origin, "rev-parse", "develop^{tree}").strip(), final)
        self.assertEqual(git(self.origin, "log", "--first-parent", "--format=%s", "develop").splitlines(),
                         ["Merge run1", "pushed from elsewhere", "base"])
        self.assertEqual((git(self.repo, "rev-parse", "develop").strip(), git(self.repo, "status", "--porcelain").strip()),
                         (self.local, ""), "this repository's branch and checkout are as they were")
        self.assertEqual(git(self.origin, "for-each-ref", "--format=%(refname)").split(), ["refs/heads/develop"],
                         "the run's branch never reached the remote")
        self.assertFalse(os.path.exists(path))
        self.assertFalse(W.branch_exists(self.repo, "run1"))
        self.assertEqual(self.land("run1", path, tip, final), result,
                         "tried again, the merge the remote holds is adopted")

    def test_a_remote_that_moved_since_the_gate_takes_the_change_merged_onto_where_it_is(self):
        path, tip = self.stand("run1")
        self.assertEqual(self.reconcile(path, tip), {"moved": False})
        ahead = self.elsewhere({"elsewhere.txt": "pushed by another\n"})
        final = W.work_tree(path)
        result = self.land("run1", path, tip)
        self.assertEqual((result["result"], result["onto"], self.remote_tip()), ("merged", ahead, result["commit"]),
                         "the remote took the merge, made onto the commit it had moved to")
        merge, landing = git(self.origin, "rev-list", "--parents", "-n", "1", "develop").split()[1:]
        self.assertEqual((merge, git(self.origin, "rev-list", "--parents", "-n", "1", landing).split()[1:],
                          git(self.origin, "rev-parse", landing + "^{tree}").strip()), (ahead, [tip], final),
                         "its first parent the remote's own tip; the change one commit on the tip it was judged on")
        self.assertEqual((git(self.origin, "show", "develop:app.txt"), git(self.origin, "show", "develop:elsewhere.txt")),
                         ("one\nrun1\n", "pushed by another\n"))
        self.assertEqual(git(self.origin, "log", "--first-parent", "--format=%s", "develop").splitlines(),
                         ["Merge run1", "pushed from elsewhere", "base"])
        self.assertEqual((git(self.repo, "rev-parse", "develop").strip(), git(self.repo, "status", "--porcelain").strip()),
                         (self.local, ""), "this repository's branch and checkout are as they were")
        self.assertEqual(self.land("run1", path, tip, final), result, "tried again, the merge the remote holds is adopted")

    def test_a_remote_that_moved_into_conflict_takes_nothing_and_its_base_is_brought_in(self):
        path, tip = self.stand("run1")
        ahead = self.elsewhere({"app.txt": "one\npushed by another\n"})
        self.assertEqual(self.land("run1", path, tip), {"result": "moved"})
        self.assertEqual((self.remote_tip(), git(self.repo, "rev-parse", "run1").strip()), (ahead, tip),
                         "nothing pushed, nothing committed")
        came = self.reconcile(path, tip)
        self.assertEqual((came["moved"], came["base_tip"], came["files"]), (True, ahead, ["app.txt"]))
        write(os.path.join(path, "app.txt"), "one\npushed by another\nrun1\n")
        final = W.work_tree(path)
        self.assertEqual(self.land("run1", path, ahead)["result"], "merged")
        self.assertEqual(git(self.origin, "rev-parse", "develop^{tree}").strip(), final)

    def test_a_remote_that_moves_under_the_push_takes_nothing_and_the_next_merge_lands_on_where_it_is(self):
        """The push is leased on the commit the merge was made onto: a remote that moved on between the look
        and the push refuses it, and the merge made for the older tip is never pushed over the newer."""
        path, tip = self.stand("run1")
        final = W.work_tree(path)
        # A commit the remote holds on no branch of the base's yet — put there between the look and the push,
        # by the repository's own commit hook as the change is committed.
        clone = os.path.join(self.tmp, "racer")
        git(self.tmp, "clone", "-q", "-c", "core.autocrlf=false", "-b", "develop", self.origin, clone)
        write(os.path.join(clone, "raced.txt"), "pushed while this landed\n")
        git(clone, "add", "-A")
        git(clone, "-c", "user.name=o", "-c", "user.email=o@o", "-c", "commit.gpgsign=false", "commit", "-q",
            "-m", "pushed while this landed")
        git(clone, "push", "-q", "origin", "HEAD:refs/heads/aside")
        raced = git(clone, "rev-parse", "HEAD").strip()
        hooks = git(self.repo, "config", "core.hooksPath").strip()
        write(os.path.join(hooks, "pre-commit"), "#!/bin/sh\ngit --git-dir='%s' update-ref refs/heads/develop %s\n"
              % (self.origin.replace("\\", "/"), raced))
        os.chmod(os.path.join(hooks, "pre-commit"), 0o755)
        self.addCleanup(lambda: os.path.exists(os.path.join(hooks, "pre-commit"))
                        and os.remove(os.path.join(hooks, "pre-commit")))
        with self.assertRaisesRegex(W.MergeRefused, "moved while this change was being landed"):
            self.land("run1", path, tip)
        self.assertEqual((self.remote_tip(), os.path.isdir(path)), (raced, True), "the remote holds nothing of the run")
        os.remove(os.path.join(hooks, "pre-commit"))
        result = self.land("run1", path, tip, final)
        self.assertEqual((result["result"], result["onto"], self.remote_tip()), ("merged", raced, result["commit"]))
        self.assertEqual(git(self.origin, "show", "develop:raced.txt"), "pushed while this landed\n")
        self.assertEqual(git(self.origin, "log", "--format=%s", "develop").splitlines().count("run1: the change"), 1,
                         "the change committed once")

    def test_a_push_the_remote_refuses_lands_nothing_and_lands_when_continued(self):
        path, tip = self.stand("run1")
        final = W.work_tree(path)
        hook = os.path.join(self.origin, "hooks", "pre-receive")
        write(hook, "#!/bin/sh\necho 'this branch takes no push' >&2\nexit 1\n")
        os.chmod(hook, 0o755)
        with self.assertRaises(W.MergeRefused) as refused:
            self.land("run1", path, tip)
        self.assertIn("the push to origin's develop was refused: remote: this branch takes no push",
                      str(refused.exception))
        self.assertEqual((self.remote_tip(), os.path.isdir(path), W.branch_exists(self.repo, "run1")), (tip, True, True),
                         "the remote has nothing, and the run keeps its worktree and branch")
        os.remove(hook)
        self.assertEqual(self.land("run1", path, tip)["result"], "merged")
        self.assertEqual(git(self.origin, "rev-parse", "develop^{tree}").strip(), final)
        self.assertEqual(git(self.origin, "log", "--format=%s", "develop").splitlines().count("run1: the change"), 1)

    def test_the_repositorys_own_pre_push_hook_judges_the_commit_being_landed(self):
        """A repository whose pushes must pass a check has it as its pre-push hook, and the controller's push
        runs it — handed the commit being landed, which this repository's own checkout never held."""
        hooks = git(self.repo, "config", "core.hooksPath").strip()
        hook, handed = os.path.join(hooks, "pre-push"), os.path.join(self.tmp, "handed-to-the-hook")
        fit = os.path.join(self.tmp, "fit-to-publish")
        write(hook, "#!/bin/sh\ncat > '%s'\n[ -e '%s' ] && exit 0\necho 'not fit to publish' >&2\nexit 1\n"
              % (handed.replace("\\", "/"), fit.replace("\\", "/")))
        os.chmod(hook, 0o755)
        self.addCleanup(lambda: os.path.exists(hook) and os.remove(hook))
        path, tip = self.stand("run1")
        final = W.work_tree(path)
        with self.assertRaises(W.MergeRefused) as refused:
            self.land("run1", path, tip)
        self.assertIn("the push to origin's develop was refused: not fit to publish", str(refused.exception),
                      "the hook's own words first, and no remote said to have refused what never reached it")
        with open(handed, encoding="utf-8") as fh:
            _, commit, to, holds = fh.read().split()
        self.assertEqual((git(self.repo, "rev-parse", commit + "^{tree}").strip(), to, holds),
                         (final, "refs/heads/develop", tip), "the merge commit itself, for the remote's base")
        self.assertNotEqual(git(self.repo, "rev-parse", "HEAD^{tree}").strip(), final,
                            "which the repository's checkout does not hold")
        self.assertEqual((self.remote_tip(), os.path.isdir(path), W.branch_exists(self.repo, "run1")), (tip, True, True),
                         "the remote has nothing, and the run keeps its worktree and branch")
        write(fit, "")
        self.assertEqual(self.land("run1", path, tip)["result"], "merged", "the same hook, letting it through")
        self.assertEqual(git(self.origin, "rev-parse", "develop^{tree}").strip(), final)
        self.assertEqual(git(self.origin, "log", "--format=%s", "develop").splitlines().count("run1: the change"), 1)

    def test_a_pre_push_gate_changed_since_the_run_began_lands_nothing(self):
        """What git runs before a push is the repository's configuration and a file to say, and a role's turn
        can change either without touching anything the controller guards — as it can where a remote leads.
        Four ways of it, each one a push that would have gone past the gate."""
        hooks = git(self.repo, "config", "core.hooksPath").strip()
        hook, refusing = os.path.join(hooks, "pre-push"), "#!/bin/sh\necho 'not fit to publish' >&2\nexit 1\n"
        self.addCleanup(lambda: os.path.exists(hook) and os.remove(hook))
        stated = (("hook.gate.event", "pre-push"),
                  ("hook.gate.command", "sh -c 'echo \"not fit to publish\" >&2; exit 1' --"))
        for key, value in stated:
            git(self.repo, "config", key, value)
        path, tip = self.stand("run1")

        def changed(way):
            with self.assertRaisesRegex(W.MergeRefused, "no longer what it was when this run began", msg=way):
                self.land("run1", path, tip)
            self.assertEqual(self.remote_tip(), tip, way)

        # A hook stated in git's configuration: made to say yes, then taken out.
        git(self.repo, "config", "hook.gate.command", "true")
        changed("the stated hook's command")
        git(self.repo, "config", "--remove-section", "hook.gate")
        changed("the stated hook, gone")
        # A hook's file, the repository's own when a run begins: its bytes, then where git looks for it.
        write(hook, refusing)
        os.chmod(hook, 0o755)
        self.gate = W.prepush_id(self.repo)
        write(hook, "#!/bin/sh\nexit 0\n")
        changed("the file's bytes")
        write(hook, refusing)
        elsewhere = os.path.join(self.tmp, "other-hooks")
        os.makedirs(elsewhere)
        git(self.repo, "config", "core.hooksPath", elsewhere)
        changed("where git looks for the file")
        git(self.repo, "config", "core.hooksPath", hooks)
        # As it was when it was taken, the gate itself answers; and the operator's own change of it is a new
        # run's to begin from.
        with self.assertRaisesRegex(W.MergeRefused, "not fit to publish"):
            self.land("run1", path, tip)
        os.remove(hook)
        self.gate = W.prepush_id(self.repo)
        self.assertEqual(self.land("run1", path, tip)["result"], "merged")

    @unittest.skipIf(WINDOWS, "git for Windows runs a hook's file whatever its mode")
    def test_a_pre_push_hook_git_would_pass_by_lands_nothing(self):
        """Git runs a hook's file only where it is executable, and where it is not says so in a hint and
        pushes: on a drive mounted without file modes no file is executable, and the repository's check
        would be passed by without a word to anyone."""
        hook = os.path.join(git(self.repo, "config", "core.hooksPath").strip(), "pre-push")
        fit = os.path.join(self.tmp, "fit-to-publish")
        write(hook, "#!/bin/sh\n[ -e '%s' ] && exit 0\necho 'not fit to publish' >&2\nexit 1\n" % fit)
        os.chmod(hook, 0o644)
        self.addCleanup(lambda: os.path.exists(hook) and os.remove(hook))
        path, tip = self.stand("run1")
        with self.assertRaisesRegex(W.MergeRefused, "pre-push hook is not executable here"):
            self.land("run1", path, tip)
        self.assertEqual((self.remote_tip(), git(self.repo, "rev-parse", "run1").strip()), (tip, tip),
                         "nothing pushed, nothing committed")
        # Made executable, as the refusal asks: the same hook, and no change of the gate.
        os.chmod(hook, 0o755)
        with self.assertRaisesRegex(W.MergeRefused, "not fit to publish"):
            self.land("run1", path, tip)
        write(fit, "")
        self.assertEqual(self.land("run1", path, tip)["result"], "merged")

    def test_a_remote_that_cannot_be_reached_is_no_answer(self):
        path, tip = self.stand("run1")
        git(self.repo, "remote", "set-url", "origin", os.path.join(self.tmp, "gone.git"))
        self.pinned = W.remote_id(self.repo, "origin")      # the operator's own change of it, taken as given
        for step in (lambda: self.reconcile(path, tip), lambda: self.land("run1", path, tip)):
            with self.assertRaises(W.GitError):
                step()
        self.assertEqual((git(self.repo, "rev-parse", "run1").strip(), os.path.isdir(path)), (tip, True),
                         "unknown is not unchanged: nothing is committed, nothing is taken for merged")

    def test_a_remote_rewound_since_it_was_looked_at_takes_nothing(self):
        """The push lands only while the remote's branch is exactly the commit the change was judged on: one
        rewound to an ancestor of it would take a plain push without a word."""
        ahead = self.elsewhere({"elsewhere.txt": "pushed by another\n"})
        path, tip = self.stand("run1")
        self.assertEqual(tip, ahead)
        # Between the look at the remote and the push: the repository's own commit hook, as the change is committed.
        hooks = git(self.repo, "config", "core.hooksPath").strip()
        write(os.path.join(hooks, "pre-commit"), "#!/bin/sh\ngit --git-dir='%s' update-ref refs/heads/develop %s\n"
              % (self.origin.replace("\\", "/"), self.local))
        os.chmod(os.path.join(hooks, "pre-commit"), 0o755)
        self.addCleanup(lambda: os.path.exists(os.path.join(hooks, "pre-commit"))
                        and os.remove(os.path.join(hooks, "pre-commit")))
        self.assertEqual(self.land("run1", path, tip), {"result": "moved"})
        self.assertEqual(self.remote_tip(), self.local, "the remote holds what it was rewound to, and nothing of the run")
        os.remove(os.path.join(hooks, "pre-commit"))
        # And the run does not go on by itself: what the remote dropped is still in its worktree.
        before = git(self.repo, "rev-parse", "run1").strip()
        with self.assertRaisesRegex(W.GitError, "rewound or rewritten"):
            self.reconcile(path, tip)
        self.assertEqual((git(self.repo, "rev-parse", "run1").strip(), W._merging(path), self.remote_tip(),
                          os.path.isfile(os.path.join(path, "elsewhere.txt"))), (before, False, self.local, True),
                         "nothing is brought in, kept or pushed: the operator decides what a rewound base means")

    def test_a_remote_rewritten_to_a_history_without_the_runs_commit_is_brought_into_nothing(self):
        """Not rewound to an ancestor but replaced: the commit the run stands on is in the base's history no more."""
        ahead = self.elsewhere({"elsewhere.txt": "pushed by another\n"})
        path, tip = self.stand("run1")
        clone = os.path.join(self.tmp, "rewriter")
        git(self.tmp, "clone", "-q", "-c", "core.autocrlf=false", "-b", "develop", self.origin, clone)
        git(clone, "-c", "user.name=o", "-c", "user.email=o@o", "-c", "commit.gpgsign=false", "commit", "-q",
            "--amend", "-m", "the same change, written again")
        git(clone, "push", "-q", "--force", "origin", "develop")
        rewritten = self.remote_tip()
        self.assertNotEqual(rewritten, ahead)
        self.assertEqual(self.land("run1", path, tip), {"result": "moved"})
        with self.assertRaisesRegex(W.GitError, "rewound or rewritten"):
            self.reconcile(path, tip)
        self.assertEqual((git(self.repo, "rev-parse", "run1").strip(), W._merging(path), self.remote_tip()),
                         (tip, False, rewritten))

    def test_a_remote_with_more_than_one_place_to_fetch_from_or_to_push_to_is_refused(self):
        """One `git push origin` writes to every push URL in turn, and one may take it while another refuses."""
        other = os.path.join(self.tmp, "other.git")
        git(self.tmp, "init", "-q", "--bare", "-b", "develop", other)
        url = git(self.repo, "remote", "get-url", "origin").strip()
        git(self.repo, "remote", "set-url", "--push", "origin", other)
        self.assertRegex(W.remote_id(self.repo, "origin"), "^[0-9a-f]{64}$",
                         "one place to fetch from and another to push to is one destination")
        git(self.repo, "remote", "set-url", "--add", "--push", "origin", url)
        with self.assertRaisesRegex(W.GitError, "2 push URLs"):
            W.remote_id(self.repo, "origin")
        git(self.repo, "config", "--unset-all", "remote.origin.pushurl")
        git(self.repo, "remote", "set-url", "--add", "origin", other)
        with self.assertRaisesRegex(W.GitError, "2 fetch URLs"):
            W.remote_id(self.repo, "origin")
        with self.assertRaisesRegex(W.GitError, "2 fetch URLs"):
            W.create(self.repo, "develop", self.root, "run1", TARGET, remote="origin", pinned="taken-before")
        self.assertFalse(W.branch_exists(self.repo, "run1"), "no run begins on a remote that leads to two places")

    def test_a_remote_that_no_longer_leads_where_it_did_is_neither_fetched_from_nor_pushed_to(self):
        """A role can rewrite the repository's configuration without touching what the controller guards. The
        destination a run began with is the only one it reaches."""
        path, tip = self.stand("run1")
        other = os.path.join(self.tmp, "other.git")
        git(self.tmp, "init", "-q", "--bare", "-b", "develop", other)
        git(self.repo, "push", "-q", other, "develop")
        url = git(self.repo, "remote", "get-url", "origin").strip()
        redirections = (
            (("remote", "set-url", "origin", other), ("remote", "set-url", "origin", url)),
            (("remote", "set-url", "--push", "origin", other), ("config", "--unset", "remote.origin.pushurl")),
            (("config", "url.%s.insteadOf" % other, url), ("config", "--unset", "url.%s.insteadOf" % other)),
            (("config", "url.%s.pushInsteadOf" % other, url), ("config", "--unset", "url.%s.pushInsteadOf" % other)))
        for redirect, restore in redirections:
            with self.subTest(redirect=redirect[:3]):
                git(self.repo, *redirect)
                for step in (lambda: self.reconcile(path, tip), lambda: self.land("run1", path, tip)):
                    with self.assertRaisesRegex(W.GitError, "no longer leads where it did"):
                        step()
                git(self.repo, *restore)
        self.assertEqual((git(other, "rev-parse", "develop").strip(), self.remote_tip(),
                          git(self.repo, "rev-parse", "run1").strip()), (tip, tip, tip),
                         "nothing reached the other destination, nothing was pushed, nothing committed")
        self.assertEqual(self.land("run1", path, tip)["result"], "merged", "where it led again, it lands")

    def test_a_repository_with_no_branch_of_its_own_for_the_base_begins_and_lands_on_the_remotes(self):
        git(self.repo, "switch", "-q", "-c", "work")
        git(self.repo, "branch", "-q", "-D", "develop")
        path, tip = self.stand("run1")
        self.assertEqual(self.reconcile(path, tip), {"moved": False})
        self.assertEqual([row["state"] for row in W.view(self.repo, "develop", "origin") if row["branch"] == "run1"],
                         ["uncommitted"], "its worktree is read against the remote's base too")
        final = W.work_tree(path)
        self.assertEqual(self.land("run1", path, tip)["result"], "merged")
        self.assertEqual(git(self.origin, "rev-parse", "develop^{tree}").strip(), final)
        self.assertFalse(W.branch_exists(self.repo, "develop"), "and no local branch of that name was made")


if __name__ == "__main__":
    unittest.main()
