"""The workbench: its API over real runs on Temporal's test server, and who may use it.

The page's own behavior in a browser is proven by the browser acceptance, not here.
"""
import asyncio
import datetime
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse

# The suite's own folder, reached from this concern's folder inside it, and the
# checkout above both: the shared harness and the fixtures live at the suite root.
HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

from temporalio.service import RPCError, RPCStatusCode  # noqa: E402

from app.application import client as runs  # noqa: E402
from app.application import stack  # noqa: E402
from app.orchestration import workflow as WF  # noqa: E402
import temporal_env as E  # noqa: E402
from app.agents import terminal  # noqa: E402
from app.interfaces.workbench import server as workbench  # noqa: E402
from fakes import FakeWorktrees, codex_review_first, codex_review_resumed  # noqa: E402
from tests.application.test_stack import free_port, lock_of_its_own  # noqa: E402
from tests.orchestration.test_workflow import Scenario  # noqa: E402

# Picked for each process: every class of a parallel run is a process of its own, with a workbench of its own.
PORT = free_port()
# Every request reads the stack afresh, so what a test says of it is what the page sees.
workbench.READING_SECONDS = 0


def stack_as(test, down=()):
    """The stack as a test says it is: Temporal up, and each host's worker running and polling but those
    in `down`. The test server runs no worker process of the stack's to read, and the stack's lock is
    the test's own."""
    mechanics, pollers = stack.mechanics, runs.pollers
    lock_of_its_own(test)

    def read(policy, component, action, *more):
        assert action == "status", "a test of the page never starts or stops a real process: %s" % action
        return True, "stopped" if component in down else "running 4242"

    async def polls(client, name, kind):
        # Polling now, whenever the page asks: the reading judges a poll by its age on the wall clock.
        return [] if runs.host_of(name) in down else [
            {"identity": "4242@test", "polled": datetime.datetime.now(datetime.timezone.utc)}]
    stack.mechanics, runs.pollers = read, polls
    test.addCleanup(setattr, stack, "mechanics", mechanics)
    test.addCleanup(setattr, runs, "pollers", pollers)


class Server:
    """One workbench per test process, over the test server's client."""
    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            policy = dict(E.POLICY, workbench_port=PORT)
            server = workbench.serve(policy, lambda work, timeout=300: E.run(work(E.client()), timeout),
                                     links=lambda trace_id: "http://langfuse.test/trace/%s" % trace_id)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            cls._instance = server
        return cls._instance


def request(method, path, body=None, token=True, host="127.0.0.1:%d" % PORT, origin=None):
    Server.get()
    connection = http.client.HTTPConnection("127.0.0.1", PORT, timeout=120)
    headers = {"Host": host}
    if token:
        headers["X-Workbench-Token"] = terminal.token() if token is True else token
    if origin:
        headers["Origin"] = origin
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    connection.request(method, path, body=data, headers=headers)
    response = connection.getresponse()
    raw = response.read()
    connection.close()
    kind = response.getheader("Content-Type") or ""
    return response.status, (json.loads(raw) if "json" in kind else raw)


class Calls(unittest.TestCase):
    """The one event loop every request's call to Temporal runs on."""

    def test_work_that_outlives_its_limit_is_cancelled_rather_than_finishing_unseen(self):
        async def connect():
            return object()
        calls = workbench.Loop(connect)
        self.addCleanup(calls.loop.call_soon_threadsafe, calls.loop.stop)
        finished = threading.Event()

        async def slow(client):
            await asyncio.sleep(1)
            finished.set()
        with self.assertRaises(TimeoutError):
            calls.call(slow, timeout=0.2)
        self.assertFalse(finished.wait(3), "the page was told it failed, so the work must not go on to finish")


class Access(unittest.TestCase):
    def test_the_api_needs_the_token_and_refuses_another_origin_or_host(self):
        self.assertEqual(request("GET", "/api/repos")[0], 200)
        self.assertEqual(request("GET", "/api/repos", token=False)[0], 403)
        self.assertEqual(request("GET", "/api/repos", token="wrong")[0], 403)
        self.assertEqual(request("POST", "/api/runs", {"task": "x"}, origin="http://evil.example")[0], 403)
        self.assertEqual(request("GET", "/", host="evil.example:%d" % PORT)[0], 403, "a rebound name is refused")
        self.assertEqual(request("POST", "/api/runs", {"task": "x"}, token=False)[0], 403)

    def test_the_page_carries_its_config_and_forbids_framing(self):
        status, page = request("GET", "/", token=False)
        self.assertEqual(status, 200)
        config = json.loads(page.split(b'<script id="config" type="application/json">')[1].split(b"</script>")[0])
        self.assertEqual(config["token"], terminal.token())
        self.assertEqual(config["terminal_ports"], {name: target["terminal_port"]
                                                    for name, target in E.POLICY["targets"].items()})
        connection = http.client.HTTPConnection("127.0.0.1", PORT)
        connection.request("GET", "/", headers={"Host": "127.0.0.1:%d" % PORT})
        response = connection.getresponse()
        response.read()
        self.assertIn("frame-ancestors 'none'", response.getheader("Content-Security-Policy"))
        for path in ("/app.js", "/style.css", "/vendor/xterm.js", "/vendor/xterm.css"):
            self.assertEqual(request("GET", path, token=False)[0], 200, path)


class Health(unittest.TestCase):
    """What the stack can do now — Temporal and each host's worker — as its one owner reads it."""

    def test_it_reports_temporal_and_each_hosts_worker_and_what_it_manages(self):
        stack_as(self, down=("windows",))
        status, health = request("GET", "/api/health")
        self.assertEqual(status, 200, health)
        self.assertEqual((health["temporal"], health["hosts"]), ("up", {"wsl": "up", "windows": "down"}))
        self.assertIn({"queue": E.WORKFLOW_QUEUE, "host": "wsl", "polled": True}, health["queues"])
        self.assertEqual({part["name"]: (part["state"], part["managed"]) for part in health["components"]},
                         {"temporal": ("up", True), "wsl": ("up", True), "windows": ("down", True)},
                         "the deployment's stack manages all three")

    def test_temporal_out_of_reach_is_reported_not_failed(self):
        stack_as(self)
        status_before = stack.status

        async def unreachable(policy, client=None, error=None):
            if client is not None:
                raise runs.Refusal("Temporal is not reachable at localhost:7233")
            return await status_before(policy, client, error)
        stack.status = unreachable
        self.addCleanup(setattr, stack, "status", status_before)
        status, health = request("GET", "/api/health")
        self.assertEqual((status, health["temporal"]), (200, "down"))
        self.assertIn("not reachable", health["error"])
        self.assertEqual(health["hosts"], {"wsl": "unknown", "windows": "unknown"})
        self.assertEqual([part["state"] for part in health["components"][1:]], ["running", "running"],
                         "the workers' processes are still read, though whether they poll cannot be")


