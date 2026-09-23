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
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="orch-git-"))
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

    def test_a_role_that_stages_fails_its_stage(self):
        path = self.worktree("run1")

        def staging_agent(worktree, argv, rdir, name, prompt, timeout, env, *, brain):
            git(worktree, "add", "-A")
            return 0, "done\n"

        from app.foundation import policy as P
        host = A.Activities(runner=staging_agent, telemetry=None)
        state = {"run_id": "run1-guard", "task": "t", "phase": "plan", "round": 0, "episode": 1,
                 "worktree_path": path, "todo_path": os.path.join(path, "todo", "x.md"), "agent_sessions": {}}
        self.addCleanup(shutil.rmtree, A.run_dir("run1-guard"), ignore_errors=True)
        with self.assertRaises(Exception) as raised:
            host.run_role({"stage": "plan", "state": state, "policy": P.load()})
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
    """Reading a change for review: bounded, so no payload can be refused, and joining back exactly."""

    def test_a_large_change_is_read_in_parts_that_join_back_into_the_whole_patch(self):
        path = self.worktree("run1", change=False)
        # A character that spans several bytes, laid so that a part's edge falls inside one.
        write(os.path.join(path, "big.txt"), "".join("строка %d ✓\n" % number for number in range(4000)))
        saved = W.PATCH_CHUNK
        W.PATCH_CHUNK = 1000
        try:
            whole, parts, reads, offset = None, [], [], 0
            while True:
                read = W.review_diff(path, offset)
                self.assertLessEqual(len(read["patch"].encode("utf-8")), W.PATCH_CHUNK)
                parts.append(read["patch"])
                reads.append(read)
                whole = read["total"]
                if read["next"] >= read["total"]:
                    break
                self.assertGreater(read["next"], offset, "a part always moves forward")
                offset = read["next"]
        finally:
            W.PATCH_CHUNK = saved
        joined = "".join(parts)
        self.assertGreater(len(parts), 20, "the change is larger than one part")
        self.assertEqual(len({read["snapshot"] for read in reads}), 1, "every part is of one change")
        self.assertEqual(len(joined.encode("utf-8")), whole, "the parts are the whole patch, byte for byte")
        self.assertEqual(joined, W.review_diff(path)["patch"][:len(joined)])
        self.assertIn("строка 3999 ✓", joined, "and it reads as the text it is")

    def test_a_change_edited_between_two_parts_is_a_different_snapshot(self):
        path = self.worktree("run1", change=False)
        write(os.path.join(path, "big.txt"), "".join("line %04d value\n" % number for number in range(500)))
        first = W.review_diff(path, 0)
        # Same size, different content: only the snapshot can tell the two changes apart.
        write(os.path.join(path, "big.txt"),
              "".join("line %04d VALUE\n" % number for number in range(500)))
        second = W.review_diff(path, 0)
        self.assertEqual(first["total"], second["total"], "the edit kept the patch exactly as long")
        self.assertNotEqual(first["snapshot"], second["snapshot"],
                            "a reader joining parts across this edit would show two changes as one")

    def test_an_offset_inside_a_character_is_refused_not_mangled(self):
        path = self.worktree("run1", change=False)
        write(os.path.join(path, "big.txt"), "строка\n" * 50)
        whole = W.review_diff(path, 0)["patch"].encode("utf-8")
        inside = next(i for i, byte in enumerate(whole) if byte & 0xC0 == 0x80)
        with self.assertRaises(RuntimeError) as caught:
            W.review_diff(path, inside)
        self.assertIn("inside a character", str(caught.exception))


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


if __name__ == "__main__":
    unittest.main()
