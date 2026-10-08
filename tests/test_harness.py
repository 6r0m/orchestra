"""The suite's own harness: a process that used the Temporal test environment exits once its tests are
done, even with an activity still running on one of its workers; and the parallel run, which gives each
test class a process of its own and fails on anything less than every class passing whole.

The interpreter joins every thread pool's threads before it runs a single atexit handler, and an
activity runs on one of those threads until its worker's shutdown cancels it. So the harness stops its
workers as the interpreter begins to shut down, ahead of that join — or a turn left running would hold
the process at exit for good.
"""
import contextlib
import io
import os
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import types
import unittest

from tests import runner
from tests.runner import end_tree, parallel

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
# Well past a worker's shutdown and the test server's, and well short of a turn's budget.
EXIT_SECONDS = 60

# A test process that ends with a run's turn still at work, as one would if a test left its run open:
# the turn heartbeats, as a real one does, and ends only once it is cancelled.
LEFT_RUNNING = textwrap.dedent("""\
    import sys, threading, time, uuid
    sys.path[:0] = [%r, %r]
    import temporal_env as E
    from app.agents import terminal
    from app.orchestration import workflow as WF

    started = threading.Event()

    def turn(worktree, argv, rdir, name, prompt, timeout, env, *, kind):
        started.set()
        while True:
            terminal._activity_tick(name)
            time.sleep(0.2)

    host, _ = E.host([])
    host.runner = turn
    run_id = uuid.uuid4().hex[:12]
    E.run(E.client().start_workflow(WF.FeatureRun.run, E.start_input(run_id), id=run_id,
                                    task_queue=E.WORKFLOW_QUEUE))
    assert started.wait(60), "the turn never started"
    print("left running", flush=True)
""") % (PKG, HERE)


class Exit(unittest.TestCase):
    def test_a_process_whose_turn_is_still_running_exits_once_its_tests_are_done(self):
        child = subprocess.Popen([sys.executable, "-c", LEFT_RUNNING], cwd=PKG, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, start_new_session=os.name != "nt")
        self.addCleanup(lambda: child.poll() is None and end_tree(child))
        lines = queue.Queue()
        threading.Thread(target=lambda: [lines.put(line) for line in child.stdout], daemon=True).start()
        # Until its main thread is done: the server's and the workers' start are not the exit's to count.
        before, deadline = [], time.monotonic() + 120
        while not before or before[-1].strip() != "left running":
            try:
                before.append(lines.get(timeout=max(0.1, deadline - time.monotonic())))
            except queue.Empty:
                end_tree(child)
                self.fail("its turn never got running: %s" % "".join(before)[-2000:])
        done = time.monotonic()
        try:
            child.wait(timeout=EXIT_SECONDS)
        except subprocess.TimeoutExpired:
            end_tree(child)
            self.fail("still running %d s after its main thread was done" % EXIT_SECONDS)
        self.assertEqual(child.returncode, 0, "".join(before)[-2000:])
        self.assertLess(time.monotonic() - done, EXIT_SECONDS)


# A class whose test leaves a sleeper whose parent has already gone — a process of its tree that no walk
# from it finds — and writes both pids where the test can look.
ORPHAN = ("import os, subprocess, sys, time, unittest\n\n"
          "SPAWN = ('import subprocess, sys; print(subprocess.Popen([sys.executable, \"-c\", "
          "\"import time; time.sleep(3600)\"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
          "stderr=subprocess.DEVNULL).pid)')\n\n"
          "class Orphaning(unittest.TestCase):\n"
          "    def test_it(self):\n"
          "        orphan = int(subprocess.run([sys.executable, '-c', SPAWN], capture_output=True, "
          "text=True).stdout)\n"
          "        with open(os.path.join(os.path.dirname(__file__), __name__ + '.pid'), 'w') as fh:\n"
          "            fh.write('%d %d' % (os.getpid(), orphan))\n")