class StackControl(unittest.TestCase):
    """The page's stack controls reach the stack's one owner, and nothing else."""

    def test_an_action_goes_to_the_owner_and_answers_with_what_each_part_came_to(self):
        stack_as(self)
        asked = []

        def stop(policy, component=None, progress=None):
            asked.append(component)
            return [{"component": component, "ok": True, "said": "stopped"}]
        self.addCleanup(setattr, stack, "ACTIONS", stack.ACTIONS)
        stack.ACTIONS = dict(stack.ACTIONS, stop=stop)
        status, body = request("POST", "/api/stack", {"action": "stop", "component": "windows"})
        self.assertEqual(status, 200, body)
        self.assertEqual((asked, body["results"][0]["said"]), (["windows"], "stopped"))
        self.assertEqual([part["name"] for part in body["health"]["components"]], ["temporal", "wsl", "windows"],
                         "with the stack's reading after it")

    def test_the_whole_stack_as_the_page_asks_for_it_reaches_the_owner_as_every_part(self):
        """The page's whole-stack buttons name no part — `component` null — which reaches the owner as the
        whole stack, as a request naming none does."""
        stack_as(self)
        asked = []

        def stop(policy, component=None, progress=None):
            asked.append(component)
            return [{"component": part, "ok": True, "said": "stopped"} for part in ("wsl", "windows", "temporal")]
        self.addCleanup(setattr, stack, "ACTIONS", stack.ACTIONS)
        stack.ACTIONS = dict(stack.ACTIONS, stop=stop)
        status, body = request("POST", "/api/stack", {"action": "stop", "component": None})
        self.assertEqual((status, asked), (200, [None]), body)

    def test_what_the_owner_does_not_do_is_refused(self):
        self.assertEqual(request("POST", "/api/stack", {"action": "delete"})[0], 400)
        self.assertEqual(request("POST", "/api/stack", {"action": "start", "component": "workbench"})[0], 400,
                         "the Workbench never manages its own process")
        self.assertEqual(request("POST", "/api/stack", {"action": "stop"}, token=False)[0], 403)

    def test_the_page_shares_one_reading_until_a_stack_action_drops_it(self):
        """The page asks three ways every few seconds, and a Windows worker's process takes half a
        second to read; after an action the page must never be shown the reading from before it."""
        stack_as(self)
        reads = []
        read = stack.mechanics

        def counted(policy, component, action, *more):
            reads.append(component)
            return read(policy, component, action, *more)
        stack.mechanics = counted
        self.addCleanup(setattr, workbench, "READING_SECONDS", workbench.READING_SECONDS)
        workbench.READING_SECONDS = 600
        self.addCleanup(setattr, stack, "ACTIONS", stack.ACTIONS)
        stack.ACTIONS = dict(stack.ACTIONS, restart=lambda policy, component=None, progress=None: [])
        request("POST", "/api/stack", {"action": "restart", "component": "wsl"})    # starts from a fresh reading
        before = len(reads)
        request("GET", "/api/health")
        request("GET", "/api/health")
        self.assertEqual(len(reads), before, "the requests of the window share the reading")
        request("POST", "/api/stack", {"action": "restart", "component": "wsl"})
        self.assertGreater(len(reads), before, "a stack action reads the stack afresh")

    def test_a_second_action_while_one_runs_is_refused_as_busy(self):
        stack_as(self)
        with stack._exclusive():
            status, body = request("POST", "/api/stack", {"action": "restart", "component": "wsl"})
        self.assertEqual(status, 409, body)


class Listing(unittest.TestCase):
    """The run list: what the operator must be able to reach, whatever else Temporal still holds."""

    class Execution:
        def __init__(self, number, running):
            self.id = "run-%02d" % number
            self.status = type("Status", (), {"name": "RUNNING" if running else "COMPLETED"})()
            self.start_time = datetime.datetime(2026, 1, 1) + datetime.timedelta(number)
            self.close_time = None if running else self.start_time
            self.task_queue = "orchestration"

    class Page:
        """One page of Temporal's listing, with the token that reads the page after it."""

        def __init__(self, items, token):
            self.items, self.next_page_token = items, token

        def __aiter__(self):
            async def listing():
                for item in self.items:
                    yield item
            return listing()

    class Client:
        """Stands in for Temporal's listing: newest first, paged, and a status filter as the server's."""

        def __init__(self, executions):
            self.executions = executions

        def list_workflows(self, query, page_size=None, next_page_token=None):
            open_only = "ExecutionStatus = 'Running'" in query
            closed_only = "ExecutionStatus != 'Running'" in query
            wanted = [execution for execution in self.executions
                      if not ((open_only and execution.status.name != "RUNNING")
                              or (closed_only and execution.status.name == "RUNNING"))]
            start = int(next_page_token) if next_page_token else 0
            items = wanted[start:start + (page_size or len(wanted))]
            end = start + len(items)
            return Listing.Page(items, str(end).encode() if end < len(wanted) else None)

    def test_a_waiting_run_is_never_dropped_and_the_older_ones_are_a_page_away(self):
        waiting = self.Execution(0, running=True)                       # the oldest run, still open
        newer = [self.Execution(number, running=False) for number in range(9, 0, -1)]
        client = self.Client(newer + [waiting])
        listed, cursor = asyncio.run(runs.runs(client, limit=3))
        self.assertEqual([run["run_id"] for run in listed][:3], ["run-09", "run-08", "run-07"],
                         "the finished runs are the newest ones, up to the limit")
        self.assertIn(waiting.id, [run["run_id"] for run in listed],
                      "an open run the operator may have to answer is listed however old it is")
        self.assertIsNotNone(cursor, "and the runs behind the limit are not lost, only a page away")
        older, after = asyncio.run(runs.runs(client, limit=3, cursor=cursor))
        self.assertEqual([run["run_id"] for run in older], ["run-06", "run-05", "run-04"])
        self.assertNotIn(waiting.id, [run["run_id"] for run in older], "open runs stay in the first page")
        self.assertIsNotNone(after)
        last, ended = asyncio.run(runs.runs(client, limit=30, cursor=after))
        self.assertEqual([run["run_id"] for run in last], ["run-03", "run-02", "run-01"])
        self.assertIsNone(ended, "the end of the history ends the listing")
        # One page owns each run: an open run listed first must not come round again as an older one,
        # where it would be cached and left showing a state it has since left.
        seen = [run["run_id"] for page in (listed, older, last) for run in page]
        self.assertEqual(len(seen), len(set(seen)), "no run is in two pages")
        self.assertEqual(sorted(seen), sorted(run.id for run in newer + [waiting]), "and none is missing")


