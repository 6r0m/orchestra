"""A role-run leaves nothing running: timeout, Stop, normal exit, and its owner's death.

Each case launches a child that starts a grandchild which outlives it — the shape
a real agent's tool calls take — and asserts the grandchild is gone afterwards.
Every case runs twice: once with the grandchild in the child's own process group,
and once with it in a session of its own, the shape that escapes a process-group
kill. The owner is also killed at moments spread across the launch itself, and on
POSIX a launch with no scope to hold it is refused before the agent runs. Runs on
both hosts: the primitive differs, the promise does not.
"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

# The suite's own folder, reached from this concern's folder inside it, and the
# checkout above both: the shared harness and the fixtures live at the suite root.
HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path.insert(0, PKG)

from app.agents import launch  # noqa: E402

WINDOWS = sys.platform.startswith("win")

GRANDCHILD = textwrap.dedent("""
    import os, sys, time
    with open(sys.argv[1], "w") as fh:
        fh.write(str(os.getpid()))
    time.sleep(120)
""")

# Starts the grandchild, waits until it is running, then sleeps or exits.
CHILD = textwrap.dedent("""
    import os, subprocess, sys, time
    marker, mode, detach = sys.argv[1], sys.argv[2], sys.argv[3] == "detached"
    subprocess.Popen([sys.executable, os.path.join(os.path.dirname(__file__), "grandchild.py"), marker],
                     start_new_session=detach)
    while not os.path.exists(marker) or not open(marker).read():
        time.sleep(0.05)
    print("grandchild started", flush=True)
    if mode == "sleep":
        time.sleep(120)
""")


def alive(pid):
    if WINDOWS:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == 259                        # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        with open("/proc/%d/stat" % pid) as fh:
            return fh.read().rsplit(")", 1)[1].split()[0] != "Z"
    except (FileNotFoundError, ProcessLookupError):
        # A process reaped between the open and the read answers ESRCH.
        return False


def gone_within(pid, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not alive(pid):
            return True
        time.sleep(0.1)
    return not alive(pid)


def force_kill(pid):
    try:
        if WINDOWS:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
        else:
            os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


class ProcessTree(unittest.TestCase):
    # The grandchild stays in its parent's process group; the subclass detaches it.
    DETACH = "plain"

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="orch-launch-")
        for name, text in (("child.py", CHILD), ("grandchild.py", GRANDCHILD)):
            with open(os.path.join(self.tmp, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        self.marker = os.path.join(self.tmp, "grandchild.pid")
        self.stdin = os.path.join(self.tmp, "in")
        open(self.stdin, "w").close()
        self.leftovers = []

    def tearDown(self):
        for pid in self.leftovers + self._grandchild(optional=True):
            force_kill(pid)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _grandchild(self, optional=False):
        try:
            with open(self.marker) as fh:
                return [int(fh.read())]
        except (OSError, ValueError):
            if optional:
                return []
            raise

    def _argv(self, mode):
        return [sys.executable, os.path.join(self.tmp, "child.py"), self.marker, mode, self.DETACH]

    def _run(self, mode, timeout, on_tick=None):
        return launch.run(self._argv(mode), self.tmp, self.stdin,
                          os.path.join(self.tmp, "out"), os.path.join(self.tmp, "err"),
                          timeout, on_tick=on_tick)

    def test_a_timeout_ends_the_whole_tree(self):
        with self.assertRaises(launch.RoleTimeout):
            self._run("sleep", timeout=5)
        pid = self._grandchild()[0]
        self.assertTrue(gone_within(pid, 5), "the grandchild outlived the timed-out role-run")

    def test_a_normal_exit_leaves_no_descendant_running(self):
        rc = self._run("exit", timeout=60)
        self.assertEqual(rc, 0)
        pid = self._grandchild()[0]
        self.assertTrue(gone_within(pid, 5), "a descendant kept running after the agent exited")

    def test_stop_ends_the_whole_tree(self):
        class Stop(Exception):
            pass

        def on_tick():
            if os.path.exists(self.marker) and open(self.marker).read():
                raise Stop()

        with self.assertRaises(Stop):
            self._run("sleep", timeout=60, on_tick=on_tick)
        pid = self._grandchild()[0]
        self.assertTrue(gone_within(pid, 5), "the grandchild outlived Stop")

    @unittest.skipUnless(WINDOWS, "Windows removes no directory a process still works in")
    def test_the_tree_is_gone_when_its_end_returns(self):
        """Ending the tree waits for every process in it: the directory they worked in is free at once, as
        removing a worktree right after its agent's end needs. Termination alone only begins it."""
        work = tempfile.mkdtemp(prefix="orch-launch-cwd-", dir=self.tmp)
        tree = launch._Tree()
        self.addCleanup(tree.close)
        tree.start(self._argv("sleep"), work, subprocess.DEVNULL, subprocess.DEVNULL, subprocess.DEVNULL, None)
        deadline = time.monotonic() + 30
        while not self._grandchild(optional=True) and time.monotonic() < deadline:
            time.sleep(0.05)
        pid = self._grandchild()[0]
        tree.kill()
        self.assertFalse(alive(pid), "a process of the tree outlived its end")
        os.rmdir(work)

    def test_the_owners_death_ends_the_whole_tree(self):
        """Killed outright, the process that launched the agent takes the tree with it."""
        owner_script = os.path.join(self.tmp, "owner.py")
        with open(owner_script, "w", encoding="utf-8") as fh:
            fh.write("import sys; sys.path.insert(0, %r); from app.agents import launch\n"
                     "launch.run(%r, %r, %r, %r, %r, 120)\n"
                     % (PKG, self._argv("sleep"), self.tmp, self.stdin,
                        os.path.join(self.tmp, "out"), os.path.join(self.tmp, "err")))
        owner = subprocess.Popen([sys.executable, owner_script])
        self.leftovers.append(owner.pid)
        deadline = time.monotonic() + 30
        while not self._grandchild(optional=True) and time.monotonic() < deadline:
            time.sleep(0.1)
        pid = self._grandchild()[0]
        owner.kill()                    # SIGKILL / TerminateProcess: no cleanup runs
        owner.wait()
        self.assertTrue(gone_within(pid, 10), "the grandchild outlived its owner's death")


