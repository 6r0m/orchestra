"""The stack's one owner: the order it starts and stops the stack's parts in, what it proves before it
calls a part up or stopped, what it sweeps once a worker is gone, and the parts it never touches.

Two kinds. The owner over stand-in mechanics, which record what it asked for. And the real scripts
over a real process — a stand-in worker, whose command line reads as the worker's and which makes a
stage's settings as `run_role` does — under a policy of the test's own, so nothing of the live stack
is touched: `workers.sh` through the owner on WSL, `workers.ps1` itself on Windows.
"""
import asyncio
import datetime
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
sys.path[:0] = [PKG, HERE]

from temporalio.service import RPCError, RPCStatusCode  # noqa: E402

from app.application import client as runs  # noqa: E402
from app.application import stack  # noqa: E402
from app.foundation import policy as P  # noqa: E402

WINDOWS = sys.platform.startswith("win")


def now():
    """This moment. The reading judges a poll by how long ago it was on the wall clock, so a test takes the
    time as it runs: the whole suite reaches these tests minutes after it imports them."""
    return datetime.datetime.now(datetime.timezone.utc)


def lock_of_its_own(test):
    """The stack's lock in a folder of the test's own: the live stack's is never taken, nor met taken."""
    folder = tempfile.mkdtemp(prefix="orch-stack-lock-")
    test.addCleanup(shutil.rmtree, folder, True)
    test.addCleanup(setattr, stack, "LOCK", stack.LOCK)
    stack.LOCK = os.path.join(folder, "stack.lock")


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def other_policy(test):
    """A policy file of the test's own: its own host name, ports and workflow queue, as the demo's."""
    tmp = tempfile.mkdtemp(prefix="orch-stack-")
    test.addCleanup(shutil.rmtree, tmp, True)
    with open(P.POLICY_FILE, encoding="utf-8") as fh:
        policy = json.load(fh)
    for role in policy["roles"].values():
        role["prompt"] = os.path.join(PKG, role["prompt"])
    host = "stack%s" % os.urandom(3).hex()
    for target in policy["targets"].values():
        target.update(host=host, terminal_port=free_port())
    policy.update(workbench_port=free_port(), workflow_queue="orchestration:%s" % host)
    path = os.path.join(tmp, "policy.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(policy, fh)
    return P.load(path), path


class Mechanics:
    """Stands in for the scripts: records each (component, action) — a sweep's named pids in `swept` —
    and answers as the test says each part is: `running` the parts whose process runs, `refuse` the
    workers a stop cannot end, `linger` the ones a stop reports gone that a second look still finds,
    `unreadable` those whose status cannot be read at all, `elevated` those a start from this side
    would run elevated, which their script refuses, `unswept` those whose sweep fails."""

    def __init__(self, running=(), refuse=(), linger=(), unreadable=(), elevated=(), unswept=()):
        self.calls, self.swept, self.running = [], [], set(running)
        self.refuse, self.linger, self.unreadable = set(refuse), set(linger), set(unreadable)
        self.elevated, self.unswept = set(elevated), set(unswept)

    def __call__(self, policy, component, action, *more):
        self.calls.append((component, action))
        if action == "status" and component in self.unreadable:
            return False, "powershell.exe: the interop call failed"
        if action == "status":
            if component == "temporal":
                return True, "temporal" if component in self.running else "none running"
            said = "running 4242" if component in self.running else "stopped"
            return True, said + ("\nelevated" if component in self.elevated else "")
        if action == "start":
            self.running.add(component)
            return True, "started"
        if action == "stop":
            if component in self.refuse:
                return False, "still running 4242"
            if component not in self.linger:
                self.running.discard(component)
            return True, "stopped"
        self.swept.append(more)
        if component in self.unswept:
            return False, "the sweep could not list the temporary folder"
        return True, "removed the settings a dead worker's stage left: /tmp/orch-claude-settings-4242-x"


@unittest.skipIf(WINDOWS, "the stack is controlled from WSL")
class Owner(unittest.TestCase):
    def setUp(self):
        lock_of_its_own(self)

    @unittest.skipIf(WINDOWS, "the stack is controlled from WSL")
    def test_a_script_that_never_returns_is_given_up_on_and_the_stack_stays_free(self):
        """A host's script call that hangs — an interop call that never returns — ends at its action's limit
        as a part not done, and the stack's lock is let go for the next action."""
        policy, _ = other_policy(self)
        folder = tempfile.mkdtemp(prefix="orch-hung-script-")
        self.addCleanup(shutil.rmtree, folder, True)
        hung = os.path.join(folder, "workers.sh")
        with open(hung, "w", encoding="utf-8") as fh:
            fh.write("sleep 30\n")
        for name, stand_in in (("SCRIPT", hung), ("SCRIPT_SECONDS", dict(stack.SCRIPT_SECONDS, status=1, stop=1))):
            self.addCleanup(setattr, stack, name, getattr(stack, name))
            setattr(stack, name, stand_in)
        began = now()
        done, said = stack.mechanics(policy, "wsl", "status")
        self.assertEqual((done, said), (False, "wsl status did not finish within 1 s"))
        [result] = stack.stop(policy, "wsl")
        self.assertFalse(result["ok"], result)
        self.assertLess((now() - began).total_seconds(), 15, "given up on at its limits, never waited out")
        with stack._exclusive():
            pass

    def use(self, mechanics, answering=True):
        """The owner over `mechanics`, with Temporal answering or not, and a started worker polling."""
        async def answers(policy, seconds):
            # Temporal answers once it runs; another policy's stack leaves it to the deployment.
            return answering and ("temporal" in mechanics.running or "temporal" not in stack.managed(policy))

        async def polls(policy, target, since):
            return 4242 if target in mechanics.running else None
        for name, stand_in in (("mechanics", mechanics), ("_answering", answers), ("_polling", polls)):
            self.addCleanup(setattr, stack, name, getattr(stack, name))
            setattr(stack, name, stand_in)
        return mechanics

    def test_start_brings_up_temporal_then_each_worker(self):
        mechanics = self.use(Mechanics())
        results = stack.start(P.load())
        self.assertEqual([call for call in mechanics.calls if call[1] == "start"],
                         [("temporal", "start"), ("wsl", "start"), ("windows", "start")])
        self.assertTrue(all(result["ok"] for result in results), results)

    def test_a_worker_is_not_started_while_temporal_does_not_answer(self):
        mechanics = self.use(Mechanics(), answering=False)
        [result] = stack.start(P.load(), "wsl")
        self.assertFalse(result["ok"])
        self.assertIn("Temporal does not answer", result["said"])
        self.assertNotIn(("wsl", "start"), mechanics.calls, "a worker exits at once without Temporal")

    def test_stop_takes_the_workers_before_temporal_and_sweeps_each_host_once_its_worker_is_gone(self):
        mechanics = self.use(Mechanics(running=("temporal", "wsl", "windows")))
        results = stack.stop(P.load())
        self.assertEqual(mechanics.calls, [
            ("windows", "status"), ("windows", "stop"), ("windows", "status"), ("windows", "sweep"),
            ("wsl", "status"), ("wsl", "stop"), ("wsl", "status"), ("wsl", "sweep"), ("temporal", "stop")])
        self.assertEqual(mechanics.swept, [(4242,), (4242,)],
                         "each sweep names the worker it proved gone: Windows gives its pid away within moments")
        self.assertTrue(all(result["ok"] for result in results), results)
        self.assertIn("removed the settings 1 of its stages left", results[0]["said"])

    def test_a_worker_not_proven_gone_is_reported_so_and_nothing_of_it_is_swept(self):
        for mechanics in (Mechanics(running=("wsl",), refuse=("wsl",)), Mechanics(running=("wsl",), linger=("wsl",))):
            self.use(mechanics)
            [result] = stack.stop(P.load(), "wsl")
            self.assertFalse(result["ok"], result)
            self.assertIn("still running", result["said"])
            self.assertNotIn(("wsl", "sweep"), mechanics.calls, "a stage of a live worker keeps its settings")

    def test_a_stop_whose_sweep_failed_is_not_reported_done(self):
        """The worker is gone, but what its stages left may not be: the operator is told, not told "stopped"."""
        self.use(Mechanics(running=("wsl",), unswept=("wsl",)))
        [result] = stack.stop(P.load(), "wsl")
        self.assertFalse(result["ok"], result)
        self.assertIn("was not swept: the sweep could not list", result["said"])

    def test_a_worker_whose_state_cannot_be_read_is_never_counted_gone(self):
        """A status call that failed says nothing: not proven gone, so nothing of it is swept."""
        mechanics = self.use(Mechanics(running=("windows",), unreadable=("windows",)))
        [result] = stack.stop(P.load(), "windows")
        self.assertFalse(result["ok"], result)
        self.assertIn("could not be read", result["said"])
        self.assertNotIn(("windows", "sweep"), mechanics.calls)

    def test_restart_stops_then_starts(self):
        mechanics = self.use(Mechanics(running=("temporal", "wsl")))
        stack.restart(P.load(), "wsl")
        self.assertEqual(mechanics.calls, [("wsl", "status"), ("wsl", "stop"), ("wsl", "status"), ("wsl", "sweep"),
                                           ("wsl", "start")])

    def test_temporal_is_up_only_once_it_answers_and_stopped_only_once_it_does_not(self):
        mechanics = self.use(Mechanics(), answering=False)
        [result] = stack.start(P.load(), "temporal")
        self.assertFalse(result["ok"])
        self.assertIn("did not answer within", result["said"])
        mechanics = self.use(Mechanics(running=("temporal",), linger=("temporal",)))
        [result] = stack.stop(P.load(), "temporal")
        self.assertEqual((result["ok"], result["said"]), (False, "its containers stopped, but it still answers"))

    def test_a_restart_leaves_a_worker_this_side_cannot_start_again_as_it_is(self):
        """WSL started by an elevated process runs Windows programs elevated, and the Windows worker never
        starts so: stopping it would only leave it down. The rest of the stack restarts."""
        mechanics = self.use(Mechanics(running=("temporal", "wsl", "windows"), elevated=("windows",)))
        results = stack.restart(P.load())
        self.assertEqual([call for call in mechanics.calls if call[0] == "windows"], [("windows", "status")],
                         "looked at, and neither stopped nor started")
        [windows] = [result for result in results if result["component"] == "windows"]
        self.assertFalse(windows["ok"])
        self.assertIn("left as it is", windows["said"])
        self.assertIn("elevated", windows["said"])
        self.assertEqual([call for call in mechanics.calls if call[1] in ("stop", "start")],
                         [("wsl", "stop"), ("temporal", "stop"), ("temporal", "start"), ("wsl", "start")])
        self.assertIn("windows", mechanics.running)

    def test_another_policys_stack_manages_its_wsl_worker_and_never_temporal(self):
        mechanics = self.use(Mechanics(running=("temporal", "wsl")))
        policy, _ = other_policy(self)
        stack.stop(policy)
        stack.restart(policy)
        self.assertEqual({component for component, _ in mechanics.calls}, {"wsl"},
                         "a demo's whole-stack stop never stops the machine's Temporal or the Windows worker")
        for component in ("temporal", "windows"):
            with self.assertRaises(runs.Refusal, msg=component):
                stack.stop(policy, component)

    def test_one_action_at_a_time(self):
        self.use(Mechanics(running=("temporal", "wsl")))
        with stack._exclusive():
            with self.assertRaises(stack.Busy):
                stack.restart(P.load(), "wsl")
        self.assertTrue(stack.restart(P.load(), "wsl")[-1]["ok"], "and once it is free, the next one runs")


@unittest.skipIf(WINDOWS, "the stack is controlled from WSL")
class Started(unittest.TestCase):
    """A start is proven only by the process its pid file names polling each of its queues since it began."""

    def polling(self, polls, seconds=4):
        saved = stack.WORKER_READY
        stack.WORKER_READY = seconds

        async def connect(identity=None):
            return object()

        async def pollers(client, name, kind):
            return polls(name)
        for module, name, stand_in in ((stack, "mechanics", Mechanics(running=("wsl",))),
                                       (runs, "connect", connect), (runs, "pollers", pollers)):
            self.addCleanup(setattr, module, name, getattr(module, name))
            setattr(module, name, stand_in)
        self.addCleanup(setattr, stack, "WORKER_READY", saved)
        return asyncio.run(stack._polling(P.load(), "wsl", now() - datetime.timedelta(seconds=1)))

    def test_its_own_polls_of_every_queue_prove_it(self):
        self.assertEqual(self.polling(lambda name: [{"identity": "4242@here", "polled": now()}]), 4242)

    def test_one_queue_unpolled_or_another_processes_polls_do_not(self):
        self.assertIsNone(self.polling(lambda name: [] if name.startswith("target:") else
                                       [{"identity": "4242@here", "polled": now()}], seconds=2))
        self.assertIsNone(self.polling(lambda name: [{"identity": "1111@here", "polled": now()}], seconds=2),
                          "the dead worker's last polls, which Temporal still lists")


@unittest.skipIf(WINDOWS, "the stack is read from WSL")
class Reading(unittest.TestCase):
    """What the reading calls up: a worker is up only as the process it is, polling now."""

    def read(self, running, polls, client=True, **processes):
        """The reading, with each worker's process as `running` and `processes` say (as `Mechanics`
        takes them) and each queue's pollers as `polls` gives them: a function from a queue's host to its
        pollers."""
        async def pollers(client, name, kind):
            return polls(runs.host_of(name))
        self.addCleanup(setattr, stack, "mechanics", stack.mechanics)
        self.addCleanup(setattr, runs, "pollers", runs.pollers)
        stack.mechanics, runs.pollers = Mechanics(running=running, **processes), pollers
        return asyncio.run(stack.status(P.load(), object() if client else None,
                                        None if client else "Temporal is not reachable"))

    @staticmethod
    def states(reading):
        return {part["name"]: part["state"] for part in reading["components"]}

    def test_a_worker_is_up_only_while_its_own_process_polls(self):
        mine = [{"identity": "4242@here", "polled": now()}]
        reading = self.read(("wsl", "windows"), lambda host: mine)
        self.assertEqual(self.states(reading), {"temporal": "up", "wsl": "up", "windows": "up"})

    def test_a_poll_of_another_process_is_not_this_ones(self):
        """Right after a restart Temporal still lists the dead worker's last polls."""
        dead = [{"identity": "1111@here", "polled": now()}]
        reading = self.read(("wsl", "windows"), lambda host: dead)
        self.assertEqual(self.states(reading)["wsl"], "starting")
        self.assertEqual(reading["hosts"]["wsl"], "down", "a run needing it is blocked until it polls")

    def test_a_worker_whose_process_is_gone_is_down_whatever_temporal_still_lists(self):
        mine = [{"identity": "4242@here", "polled": now()}]
        self.assertEqual(self.states(self.read(("windows",), lambda host: mine))["wsl"], "down")

    def test_a_poll_older_than_a_long_poll_does_not_count(self):
        old = [{"identity": "4242@here", "polled": now() - runs.POLLING - datetime.timedelta(seconds=5)}]
        self.assertEqual(self.states(self.read(("wsl", "windows"), lambda host: old))["windows"], "starting")

    def test_a_worker_whose_process_cannot_be_read_is_unknown_and_says_why(self):
        """Never "down", which would offer to start a second one beside it."""
        mine = [{"identity": "4242@here", "polled": now()}]
        reading = self.read(("wsl", "windows"), lambda host: mine, unreadable=("windows",))
        windows = [part for part in reading["components"] if part["name"] == "windows"][0]
        self.assertEqual((windows["state"], reading["hosts"]["windows"]), ("unknown", "unknown"))
        self.assertIn("interop call failed", windows["detail"])
        self.assertFalse(windows["startable"])

    def test_a_worker_this_side_would_start_elevated_is_not_offered_a_start_and_says_why(self):
        mine = [{"identity": "4242@here", "polled": now()}]
        reading = self.read(("wsl", "windows"), lambda host: mine, elevated=("windows",))
        parts = {part["name"]: part for part in reading["components"]}
        self.assertEqual((parts["windows"]["state"], parts["windows"]["startable"]), ("up", False),
                         "it runs and polls, and a start or restart from here would be refused")
        self.assertIn("run elevated", parts["windows"]["detail"])
        self.assertTrue(parts["wsl"]["startable"] and parts["temporal"]["startable"])

    def test_an_idle_workers_last_poll_a_long_poll_ago_still_counts(self):
        idle = [{"identity": "4242@here", "polled": now() - datetime.timedelta(seconds=62)}]
        self.assertEqual(self.states(self.read(("wsl", "windows"), lambda host: idle))["wsl"], "up",
                         "a worker waits out a long poll of about a minute before it polls again")

    def test_temporal_that_stops_answering_on_a_held_connection_reads_down_and_says_why(self):
        """How the Workbench sees Temporal once its own Stop took it: its connection is kept, and fails."""
        async def refused(client, name, kind):
            raise RPCError("connection refused", RPCStatusCode.UNAVAILABLE, b"")
        self.addCleanup(setattr, stack, "mechanics", stack.mechanics)
        self.addCleanup(setattr, runs, "pollers", runs.pollers)
        stack.mechanics, runs.pollers = Mechanics(running=("wsl", "windows")), refused
        reading = asyncio.run(stack.status(P.load(), object()))
        self.assertEqual(self.states(reading), {"temporal": "down", "wsl": "running", "windows": "running"})
        self.assertEqual(reading["hosts"], {"wsl": "unknown", "windows": "unknown"})
        self.assertIn("did not answer: connection refused", reading["error"])

    def test_temporal_out_of_reach_leaves_the_processes_known_and_the_hosts_unknown(self):
        reading = self.read(("wsl",), lambda host: [], client=False)
        self.assertEqual(self.states(reading), {"temporal": "down", "wsl": "running", "windows": "down"})
        self.assertEqual(reading["hosts"], {"wsl": "unknown", "windows": "down"})
        self.assertIn("not reachable", reading["error"])


# A worker in the middle of a traced Claude stage, as far as the lifecycle can tell: its command line
# reads as the worker's, it records its pid where the worker does, and its stage's settings — the
# trace store's key in them — are named after it, as `run_role` makes them inside a worker.
STAND_IN = textwrap.dedent("""\
    import os, sys, time
    sys.path.insert(0, %r)
    from app.application import stack
    from app.foundation import policy as P
    from app.observability import telemetry
    policy, target = P.load(), sys.argv[-1]
    with open(stack.pid_file(policy, target), "w") as fh:
        fh.write(str(os.getpid()))
    span = telemetry._Span(traceparent="00-%%032x-%%016x-01" %% (1, 2))
    print(os.getpid(), telemetry.harness_settings(policy["roles"]["engineer"], span), flush=True)
    try:
        time.sleep(600)
    except KeyboardInterrupt:
        pass
""") % PKG


class RealWorker(unittest.TestCase):
    """The scripts over a real process, under a policy of the test's own."""

    def setUp(self):
        lock_of_its_own(self)

    def stand_in(self, policy_path, target):
        env = dict(os.environ, ORCH_POLICY=policy_path, LANGFUSE_PUBLIC_KEY="pk-lf-test",
                   LANGFUSE_SECRET_KEY="sk-lf-test")
        # Where the scripts' sweep looks: the worker's temporary folder, pinned to /tmp on WSL.
        if not WINDOWS:
            env["TMPDIR"] = "/tmp"
        worker = subprocess.Popen([sys.executable, "-c", STAND_IN, "-m", "app.interfaces.worker", target], cwd=PKG,
                                  env=env, stdout=subprocess.PIPE, text=True)
        self.addCleanup(worker.wait)
        self.addCleanup(worker.kill)
        # Its own pid: on Windows a virtual environment's python.exe starts the interpreter as a child.
        pid, _, settings = worker.stdout.readline().strip().partition(" ")
        worker.stdout.close()
        self.assertTrue(settings and os.path.isfile(settings), "the stand-in made its stage's settings: %r" % settings)
        self.addCleanup(shutil.rmtree, os.path.dirname(settings), True)
        self.assertTrue(os.path.basename(os.path.dirname(settings)).startswith("orch-claude-settings-%s-" % pid),
                        "named after the worker that made them")
        return worker, int(pid), settings

    def record(self, policy, target):
        record = stack.pid_file(policy, target)
        self.addCleanup(lambda: os.path.exists(record) and os.remove(record))
        return record

    @unittest.skipIf(WINDOWS, "the stack is controlled from WSL")
    def test_stopping_a_worker_takes_its_stages_settings_with_it(self):
        policy, path = other_policy(self)
        record = self.record(policy, "wsl")
        worker, pid, settings = self.stand_in(path, "wsl")
        self.assertEqual(stack.mechanics(policy, "wsl", "status")[1], "running %d" % pid)
        [result] = stack.stop(policy, "wsl")
        self.assertTrue(result["ok"], result)
        self.assertIsNotNone(worker.poll(), "the worker is gone")
        self.assertFalse(os.path.exists(record), "and so is its record")
        self.assertFalse(os.path.exists(os.path.dirname(settings)), "and its stage's settings, key and all, at once")
        self.assertIn("removed the settings", result["said"])

    @unittest.skipIf(WINDOWS, "the stack is controlled from WSL")
    def test_a_stop_whose_sweep_cannot_take_what_its_stages_left_is_not_reported_done(self):
        """Through `workers.sh` and the worker's own sweep: settings the sweep cannot remove fail the stop."""
        if os.geteuid() == 0:
            self.skipTest("root removes them whatever their mode")
        policy, path = other_policy(self)
        self.record(policy, "wsl")
        worker, pid, settings = self.stand_in(path, "wsl")
        # Writable again whatever happens, an interrupt included: in /tmp, where the live worker's sweep looks,
        # a folder it cannot empty would fail every stop of it.
        os.chmod(os.path.dirname(settings), 0o500)
        try:
            [result] = stack.stop(policy, "wsl")
        finally:
            os.chmod(os.path.dirname(settings), 0o700)
        self.assertIsNotNone(worker.poll(), "the worker is gone")
        self.assertFalse(result["ok"], result)
        self.assertIn("was not swept", result["said"])
        self.assertIn(os.path.dirname(settings), result["said"])
        self.assertTrue(os.path.isfile(settings), "the control: they are still there")

    @unittest.skipIf(WINDOWS, "the stack is controlled from WSL")
    def test_a_record_naming_another_process_is_not_its_worker(self):
        policy, _ = other_policy(self)
        with open(self.record(policy, "wsl"), "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
        self.assertEqual(stack.mechanics(policy, "wsl", "status")[1], "stopped",
                         "a reused pid is never taken for the worker")
        self.assertTrue(stack.mechanics(policy, "wsl", "stop")[0])
        self.assertTrue(os.path.exists("/proc/%d" % os.getpid()), "and a stop never signals it")

    def test_a_second_worker_stops_at_the_port_the_first_holds_and_leaves_its_record(self):
        """A second worker of one policy never takes the first one's place: it stops at the terminal port
        the first holds, before it writes a record of its own, so the first one's stays as it was."""
        policy, path = other_policy(self)
        target = "windows" if WINDOWS else "wsl"
        record = self.record(policy, target)
        with open(record, "w", encoding="utf-8") as fh:
            fh.write("4242")
        temp = tempfile.mkdtemp(prefix="orch-second-")
        self.addCleanup(shutil.rmtree, temp, True)
        with socket.socket() as first:
            first.bind(("127.0.0.1", policy["targets"][target]["terminal_port"]))
            first.listen()
            # Its own temporary folder, for the sweep it makes as it starts; no Temporal, were it to get there.
            done = subprocess.run([sys.executable, "-m", "app.interfaces.worker", target], cwd=PKG,
                                  env=dict(os.environ, ORCH_POLICY=path, TMPDIR=temp, TMP=temp, TEMP=temp,
                                           TEMPORAL_ADDRESS="127.0.0.1:9"),
                                  capture_output=True, text=True, timeout=120)
        self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("not reachable", done.stdout + done.stderr, "it stopped at the port, before Temporal")
        with open(record, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "4242", "the first one's record is as it was")

    def test_a_sweep_takes_what_the_worker_it_names_left_though_its_pid_is_now_another_process(self):
        """The pid the owner proved gone reaches the sweep through the host's own script: a stage's settings
        under that pid are taken though the pid now runs something else — here this test — and without it
        they are not."""
        policy, _ = other_policy(self)
        target = "windows" if WINDOWS else "wsl"
        # Where each host's sweep looks: the worker's temporary folder, pinned to /tmp on WSL.
        folder = os.path.join(tempfile.gettempdir() if WINDOWS else "/tmp",
                              "orch-claude-settings-%d-reused" % os.getpid())
        os.makedirs(folder)
        self.addCleanup(shutil.rmtree, folder, True)
        with open(os.path.join(folder, "settings.json"), "w", encoding="utf-8") as fh:
            fh.write("{}")

        def sweep(*gone):
            if WINDOWS:
                code, said = self.windows("sweep", stack.worker_name(policy, target), *gone)
                return code == 0, said
            return stack.mechanics(policy, target, "sweep", *gone)
        done, said = sweep()
        self.assertTrue(done, said)
        self.assertTrue(os.path.isdir(folder), "the control: unnamed, a live pid's settings stay")
        done, said = sweep(str(os.getpid()))
        self.assertTrue(done, said)
        self.assertFalse(os.path.exists(folder), "named, they go: %s" % said)

    @staticmethod
    def first(done):
        """A status's own word: an elevated shell adds a line saying a start from it would be refused."""
        code, said = done
        return code, said.splitlines()[0] if said else said

    def windows(self, action, name, *more):
        done = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                               os.path.join(PKG, "workers.ps1"), action, name] + list(more),
                              capture_output=True, text=True, timeout=300)
        return done.returncode, done.stdout.strip()

    @unittest.skipUnless(WINDOWS, "the Windows worker's own mechanics")
    def test_the_windows_worker_is_known_by_its_command_line_and_its_stages_settings_go_once_it_is_gone(self):
        policy, path = other_policy(self)
        self.record(policy, "windows")
        name = stack.worker_name(policy, "windows")
        worker, pid, settings = self.stand_in(path, "windows")
        self.assertEqual(self.first(self.windows("status", name)), (0, "running %d" % pid))
        self.assertEqual(self.windows("stop", name), (0, "stopped"))
        self.assertIsNotNone(worker.wait(30), "the worker is gone")
        self.assertTrue(os.path.isfile(settings), "the control: a killed stage leaves its settings")
        # Named, as the owner names the worker it proved gone: its pid may already be another process's.
        code, said = self.windows("sweep", name, str(pid))
        self.assertEqual(code, 0, said)
        self.assertIn(os.path.dirname(settings), said)
        self.assertFalse(os.path.exists(os.path.dirname(settings)), "the sweep took them, key and all")

    @unittest.skipUnless(WINDOWS, "the Windows worker's own mechanics")
    def test_a_windows_sweep_that_cannot_take_what_its_stages_left_fails_and_names_it(self):
        """Through `workers.ps1`: a stage's settings still held open after its worker is gone fail the sweep,
        which the stack then reports; once let go, the sweep takes them."""
        policy, path = other_policy(self)
        self.record(policy, "windows")
        name = stack.worker_name(policy, "windows")
        worker, pid, settings = self.stand_in(path, "windows")
        self.assertEqual(self.windows("stop", name), (0, "stopped"))
        self.assertIsNotNone(worker.wait(30), "the worker is gone")
        held = open(settings, "a", encoding="utf-8")
        code, said = self.windows("sweep", name, str(pid))
        held.close()
        self.assertNotEqual(code, 0, said)
        self.assertIn("could not remove the settings a dead worker's stage left: %s" % os.path.dirname(settings), said)
        code, said = self.windows("sweep", name, str(pid))
        self.assertEqual(code, 0, said)
        self.assertFalse(os.path.exists(os.path.dirname(settings)), "let go, they went")

    @unittest.skipUnless(WINDOWS, "the Windows worker's own mechanics")
    def test_a_windows_record_naming_another_process_is_not_its_worker(self):
        policy, _ = other_policy(self)
        with open(self.record(policy, "windows"), "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
        name = stack.worker_name(policy, "windows")
        self.assertEqual(self.first(self.windows("status", name)), (0, "stopped"),
                         "a reused pid is never taken for the worker")
        self.assertEqual(self.windows("stop", name), (0, "stopped"), "and a stop never ends it")


if __name__ == "__main__":
    unittest.main()
