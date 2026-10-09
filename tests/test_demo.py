"""How `make demo` ends: in a worktree the other host's git made it takes back the environment it built there,
and one it could not take back fails it — a demo passes only with nothing of its own left behind."""
import contextlib
import io
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest

from app.foundation import envpath

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Ran:
    """A demo whose runs passed and whose own cleanup left nothing: what is under test is what follows it."""
    runs = ["a-run"]

    def run(self):
        pass

    def cleanup(self):
        return []


@unittest.skipUnless(os.name == "posix", "`make demo` runs on WSL and Linux")
class TheEnvironmentItBuilt(unittest.TestCase):
    def setUp(self):
        tools = os.path.join(PKG, "tools")
        sys.path.insert(0, tools)
        try:
            import demo
        finally:
            sys.path.remove(tools)
        self.demo = demo
        self.tmp = tempfile.mkdtemp(prefix="orchestra-demo-end-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.checkout = os.path.join(self.tmp, "checkout")
        os.makedirs(self.checkout)
        # Environments land under this test's own cache root, and the demo's checkout is this test's.
        saved = os.environ.get("XDG_CACHE_HOME")
        os.environ["XDG_CACHE_HOME"] = os.path.join(self.tmp, "cache")
        self.addCleanup(lambda: os.environ.pop("XDG_CACHE_HOME", None) if saved is None
                        else os.environ.__setitem__("XDG_CACHE_HOME", saved))
        for name, stand_in in (("PKG", self.checkout), ("Demo", Ran)):
            self.addCleanup(setattr, demo, name, getattr(demo, name))
            setattr(demo, name, stand_in)
        self.addCleanup(signal.signal, signal.SIGINT, signal.getsignal(signal.SIGINT))

    def another_hosts(self):
        """A worktree the other host's git made: its `.git` names a gitdir this host cannot spell."""
        with open(os.path.join(self.checkout, ".git"), "w", encoding="utf-8") as fh:
            fh.write("gitdir: Q:/no/such/repository/.git/worktrees/run\n")

    def environment(self, marked=True):
        path = envpath.environment_for(self.checkout)
        os.makedirs(os.path.join(path, "lib"))
        if marked:
            open(os.path.join(path, "pyvenv.cfg"), "w", encoding="utf-8").close()
        return path

    def end(self):
        """The demo's own result — 0, or what it exits with — and what it printed."""
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            try:
                result = self.demo.main()
            except SystemExit as failed:
                result = failed.code
        return result, said.getvalue()

    def test_in_another_hosts_worktree_it_takes_the_environment_back_and_passes(self):
        self.another_hosts()
        built = self.environment()
        result, said = self.end()
        self.assertEqual((result, "DEMO PASSED" in said), (0, True), said)
        self.assertFalse(os.path.exists(built), "the environment it built here is gone with it")
        # None there to take back — never built, or taken back already — is nothing left behind.
        result, said = self.end()
        self.assertEqual((result, "DEMO PASSED" in said), (0, True), said)

    def test_an_environment_it_cannot_take_back_fails_the_demo(self):
        self.another_hosts()
        built = self.environment(marked=False)      # not what the guarded removal takes: it refuses
        result, said = self.end()
        self.assertNotEqual(result, 0, "a refused removal is something left behind: %s" % said)
        self.assertIn("left behind", str(result))
        self.assertIn(built, str(result), "and the result names it")
        self.assertNotIn("DEMO PASSED", said)
        self.assertTrue(os.path.isdir(os.path.join(built, "lib")), "the refusal removed nothing")

    def test_a_checkout_this_hosts_git_reads_keeps_its_environment(self):
        # Its `.git` a pointer too, as a worktree's is — but one this host's git follows.
        subprocess.run(["git", "init", "--quiet", "--separate-git-dir", os.path.join(self.tmp, "gitdir"),
                        self.checkout], check=True, capture_output=True)
        self.assertTrue(os.path.isfile(os.path.join(self.checkout, ".git")))
        built = self.environment()
        result, said = self.end()
        self.assertEqual((result, "DEMO PASSED" in said), (0, True), said)
        self.assertTrue(os.path.isfile(os.path.join(built, "pyvenv.cfg")),
                        "the environment the live stack may be running from is never the demo's to remove")


if __name__ == "__main__":
    unittest.main()
