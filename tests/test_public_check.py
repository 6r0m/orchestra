"""The public gate scans staged and working-tree bytes as separate snapshots, and — as git's pre-push
hook — each commit a push carries instead of the checkout."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parent.parent / "tools" / "public_check.sh"
ZERO = "0" * 40


class Gate(unittest.TestCase):
    """A disposable repository holding the gate's script, and a stand-in for the scanner's image: it finds
    the control in a folder of files, or in the history `--log-opts` names — every ref's when none is named."""

    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="orchestra-public-check-")
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)
        self.repo = self.scratch / "repo"
        (self.repo / "tools").mkdir(parents=True)
        shutil.copyfile(SOURCE, self.repo / "tools" / "public_check.sh")
        bin_dir = self.scratch / "bin"
        bin_dir.mkdir()
        docker = bin_dir / "docker"
        docker.write_text("""#!/usr/bin/env bash
scan=
previous=
no_git=false
log=--all
for arg in "$@"; do
    if [ "$previous" = -v ]; then scan="${arg%:/scan:ro}"; fi
    if [ "$arg" = --no-git ]; then no_git=true; fi
    case "$arg" in --log-opts=*) log="${arg#--log-opts=}" ;; esac
    previous="$arg"
done
if [ "$no_git" = true ]; then
    if grep -R -E -q 'ghp_|STAGED_CONTROL' "$scan"; then exit 1; fi
elif git -C "$scan" log -p "$log" 2>/dev/null | grep -q '^+.*STAGED_CONTROL'; then
    exit 1
fi
exit 0
""", encoding="utf-8")
        docker.chmod(0o755)
        copying = bin_dir / "cp"
        copying.write_text("""#!/usr/bin/env bash
for arg in "$@"; do
    if [ -n "${CONTROL_COPY_FAIL:-}" ] && [ "$arg" = "$CONTROL_COPY_FAIL" ]; then exit 41; fi
done
exec /usr/bin/cp "$@"
""", encoding="utf-8")
        copying.chmod(0o755)
        # A git from before hooks could be stated in its configuration: it knows `git hook run` and no other.
        older = bin_dir / "git"
        older.write_text("""#!/usr/bin/env bash
if [ -n "${CONTROL_OLDER_GIT:-}" ] && [ "${1:-}" = hook ] && [ "${2:-}" != run ]; then
    echo "usage: git hook run [--ignore-missing] <hook-name> [-- <hook-args>]" >&2
    exit 129
fi
exec /usr/bin/git "$@"
""", encoding="utf-8")
        older.chmod(0o755)
        self.environment = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ["PATH"])
        subprocess.run(["git", "init", "--quiet", "--initial-branch", "main"], cwd=self.repo, check=True,
                       capture_output=True)

    def git(self, *args, cwd=None, check=True):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                               *args], cwd=cwd or self.repo, env=self.environment, check=check,
                              capture_output=True, text=True)

    def stage(self, content, name="safe.txt"):
        path = self.repo / name
        path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", "--", name], cwd=self.repo, check=True, capture_output=True)
        return path

    def commit(self, content, name="safe.txt"):
        self.stage(content, name)
        self.git("commit", "--quiet", "--message", "a commit")
        return self.git("rev-parse", "HEAD").stdout.strip()

    def check(self, *arguments, lines=None, **changes):
        environment = dict(self.environment, **changes)
        return subprocess.run(["bash", "tools/public_check.sh", *arguments], cwd=self.repo, env=environment,
                              input=None if lines is None else "".join(line + "\n" for line in lines),
                              capture_output=True, text=True, check=False)

    def pushed(self, *lines):
        """The gate as git runs its pre-push hook: one line a ref on stdin."""
        return self.check("--pushed", lines=lines)


def ref(commit, to="refs/heads/main"):
    """A ref as git hands it to a pre-push hook: the local name, its commit, the remote name, what it holds."""
    return "refs/heads/work %s %s %s" % (commit, to, ZERO)