class DetachedProcessTree(ProcessTree):
    """The same four promises when a descendant starts a session of its own to escape.

    This is what a process-group kill alone cannot contain, and what the cgroup can.
    """
    DETACH = "detached"


# Records its own pid first thing, then starts a detached grandchild that records its pid.
EARLY_CHILD = textwrap.dedent("""
    import os, subprocess, sys, time
    folder = sys.argv[1]
    with open(os.path.join(folder, "child-%d.pid" % os.getpid()), "w") as fh:
        fh.write(str(os.getpid()))
    subprocess.Popen([sys.executable, "-c",
                      "import os, sys, time; open(os.path.join(sys.argv[1], 'gc-%d.pid' % os.getpid()), 'w')"
                      ".write(str(os.getpid())); time.sleep(120)", folder], start_new_session=True)
    time.sleep(120)
""")


class StartupDeath(unittest.TestCase):
    """The owner killed while the agent is still being launched leaves nothing running.

    The kill lands at a spread of moments from the owner's own start, so some fall while
    the containment is still being set up and before anything the agent starts exists.
    """

    # Measured on WSL: the agent and its grandchild are up about 0.1s after the owner starts,
    # so most kills land inside that window; the later ones cover a slower host.
    DELAYS = (0.02, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.1, 0.12, 0.3, 1.0)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="orch-startup-")
        import shutil
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        with open(os.path.join(self.tmp, "child.py"), "w", encoding="utf-8") as fh:
            fh.write(EARLY_CHILD)
        self.stdin = os.path.join(self.tmp, "in")
        open(self.stdin, "w").close()

    def _pids(self, folder):
        pids = []
        for name in os.listdir(folder):
            if name.endswith(".pid"):
                try:
                    with open(os.path.join(folder, name)) as fh:
                        pids.append(int(fh.read()))
                except (OSError, ValueError):
                    pass
        return pids

    def _trial(self, delay, contained=True):
        folder = tempfile.mkdtemp(dir=self.tmp)
        argv = [sys.executable, os.path.join(self.tmp, "child.py"), folder]
        if contained:
            code = ("import sys; sys.path.insert(0, %r); from app.agents import launch\n"
                    "launch.run(%r, %r, %r, %r, %r, 120)\n"
                    % (PKG, argv, self.tmp, self.stdin, os.path.join(folder, "out"), os.path.join(folder, "err")))
        else:
            # Control: the same agent launched with nothing containing it.
            code = "import subprocess, time; subprocess.Popen(%r, start_new_session=True); time.sleep(120)\n" % argv
        owner = subprocess.Popen([sys.executable, "-c", code])
        time.sleep(delay)
        owner.kill()
        owner.wait()
        # Long enough for a launch the owner's death interrupted to have finished coming up.
        time.sleep(3)
        survivors = [pid for pid in self._pids(folder) if alive(pid)]
        for pid in survivors:
            force_kill(pid)
        return survivors

    def test_an_owner_killed_during_launch_leaves_nothing_running(self):
        for delay in self.DELAYS:
            self.assertEqual(self._trial(delay), [],
                             "something the agent started outlived an owner killed %.2fs in" % delay)

    def test_control_an_uncontained_launch_leaves_its_processes_running(self):
        self.assertNotEqual(self._trial(1.5, contained=False), [],
                            "the check sees a survivor when nothing contains the launch")