class View(unittest.TestCase):
    """What a run is now, read from the facts the workflow and Temporal hold."""

    READING = {"hosts": {"wsl": "down", "windows": "up"},
               "queues": [{"queue": "orchestration", "host": "wsl"}, {"queue": "target:wsl:local", "host": "wsl"},
                          {"queue": "target:windows:local", "host": "windows"}]}

    def listed(self, queue="orchestration", execution="RUNNING"):
        return {"run_id": "r", "execution": execution, "started": None, "closed": None, "task_queue": queue}

    def test_a_run_that_is_stopping_says_so_and_takes_no_answer(self):
        status = {"state": {"status": "STOPPING", "current": {"stage": "merge", "role": None, "since": "t"}},
                  "stop": None, "queue": "target:wsl:host"}
        view = runs.view(self.listed(), status, {"hosts": {"wsl": "up"}, "queues": []})
        self.assertEqual((view["state"], view["stage"], view["actions"]), ("stopping", "merge", []))

    def test_a_failed_stage_says_its_failure_and_takes_continue(self):
        status = {"state": {}, "queue": "target:wsl:local",
                  "stop": {"id": "r:3", "reason": "failed", "feedback": "agent_exit: plan failed rc=1\nsee its logs",
                           "hint": "fix the cause, then continue", "phase": "plan", "todo": None,
                           "actions": ["continue"], "since": "t"}}
        view = runs.view(self.listed(), status, {"hosts": {"wsl": "up"}, "queues": []})
        self.assertEqual((view["state"], view["failure"], view["actions"]),
                         ("failed", "agent_exit: plan failed rc=1\nsee its logs", ["continue"]))

    def test_a_run_is_blocked_by_the_down_worker_of_a_queue_it_needs(self):
        status = {"state": {}, "stop": None, "queue": "target:windows:local"}
        self.assertEqual(runs.view(self.listed(), status, self.READING)["blocked_by"], ["wsl"],
                         "the WSL worker runs its workflow, and is down; the Windows one it also needs is up")

    def test_a_run_is_blocked_by_its_target_hosts_worker_alone_and_a_run_elsewhere_is_not(self):
        """The workflow worker up and the Windows one down: a Windows run is blocked by it, and a WSL run is
        not — a WSL run never waits on the Windows worker."""
        reading = dict(self.READING, hosts={"wsl": "up", "windows": "down"})
        on_windows = {"state": {}, "stop": None, "queue": "target:windows:local"}
        on_wsl = {"state": {}, "stop": None, "queue": "target:wsl:local"}
        self.assertEqual(runs.view(self.listed(), on_windows, reading)["blocked_by"], ["windows"])
        self.assertEqual(runs.view(self.listed(), on_wsl, reading)["blocked_by"], [])

    def test_a_run_whose_status_cannot_be_read_is_blocked_by_the_worker_its_listing_names(self):
        self.assertEqual(runs.view(self.listed(), None, self.READING)["blocked_by"], ["wsl"],
                         "a query needs the workflow worker; the listing still says which queue it runs on")

    def test_a_run_on_another_stacks_queues_is_not_this_readings_to_judge(self):
        status = {"state": {}, "stop": None, "queue": "target:wsl:demo1"}
        self.assertEqual(runs.view(self.listed("orchestration:demo1"), status, self.READING)["blocked_by"], [],
                         "a demo's run shown here offers no start of this stack's worker")


@unittest.skipIf(sys.platform.startswith("win"), "the workbench runs on WSL, where repos.json's paths are")
class Kept(unittest.TestCase):
    """What a closed run kept, as the one rule the page, the worktree view and the removal read says."""

    @staticmethod
    def listed(execution="CANCELED"):
        return {"run_id": "r1", "execution": execution}

    @staticmethod
    def status(**state):
        return {"state": dict({"worktree_path": "/fake/worktree/r1"}, **state)}

    def test_only_a_closed_run_that_made_a_worktree_it_neither_merged_nor_removed_keeps_one(self):
        self.assertIsNone(runs.not_kept(self.listed(), self.status(status="STOPPED")))
        self.assertIsNone(runs.not_kept(self.listed("TERMINATED"), self.status(status="READY_FOR_HUMAN")))
        self.assertIsNone(runs.not_kept(self.listed(), self.status(status="STOPPED"), "FAILED"),
                          "a removal git refused leaves the work where it was")
        self.assertIn("still open", runs.not_kept(self.listed("RUNNING"), None))
        for status in ("MERGED", "DISCARDED"):
            self.assertIn("nothing of it was kept", runs.not_kept(self.listed(), self.status(status=status)))
        self.assertIn("never made a worktree", runs.not_kept(self.listed(), {"state": {"status": "STOPPED"}}))
        self.assertIn("removed already", runs.not_kept(self.listed(), self.status(status="STOPPED"), "COMPLETED"))