# Stand-in test modules for the parallel run, written to a folder of each test's own: never the suite's.
STANDINS = {
    "passing": "import unittest\n\nclass Passing(unittest.TestCase):\n"
               "    def test_one(self):\n        pass\n\n    def test_two(self):\n        pass\n",
    "failing": "import unittest\n\nclass Failing(unittest.TestCase):\n"
               "    def test_it(self):\n        self.fail('as asked')\n",
    "erring": "import unittest\n\nclass Erring(unittest.TestCase):\n"
              "    def test_it(self):\n        raise RuntimeError('as asked')\n",
    "broken": "import a_module_that_is_nowhere\n",
    # It and a process of its own, their pids written where the test can look once the run has ended them.
    "hanging": "import os, subprocess, sys, time, unittest\n\nclass Hanging(unittest.TestCase):\n"
               "    def test_it(self):\n"
               "        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(3600)'])\n"
               "        with open(os.path.join(os.path.dirname(__file__), __name__ + '.pid'), 'w') as fh:\n"
               "            fh.write('%d %d' % (os.getpid(), child.pid))\n"
               "        time.sleep(3600)\n",
    # It, and a sleeper whose parent has already gone: a process of its tree that no walk from it finds.
    "orphaning": ORPHAN + "        time.sleep(3600)\n",
    # The same, and then it passes: what a class that finished left running.
    "leaving": ORPHAN,
    "twoclasses": "import unittest\n\nclass First(unittest.TestCase):\n    def test_it(self):\n        pass\n\n\n"
                  "class Second(unittest.TestCase):\n    def test_it(self):\n        pass\n",
    # One test fewer in the class's own process — the one its run names — than discovery found.
    "shrinking": "import sys, unittest\n\nclass Shrinking(unittest.TestCase):\n"
                 "    def test_one(self):\n        pass\n\n"
                 "    if not any(arg.endswith('.Shrinking') for arg in sys.argv):\n"
                 "        def test_two(self):\n            pass\n",
}
STANDINS["hanging_too"] = STANDINS["hanging"]


def held(pid):
    """A handle to wait on Windows process `pid` with, or None once it is gone."""
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    return kernel32.OpenProcess(0x00100000, False, pid) or None           # SYNCHRONIZE


def ended_now(handle):
    """Whether the process `handle` holds has ended at this moment, with no time given it to end in."""
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    return kernel32.WaitForSingleObject(handle, 0) == 0                   # WAIT_OBJECT_0


def let_go(handle):
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel32.CloseHandle(handle)


