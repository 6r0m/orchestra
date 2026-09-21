"""A worker killed mid-stage leaves that stage's settings, which hold the trace store's key; the next
worker to start removes them, and never a stage's that still runs.

Real processes, in a temporary folder of the test's own: a stage that makes its settings as
`run_role` does and is killed while it runs, and the worker's own entry point, started after it as a
restart starts it — with no Temporal to reach, so it stops once it has started.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))

# A process in the middle of a traced Claude stage: its settings made, as `run_role` makes them.
STAGE = textwrap.dedent("""\
    import sys, time
    sys.path.insert(0, %r)
    from app.foundation import policy as P
    from app.observability import telemetry
    span = telemetry._Span(traceparent="00-%%032x-%%016x-01" %% (1, 2))
    print(telemetry.harness_settings(P.load()["roles"]["engineer"], span), flush=True)
    time.sleep(600)
""") % PKG


class StaleSettings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="orch-sweep-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env = dict(os.environ, TMPDIR=self.tmp, TMP=self.tmp, TEMP=self.tmp,
                        LANGFUSE_PUBLIC_KEY="pk-lf-test", LANGFUSE_SECRET_KEY="sk-lf-test",
                        # Nothing listens here: the worker gets as far as its connection and stops.
                        TEMPORAL_ADDRESS="127.0.0.1:9")

    def stage(self):
        child = subprocess.Popen([sys.executable, "-c", STAGE], cwd=PKG, env=self.env, stdout=subprocess.PIPE,
                                 text=True)
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        path = child.stdout.readline().strip()
        child.stdout.close()
        self.assertTrue(path and os.path.isfile(path), "the stage made its settings: %r" % path)
        return child, path

    def restart_worker(self):
        target = "windows" if os.name == "nt" else "wsl"
        done = subprocess.run([sys.executable, "-m", "app.interfaces.worker", target], cwd=PKG, env=self.env,
                              capture_output=True, text=True, timeout=120)
        self.assertIn("not reachable", done.stdout + done.stderr, "the worker started, then stopped at Temporal")

    def test_a_worker_killed_mid_stage_leaves_settings_the_next_worker_removes(self):
        child, path = self.stage()
        child.kill()
        child.wait()
        self.assertTrue(os.path.isfile(path), "the control: the killed stage left its settings, key and all")
        self.restart_worker()
        self.assertFalse(os.path.exists(os.path.dirname(path)), "the restarted worker removed them")

    def test_a_stage_that_still_runs_keeps_its_settings(self):
        child, path = self.stage()
        self.restart_worker()
        self.assertIsNone(child.poll())
        self.assertTrue(os.path.isfile(path), "a worker starting beside a running stage leaves its settings")


if __name__ == "__main__":
    unittest.main()
