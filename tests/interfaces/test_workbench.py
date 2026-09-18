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

from app.application import client as runs  # noqa: E402
import temporal_env as E  # noqa: E402
from app.agents import terminal  # noqa: E402
from app.interfaces.workbench import server as workbench  # noqa: E402
from fakes import FakeWorktrees, codex_review_first, codex_review_resumed  # noqa: E402
from tests.orchestration.test_workflow import Scenario  # noqa: E402

PORT = 18490


class Server:
    """One workbench per test process, over the test server's client."""
    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            policy = dict(E.POLICY, workbench_port=PORT)
            server = workbench.serve(policy, lambda work: E.run(work(E.client())),
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


class Listing(unittest.TestCase):
    """The run list: what the operator must be able to reach, whatever else Temporal still holds."""

    class Execution:
        def __init__(self, number, running):
            self.id = "run-%02d" % number
            self.status = type("Status", (), {"name": "RUNNING" if running else "COMPLETED"})()
            self.start_time = datetime.datetime(2026, 1, 1) + datetime.timedelta(number)
            self.close_time = None if running else self.start_time

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


@unittest.skipIf(sys.platform.startswith("win"), "the workbench runs on WSL, where repos.json's paths are")
class Runs(Scenario):
    """A run seen, reviewed and answered through the workbench, exactly as the workflow allows."""

    def setUp(self):
        # The test server has no poller descriptions to check; the preflight is the CLI's concern.
        saved = runs.preflight

        async def no_preflight(client, needed):
            return None
        runs.preflight = no_preflight
        self.addCleanup(setattr, runs, "preflight", saved)
        # A repository of this test's own, on a path this host runs: where the checkout happens to
        # live must not decide which worker the page's run waits for.
        self.repo = tempfile.mkdtemp(prefix="orch-page-")
        self.addCleanup(shutil.rmtree, self.repo, True)

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
        self.assertEqual(listed[0]["stop"]["reason"], "approval")
        self.assertEqual(listed[0]["task"], "a workbench run")

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

        final = body["stop"]["id"]
        self.assertEqual(request("POST", "/api/runs/%s/answer" % run_id,
                                 {"stop": final, "action": "discard", "confirm": False})[0], 422)
        status, _ = request("POST", "/api/runs/%s/answer" % run_id, {"stop": final, "action": "merge", "text": "merge"})
        self.assertEqual(status, 200)
        self.wait_for(run_id, lambda body: body["state"]["status"] == "MERGED")
        self.assertEqual(request("GET", "/api/runs/no-such-run")[0], 404)


if __name__ == "__main__":
    unittest.main()