class Runs(Scenario):
    """A run seen, reviewed and answered through the workbench, exactly as the workflow allows."""

    def setUp(self):
        # The test server has no poller descriptions to check; the preflight is the CLI's concern.
        saved = self.preflight = runs.preflight

        async def no_preflight(client, needed):
            return None
        runs.preflight = no_preflight
        self.addCleanup(setattr, runs, "preflight", saved)
        self.workers_down()
        # The page reads a change by awaiting a workflow's result, and on the time-skipping server
        # that lets time jump to the next timer — for a run parked at a gate, the test server's
        # default ten-year run timeout, which closes the run under the test. A person answers a gate
        # in real time, so these scenarios run in it.
        skipping = E.env().auto_time_skipping_disabled()
        skipping.__enter__()
        self.addCleanup(skipping.__exit__, None, None, None)
        # A repository of this test's own, on a path this host runs: where the checkout happens to
        # live must not decide which worker the page's run waits for.
        self.repo = tempfile.mkdtemp(prefix="orch-page-")
        self.addCleanup(shutil.rmtree, self.repo, True)

    def workers_down(self, *hosts):
        """Which hosts' workers read as down."""
        stack_as(self, down=hosts)

    def start(self, task):
        status, started = request("POST", "/api/runs", {"task": task, "repo": self.repo})
        self.assertEqual(status, 200, started)
        run_id = started["run_id"]
        self.addCleanup(lambda: E.Run.cleanup(type("R", (), {"run_id": run_id})()))
        return run_id

    def test_a_waiting_run_says_what_it_waits_at_since_when_and_what_it_takes(self):
        a1, _ = codex_review_first("PASS", "Direction: A.")
        self.host, self.agent = E.host([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1)], git=FakeWorktrees())
        run_id = self.start("a run that waits")
        view = self.wait_for(run_id, lambda body: body["stop"] and body["stop"]["reason"] == "approval")["view"]
        self.assertEqual((view["state"], view["goal"], view["host"]), ("waiting", "a run that waits", "wsl"))
        self.assertEqual(view["stop"]["reason"], "approval")
        self.assertEqual(view["actions"], ["approve", "revise"])
        self.assertTrue(datetime.datetime.fromisoformat(view["since"]), "since when it waits")
        self.assertEqual(view["blocked_by"], [])
        self.assertTrue(view["worktree"], "where its work is")

    def test_a_working_run_says_its_stage_its_role_and_since_when(self):
        release = threading.Event()
        self.addCleanup(release.set)
        self.host, self.agent = E.host([], git=FakeWorktrees())

        def working(worktree, argv, rdir, name, prompt, timeout, env, *, brain):
            release.wait(60)
            return 1, ""
        self.host.runner = working
        run_id = self.start("a run at work")
        # Ended before its agent is released, so its stage can never run on a later test's fakes.
        self.addCleanup(lambda: E.run(E.client().get_workflow_handle(run_id).terminate("the test is over")))
        view = self.wait_for(run_id, lambda body: body["view"]["stage"] == "plan")["view"]
        self.assertEqual((view["state"], view["stage"], view["role"]), ("running", "plan", "engineer"))
        self.assertTrue(datetime.datetime.fromisoformat(view["since"]), "since when it works")
        self.assertEqual(view["actions"], [], "nothing to answer while it works")

    def test_a_run_whose_hosts_worker_is_down_says_which(self):
        a1, _ = codex_review_first("PASS", "Direction: A.")
        self.host, self.agent = E.host([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1)], git=FakeWorktrees())
        run_id = self.start("a run on a host with no worker")
        self.wait_for(run_id, lambda body: body["stop"] and body["stop"]["reason"] == "approval")
        self.workers_down("wsl")
        view = request("GET", "/api/runs/%s" % run_id)[1]["view"]
        self.assertEqual(view["blocked_by"], ["wsl"])

    def test_a_run_whose_workflow_worker_is_down_is_still_shown_blocked_by_it(self):
        """Its status is a query only its workflow worker answers, and with none it waits: the page asks for a
        moment at most, then shows the run from its listing."""
        a1, _ = codex_review_first("PASS", "Direction: A.")
        self.host, self.agent = E.host([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1)], git=FakeWorktrees())
        run_id = self.start("a run whose worker goes down")
        self.wait_for(run_id, lambda body: body["stop"] and body["stop"]["reason"] == "approval")
        self.workers_down("wsl")
        saved = runs.status

        bounds = []

        async def unanswered(client, run_id, timeout=None):
            bounds.append(timeout)
            await asyncio.sleep(timeout.total_seconds() if timeout else 3600)
            raise RuntimeError("no worker polls its workflow queue")
        runs.status = unanswered
        self.addCleanup(setattr, runs, "status", saved)
        began = time.monotonic()
        status, body = request("GET", "/api/runs/%s" % run_id)
        self.assertEqual(status, 200, body)
        self.assertLess(time.monotonic() - began, 15, "a moment for its status, not the page's minutes")
        self.assertEqual(bounds, [workbench.STATUS_SECONDS])
        self.assertIn("cannot be read", body["unreadable"])
        self.assertEqual(body["view"]["blocked_by"], ["wsl"], "blocked by the worker its listing says it runs on")
        self.assertEqual(request("GET", "/api/runs/no-such-run")[0], 404, "a run Temporal does not hold is still none")

    def wait_for(self, run_id, check, seconds=120):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            status, body = request("GET", "/api/runs/%s" % run_id)
            if status == 200 and check(body):
                return body
            time.sleep(0.5)
        self.fail("run %s never reached the expected state" % run_id)

    def test_start_list_review_and_answer_a_run(self):
        a1, _ = codex_review_first("PASS", "Direction: A.")
        git = FakeWorktrees()
        self.host, self.agent = E.host([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1),
                                        ("build-e2-1", 0, "built\n"), ("verify-e2-1", 0, codex_review_resumed("PASS"))],
                                       git=git)
        self.assertEqual(request("POST", "/api/runs", {"task": ""})[0], 400)
        status, started = request("POST", "/api/runs", {"task": "a workbench run", "repo": self.repo})
        self.assertEqual(status, 200, started)
        run_id = started["run_id"]
        self.addCleanup(lambda: E.Run.cleanup(type("R", (), {"run_id": run_id})()))

        body = self.wait_for(run_id, lambda body: body["stop"] and body["stop"]["reason"] == "approval")
        self.assertEqual(body["links"]["temporal"].rsplit("/", 1)[1], run_id)
        # The time-skipping server implements no listing; what is listed is Temporal's, what is shown is ours.
        saved_runs = runs.runs

        async def listing(client, limit=200, cursor=None):
            return ([{"run_id": run_id, "execution": "RUNNING", "started": "2026-09-17T10:00:00",
                      "closed": None}], None)
        runs.runs = listing
        self.addCleanup(setattr, runs, "runs", saved_runs)
        page = request("GET", "/api/runs")[1]
        self.assertIsNone(page["cursor"], "no older page when the listing ended")
        listed = [run for run in page["runs"] if run["run_id"] == run_id]
        self.assertEqual((listed[0]["state"], listed[0]["stop"]["reason"]), ("waiting", "approval"))
        self.assertEqual(listed[0]["goal"], "a workbench run")

        approval = body["stop"]["id"]
        self.assertEqual(request("POST", "/api/runs/%s/answer" % run_id, {"stop": approval, "action": "merge"})[0], 422,
                         "an answer the stop does not offer is the workflow's refusal")
        self.assertEqual(request("POST", "/api/runs/%s/answer" % run_id, {"action": "approve"})[0], 400)
        status, answered = request("POST", "/api/runs/%s/answer" % run_id, {"stop": approval, "action": "approve"})
        self.assertEqual((status, answered["answered"]), (200, approval))

        body = self.wait_for(run_id, lambda body: body["stop"] and body["stop"]["reason"] == "final")
        self.assertEqual(request("POST", "/api/runs/%s/answer" % run_id, {"stop": approval, "action": "approve"})[0],
                         409, "an answer for a stop the run has left is refused")
        self.assertEqual([verdict["verdict"] for verdict in body["timeline"] if verdict.get("verdict")], ["PASS", "PASS"])

        status, diff = request("GET", "/api/runs/%s/diff" % run_id)
        self.assertEqual((status, diff["base"], diff["offset"]), (200, "abc1234", 0))
        self.assertEqual((diff["total"], diff["next"]), (len(diff["patch"]), len(diff["patch"])),
                         "a change read whole says so")
        self.assertIn(("review_diff", "/fake/worktree/%s" % run_id, 0), git.calls)
        status, part = request("GET", "/api/runs/%s/diff?offset=5" % run_id)
        self.assertEqual((status, part["offset"]), (200, 5), "the rest of a change too large for one payload")
        self.assertEqual(request("GET", "/api/runs/%s/diff?offset=x" % run_id)[0], 400)

        status, view = request("GET", "/api/worktrees?repo=" + urllib.parse.quote(self.repo))
        self.assertEqual(status, 200, view)
        self.assertEqual([(row["branch"], row["state"]) for row in view["rows"]],
                         [("one", "unmerged"), ("two", "merged")], "D2: the worktrees and their merge state")
        self.assertEqual(view["base_branch"], "develop")

        described = E.run(E.client().get_workflow_handle(run_id).describe())
        self.assertEqual(described.status.name, "RUNNING", "reading the change left the run at its gate")
        final = body["stop"]["id"]
        self.assertEqual(request("POST", "/api/runs/%s/answer" % run_id,
                                 {"stop": final, "action": "discard", "confirm": False})[0], 422)
        # As the page sends it: the action the stop published, and no words when none were written.
        status, refused = request("POST", "/api/runs/%s/answer" % run_id, {"stop": final, "action": "revise:architect"})
        self.assertEqual(status, 422, refused)
        self.assertIn("needs the feedback", refused["error"], "the role-named action reached the workflow's check")
        status, _ = request("POST", "/api/runs/%s/answer" % run_id, {"stop": final, "action": "merge", "text": "merge"})
        self.assertEqual(status, 200)
        closed = self.wait_for(run_id, lambda body: body["state"]["status"] == "MERGED")
        self.assertEqual((closed["view"]["state"], closed["view"]["status"]), ("closed", "MERGED"))
        self.assertEqual(request("GET", "/api/runs/no-such-run")[0], 404)

    def test_the_operators_words_reach_the_role_they_are_for(self):
        """A revise sent as the page sends it — the action, with the note typed beside it — reaches the
        engineer's next plan, word for word."""
        a1, _ = codex_review_first("PASS", "Direction: A.")
        a2, _ = codex_review_first("PASS", "Direction: B.")
        self.host, self.agent = E.host([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1),
                                        ("plan-e2-1", 0, "planned again\n"), ("assess-e2-1", 0, a2)],
                                       git=FakeWorktrees())
        run_id = self.start("a run whose plan is sent back with words")
        stop = self.wait_for(run_id, lambda body: body["stop"] and body["stop"]["reason"] == "approval")["stop"]
        status, body = request("POST", "/api/runs/%s/answer" % run_id,
                               {"stop": stop["id"], "action": "revise", "text": "split the change in two"})
        self.assertEqual(status, 200, body)
        self.wait_for(run_id, lambda body: body["stop"] and body["stop"]["id"] != stop["id"])
        replanned = [call for call in self.agent.calls if call["name"] == "plan-e2-1"]
        self.assertEqual(len(replanned), 1, [call["name"] for call in self.agent.calls])
        self.assertIn("split the change in two", replanned[0]["prompt"])

    def test_stop_ends_a_run_and_a_closed_run_refuses_it(self):
        a1, _ = codex_review_first("PASS", "Direction: A.")
        git = FakeWorktrees()
        self.host, self.agent = E.host([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1)], git=git)
        run_id = self.start("a run to stop")
        self.wait_for(run_id, lambda body: body["stop"] and body["stop"]["reason"] == "approval")
        status, body = request("POST", "/api/runs/%s/stop" % run_id, {})
        self.assertEqual(status, 200, body)
        closed = self.wait_for(run_id, lambda body: body["view"]["state"] == "closed")["view"]
        self.assertEqual((closed["status"], closed["execution"]), ("STOPPED", "CANCELED"))
        self.assertEqual([call[0] for call in git.calls], ["create"], "a Stop runs no git")
        status, body = request("POST", "/api/runs/%s/stop" % run_id, {})
        self.assertEqual(status, 409, body)

    def test_force_terminate_asks_for_its_confirmation_and_ends_a_run_at_once(self):
        release = threading.Event()
        self.addCleanup(release.set)
        self.host, self.agent = E.host([], git=FakeWorktrees())

        def working(worktree, argv, rdir, name, prompt, timeout, env, *, brain):
            release.wait(60)
            return 1, ""
        self.host.runner = working
        run_id = self.start("a run to terminate")
        self.wait_for(run_id, lambda body: body["view"]["stage"] == "plan")
        status, body = request("POST", "/api/runs/%s/terminate" % run_id, {})
        self.assertEqual(status, 400, body)
        self.assertIn("confirm", body["error"])
        self.assertEqual(E.run(E.client().get_workflow_handle(run_id).describe()).status.name, "RUNNING",
                         "unconfirmed, nothing happened")
        status, body = request("POST", "/api/runs/%s/terminate" % run_id, {"confirm": True})
        self.assertEqual(status, 200, body)
        self.assertEqual(E.run(E.client().get_workflow_handle(run_id).describe()).status.name, "TERMINATED")
        status, body = request("POST", "/api/runs/%s/terminate" % run_id, {"confirm": True})
        self.assertEqual(status, 409, body)

    def test_what_a_stopped_run_kept_is_listed_and_removed_through_its_hosts_git_once_confirmed(self):
        a1, _ = codex_review_first("PASS", "Direction: A.")

        class Kept(FakeWorktrees):
            rows = []

            def view(self, repo, base):
                return self.rows
        git = Kept()
        self.host, self.agent = E.host([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1)], git=git)
        run_id = self.start("a run whose work is kept")
        self.wait_for(run_id, lambda body: body["stop"] and body["stop"]["reason"] == "approval")
        git.rows = [{"path": "/fake/worktree/%s" % run_id, "branch": run_id, "state": "unmerged"},
                    {"path": "/fake/repo", "branch": "develop", "state": "base"}]
        rows = request("GET", "/api/worktrees?repo=" + urllib.parse.quote(self.repo))[1]["rows"]
        self.assertEqual([(row["run"], row["removable"]) for row in rows], [("RUNNING", False), (None, False)],
                         "an open run's worktree is its own")
        status, refused = request("POST", "/api/runs/%s/remove" % run_id, {"confirm": True})
        self.assertEqual(status, 400, refused)
        self.assertIn("stop it first", refused["error"])

        self.assertEqual(request("POST", "/api/runs/%s/stop" % run_id, {})[0], 200)
        self.wait_for(run_id, lambda body: body["view"]["state"] == "closed")
        rows = request("GET", "/api/worktrees?repo=" + urllib.parse.quote(self.repo))[1]["rows"]
        self.assertEqual([(row["run"], row["removable"]) for row in rows], [("CANCELED", True), (None, False)])
        bounds, saved = [], runs.status

        async def unanswered(client, run_id, timeout=None):
            bounds.append(timeout)
            await asyncio.sleep(timeout.total_seconds() if timeout else 3600)
            raise RuntimeError("no worker polls its workflow queue")
        runs.status = unanswered
        try:
            began = time.monotonic()
            rows = request("GET", "/api/worktrees?repo=" + urllib.parse.quote(self.repo))[1]["rows"]
        finally:
            runs.status = saved
        self.assertLess(time.monotonic() - began, 15, "a moment for its status, not the page's minutes")
        self.assertEqual((bounds, rows[0]["removable"]), ([workbench.STATUS_SECONDS], False),
                         "a status not read in time is not removable")
        self.assertEqual(request("POST", "/api/runs/%s/remove" % run_id, {})[0], 400, "unconfirmed")
        self.assertNotIn("discard", [call[0] for call in git.calls], "nothing was removed unconfirmed")
        status, body = request("POST", "/api/runs/%s/remove" % run_id, {"confirm": True})
        self.assertEqual((status, body), (200, {"removed": run_id}))
        self.assertEqual([call for call in git.calls if call[0] == "discard"], [("discard", run_id)],
                         "removed once, by its host's git, as a discard removes it")

    def test_a_removal_its_hosts_git_refuses_says_why_and_runs_again_only_when_asked_again(self):
        a1, _ = codex_review_first("PASS", "Direction: A.")

        class Locked(FakeWorktrees):
            refusals = ["fatal: '/fake/worktree' is locked, use 'git worktree unlock' first"]

            def discard(self, repo, worktree, run_id):
                super().discard(repo, worktree, run_id)
                if self.refusals:
                    raise RuntimeError(self.refusals.pop(0))
        git = Locked()
        self.host, self.agent = E.host([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1)], git=git)
        run_id = self.start("a run whose removal git refuses")
        self.wait_for(run_id, lambda body: body["stop"] and body["stop"]["reason"] == "approval")
        self.assertEqual(request("POST", "/api/runs/%s/stop" % run_id, {})[0], 200)
        self.wait_for(run_id, lambda body: body["view"]["state"] == "closed")

        def discards():
            return [call for call in git.calls if call[0] == "discard"]
        status, body = request("POST", "/api/runs/%s/remove" % run_id, {"confirm": True})
        self.assertEqual(status, 400, body)
        self.assertIn("is locked", body["error"], "git's own word on why")
        self.assertEqual(len(discards()), 1, "tried once, never again by itself")
        self.assertTrue(request("GET", "/api/runs/%s" % run_id)[1]["view"]["kept"], "and it is still there to remove")
        self.assertEqual(request("POST", "/api/runs/%s/remove" % run_id, {"confirm": True}), (200, {"removed": run_id}))
        self.assertFalse(request("GET", "/api/runs/%s" % run_id)[1]["view"]["kept"])
        status, body = request("POST", "/api/runs/%s/remove" % run_id, {"confirm": True})
        self.assertEqual(status, 400, body)
        self.assertIn("removed already", body["error"])
        self.assertEqual(len(discards()), 2)

    def test_a_second_removal_while_one_runs_is_refused(self):
        a1, _ = codex_review_first("PASS", "Direction: A.")
        discarding, let_go = threading.Event(), threading.Event()
        self.addCleanup(let_go.set)

        class Slow(FakeWorktrees):
            def discard(self, repo, worktree, run_id):
                super().discard(repo, worktree, run_id)
                discarding.set()
                let_go.wait(60)
        git = Slow()
        self.host, self.agent = E.host([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1)], git=git)
        run_id = self.start("a run removed twice at once")
        self.wait_for(run_id, lambda body: body["stop"] and body["stop"]["reason"] == "approval")
        self.assertEqual(request("POST", "/api/runs/%s/stop" % run_id, {})[0], 200)
        self.wait_for(run_id, lambda body: body["view"]["state"] == "closed")
        first = []
        pressed = threading.Thread(target=lambda: first.append(
            request("POST", "/api/runs/%s/remove" % run_id, {"confirm": True})))
        pressed.start()
        self.assertTrue(discarding.wait(30), "the first removal is under way")
        status, body = request("POST", "/api/runs/%s/remove" % run_id, {"confirm": True})
        self.assertEqual(status, 400, body)
        self.assertIn("being removed already", body["error"])
        let_go.set()
        pressed.join(60)
        self.assertEqual(first, [(200, {"removed": run_id})])
        self.assertEqual([call for call in git.calls if call[0] == "discard"], [("discard", run_id)])

    def test_an_answer_or_a_change_read_while_no_worker_can_read_the_run_is_refused_at_once(self):
        """The page keeps a stop's buttons while its run cannot be read; pressing one is refused at once,
        naming the worker, rather than waiting for a query no worker answers."""
        a1, _ = codex_review_first("PASS", "Direction: A.")
        self.host, self.agent = E.host([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1)], git=FakeWorktrees())
        run_id = self.start("a run whose worker goes down at its stop")
        stop = self.wait_for(run_id, lambda body: body["stop"] and body["stop"]["reason"] == "approval")["stop"]
        asked = []

        async def unanswered(client, run_id, timeout=None):
            asked.append(run_id)
            await asyncio.sleep(30)                 # as a query no worker answers waits
        self.addCleanup(setattr, runs, "status", runs.status)
        runs.status, runs.preflight = unanswered, self.preflight
        self.workers_down("wsl")
        began = time.monotonic()
        status, body = request("POST", "/api/runs/%s/answer" % run_id, {"stop": stop["id"], "action": "approve"})
        self.assertEqual(status, 400, body)
        self.assertIn("the wsl worker is not running", body["error"])
        status, body = request("GET", "/api/runs/%s/diff" % run_id)
        self.assertEqual(status, 400, body)
        self.assertIn("the wsl worker is not running", body["error"])
        self.assertEqual(asked, [], "its status was never asked")
        self.assertLess(time.monotonic() - began, 10)

    def test_stop_and_force_terminate_are_taken_while_no_worker_can_read_the_run(self):
        """Temporal records a Stop and a termination with no worker polling: neither waits on one, nor is
        refused for want of one."""
        a1, _ = codex_review_first("PASS", "Direction: A.")
        self.host, self.agent = E.host([("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, a1),
                                        ("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, a1)], git=FakeWorktrees())
        stopped = self.start("a run stopped while its workers are down")
        self.wait_for(stopped, lambda body: body["stop"] and body["stop"]["reason"] == "approval")
        terminated = self.start("a run terminated while its workers are down")
        self.wait_for(terminated, lambda body: body["stop"] and body["stop"]["reason"] == "approval")

        async def unanswered(client, run_id, timeout=None):
            await asyncio.sleep(30)                 # as a query no worker answers waits
        self.addCleanup(setattr, runs, "status", runs.status)
        runs.status, runs.preflight = unanswered, self.preflight
        self.workers_down("wsl", "windows")
        began = time.monotonic()
        status, body = request("POST", "/api/runs/%s/stop" % stopped, {})
        self.assertEqual((status, body), (200, {"stopping": stopped}))
        status, body = request("POST", "/api/runs/%s/terminate" % terminated, {"confirm": True})
        self.assertEqual((status, body), (200, {"terminated": terminated}))
        self.assertLess(time.monotonic() - began, 10, "neither waited on a worker")
        self.assertEqual(E.run(E.client().get_workflow_handle(terminated).describe()).status.name, "TERMINATED")
        deadline = time.monotonic() + 60
        handle = E.client().get_workflow_handle(stopped)
        while E.run(handle.describe()).close_time is None and time.monotonic() < deadline:
            time.sleep(0.2)
        self.assertEqual(E.run(handle.describe()).status.name, "CANCELED")

    def test_an_answer_whose_run_does_not_answer_in_time_is_refused_naming_its_worker(self):
        """The preflight counts a worker dead for under a minute and a half as polling: a status that does not
        come in time is refused all the same, naming that worker, never waited on for the page's minutes."""
        a1, _ = codex_review_first("PASS", "Direction: A.")
        self.host, self.agent = E.host([("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, a1)], git=FakeWorktrees())
        run_id = self.start("a run whose worker has just died")
        stop = self.wait_for(run_id, lambda body: body["stop"] and body["stop"]["reason"] == "approval")["stop"]
        bounds = []

        async def late(client, run_id, timeout=None):
            bounds.append(timeout)
            raise RPCError("deadline exceeded", RPCStatusCode.DEADLINE_EXCEEDED, b"")
        self.addCleanup(setattr, runs, "status", runs.status)
        runs.status = late
        status, body = request("POST", "/api/runs/%s/answer" % run_id, {"stop": stop["id"], "action": "approve"})
        self.assertEqual(status, 400, body)
        self.assertIn("the wsl worker may be down", body["error"])
        self.assertEqual(bounds, [runs.READ], "asked for its status once, and for a bounded time")

    def test_the_list_shows_each_run_while_its_worker_is_down_and_reads_it_again_after(self):
        """A run's status is a query only its workflow worker answers: the list waits a moment for each,
        shows the run from its listing, blocked by that worker — and once the worker is back reads it
        again: a closed run's end is never kept as unknown."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        open_run, closed_run = "listed-open-%s" % os.urandom(3).hex(), "listed-closed-%s" % os.urandom(3).hex()
        listed = [{"run_id": open_run, "execution": "RUNNING", "started": now, "closed": None,
                   "task_queue": E.WORKFLOW_QUEUE},
                  {"run_id": closed_run, "execution": "CANCELED", "started": now, "closed": now,
                   "task_queue": E.WORKFLOW_QUEUE}]

        async def listing(client, limit=200, cursor=None):
            return [dict(run) for run in listed], None

        async def unanswered(client, run_id, timeout=None):
            await asyncio.sleep(timeout.total_seconds() if timeout else 3600)
            raise RuntimeError("no worker polls its workflow queue")
        self.addCleanup(setattr, runs, "runs", runs.runs)
        self.addCleanup(setattr, runs, "status", runs.status)
        runs.runs, runs.status = listing, unanswered
        self.workers_down("wsl")
        began = time.monotonic()
        status, body = request("GET", "/api/runs")
        self.assertEqual(status, 200, body)
        self.assertLess(time.monotonic() - began, 15, "a moment for each status, not the page's minutes")
        shown = {run["run_id"]: run for run in body["runs"]}
        self.assertEqual(shown[open_run]["blocked_by"], ["wsl"], "blocked by the worker its listing names")
        self.assertEqual((shown[closed_run]["state"], shown[closed_run]["status"]), ("closed", None))

        async def answered(client, run_id, timeout=None):
            return {"state": {"status": "STOPPED", "task": "a run"}, "stop": None, "queue": None,
                    "workflow_queue": E.WORKFLOW_QUEUE}
        runs.status = answered
        self.workers_down()
        shown = {run["run_id"]: run for run in request("GET", "/api/runs")[1]["runs"]}
        self.assertEqual(shown[closed_run]["status"], "STOPPED", "read once it could be, never kept unread")

    def test_a_removal_while_no_worker_can_read_the_run_is_refused_at_once_naming_that_worker(self):
        """A closed run's status is a query only a worker of its workflow queue answers; with none polling
        it the query would wait, so the removal is refused before asking it."""
        a1, _ = codex_review_first("PASS", "Direction: A.")
        git = FakeWorktrees()
        self.host, self.agent = E.host([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1)], git=git)
        run_id = self.start("a run whose worker is down")
        self.wait_for(run_id, lambda body: body["stop"] and body["stop"]["reason"] == "approval")
        self.assertEqual(request("POST", "/api/runs/%s/stop" % run_id, {})[0], 200)
        self.wait_for(run_id, lambda body: body["view"]["state"] == "closed")
        asked = []

        async def unanswered(client, run_id, timeout=None):
            asked.append(run_id)
            await asyncio.sleep(30)                 # as a query no worker answers waits
        self.addCleanup(setattr, runs, "status", runs.status)
        runs.status, runs.preflight = unanswered, self.preflight
        self.workers_down("wsl")
        began = time.monotonic()
        status, body = request("POST", "/api/runs/%s/remove" % run_id, {"confirm": True})
        self.assertEqual(status, 400, body)
        self.assertIn("the wsl worker is not running", body["error"])
        self.assertEqual(asked, [], "its status was never asked")
        self.assertLess(time.monotonic() - began, 10)
        self.assertNotIn("discard", [call[0] for call in git.calls])

    def test_a_status_no_worker_answers_ends_at_its_bound_as_a_refusal_naming_the_worker(self):
        """Temporal's own query, not a stand-in: on a workflow queue no worker polls, a status read ends when
        its bound does and is refused naming the worker. The preflight is passed as it is by a worker dead
        for under a minute and a half."""
        run_id = "unread-%s" % os.urandom(4).hex()
        queue = "orchestration:gone-%s" % run_id
        E.run(E.client().start_workflow(WF.FeatureRun.run, {"task": "never read"}, id=run_id, task_queue=queue))
        self.addCleanup(lambda: E.run(E.client().get_workflow_handle(run_id).terminate("test over")))

        async def passes(client, needed):
            return None
        for name, stand_in in (("preflight", passes), ("READ", datetime.timedelta(seconds=2))):
            self.addCleanup(setattr, runs, name, getattr(runs, name))
            setattr(runs, name, stand_in)
        began = time.monotonic()
        with self.assertRaisesRegex(runs.Refusal, "status did not come .*: the wsl worker may be down"):
            E.run(runs.readable_status(E.client(), run_id))
        self.assertLess(time.monotonic() - began, 10, "ended at its bound")

    def test_a_removal_whose_run_does_not_answer_in_time_is_refused_naming_its_worker(self):
        """A worker dead for under a minute and a half still counts as polling: a closed run's status that does
        not come in time refuses its removal all the same, naming that worker, never waited on for minutes."""
        a1, _ = codex_review_first("PASS", "Direction: A.")
        git = FakeWorktrees()
        self.host, self.agent = E.host([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1)], git=git)
        run_id = self.start("a run whose worker has just died")
        self.wait_for(run_id, lambda body: body["stop"] and body["stop"]["reason"] == "approval")
        self.assertEqual(request("POST", "/api/runs/%s/stop" % run_id, {})[0], 200)
        self.wait_for(run_id, lambda body: body["view"]["state"] == "closed")
        bounds = []

        async def late(client, run_id, timeout=None):
            bounds.append(timeout)
            raise RPCError("deadline exceeded", RPCStatusCode.DEADLINE_EXCEEDED, b"")
        self.addCleanup(setattr, runs, "status", runs.status)
        runs.status = late
        status, body = request("POST", "/api/runs/%s/remove" % run_id, {"confirm": True})
        self.assertEqual(status, 400, body)
        self.assertIn("the wsl worker may be down", body["error"])
        self.assertEqual(bounds, [runs.READ], "asked for its status once, and for a bounded time")
        self.assertNotIn("discard", [call[0] for call in git.calls])

    def test_a_run_that_merged_kept_nothing_to_remove(self):
        a1, _ = codex_review_first("PASS", "Direction: A.")
        git = FakeWorktrees()
        self.host, self.agent = E.host([("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, a1), ("build-e2-1", 0, "b\n"),
                                        ("verify-e2-1", 0, codex_review_resumed("PASS"))], git=git)
        run_id = self.start("a run that merges")
        stop = self.wait_for(run_id, lambda body: body["stop"] and body["stop"]["reason"] == "approval")["stop"]
        request("POST", "/api/runs/%s/answer" % run_id, {"stop": stop["id"], "action": "approve"})
        stop = self.wait_for(run_id, lambda body: body["stop"] and body["stop"]["reason"] == "final")["stop"]
        request("POST", "/api/runs/%s/answer" % run_id, {"stop": stop["id"], "action": "merge"})
        self.wait_for(run_id, lambda body: body["state"]["status"] == "MERGED")
        status, body = request("POST", "/api/runs/%s/remove" % run_id, {"confirm": True})
        self.assertEqual(status, 400, body)
        self.assertIn("nothing of it was kept", body["error"])

    def test_an_answer_to_a_run_that_has_closed_is_refused_as_not_waiting(self):
        """A closed run still answers its status query with the stop it closed at, from its
        history, so the page offers the answer; the Update then finds no open run. That is a
        refusal, not a failure of the page."""
        a1, _ = codex_review_first("PASS", "Direction: A.")
        self.host, self.agent = E.host([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1)],
                                       git=FakeWorktrees())
        status, started = request("POST", "/api/runs", {"task": "a run closed at its gate", "repo": self.repo})
        self.assertEqual(status, 200, started)
        run_id = started["run_id"]
        self.addCleanup(lambda: E.Run.cleanup(type("R", (), {"run_id": run_id})()))
        stop = self.wait_for(run_id, lambda body: body["stop"] and body["stop"]["reason"] == "approval")["stop"]
        E.run(E.client().get_workflow_handle(run_id).terminate("closed by the test"))

        self.assertEqual(request("GET", "/api/runs/%s" % run_id)[1]["stop"]["id"], stop["id"],
                         "the precondition: the closed run still shows the stop it closed at")
        status, body = request("POST", "/api/runs/%s/answer" % run_id, {"stop": stop["id"], "action": "approve"})
        self.assertEqual(status, 409, body)


if __name__ == "__main__":
    unittest.main()