@unittest.skipUnless(WINDOWS, "the job object is the Windows primitive")
class SuspendedOrphan(unittest.TestCase):
    """An owner that dies after creating the agent but before the agent is inside its job leaves nothing.

    The owner is held in that gap on purpose: its call placing the process in the job waits
    first. An agent created suspended outside its job never runs, so it writes no pid file;
    it is found by its command line instead.
    """

    OWNER = textwrap.dedent("""
        import sys, time
        sys.path.insert(0, %(pkg)r)
        from app.agents import launch

        class Slow:
            def __init__(self, kernel32):
                self.kernel32 = kernel32

            def __getattr__(self, name):
                return getattr(self.kernel32, name)

            def AssignProcessToJobObject(self, *args):
                print("in the gap", flush=True)
                time.sleep(30)
                return self.kernel32.AssignProcessToJobObject(*args)

        init = launch._WindowsTree.__init__

        def slow_init(self):
            init(self)
            self.kernel32 = Slow(self.kernel32)

        launch._WindowsTree.__init__ = slow_init
        tree = launch._WindowsTree()
        print("created", flush=True)
        tree.start(%(argv)r, %(cwd)r, None, None, None, None)
        print("in the gap", flush=True)
        time.sleep(30)
    """)

    def test_an_owner_killed_before_the_agent_is_in_its_job_leaves_nothing(self):
        tmp = tempfile.mkdtemp(prefix="orch-orphan-")
        import shutil
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        marker = "orphan-%d" % os.getpid()
        argv = [sys.executable, "-c", "import time; time.sleep(120)", marker]
        owner = subprocess.Popen([sys.executable, "-c", self.OWNER % {"pkg": PKG, "argv": argv, "cwd": tmp}],
                                 stdout=subprocess.PIPE)
        self.assertEqual(owner.stdout.readline().strip(), b"created")
        self.assertEqual(owner.stdout.readline().strip(), b"in the gap")
        owner.kill()
        owner.wait()
        time.sleep(3)
        leftovers = [pid for pid in self._with_command_line(marker) if pid != owner.pid]
        for pid in leftovers:
            force_kill(pid)
        self.assertEqual(leftovers, [], "the agent outlived its owner, suspended outside any job")

    @staticmethod
    def _with_command_line(marker):
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*%s*' "
                              "-and $_.Name -eq 'python.exe' }).ProcessId" % marker],
                             capture_output=True, text=True).stdout
        return [int(pid) for pid in out.split()]


@unittest.skipIf(WINDOWS, "the scope is the POSIX primitive")
class NoScope(unittest.TestCase):
    """Without a systemd user manager to create its scope, the agent is refused before it runs."""

    def test_the_agent_never_runs_without_a_scope(self):
        tmp = tempfile.mkdtemp(prefix="orch-noscope-")
        import shutil
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        sentinel = os.path.join(tmp, "RAN")
        stdin = os.path.join(tmp, "in")
        open(stdin, "w").close()
        argv = [sys.executable, "-c", "open(%r, 'w').write('x')" % sentinel]
        unreachable = dict(os.environ, DBUS_SESSION_BUS_ADDRESS="unix:path=%s/no-bus" % tmp,
                           XDG_RUNTIME_DIR=os.path.join(tmp, "no-runtime"))
        with self.assertRaises(launch.ExecutorError):
            launch.run(argv, tmp, stdin, os.path.join(tmp, "out"), os.path.join(tmp, "err"), 60,
                       env=unreachable)
        self.assertFalse(os.path.exists(sentinel), "a refused launch runs nothing")
        # Control: the same agent with the user manager reachable runs.
        self.assertEqual(launch.run(argv, tmp, stdin, os.path.join(tmp, "out"), os.path.join(tmp, "err"), 60), 0)
        self.assertTrue(os.path.exists(sentinel))


