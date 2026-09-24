"""A worker killed mid-stage leaves that stage's settings, which hold the trace store's key; the next
worker to start removes them, and never a stage's that still runs.

Real processes, in a temporary folder of the test's own: a stage that makes its settings as
`run_role` does and is killed while it runs, and the worker's own entry point, started after it as a
restart starts it — under a policy of the test's own, on free ports, and with no Temporal to reach,
so it stops once it has started.
"""
import json
import os
import shutil
import socket
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


def port_for_another_process():
    """A port another process will bind, told its number through a policy: free now, then let go, so
    something else may take it first. A socket this process holds binds port 0 instead."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class StaleSettings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="orch-sweep-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        with open(os.path.join(PKG, "policy.json"), encoding="utf-8") as fh:
            policy = json.load(fh)
        for role in policy["roles"].values():
            role["prompt"] = os.path.join(PKG, role["prompt"])
        for target in policy["targets"].values():
            target.update(host="sweep%s" % os.urandom(3).hex(), terminal_port=port_for_another_process())
        policy.update(workbench_port=port_for_another_process(), workflow_queue="orchestration:sweep")
        path = os.path.join(self.tmp, "policy.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(policy, fh)
        self.env = dict(os.environ, TMPDIR=self.tmp, TMP=self.tmp, TEMP=self.tmp, ORCH_POLICY=path,
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

    def test_a_sweep_that_cannot_remove_a_dead_stages_settings_names_them_and_fails(self):
        """A stop is reported done only once what its stages left is gone: settings the sweep cannot
        remove still hold the key, so it names them and fails, and the stack's stop with it."""
        child, path = self.stage()
        child.kill()
        child.wait()
        folder = os.path.dirname(path)
        # Held as a sweep may meet them: on Windows a file still open, elsewhere a folder not writable.
        if os.name == "nt":
            held = open(path, "a", encoding="utf-8")
            self.addCleanup(held.close)
        else:
            if os.geteuid() == 0:
                self.skipTest("root removes it whatever its mode")
            os.chmod(folder, 0o500)
            self.addCleanup(os.chmod, folder, 0o700)
        done = subprocess.run([sys.executable, "-m", "app.interfaces.worker", "sweep"], cwd=PKG, env=self.env,
                              capture_output=True, text=True, timeout=120)
        self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("could not remove the settings a dead worker's stage left: %s" % folder, done.stdout)
        self.assertTrue(os.path.isfile(path), "the control: they are still there")

    def test_a_stage_that_still_runs_keeps_its_settings(self):
        child, path = self.stage()
        self.restart_worker()
        self.assertIsNone(child.poll())
        self.assertTrue(os.path.isfile(path), "a worker starting beside a running stage leaves its settings")


class NamedGone(unittest.TestCase):
    """The sweep after the stack has stopped a worker names that worker's pid, and takes its settings even
    when the pid already belongs to another process — Windows gives a pid away within moments."""

    def settings_of(self, pid):
        """Settings a stage of process `pid` left, where the sweep looks: a temporary folder of the test's own."""
        from app.observability import telemetry
        root = tempfile.mkdtemp(prefix="orch-sweep-")
        self.addCleanup(shutil.rmtree, root, True)
        self.addCleanup(setattr, tempfile, "tempdir", tempfile.tempdir)
        tempfile.tempdir = root
        folder = tempfile.mkdtemp(prefix="%s%d-" % (telemetry.SETTINGS_DIR_PREFIX, pid))
        with open(os.path.join(folder, telemetry.SETTINGS_FILE), "w", encoding="utf-8") as fh:
            fh.write("{}")
        return folder

    def test_a_pid_named_gone_is_taken_at_its_word_even_while_another_process_holds_it(self):
        from app.observability import telemetry
        # This test's own process stands for the new one that was given the stopped worker's pid.
        folder = self.settings_of(os.getpid())
        telemetry.discard_stale_settings()
        self.assertTrue(os.path.isdir(folder), "the control: a folder of a live process is never taken unnamed")
        telemetry.discard_stale_settings(gone=(os.getpid() + 1,))
        self.assertTrue(os.path.isdir(folder), "nor for a pid named that is not its own")
        telemetry.discard_stale_settings(gone=(os.getpid(),))
        self.assertFalse(os.path.exists(folder), "named gone, its settings go, key and all")


if __name__ == "__main__":
    unittest.main()