@unittest.skipUnless(os.name == "posix", "the public gate's shell controls run on WSL")
class PublicCheckSnapshots(Gate):
    def test_staged_control_survives_a_clean_worktree(self):
        path = self.stage("STAGED_CONTROL")
        path.write_text("clean", encoding="utf-8")
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FAIL Gitleaks found something in the staged index", result.stdout)
        self.assertIn("ok   no secret in the tracked files still present", result.stdout)

    def test_staged_control_survives_an_unstaged_deletion(self):
        self.stage("STAGED_CONTROL").unlink()
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FAIL Gitleaks found something in the staged index", result.stdout)
        self.assertNotIn("cp: cannot stat", result.stderr)

    def test_unstaged_control_is_scanned_separately(self):
        self.stage("clean").write_text("STAGED_CONTROL", encoding="utf-8")
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("ok   no secret in the staged index", result.stdout)
        self.assertIn("FAIL Gitleaks found something in a tracked file", result.stdout)

    def test_skip_worktree_does_not_hide_the_index(self):
        path = self.stage("STAGED_CONTROL")
        subprocess.run(["git", "update-index", "--skip-worktree", "safe.txt"], cwd=self.repo,
                       check=True, capture_output=True)
        path.write_text("clean", encoding="utf-8")
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FAIL Gitleaks found something in the staged index", result.stdout)

    def test_safe_unstaged_deletion_does_not_break_export(self):
        self.stage("clean").unlink()
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PUBLIC CHECK PASSED", result.stdout)
        self.assertNotIn("cp: cannot stat", result.stderr)

    def test_worktree_copy_failure_refuses(self):
        self.stage("clean")
        result = self.check(CONTROL_COPY_FAIL="safe.txt")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FAIL could not export safe.txt for the secret scan", result.stdout)
        self.assertNotIn("ok   no secret in the tracked files still present", result.stdout)


@unittest.skipUnless(os.name == "posix", "the public gate's shell controls run on WSL")
class PushedCommits(Gate):
    """As the pre-push hook the gate judges what a push carries. A run landed on a remote is pushed as a
    commit this checkout never held, so the checkout — its index and its files — says nothing of it."""

    def test_a_pushed_commit_is_refused_for_what_it_holds_whatever_the_checkout_holds(self):
        held = self.commit("STAGED_CONTROL")
        self.stage("clean")
        by_hand = self.check()
        self.assertIn("ok   no secret in the staged index", by_hand.stdout)
        self.assertIn("ok   no secret in the tracked files still present", by_hand.stdout)
        result = self.pushed(ref(held))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FAIL Gitleaks found something in commit %s" % held[:12], result.stderr)
        self.assertIn("PUBLIC CHECK FAILED for commit %s" % held[:12], result.stderr)
        self.assertNotIn("ok  ", result.stderr, "a hook says what it refuses and its verdict, nothing else")

    def test_a_clean_pushed_commit_passes_whatever_the_checkout_holds(self):
        clean = self.commit("clean")
        self.stage("STAGED_CONTROL")
        self.assertEqual(self.check().returncode, 1, "the checkout itself is not fit to publish")
        result = self.pushed(ref(clean))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PUBLIC CHECK PASSED for commit %s" % clean[:12], result.stderr)
        self.assertEqual(self.git("show", ":safe.txt").stdout, "STAGED_CONTROL",
                         "the checkout's own index is neither read nor written")

    def test_a_pushed_commit_that_tracks_what_is_private_is_refused(self):
        held = self.commit("KEY=value", name=".env")
        self.git("rm", "--quiet", "--cached", ".env")
        self.assertIn("ok   .env is not tracked", self.check().stdout)
        result = self.pushed(ref(held))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FAIL .env is tracked", result.stderr)

    def test_the_history_a_pushed_commit_carries_is_judged_and_no_other(self):
        held = self.commit("STAGED_CONTROL")
        tip = self.commit("clean")
        result = self.pushed(ref(tip))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FAIL Gitleaks found something in the history of commit %s" % tip[:12], result.stderr)
        self.assertNotIn("found something in commit", result.stderr, "its own files are clean")
        # A commit with a history of its own, in a repository whose other branch holds the control.
        self.git("checkout", "--quiet", "--orphan", "apart")
        apart = self.commit("clean again")
        self.assertNotEqual(self.git("merge-base", "--is-ancestor", held, apart, check=False).returncode, 0)
        self.assertEqual(self.pushed(ref(apart)).returncode, 0)

    def test_every_ref_of_a_push_is_judged_and_a_deleted_one_publishes_nothing(self):
        clean = self.commit("clean")
        held = self.commit("STAGED_CONTROL")
        gone = "(delete) %s refs/heads/gone %s" % (ZERO, held)
        self.assertEqual(self.pushed().returncode, 0, "a push that carries nothing")
        self.assertEqual(self.pushed(gone).returncode, 0)
        self.assertEqual(self.pushed(ref(clean), gone).returncode, 0)
        result = self.pushed(ref(clean), gone, ref(held, "refs/heads/other"))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("PUBLIC CHECK PASSED for commit %s" % clean[:12], result.stderr)
        self.assertIn("PUBLIC CHECK FAILED for commit %s" % held[:12], result.stderr)

    def test_a_line_that_names_no_commit_is_refused(self):
        self.commit("clean")
        for line in (ref("f" * 40), ref(ZERO), "refs/heads/work", ""):
            result = self.pushed(line)
            self.assertEqual(result.returncode, 1, "%r: %s" % (line, result.stdout + result.stderr))
            self.assertIn("PUBLIC CHECK FAILED", result.stderr)

    def test_a_commit_is_judged_by_hand_as_a_push_of_it_would_be(self):
        held = self.commit("STAGED_CONTROL")
        self.stage("clean")
        result = self.check("--commit", "HEAD")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FAIL Gitleaks found something in commit %s" % held[:12], result.stdout)
        self.assertIn("ok   .env is not tracked", result.stdout)