def alive(pid):
    """Whether `pid` still runs; a zombie, ended and not yet reaped, does not."""
    if os.name == "nt":
        listed = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/NH"], capture_output=True, text=True)
        return str(pid) in listed.stdout
    try:
        with open("/proc/%d/stat" % pid, encoding="utf-8") as fh:
            return fh.read().rsplit(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return False


class Parallel(unittest.TestCase):
    """Each class in a process of its own; the run fails on anything short of every class passing whole."""

    def standins(self, *kinds):
        folder = tempfile.mkdtemp(prefix="orchestra-runner-")
        self.addCleanup(shutil.rmtree, folder, True)
        names = {kind: "test_%s_%s" % (kind, os.urandom(3).hex()) for kind in kinds}
        for kind, name in names.items():
            with open(os.path.join(folder, name + ".py"), "w", encoding="utf-8") as fh:
                fh.write(STANDINS[kind])
        return folder, names

    def run_parallel(self, folder, names, **bounds):
        said = io.StringIO()
        with contextlib.redirect_stdout(said), contextlib.redirect_stderr(said):
            code = parallel(names, start=folder, top=folder, at_once=bounds.pop("at_once", 4),
                            out=os.path.join(folder, "out"), **bounds)
        return code, said.getvalue()

    @staticmethod
    def pids(folder, modules):
        found = []
        for module in modules:
            path = os.path.join(folder, module + ".pid")
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    found += [int(pid) for pid in fh.read().split()]
        return found

    def still_running(self, folder, modules, grace=5):
        """The pids the hanging stand-ins wrote that still run, `grace` seconds after their run ended them."""
        pids = self.pids(folder, modules)
        self.assertEqual(len(pids), 2 * len(modules), "each hanging class got going: %s" % pids)
        deadline = time.monotonic() + grace
        while any(alive(pid) for pid in pids) and time.monotonic() < deadline:
            time.sleep(0.1)
        return [pid for pid in pids if alive(pid)]

    def interrupted_when_hanging(self, folder, modules, signals, then=None):
        """Runs `modules` with the runner's pauses standing in: once every hanging class has written its
        pids, each of `signals` is raised in turn — the first as the run notices, the rest as it ends what
        runs — or, with `then`, that exception instead."""
        raised = []

        def pause(seconds):
            time.sleep(seconds)
            if not raised and len(self.pids(folder, modules)) == 2 * len(modules):
                raised.append(True)
                if then:
                    raise then
                signal.raise_signal(signals[0])
        ending = runner.end_tree

        def end_tree_and_signal_again(*args):
            ending(*args)
            for number in signals[1:]:
                signal.raise_signal(number)
        for name, stand_in in (("time", types.SimpleNamespace(monotonic=time.monotonic, sleep=pause)),
                               ("end_tree", end_tree_and_signal_again)):
            self.addCleanup(setattr, runner, name, getattr(runner, name))
            setattr(runner, name, stand_in)
        before = signal.getsignal(signal.SIGINT)
        try:
            code, said = self.run_parallel(folder, modules, at_once=2)
        except KeyboardInterrupt:
            self.fail("a signal escaped the run's ending of what it had running")
        self.assertIs(signal.getsignal(signal.SIGINT), before, "the run's own handlers put back")
        return code, said

    def test_each_class_runs_in_a_process_of_its_own_and_a_named_module_runs_alone(self):
        folder, name = self.standins("passing", "failing")
        code, said = self.run_parallel(folder, [name["passing"]])
        self.assertEqual(code, 0, said)
        self.assertIn("%s.Passing — ok" % name["passing"], said)
        self.assertEqual(os.listdir(os.path.join(folder, "out")), ["%s.Passing.log" % name["passing"]],
                         "one process, its own output, and only the module named")
        self.assertIn("1 classes, 2 tests", said)

    def test_a_failure_an_error_or_a_module_that_does_not_load_fails_the_run_and_says_why(self):
        folder, name = self.standins("passing", "failing", "erring", "broken")
        code, said = self.run_parallel(folder, list(name.values()))
        self.assertEqual(code, 1, said)
        self.assertIn("%s.Passing — ok" % name["passing"], said)
        for kind, cls in (("failing", ".Failing"), ("erring", ".Erring"), ("broken", "")):
            self.assertIn("%s%s — FAILED" % (name[kind], cls), said)
        self.assertIn("a_module_that_is_nowhere", said, "the load failure's own error, printed")
        self.assertIn("RuntimeError: as asked", said)

    def test_a_class_that_hangs_is_dumped_ended_and_fails_the_run(self):
        folder, name = self.standins("hanging")
        began = time.monotonic()
        code, said = self.run_parallel(folder, [name["hanging"]], limit=10, dump_before=5)
        self.assertEqual(code, 1, said)
        self.assertLess(time.monotonic() - began, 40, "ended at its bound, never waited out")
        self.assertIn("%s.Hanging — HUNG" % name["hanging"], said)
        self.assertIn("in test_it", said, "its threads dumped before it was ended: where it hung")
        self.assertEqual(self.still_running(folder, [name["hanging"]]), [], "its whole process tree ended")

    def test_a_class_that_runs_fewer_tests_than_it_holds_fails_the_run(self):
        folder, name = self.standins("shrinking")
        code, said = self.run_parallel(folder, [name["shrinking"]])
        self.assertEqual(code, 1, said)
        self.assertIn("ran 1 of its 2 tests", said)

    def test_a_run_that_finds_or_runs_no_tests_fails(self):
        folder = tempfile.mkdtemp(prefix="orchestra-runner-")
        self.addCleanup(shutil.rmtree, folder, True)
        code, said = self.run_parallel(folder, [])
        self.assertEqual(code, 5, said)
        self.assertIn("no tests found", said)
        done = subprocess.run([sys.executable, "-m", "tests", "discover", "-s", folder, "-t", folder], cwd=PKG,
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 5, "one process that ran nothing fails as well: %s" % done.stderr)

    def test_an_interrupted_run_ends_every_class_though_interrupted_again_while_it_does(self):
        """`uv run` passes a terminal's interrupt on twice: the second must not cut the ending short."""
        folder, name = self.standins("hanging", "hanging_too")
        hanging = [name["hanging"], name["hanging_too"]]
        code, said = self.interrupted_when_hanging(folder, hanging, [signal.SIGINT, signal.SIGINT])
        self.assertEqual(code, 130, said)
        self.assertIn("interrupted: ended the 2 classes still running", said)
        self.assertEqual(self.still_running(folder, hanging), [], "no class left running, detached")

    def test_a_class_is_ended_with_every_process_of_its_tree_one_whose_parent_is_gone_too(self):
        """An orphan is its class's all the same, and ends with it. On Windows a job holds the whole tree,
        and its end is proved before the run goes on, so nothing is left for a grace to wait out."""
        folder, name = self.standins("orphaning")
        code, said = self.interrupted_when_hanging(folder, [name["orphaning"]], [signal.SIGINT])
        self.assertEqual(code, 130, said)
        self.assertEqual(self.still_running(folder, [name["orphaning"]], grace=0 if os.name == "nt" else 5),
                         [], "the class and its orphan both ended")

    def test_a_class_that_finished_leaves_nothing_running_its_orphan_included(self):
        """A class that passed may still have left something running; it ends with the class. On Windows the
        end is proved before the run goes on: a process held from before it has ended the moment the run
        returns. The control, a job closed and not waited on, leaves it still ending then (measured once)."""
        folder, name = self.standins("leaving")
        module, holding = name["leaving"], {}
        ending = runner.end_tree

        def hold_then_end(child, tree=None):
            if os.name == "nt":
                for pid in self.pids(folder, [module]):
                    handle = held(pid)
                    if handle:
                        holding[pid] = handle
                        self.addCleanup(let_go, handle)
            return ending(child, tree)
        self.addCleanup(setattr, runner, "end_tree", ending)
        runner.end_tree = hold_then_end
        code, said = self.run_parallel(folder, [module])
        self.assertEqual(code, 0, said)
        if os.name == "nt":
            self.assertTrue(holding, "the orphan was held before its end")
            self.assertEqual([pid for pid, handle in holding.items() if not ended_now(handle)], [],
                             "each process of the class's tree had ended when the run returned")
        self.assertEqual(self.still_running(folder, [module], grace=0 if os.name == "nt" else 5), [],
                         "the class and its orphan both ended")

    def test_a_class_whose_end_is_not_proved_fails_the_run_and_says_so(self):
        folder, name = self.standins("passing")
        ending = runner.end_tree

        def unproved(child, tree=None):
            ending(child, tree)
            raise TimeoutError("the class's process tree did not end within 30s of its kill: process 4242 is "
                               "still there")
        self.addCleanup(setattr, runner, "end_tree", ending)
        runner.end_tree = unproved
        code, said = self.run_parallel(folder, [name["passing"]])
        self.assertEqual(code, 1, said)
        self.assertIn("%s.Passing — FAILED — its processes were not proved ended" % name["passing"], said)
        self.assertIn("process 4242 is still there", said)

    @unittest.skipIf(os.name == "nt", "a termination and a hang-up are POSIX signals")
    def test_a_terminated_run_ends_every_class_as_an_interrupted_one_does(self):
        folder, name = self.standins("hanging")
        code, said = self.interrupted_when_hanging(folder, [name["hanging"]], [signal.SIGTERM, signal.SIGHUP])
        self.assertEqual(code, 130, said)
        self.assertEqual(self.still_running(folder, [name["hanging"]]), [])

    def test_a_run_that_fails_any_other_way_leaves_no_class_running(self):
        folder, name = self.standins("hanging")
        with self.assertRaisesRegex(RuntimeError, "the run broke"):
            self.interrupted_when_hanging(folder, [name["hanging"]], [], then=RuntimeError("the run broke"))
        self.assertEqual(self.still_running(folder, [name["hanging"]]), [])

    def test_discovery_splits_modules_into_classes_and_a_narrower_or_repeated_name_runs_once(self):
        folder, name = self.standins("passing", "twoclasses")
        for names, ran in (([], "3 classes, 4 tests"),
                           (["%s.Passing.test_one" % name["passing"]], "1 classes, 1 tests"),
                           ([name["passing"], name["passing"] + ".Passing"], "1 classes, 2 tests"),
                           ([os.path.join(folder, name["twoclasses"] + ".py")], "2 classes, 2 tests")):
            code, said = self.run_parallel(folder, names)
            self.assertEqual((code, ran in said), (0, True), "%s: %s" % (names, said))

    def test_a_named_module_that_does_not_load_says_its_own_error(self):
        """unittest names a failed named load after its last part alone: the run keeps the whole name."""
        folder = tempfile.mkdtemp(prefix="orchestra-runner-")
        self.addCleanup(shutil.rmtree, folder, True)
        package = "pkg_%s" % os.urandom(3).hex()
        os.makedirs(os.path.join(folder, package))
        open(os.path.join(folder, package, "__init__.py"), "w", encoding="utf-8").close()
        with open(os.path.join(folder, package, "test_broken.py"), "w", encoding="utf-8") as fh:
            fh.write(STANDINS["broken"])
        code, said = self.run_parallel(folder, ["%s.test_broken" % package])
        self.assertEqual(code, 1, said)
        self.assertIn("%s.test_broken — FAILED" % package, said)
        self.assertIn("a_module_that_is_nowhere", said, "its own error, not a module named after its last part")

    def test_a_flag_or_a_name_that_holds_no_tests_is_refused(self):
        folder, name = self.standins("passing")
        code, said = self.run_parallel(folder, ["-v"])
        self.assertEqual((code, "test names only" in said), (5, True), said)
        code, said = self.run_parallel(folder, [name["passing"], "os"])
        self.assertEqual((code, "no tests in os" in said), (5, True), said)

    def test_a_class_process_finds_the_checkout_by_its_own_start_never_through_pythonpath(self):
        """Everything a class starts inherits its environment — the agents' launched-by-path files among
        them, which must import nothing of ours: only a folder of stand-ins goes on PYTHONPATH."""
        self.assertEqual(runner.child_env(runner.PKG, 10).get("PYTHONPATH"), os.environ.get("PYTHONPATH"),
                         "nothing of the checkout added")
        folder = tempfile.mkdtemp(prefix="orchestra-runner-")
        self.addCleanup(shutil.rmtree, folder, True)
        self.assertEqual(runner.child_env(folder, 10)["PYTHONPATH"].split(os.pathsep)[0], folder)


@unittest.skipUnless(os.name == "posix", "run-tests.sh is the runner of WSL and Linux")
class TheRunnersEnvironment(unittest.TestCase):
    """`run-tests.sh` builds the environment its tests run in. One built for a checkout is removed with
    that checkout by the host whose git owns it — and a run's worktree made by the other host's git is
    never this host's to remove, so an environment kept for it here would outlive it."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="orchestra-runner-script-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.checkout = os.path.join(self.tmp, "checkout")
        os.makedirs(os.path.join(self.checkout, "app", "foundation"))
        shutil.copyfile(os.path.join(PKG, "run-tests.sh"), os.path.join(self.checkout, "run-tests.sh"))
        shutil.copyfile(os.path.join(PKG, "app", "foundation", "envpath.py"),
                        os.path.join(self.checkout, "app", "foundation", "envpath.py"))
        # A stand-in for uv: it answers where the environment lives as the real one does — by running
        # envpath.py — builds one by making its folder, and "runs the tests" by saying which it was given.
        # Told to end while they run, they take a moment to, and say so only if that environment was still
        # there once they had.
        tools = os.path.join(self.tmp, "bin")
        os.makedirs(tools)
        self.said = os.path.join(self.tmp, "said")
        with open(os.path.join(tools, "uv"), "w", encoding="utf-8") as fh:
            fh.write(textwrap.dedent("""\
                #!/usr/bin/env bash
                case " $* " in
                    *" envpath.py "*|*envpath.py*) exec "%s" "${@: -2:1}" "${@: -1}" ;;
                esac
                case " $* " in
                    *" sync "*) mkdir -p "$UV_PROJECT_ENVIRONMENT" && : > "$UV_PROJECT_ENVIRONMENT/pyvenv.cfg" ;;
                    *" run "*)
                        ended() {
                            sleep 0.5
                            [ -f "$UV_PROJECT_ENVIRONMENT/pyvenv.cfg" ] && echo ended-in-their-environment >> "%s"
                            exit 143
                        }
                        trap ended TERM
                        echo "$UV_PROJECT_ENVIRONMENT" > "%s"
                        if [ -n "${CONTROL_TESTS_WAIT:-}" ]; then
                            sleep 60 & wait
                        fi
                        exit "${CONTROL_TESTS_EXIT:-0}" ;;
                esac
                """) % (sys.executable, self.said, self.said))
        os.chmod(os.path.join(tools, "uv"), 0o755)
        self.cache = os.path.join(self.tmp, "cache")
        self.environment = dict(os.environ, PATH=tools + os.pathsep + os.environ["PATH"], XDG_CACHE_HOME=self.cache)

    def run_tests(self, **changes):
        done = subprocess.run(["bash", os.path.join(self.checkout, "run-tests.sh"), "tests.some"],
                              env=dict(self.environment, **changes), capture_output=True, text=True)
        with open(self.said, encoding="utf-8") as fh:
            return done, fh.read().strip()

    def kept(self):
        root = os.path.join(self.cache, "orchestra")
        return sorted(os.listdir(root)) if os.path.isdir(root) else []

    def test_a_checkout_this_hosts_git_reads_keeps_its_environment(self):
        subprocess.run(["git", "init", "--quiet", self.checkout], check=True, capture_output=True)
        done, used = self.run_tests()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(os.path.dirname(used), os.path.join(self.cache, "orchestra"), "under the root, by its name")
        self.assertTrue(os.path.isfile(os.path.join(used, "pyvenv.cfg")), "and there for the next run")

    def test_a_checkout_it_does_not_read_gets_one_that_ends_with_the_tests(self):
        """A worktree the other host's git made: its `.git` names a gitdir this host cannot spell."""
        with open(os.path.join(self.checkout, ".git"), "w", encoding="utf-8") as fh:
            fh.write("gitdir: Q:/no/such/repository/.git/worktrees/run\n")
        for exit_code in (0, 3):
            done, used = self.run_tests(CONTROL_TESTS_EXIT=str(exit_code))
            self.assertEqual(done.returncode, exit_code, "the tests' own result is the runner's: %s" % done.stderr)
            self.assertFalse(os.path.exists(used), "the environment the tests ran in is gone with them")
            self.assertEqual(self.kept(), [], "and none was kept under the root for a checkout no one here removes")

    def test_ended_from_outside_it_hands_the_end_on_and_still_takes_its_environment_back(self):
        with open(os.path.join(self.checkout, ".git"), "w", encoding="utf-8") as fh:
            fh.write("gitdir: Q:/no/such/repository/.git/worktrees/run\n")
        runner_script = subprocess.Popen(["bash", os.path.join(self.checkout, "run-tests.sh"), "tests.some"],
                                         env=dict(self.environment, CONTROL_TESTS_WAIT="1"),
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: runner_script.poll() is None and runner_script.kill())
        # The tests say which environment they were given only once a signal can reach them.
        deadline = time.monotonic() + 30
        while not (os.path.exists(self.said) and os.path.getsize(self.said)) and time.monotonic() < deadline:
            time.sleep(0.05)
        with open(self.said, encoding="utf-8") as fh:
            used = fh.read().strip()
        self.assertTrue(os.path.isdir(used), "the tests are running in it")
        runner_script.send_signal(signal.SIGTERM)
        self.assertNotEqual(runner_script.wait(timeout=30), 0)
        with open(self.said, encoding="utf-8") as fh:
            self.assertIn("ended-in-their-environment", fh.read(),
                          "the tests were told, and waited for: their environment was theirs until they had ended")
        self.assertFalse(os.path.exists(used), "and gone only then")


if __name__ == "__main__":
    unittest.main()
