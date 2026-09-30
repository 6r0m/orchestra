"""The public gate scans staged and working-tree bytes as separate snapshots."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parent.parent / "tools" / "public_check.sh"


@unittest.skipUnless(os.name == "posix", "the public gate's shell controls run on WSL")
class PublicCheckSnapshots(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="orchestra-public-check-")
        self.addCleanup(scratch.cleanup)
        self.repo = Path(scratch.name)
        (self.repo / "tools").mkdir()
        shutil.copyfile(SOURCE, self.repo / "tools" / "public_check.sh")
        bin_dir = self.repo / "bin"
        bin_dir.mkdir()
        docker = bin_dir / "docker"
        docker.write_text("""#!/usr/bin/env bash
scan=
previous=
no_git=false
for arg in "$@"; do
    if [ "$previous" = -v ]; then scan="${arg%:/scan:ro}"; fi
    if [ "$arg" = --no-git ]; then no_git=true; fi
    previous="$arg"
done
if [ "$no_git" = true ] && grep -R -E -q 'ghp_|STAGED_CONTROL' "$scan"; then exit 1; fi
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
        self.environment = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ["PATH"])
        subprocess.run(["git", "init", "--quiet"], cwd=self.repo, check=True, capture_output=True)

    def stage(self, content):
        path = self.repo / "safe.txt"
        path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", "--", "safe.txt"], cwd=self.repo, check=True, capture_output=True)
        return path

    def check(self, **changes):
        environment = dict(self.environment, **changes)
        return subprocess.run(["bash", "tools/public_check.sh"], cwd=self.repo, env=environment,
                              capture_output=True, text=True, check=False)

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