@unittest.skipUnless(os.name == "posix", "the public gate's shell controls run on WSL")
class InstalledHook(Gate):
    """`--install` has git itself run the gate before a push: the proof is a real push."""

    def setUp(self):
        super().setUp()
        self.origin = self.scratch / "origin.git"
        subprocess.run(["git", "init", "--quiet", "--bare", "--initial-branch", "main", str(self.origin)],
                       check=True, capture_output=True)
        self.git("remote", "add", "origin", str(self.origin))

    def remote(self):
        return self.git("rev-parse", "--verify", "--quiet", "refs/heads/main", cwd=self.origin,
                        check=False).stdout.strip()

    def stated(self):
        """What the clone's configuration says of the hook: its events, then its commands."""
        return [self.git("config", "--local", "--get-all", "hook.public-check." + key, check=False).stdout.splitlines()
                for key in ("event", "command")]

    def test_a_push_of_a_commit_the_gate_refuses_reaches_no_remote(self):
        installed = self.check("--install")
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        self.assertFalse((self.repo / ".git" / "hooks" / "pre-push").exists(),
                         "no file is written: where a drive keeps no file modes git would run none")
        clean = self.commit("clean")
        self.git("push", "--quiet", "origin", "%s:refs/heads/main" % clean)
        self.assertEqual(self.remote(), clean, "a clean commit is pushed as before")
        held = self.commit("STAGED_CONTROL")
        self.stage("clean")
        refused = self.git("push", "origin", "%s:refs/heads/main" % held, check=False)
        self.assertNotEqual(refused.returncode, 0, refused.stdout + refused.stderr)
        self.assertIn("FAIL Gitleaks found something in commit %s" % held[:12], refused.stderr)
        self.assertEqual(self.remote(), clean, "the remote holds what it held")

    def test_a_push_from_a_worktree_of_the_clone_is_judged_by_the_clones_own_gate(self):
        """A run's worktree holds its own copy of everything tracked, the gate included once it is — and no
        run judges its own landing."""
        self.assertEqual(self.check("--install").returncode, 0)
        held = self.commit("STAGED_CONTROL")
        worktree = self.scratch / "worktree"
        self.git("worktree", "add", "--quiet", "--detach", str(worktree), held)
        self.assertFalse((worktree / "tools").exists(), "nothing of the gate is in the worktree to be run")
        refused = self.git("push", "origin", "%s:refs/heads/main" % held, cwd=worktree, check=False)
        self.assertNotEqual(refused.returncode, 0, refused.stdout + refused.stderr)
        self.assertIn("PUBLIC CHECK FAILED for commit %s" % held[:12], refused.stderr)
        self.assertEqual(self.remote(), "")

    def test_installing_again_states_the_hook_once(self):
        self.assertEqual(self.check("--install").returncode, 0)
        once = self.stated()
        self.assertEqual(([len(values) for values in once], once[0]), ([1, 1], ["pre-push"]))
        self.assertEqual((self.check("--install").returncode, self.stated()), (0, once))

    def test_a_git_that_would_not_run_the_hook_is_left_with_none(self):
        """A hook only believed to be installed is worse than none: git itself is asked whether it runs it."""
        result = self.check("--install", CONTROL_OLDER_GIT="1")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FAIL this git runs no hook from its configuration", result.stdout)
        self.assertEqual(self.stated(), [[], []])