@unittest.skipIf(WINDOWS, "the scope is the POSIX primitive")
class HungSystemd(unittest.TestCase):
    """A user systemd manager that hangs, rather than one that is plainly absent.

    Hung `systemctl` and `systemd-run` are shims first on PATH that never return.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="orch-hung-")
        import shutil
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.shims = os.path.join(self.tmp, "shims")
        os.makedirs(self.shims)
        self.shim_pids = os.path.join(self.tmp, "shim.pids")
        self.addCleanup(self._kill_shims)
        with open(os.path.join(self.tmp, "child.py"), "w", encoding="utf-8") as fh:
            fh.write(CHILD)
        with open(os.path.join(self.tmp, "grandchild.py"), "w", encoding="utf-8") as fh:
            fh.write(GRANDCHILD)
        self.stdin = os.path.join(self.tmp, "in")
        open(self.stdin, "w").close()

    def _kill_shims(self):
        try:
            with open(self.shim_pids) as fh:
                for pid in fh.read().split():
                    force_kill(int(pid))
        except OSError:
            pass

    def _hang(self, name):
        path = os.path.join(self.shims, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\necho $$ >> %s\nexec sleep 600\n" % self.shim_pids)
        os.chmod(path, 0o755)
        return path

    def _owner(self, body, env_path):
        code = ("import sys; sys.path.insert(0, %r); from app.agents import launch\n%s"
                % (PKG, body))
        env = dict(os.environ, PATH=env_path + os.pathsep + os.environ["PATH"])
        return subprocess.Popen([sys.executable, "-c", code], env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)

    def test_control_the_shims_really_hang(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            subprocess.run([self._hang("systemctl")], timeout=1)

    def test_a_refused_launch_returns_even_when_systemd_hangs(self):
        self._hang("systemctl")
        self._hang("systemd-run")
        body = ("launch.SCOPE_SECONDS = 2\nlaunch.SYSTEMCTL_SECONDS = 2\n"
                "try:\n"
                "    launch.run([sys.executable, '-c', 'pass'], %r, %r, %r, %r, 60)\n"
                "except launch.ExecutorError:\n"
                "    print('REFUSED')\n"
                % (self.tmp, self.stdin, os.path.join(self.tmp, "out"), os.path.join(self.tmp, "err")))
        owner = self._owner(body, self.shims)
        try:
            out, _ = owner.communicate(timeout=40)
        except subprocess.TimeoutExpired:
            owner.kill()
            owner.communicate()
            self.fail("the refused launch hung with systemd")
        self.assertIn("REFUSED", out)

    def test_the_owners_death_ends_the_tree_even_when_systemctl_hangs(self):
        """Once the agent is running, killing its scope needs no systemd at all."""
        marker = os.path.join(self.tmp, "grandchild.pid")
        # Only systemctl hangs: the scope is created by the real systemd-run, first on PATH after the shims.
        self._hang("systemctl")
        argv = [sys.executable, os.path.join(self.tmp, "child.py"), marker, "sleep", "detached"]
        body = "launch.run(%r, %r, %r, %r, %r, 120)\n" % (
            argv, self.tmp, self.stdin, os.path.join(self.tmp, "out"), os.path.join(self.tmp, "err"))
        owner = self._owner(body, self.shims)
        deadline = time.monotonic() + 30
        while not (os.path.exists(marker) and open(marker).read()) and time.monotonic() < deadline:
            time.sleep(0.1)
        with open(marker) as fh:
            pid = int(fh.read())
        owner.kill()
        owner.communicate()
        survived = not gone_within(pid, 10)
        if survived:
            force_kill(pid)
        self.assertFalse(survived, "the grandchild outlived its owner while systemctl hung")


class NoShell(unittest.TestCase):
    """Operator text reaches the agent byte for byte and executes nothing."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="orch-argv-")
        import shutil
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.sentinel = os.path.join(self.tmp, "EXECUTED")
        self.hostile = ('cost $5 and $(touch %s) and `touch %s` and "quoted" \'single\'; touch %s & echo %%PATH%%'
                        % (self.sentinel, self.sentinel, self.sentinel))
        self.agent = os.path.join(self.tmp, "agent.py")
        with open(self.agent, "w", encoding="utf-8") as fh:
            fh.write("import json, sys\n"
                     "json.dump({'argv': sys.argv[1:], 'stdin': sys.stdin.buffer.read().decode('utf-8')},"
                     " open(sys.argv[1], 'w', encoding='utf-8'))\n")

    def test_task_text_in_argv_and_on_stdin_arrives_verbatim(self):
        capture = os.path.join(self.tmp, "capture.json")
        prompt = os.path.join(self.tmp, "prompt")
        with open(prompt, "w", encoding="utf-8", newline="") as fh:
            fh.write(self.hostile)
        rc = launch.run([sys.executable, self.agent, capture, self.hostile], self.tmp, prompt,
                        os.path.join(self.tmp, "out"), os.path.join(self.tmp, "err"), 60)
        self.assertEqual(rc, 0)
        with open(capture, encoding="utf-8") as fh:
            seen = json.load(fh)
        self.assertEqual((seen["argv"][1], seen["stdin"]), (self.hostile, self.hostile))
        self.assertFalse(os.path.exists(self.sentinel), "nothing in the text may be executed")

    @unittest.skipIf(WINDOWS, "the control uses a POSIX shell")
    def test_control_the_same_text_through_a_shell_executes(self):
        subprocess.run("%s %s %s %s" % (sys.executable, self.agent, os.path.join(self.tmp, "c.json"), self.hostile),
                       shell=True, stdin=subprocess.DEVNULL, capture_output=True, cwd=self.tmp)
        self.assertTrue(os.path.exists(self.sentinel), "a shell runs the text, which is what argv prevents")


if __name__ == "__main__":
    unittest.main()
