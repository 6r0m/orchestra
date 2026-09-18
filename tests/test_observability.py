"""What the operator observes, through the fake seams: console lines, `--show`, stops, and the trace.

The trace is proven the way the workflow is — the real workflow and activities on the
time-skipping test server, with no agent CLI and no network — and its row shapes, masking,
credentials and uploads directly against `telemetry.py`.
"""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
REPO = PKG
sys.path[:0] = [PKG, HERE]

import activities as A  # noqa: E402
import cli  # noqa: E402
import launch  # noqa: E402
import policy as policy_mod  # noqa: E402
import temporal_env as E  # noqa: E402
import trace_rows  # noqa: E402
import worktrees  # noqa: E402
from fakes import (FakeAgent, FakeWorktrees, Recorder, codex_review_first,  # noqa: E402
                   codex_review_resumed)
from test_workflow import Scenario  # noqa: E402

POL = policy_mod.load()
WINDOWS = sys.platform.startswith("win")


def patch_script():
    """plan -> assess PATCH -> plan -> assess PASS -> approval."""
    a1, _ = codex_review_first("PATCH", "dependency claim needs correction")
    return [("plan-e1-1", 0, "v1\n"), ("assess-e1-1", 0, a1),
            ("plan-e1-2", 0, "v2\n"),
            ("assess-e1-2", 0, codex_review_resumed("PASS", "good"))]


def captured(coro):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = E.run(coro)
    return code, out.getvalue()


class Console(Scenario):
    """One line per stage transition, kept by the workflow and printed by whoever follows it."""

    def test_patch_loop_renders_the_operator_console(self):
        run = self.drive(patch_script())
        self.assertEqual(run.status["lines"], [
            "[plan e1 r1] engineer started",
            "[plan e1 r1] completed",
            "[assess e1 r1] architect started",
            "[assess e1 r1] PATCH -> plan",
            "[plan e1 r2] engineer started",
            "[plan e1 r2] completed",
            "[assess e1 r2] architect started",
            "[assess e1 r2] PASS -> human (approval)",
            "stopped: approval",
        ])
        self.assertEqual((run.stop["reason"], run.stop["phase"]), ("approval", "plan"))

    def test_a_follower_prints_each_line_once(self):
        run = self.drive(patch_script())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            E.run(cli.follow(run.handle))
            E.run(cli.follow(run.handle, printed=len(run.status["lines"])))
        self.assertEqual(out.getvalue().splitlines(), run.status["lines"])


class Show(Scenario):
    """`--show`: the run's history from its workflow."""

    def test_show_reconstructs_the_run_and_refuses_an_unknown_id(self):
        a1, _ = codex_review_first("PASS")
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1)])
        code, out = captured(cli._show(E.client(), run.run_id))
        self.assertEqual(code, 0, out)
        for text in ("plan", "assess", "PASS", "approval", "what the architect said", "fb", "gap", "logs",
                     "history events"):
            self.assertIn(text, out)
        code, _ = captured(cli._show(E.client(), "deadbeefdead"))
        self.assertEqual(code, 3)


class Hermetic(Scenario):
    """A client passed in means an injected world: no real Langfuse client is ever resolved."""

    def test_an_injected_client_never_resolves_a_real_langfuse_client(self):
        import telemetry
        calls = []
        original = telemetry.resolve
        telemetry.resolve = lambda *args, **kwargs: calls.append(args) or (_ for _ in ()).throw(
            AssertionError("real telemetry.resolve called from a test"))
        repo = tempfile.mkdtemp(prefix="orch-herm-")
        self.addCleanup(shutil.rmtree, repo, ignore_errors=True)
        a1, _ = codex_review_first("PASS")
        E.host([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1)])
        try:
            code, out = captured(cli.run(["toy task", "--repo", repo], client=E.client(), check=False))
        finally:
            telemetry.resolve = original
        found = re.search(r"run-id: ([\w-]+)", out)
        if found:
            self.addCleanup(shutil.rmtree, A.run_dir(found.group(1)), ignore_errors=True)
        self.assertEqual(code, 2, out)
        self.assertEqual(calls, [], "no Langfuse client may be resolved when a client is injected")


class RunIds(unittest.TestCase):
    """A readable run id whose random tail meets a run Temporal still holds draws again."""

    def test_a_start_that_meets_a_retained_run_id_starts_under_a_fresh_one(self):
        import worktrees
        repo = tempfile.mkdtemp(prefix="orch-ids-")
        self.addCleanup(shutil.rmtree, repo, ignore_errors=True)
        taken = "toy-task-%s" % uuid.uuid4().hex[:8]
        fresh = "toy-task-%s" % uuid.uuid4().hex[:8]
        drawn = iter([taken, taken, fresh])
        original = worktrees.run_id
        worktrees.run_id = lambda task: next(drawn)
        self.addCleanup(setattr, worktrees, "run_id", original)
        for rid in (taken, fresh):
            self.addCleanup(shutil.rmtree, A.run_dir(rid), ignore_errors=True)
        a1, _ = codex_review_first("PASS")
        E.host([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1)])
        _, first = captured(cli.run(["toy task", "--repo", repo], client=E.client(), check=False))
        self.assertIn("run-id: %s" % taken, first)
        E.host([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1)])
        _, second = captured(cli.run(["toy task", "--repo", repo], client=E.client(), check=False))
        self.assertIn("run-id: %s" % fresh, second, "the retained id is never reused")
        self.assertRaises(StopIteration, next, drawn)


class Verdicts(unittest.TestCase):
    """`--show`'s explanation: one entry per judgement, never deduplicated on text."""

    def _render(self, timeline):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.print_verdicts(timeline)
        return out.getvalue()

    def entry(self, stage, verdict, feedback, episode, rnd):
        return {"stage": stage, "phase": "plan", "episode": episode, "round": rnd, "verdict": verdict,
                "feedback": feedback, "at": "2026-09-08T00:00:00"}

    def test_a_verdict_is_labelled_with_the_stage_that_gave_it(self):
        text = self._render([{"stage": "plan", "phase": "plan", "episode": 1, "round": 1, "at": "x"},
                             self.entry("assess", "PATCH", "finding A", 1, 1)])
        self.assertIn("assess e1 r1 -> PATCH", text)
        self.assertNotIn("plan e1 r1 -> PATCH", text)

    def test_an_unchanged_or_repeated_finding_is_never_swallowed(self):
        """The engineer failed to fix it, or regressed: that must stay visible."""
        text = self._render([self.entry("assess", "PATCH", "finding A", 1, 1),
                             self.entry("assess", "PATCH", "finding A", 1, 2),
                             self.entry("assess", "PATCH", "finding B", 2, 1),
                             self.entry("assess", "PATCH", "finding A", 3, 1)])
        self.assertEqual(text.count("finding A"), 3)
        self.assertEqual(text.count("finding B"), 1)
        self.assertEqual(text.count("-> PATCH"), 4)


class Preflight(unittest.TestCase):
    """A run is refused before any work while a queue it needs has no worker."""

    def test_no_worker_refuses_and_starts_nothing(self):
        class Service:
            async def describe_task_queue(self, request):
                return type("Reply", (), {"pollers": []})()

        class Client:
            namespace = "orchestration"
            workflow_service = Service()
            started = []

            async def start_workflow(self, *args, **kwargs):
                Client.started.append(args)

        repo = tempfile.mkdtemp(prefix="orch-preflight-")
        self.addCleanup(shutil.rmtree, repo, ignore_errors=True)
        code, out = captured(cli.run(["toy task", "--repo", repo], client=Client(), tele=object()))
        self.assertEqual(code, 4, out)
        self.assertIn("no worker is polling", out)
        self.assertEqual(Client.started, [])


class Elapsed(unittest.TestCase):
    """Checkpoint-to-checkpoint wall time; it must never invent a number."""

    def test_formats_and_refuses_what_it_cannot_compute(self):
        self.assertEqual(cli._elapsed("2026-09-08T13:22:50", "2026-09-08T13:22:53"), "3s")
        self.assertEqual(cli._elapsed("2026-09-08T13:22:50", "2026-09-08T13:23:50"), "1m00s")
        self.assertEqual(cli._elapsed("2026-09-08T13:22:54", "2026-09-08T13:27:04"), "4m10s")
        self.assertEqual(cli._elapsed(None, "2026-09-08T13:22:50"), "-")
        self.assertEqual(cli._elapsed("not-a-time", "2026-09-08T13:22:50"), "-")
        # a clock that went backwards is reported as unknown, never as a number
        self.assertEqual(cli._elapsed("2026-09-08T13:23:50", "2026-09-08T13:22:50"), "-")


class EntryPoint(unittest.TestCase):
    """The operator's task text reaches argv byte-for-byte."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="orch-make-")
        self.capture = os.path.join(self.tmp, "argv.json")
        self.stub = os.path.join(self.tmp, "stub.py")
        # A payload that is detectable but harmless: if Make or the shell ever
        # executes it, the sentinel appears and the test fails loudly. Proving
        # "nothing ran" beats hoping a destructive payload does no damage.
        self.sentinel = os.path.join(self.tmp, "EXECUTED")
        self.hostile = ('cost is $5 (approx) and $(HOME) and '
                        '$(shell touch %s) and `touch %s` and "quoted"; '
                        'touch %s' % (self.sentinel, self.sentinel,
                                      self.sentinel))
        with open(self.stub, "w", encoding="utf-8") as fh:
            fh.write("import json, sys\n"
                     "json.dump(sys.argv[1:], open(%r, 'w'))\n" % self.capture)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make(self, *args):
        return subprocess.run(
            ["make", "-C", REPO, "feature",
             "V=%s %s" % (sys.executable, self.stub)] + list(args),
            capture_output=True, text=True, timeout=120)

    def test_hostile_task_text_arrives_verbatim_as_one_argument(self):
        done = self._make("TASK=" + self.hostile)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        argv = json.load(open(self.capture))
        self.assertEqual(len(argv), 2, argv)      # cli.py path + the task
        self.assertEqual(argv[1], self.hostile)
        self.assertIn("$5", argv[1], "Make must not eat a bare $")
        self.assertIn("$(HOME)", argv[1], "Make must not expand $(...)")
        self.assertFalse(os.path.exists(self.sentinel),
                         "nothing in the task text may be executed by Make "
                         "or by the shell")

    def test_missing_task_refuses_with_usage(self):
        done = self._make()
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertIn("usage", (done.stdout + done.stderr).lower())
        self.assertFalse(os.path.exists(self.capture))


class _Events:
    """The part of a Langfuse client the trace rows use, recording instead of sending.

    `create_event` is kept apart: the SDK marks such an event a root, and a root
    renames the whole trace, so nothing may call it. Metadata accumulates across
    updates, as the SDK's one attribute per metadata key does.
    """

    def __init__(self):
        self.events = []
        self.scores = []
        self.create_event_calls = []

    def create_trace_id(self, seed=None):
        return "0" * 32

    def get_trace_url(self, *, trace_id=None):
        return "http://localhost:3000/project/orchestration/traces/%s" % (trace_id or "")

    def create_event(self, **kwargs):
        self.create_event_calls.append(kwargs)

    def create_score(self, **kwargs):
        self.scores.append(kwargs)

    def start_as_current_observation(self, **kwargs):
        record = dict(kwargs)
        self.events.append(record)

        class Span:
            def update(self, **fields):
                metadata = fields.pop("metadata", None)
                if metadata:
                    record["metadata"] = dict(record.get("metadata") or {}, **metadata)
                record.update(fields)

        class Context:
            def __enter__(self):
                return Span()

            def __exit__(self, *exc):
                return False

        return Context()


def _git(path, *args):
    # Pinned so a machine's own config (signing, hooks, identity) cannot change
    # what the repository under test contains.
    return subprocess.run(
        ["git", "-C", path, "-c", "user.email=t@t", "-c", "user.name=t",
         "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"]
        + list(args), capture_output=True, check=True).stdout


class FinalDiff(unittest.TestCase):
    """The diff the operator reviews is `gdiff -s`, byte for byte.

    Regression for a final diff that named new files without their contents, so
    a file holding the whole implementation showed up as a bare path, and that
    rendered any git failure as "no changes".
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="orch-final-diff-")
        self.repo = os.path.join(self.tmp, "worktree")
        os.makedirs(self.repo)
        _git(self.repo, "init", "-q")
        files = {".gitignore": "*.log\n", "kept.txt": "one\n",
                 "staged.txt": "a\n", "gone.txt": "bye\n"}
        for name, text in files.items():
            with open(os.path.join(self.repo, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "base")
        # Every kind of change a role can leave behind: unstaged, staged,
        # deleted, new (with a space in its name) and ignored.
        with open(os.path.join(self.repo, "kept.txt"), "w", encoding="utf-8") as fh:
            fh.write("two\n")
        with open(os.path.join(self.repo, "staged.txt"), "w", encoding="utf-8") as fh:
            fh.write("b\n")
        _git(self.repo, "add", "staged.txt")
        os.remove(os.path.join(self.repo, "gone.txt"))
        with open(os.path.join(self.repo, "new file.txt"), "w", encoding="utf-8") as fh:
            fh.write("created by the engineer\nsecond line\n")
        with open(os.path.join(self.repo, "debug.log"), "w", encoding="utf-8") as fh:
            fh.write("ignored\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _gdiff_s(self):
        """What `gdiff -s` copies, run literally on a copy of the worktree."""
        copy = os.path.join(self.tmp, "gdiff-copy")
        shutil.copytree(self.repo, copy)
        _git(copy, "add", "-A")
        return _git(copy, "diff", "--no-ext-diff", "--no-textconv",
                    "--cached").decode("utf-8")

    def test_review_diff_is_gdiff_s_and_leaves_the_index_alone(self):
        import telemetry
        client = _Events()
        values = {"run_id": "r1", "worktree_path": self.repo}
        telemetry.final_diff(client, values, worktrees.review_diff)
        self.assertEqual(client.events, [], "a run that stopped is not finished")

        # `git status` refreshes the index's stat cache itself, so it runs
        # before the snapshot: afterwards, any change to those bytes is ours.
        status_before = _git(self.repo, "status", "--porcelain", "-z")
        staged_before = _git(self.repo, "diff", "--cached", "--name-status")
        index = os.path.join(self.repo, ".git", "index")
        index_before = open(index, "rb").read()
        telemetry.final_diff(client, dict(values, status="READY_FOR_HUMAN"),
                             worktrees.review_diff)

        self.assertEqual(len(client.events), 1)
        patch = client.events[0]["output"]["patch"]
        self.assertEqual(patch, self._gdiff_s())
        self.assertIn("+created by the engineer", patch)
        self.assertNotIn("debug.log", patch)
        self.assertEqual(open(index, "rb").read(), index_before,
                         "an observability write must not touch the index")
        self.assertEqual(_git(self.repo, "diff", "--cached", "--name-status"),
                         staged_before)
        self.assertEqual(_git(self.repo, "status", "--porcelain", "-z"),
                         status_before)

    def test_a_git_failure_is_reported_never_rendered_as_no_changes(self):
        import telemetry
        not_a_repo = os.path.join(self.tmp, "plain")
        os.makedirs(not_a_repo)
        for path in (not_a_repo, os.path.join(self.tmp, "missing")):
            client = _Events()
            telemetry.final_diff(client, {"run_id": "r1", "worktree_path": path,
                                          "status": "READY_FOR_HUMAN"}, worktrees.review_diff)
            self.assertEqual(len(client.events), 1, path)
            event = client.events[0]
            self.assertEqual(event.get("level"), "ERROR", path)
            self.assertEqual((event.get("metadata") or {}).get("error_type"), "git_error", path)
            self.assertNotIn("patch", event.get("output") or {}, path)


class SecretsFileCredentials(unittest.TestCase):
    """The Langfuse keys come from `.env`, this checkout's one private file.

    Each test points the module at a file of its own. Keys are compared as
    booleans, so a failing assertion never prints one.
    """

    def setUp(self):
        import telemetry
        self.telemetry = telemetry
        self.tmp = tempfile.mkdtemp(prefix="orch-secrets-")
        self.saved = {k: os.environ.get(k) for k in
                      ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST",
                       "LANGFUSE_LOGIN_PASSWORD", "POSTGRES_PASSWORD")}
        self.source = getattr(telemetry, "SECRETS_FILE", None)
        self.warned = set(telemetry._warned)
        telemetry._warned.clear()
        for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_LOGIN_PASSWORD", "POSTGRES_PASSWORD"):
            os.environ.pop(key, None)
        telemetry.SECRETS_FILE = os.path.join(self.tmp, "langfuse.env")

    def tearDown(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.telemetry.SECRETS_FILE = self.source
        self.telemetry._warned.clear()
        self.telemetry._warned.update(self.warned)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, data):
        with open(self.telemetry.SECRETS_FILE, "wb") as fh:
            fh.write(data)

    def configured(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            result = self.telemetry.configured()
        return result, err.getvalue()

    def test_the_file_is_this_checkouts_own_dotenv(self):
        self.assertEqual(self.source, os.path.join(REPO, ".env"),
                         "one private file, named by .env.example and ignored by git")

    def test_the_key_pair_comes_from_the_file_and_nothing_else_does(self):
        self.write(b"# every Langfuse credential\n"
                   b"LANGFUSE_PUBLIC_KEY=pk-lf-file\n"
                   b"LANGFUSE_SECRET_KEY='sk-lf-file'\n"
                   b"LANGFUSE_LOGIN_PASSWORD=the-ui-login\n"
                   b"POSTGRES_PASSWORD=the-stack-database\n")
        result, err = self.configured()
        self.assertTrue(result)
        self.assertEqual(err, "")
        self.assertTrue(os.environ.get("LANGFUSE_PUBLIC_KEY") == "pk-lf-file", "public key not from the file")
        self.assertTrue(os.environ.get("LANGFUSE_SECRET_KEY") == "sk-lf-file", "secret key not from the file")
        # Role-runs inherit this environment: the login and the stack's own secrets stay out of it.
        self.assertTrue("LANGFUSE_LOGIN_PASSWORD" not in os.environ and "POSTGRES_PASSWORD" not in os.environ,
                        "only the key pair is exported")

    def test_an_explicit_environment_wins(self):
        self.write(b"LANGFUSE_PUBLIC_KEY=pk-lf-file\nLANGFUSE_SECRET_KEY=sk-lf-file\n")
        os.environ.update(LANGFUSE_PUBLIC_KEY="pk-lf-env", LANGFUSE_SECRET_KEY="sk-lf-env")
        result, err = self.configured()
        self.assertTrue(result)
        self.assertTrue(os.environ.get("LANGFUSE_SECRET_KEY") == "sk-lf-env", "the environment was overridden")

    def test_no_file_leaves_tracing_off_quietly(self):
        self.assertEqual(self.configured(), (False, ""))

    def test_a_file_without_the_keys_leaves_tracing_off_quietly(self):
        self.write(b"POSTGRES_PASSWORD=the-stack-database\n")
        self.assertEqual(self.configured(), (False, ""))

    def test_a_file_that_cannot_be_read_is_reported_once(self):
        # Not UTF-8, as a legacy Windows code page would save it.
        self.write(b"LANGFUSE_PUBLIC_KEY=pk-lf-file\nLANGFUSE_SECRET_KEY=sk-lf-\xff\n")
        first, err = self.configured()
        second, again = self.configured()
        self.assertFalse(first or second)
        self.assertIn("cannot read", err)
        self.assertEqual(len(err.splitlines()) + len(again.splitlines()), 1, "said once")


class CorrelationId(Scenario):
    """The trace ids a run carries are never consulted."""

    def _run(self, root):
        import telemetry
        original = telemetry.open_work_item, telemetry.open_phase
        telemetry.open_work_item = lambda *args, **kwargs: (("%032x" % 1) if root else None, root)
        telemetry.open_phase = lambda client, values, phase: ("%016x" % len(phase)) if root else None
        try:
            a1, _ = codex_review_first("PATCH")
            run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1),
                              ("plan-e1-2", 0, "replanned\n"), ("assess-e1-2", 0, codex_review_resumed("PASS")),
                              ("build-e2-1", 0, "built\n"), ("verify-e2-1", 0, codex_review_resumed("PASS"))],
                             telemetry=Recorder(), auto=True)
        finally:
            telemetry.open_work_item, telemetry.open_phase = original
        return self.names(), run.state

    def test_a_trace_root_never_changes_the_route_or_outcome(self):
        calls_without, without = self._run(None)
        calls_with, with_root = self._run("00000000deadbeef")
        self.assertEqual(with_root.get("trace_root"), "00000000deadbeef")
        self.assertEqual(with_root.get("trace_id"), "%032x" % 1)
        self.assertEqual(set(with_root.get("trace_phases") or {}), {"plan", "build"})
        self.assertEqual(calls_with, calls_without)
        ignore = ("trace_id", "trace_root", "trace_phases", "label", "agent_sessions", "run_id", "worktree",
                  "worktree_path", "todo_path", "plan")
        self.assertEqual({k: v for k, v in with_root.items() if k not in ignore},
                         {k: v for k, v in without.items() if k not in ignore})


class ClaudeTracingGate(unittest.TestCase):
    """The Claude plugin is off for the user; only a traced role-run turns it on.

    Regression for the plugin tracing every Claude Code session on the machine —
    the operator's own chats in other repositories — into the work-item list.
    """

    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST")}
        os.environ.update(LANGFUSE_PUBLIC_KEY="pk-lf-test", LANGFUSE_SECRET_KEY="sk-lf-test",
                          LANGFUSE_HOST="http://localhost:3000")
        self.addCleanup(self._restore)

    def _restore(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def role_run(self, script, state, stage, telemetry=None, runner_class=FakeAgent):
        """One role activity, called directly, over a fake agent and fake git."""
        run_id = "gate-%s" % stage
        self.addCleanup(shutil.rmtree, A.run_dir(run_id), ignore_errors=True)
        agent = runner_class(script)
        host = A.Activities(runner=agent, git=FakeWorktrees(), telemetry=telemetry)
        base = {"run_id": run_id, "task": "toy task", "phase": "plan", "round": 0, "episode": 1,
                "worktree_path": "/fake/worktree", "todo_path": "/fake/worktree/todo/t.md", "agent_sessions": {},
                "repo": "example", "target": "wsl"}
        base.update(state)
        return host.run_role({"stage": stage, "state": base, "policy": POL}), agent

    def test_only_a_traced_claude_role_run_enables_the_plugin(self):
        """The run's own settings carry both keys, and only this user can read them."""
        import stat
        import nodes as N
        import telemetry
        tmp = tempfile.mkdtemp(prefix="orch-cc-gate-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        engineer, architect = POL["roles"]["engineer"], POL["roles"]["architect"]
        traced = telemetry._Span(traceparent="00-%032x-%016x-01" % (1, 2))
        path = telemetry.harness_settings(engineer, traced)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {
                "enabledPlugins": {telemetry.CLAUDE_PLUGIN: True},
                "pluginConfigs": {telemetry.CLAUDE_PLUGIN: {"options": {
                    "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
                    "LANGFUSE_SECRET_KEY": "sk-lf-test",
                    "LANGFUSE_BASE_URL": "http://localhost:3000"}}}})
        if not WINDOWS:
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode), 0o700)
        argv, _ = N.build_argv("engineer", engineer, None, tmp, path)
        self.assertEqual(argv[argv.index("--settings") + 1], path)
        self.assertNotIn("sk-lf-test", " ".join(argv), "the secret never reaches the command line")
        telemetry.discard_settings(path)
        self.assertFalse(os.path.exists(path) or os.path.exists(os.path.dirname(path)))
        telemetry.discard_settings(path)
        for name in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
            value = os.environ.pop(name)
            self.assertIsNone(telemetry.harness_settings(engineer, traced))
            os.environ[name] = value
        self.assertIsNone(telemetry.harness_settings(engineer, telemetry._Span()))
        argv, _ = N.build_argv("engineer", engineer, None, tmp, None)
        self.assertNotIn("--settings", argv)
        self.assertIsNone(telemetry.harness_settings(architect, traced))

    def _fake_settings(self, made):
        import telemetry

        def settings(role, span):
            path = os.path.join(tempfile.mkdtemp(prefix=telemetry.SETTINGS_DIR_PREFIX), telemetry.SETTINGS_FILE)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("{}")
            made.append(path)
            return path
        return settings

    def test_the_settings_file_survives_a_rehydrate_and_goes_after_it(self):
        import telemetry
        made, present = [], {}

        class Watching(FakeAgent):
            def __call__(self, worktree, argv, rdir, name, prompt, timeout, env, *, brain):
                present[name] = bool(made) and os.path.exists(made[-1])
                return FakeAgent.__call__(self, worktree, argv, rdir, name, prompt, timeout, env,
                                          brain=brain)

        original = telemetry.harness_settings
        telemetry.harness_settings = self._fake_settings(made)
        try:
            self.role_run([("build-e2-2", 1, "Error: No conversation found with session ID: dead\n"),
                           ("build-e2-2-rehydrated", 0, "rebuilt\n")],
                          {"phase": "build", "round": 1, "episode": 2, "agent_sessions": {"engineer": "dead"}},
                          "build", runner_class=Watching)
        finally:
            telemetry.harness_settings = original
        self.assertTrue(present["build-e2-2"] and present["build-e2-2-rehydrated"])
        self.assertFalse(any(os.path.exists(os.path.dirname(p)) for p in made))

    def test_the_settings_file_lives_only_as_long_as_its_role_run(self):
        """It carries the secret, so a stage removes it on the way out, failure included."""
        import telemetry
        made = []
        original = telemetry.harness_settings
        telemetry.harness_settings = self._fake_settings(made)
        try:
            self.role_run([("plan-e1-1", 0, "p\n")], {}, "plan")
            self.assertFalse(any(os.path.exists(os.path.dirname(p)) for p in made), "left behind after a stage")
            with self.assertRaises(Exception):
                self.role_run([("plan-e1-1", 1, "boom\n")], {}, "plan")
            self.assertEqual(len(made), 2)
            self.assertFalse(any(os.path.exists(os.path.dirname(p)) for p in made), "left behind after a failure")
        finally:
            telemetry.harness_settings = original

    def test_a_role_runs_settings_are_private_and_off_the_repository_drive(self):
        import stat
        seen = []

        class Watching(FakeAgent):
            def __call__(self, worktree, argv, rdir, name, prompt, timeout, env, *, brain):
                if "--settings" in argv:
                    path = argv[argv.index("--settings") + 1]
                    seen.append((path, stat.S_IMODE(os.stat(path).st_mode),
                                 stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode)))
                return FakeAgent.__call__(self, worktree, argv, rdir, name, prompt, timeout, env,
                                          brain=brain)

        with contextlib.redirect_stderr(io.StringIO()):
            self.role_run([("plan-e1-1", 0, "p\n")], {}, "plan", telemetry=Recorder(), runner_class=Watching)
        self.assertEqual(len(seen), 1, "the engineer's role-run was traced")
        path, file_mode, dir_mode = seen[0]
        self.assertFalse(os.path.abspath(path).startswith(REPO + os.sep), "the settings file sits on the repository's drive")
        if not WINDOWS:
            self.assertEqual((file_mode, dir_mode), (0o600, 0o700))
        self.assertFalse(os.path.exists(path) or os.path.exists(os.path.dirname(path)))

    def test_a_failed_write_leaves_no_secret_behind(self):
        """A settings file that could not be written whole is removed, not abandoned.

        The caller deletes only a file it was handed, so a half-written one that
        already holds the secret has to go before `harness_settings` gives up.
        """
        import telemetry
        tmp = tempfile.mkdtemp(prefix="orch-cc-partial-")
        saved = {k: os.environ.get(k) for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")}
        os.environ.update(LANGFUSE_PUBLIC_KEY="pk-lf-test", LANGFUSE_SECRET_KEY="sk-lf-test")
        original, tempdir = json.dump, tempfile.tempdir
        # Where the private directory is made, so the test can see what is left.
        tempfile.tempdir = tmp

        def partial(obj, fh, *args, **kwargs):
            fh.write('{"pluginConfigs": {"secret": "sk-lf-test')
            raise OSError("disk full")

        json.dump = partial
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                path = telemetry.harness_settings(
                    POL["roles"]["engineer"], telemetry._Span(traceparent="00-%032x-%016x-01" % (1, 2)))
            self.assertIsNone(path)
            self.assertEqual(os.listdir(tmp), [], "the half-written secret and its directory are gone")
        finally:
            json.dump, tempfile.tempdir = original, tempdir
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            shutil.rmtree(tmp, ignore_errors=True)


class _FakeSpan:
    def __init__(self):
        self.updates = []

    def update(self, **kwargs):
        self.updates.append(kwargs)


class _FakeContext:
    def __exit__(self, *args):
        return False


class TraceShape(Scenario):
    """What the operator navigates: the work item, its plan and build, their rounds."""

    def test_a_row_is_named_for_its_kind_of_step_never_for_its_round_or_outcome(self):
        """Dashboards, saved views and the agent graph group rows by name.

        A name carrying the round or the verdict splits one kind of step into as
        many names as there are rounds and outcomes, so those are metadata. The role
        stays in the name: an engineer's step and an architect's are different kinds.
        """
        import telemetry
        self.assertEqual([telemetry.stage_name(stage, role) for stage, role in
                          (("plan", "engineer"), ("assess", "architect"),
                           ("build", "engineer"), ("verify", "architect"))],
                         ["engineer-plan", "architect-assess", "engineer-build", "architect-verify"])
        for fields in ({"verdict": "PATCH", "feedback": "f"}, {"response": "done"},
                       {"error_type": "timeout", "error": RuntimeError("late")}):
            span = _FakeSpan()
            with contextlib.redirect_stderr(io.StringIO()):
                telemetry.end(telemetry._Span(_FakeContext(), span), **fields)
            self.assertEqual([u for u in span.updates if "name" in u], [], fields)

    def test_an_outcome_is_written_once(self):
        """What a person reads lands in the output alone; metadata keeps what filters.

        Copying the response, feedback and reasoning into metadata as well printed
        each of them twice on the same page.
        """
        import telemetry
        span = _FakeSpan()
        telemetry.end(telemetry._Span(_FakeContext(), span),
                      verdict="PATCH", gate_reason="", feedback="fix the call sites",
                      reasoning="because", session="s1")
        self.assertEqual([u["metadata"] for u in span.updates if "metadata" in u],
                         [{"verdict": "PATCH", "provider_session_id": "s1"}])
        self.assertEqual([u["output"] for u in span.updates if "output" in u],
                         [{"verdict": "PATCH", "feedback": "fix the call sites", "reasoning": "because"}])

    def test_only_the_work_item_is_a_root(self):
        """Every row added under the work item says it is not a root.

        Langfuse lets any root rename the trace, and one run's work item came out
        named "Plan". The SDK marks what it creates from a trace context as a
        root, and an event it creates cannot be unmarked.
        """
        import types
        import telemetry
        from langfuse import LangfuseOtelSpanAttributes as attrs
        from opentelemetry import trace as otel

        class Current:
            def __init__(self):
                self.flags = []

            def set_attribute(self, key, value):
                if key in (attrs.AS_ROOT, attrs.IS_APP_ROOT):
                    self.flags.append((key, value))

            def get_span_context(self):
                return types.SimpleNamespace(trace_id=1, span_id=2)

        current, client = Current(), _Events()
        values = {"run_id": "r1", "phase": "plan", "trace_root": "a" * 16,
                  "trace_phases": {"plan": "b" * 16}, "gate_reason": "blocker",
                  "status": "READY_FOR_HUMAN", "worktree_path": None}
        original = otel.get_current_span
        otel.get_current_span = lambda: current
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                telemetry.open_phase(client, values, "build")
                telemetry.gate_event(client, values, {"reason": "blocker", "phase": "plan",
                                                      "feedback": "f"})
                telemetry.gate_answer(client, values, "use B")
                telemetry.final_diff(client, values, worktrees.review_diff)
        finally:
            otel.get_current_span = original
        self.assertEqual(client.create_event_calls, [], "an event cannot be unmarked as a root")
        self.assertEqual([e["name"] for e in client.events],
                         ["build-phase", "human-gate", "human-answer", "final-diff"])
        for flag in (attrs.AS_ROOT, attrs.IS_APP_ROOT):
            self.assertEqual([v for k, v in current.flags if k == flag], [False] * 4,
                             "%s must be cleared on every row under the work item" % flag)

    def test_a_node_that_fails_after_opening_is_still_closed(self):
        """A failure after a node opens still closes it.

        Left open, it stays the current context, and the rows that follow would
        attach beneath a node that was never finished.
        """
        import types
        import telemetry
        from opentelemetry import trace as otel
        exits = []

        class Span:
            def update(self, **kwargs):
                raise RuntimeError("update refused")

        class Context:
            def __enter__(self):
                return Span()

            def __exit__(self, *exc):
                exits.append(True)
                return False

        class Client:
            def create_trace_id(self, seed):
                return "%032x" % 1

            def start_as_current_observation(self, **kwargs):
                return Context()

        class Current:
            def set_attribute(self, key, value):
                pass

            def get_span_context(self):
                return types.SimpleNamespace(trace_id=1, span_id=2)

        original = otel.get_current_span
        otel.get_current_span = lambda: Current()
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertIsNone(telemetry.open_phase(Client(), {"run_id": "r1", "trace_root": "a" * 16},
                                                       "plan"))
                self.assertEqual(telemetry.open_work_item(Client(), {"run_id": "r1", "label": "label",
                                                                     "task": "task"}), (None, None))
        finally:
            otel.get_current_span = original
        self.assertEqual(exits, [True, True])

    def test_a_diff_past_the_cap_is_cut_and_marked(self):
        """The final diff is the whole `gdiff -s` patch up to its cap, and says when it is not."""
        import telemetry
        read = lambda path: {"base": "abc1234", "summary": " 1 file changed",
                             "summary_total": 15, "patch": "x" * 50,
                             "offset": 0, "next": 50, "total": 50}
        saved = telemetry.DIFF_MAX_CHARS
        telemetry.DIFF_MAX_CHARS = 10
        client = _Events()
        try:
            telemetry.final_diff(client, {"run_id": "r1", "status": "READY_FOR_HUMAN",
                                          "worktree_path": "/wt"}, read)
        finally:
            telemetry.DIFF_MAX_CHARS = saved
        output = client.events[0]["output"]
        self.assertEqual((len(output["patch"]), output["truncated"]), (10, True))

    def test_the_work_item_is_a_genuine_root_and_its_rows_join_its_trace(self):
        """The work item is opened with no trace context; everything after joins its ids.

        Langfuse names a trace after its parentless observation. A trace context
        gives the observation it creates a parent even when no parent id is
        passed, so the root is opened without one, takes the SDK's own trace id,
        and both ids are checkpointed for every later process.
        """
        import types
        import telemetry
        from opentelemetry import trace as otel

        class Current:
            def set_attribute(self, key, value):
                pass

            def get_span_context(self):
                return types.SimpleNamespace(trace_id=0xabc, span_id=0xdef)

        client = _Events()
        original = otel.get_current_span
        otel.get_current_span = lambda: Current()
        try:
            ids = telemetry.open_work_item(client, {"run_id": "r1", "label": "the label", "task": "task"})
            self.assertNotIn("trace_context", client.events[0],
                             "a trace context gives the root a parent")
            self.assertEqual(ids, ("%032x" % 0xabc, "%016x" % 0xdef))
            values = {"run_id": "r1", "phase": "plan", "trace_id": ids[0], "trace_root": ids[1]}
            telemetry.open_phase(client, values, "plan")
            telemetry.gate_event(client, values, {"reason": "approval", "phase": "plan",
                                                  "feedback": "the summary"})
        finally:
            otel.get_current_span = original
        self.assertEqual([row["trace_context"] for row in client.events[1:]],
                         [{"trace_id": ids[0], "parent_span_id": ids[1]}] * 2)

    def test_a_run_whose_root_never_opened_still_keeps_one_trace(self):
        import telemetry
        client = _Events()
        self.assertEqual(telemetry._work_item_context(client, {"run_id": "r1", "trace_id": "f" * 32}),
                         {"trace_id": "f" * 32})
        self.assertEqual(telemetry._work_item_context(client, {"run_id": "r1"}),
                         {"trace_id": client.create_trace_id(seed="r1")})

    def test_stages_hang_from_their_phase(self):
        import telemetry
        client = _Events()
        base = {"run_id": "r1", "trace_root": "a" * 16}
        self.assertEqual(telemetry._phase_context(
            client, dict(base, phase="build", trace_phases={"build": "c" * 16}))["parent_span_id"], "c" * 16)
        self.assertEqual(telemetry._phase_context(
            client, dict(base, phase="build", trace_phases={"plan": "b" * 16}))["parent_span_id"], "a" * 16,
            "a phase without a node falls back to the work item")

    def test_gate_rows_sit_where_they_belong(self):
        import telemetry
        values = {"run_id": "r1", "phase": "plan", "trace_root": "a" * 16,
                  "trace_phases": {"plan": "b" * 16}}
        client = _Events()
        telemetry.gate_event(client, values, {"reason": "approval", "phase": "plan",
                                              "feedback": "the summary", "todo": "/wt/todo.md"})
        telemetry.gate_event(client, values, {"reason": "blocker", "phase": "plan",
                                              "feedback": "the finding", "todo": "/wt/todo.md"})
        approval, blocker = client.events
        self.assertEqual(approval["trace_context"]["parent_span_id"], "a" * 16,
                         "approval closes the plan, so it sits between plan and build")
        self.assertEqual(approval["output"], {"summary": "the summary"},
                         "the output is what the person reads, and nothing beside it")
        self.assertEqual(approval["input"]["todo"], "/wt/todo.md")
        self.assertEqual(blocker["trace_context"]["parent_span_id"], "b" * 16,
                         "any other stop belongs to the phase it interrupted")
        self.assertEqual(blocker["output"], {"feedback": "the finding"})

    def test_a_stage_row_carries_only_what_a_reader_needs(self):
        """The work item's own name, session and tags, no internal or empty fields in a round's input,
        and metadata that points at the stage's logs instead of the counters naming them.

        Every row carries the same few tags, so no stage can retag the work item as
        itself; and `episode` plus null fields filled every round's input.
        """
        import types
        import telemetry
        from langfuse import LangfuseOtelSpanAttributes as attrs
        from opentelemetry import trace as otel

        class Span:
            def __init__(self):
                self.attributes, self.updates = {}, []

            def set_attribute(self, key, value):
                self.attributes[key] = value

            def get_span_context(self):
                return types.SimpleNamespace(trace_id=1, span_id=2)

            def update(self, **kwargs):
                self.updates.append(kwargs)

        span = Span()

        class Context:
            def __enter__(self):
                return span

            def __exit__(self, *exc):
                return False

        class Client:
            def create_trace_id(self, seed):
                return "%032x" % 1

            def start_as_current_observation(self, **kwargs):
                return Context()

        original = otel.get_current_span
        otel.get_current_span = lambda: span
        try:
            state = {"run_id": "r1", "label": "the label", "task": "t", "trace_root": "a" * 16,
                     "phase": "plan", "episode": 2, "round": 0, "phase_rounds": 2,
                     "guidance": "use B"}
            telemetry.begin(Client(), state, "plan", "engineer", {"brain": "claude"})
        finally:
            otel.get_current_span = original
        self.assertEqual(span.attributes.get(attrs.TRACE_SESSION_ID), "the label")
        self.assertEqual(span.attributes.get(attrs.TRACE_NAME), "orchestration-run")
        self.assertEqual(list(span.attributes.get(attrs.TRACE_TAGS) or ()), telemetry.tags(state))
        self.assertIs(span.attributes.get(attrs.IS_APP_ROOT), False,
                      "a round's parent lives in another process, which makes the SDK call it an app root")
        self.assertEqual([u["input"] for u in span.updates if "input" in u],
                         [{"task": "t", "stage": "plan", "role": "engineer", "round": 3,
                           "guidance": "use B"}])
        metadata = [u["metadata"] for u in span.updates if "metadata" in u][0]
        self.assertEqual((metadata["round"], metadata["phase"], metadata["stage"], metadata["role"]),
                         (3, "plan", "plan", "engineer"))
        self.assertFalse({"episode", "attempt"} & set(metadata),
                         "two more counters beside the round read as a contradiction")
        span.updates.clear()
        otel.get_current_span = lambda: span
        try:
            telemetry.begin(Client(), state, "plan", "engineer", {"brain": "claude"},
                            log="tmp/orchestration/r1/logs/plan-e2-1")
        finally:
            otel.get_current_span = original
        metadata = [u["metadata"] for u in span.updates if "metadata" in u][0]
        self.assertEqual(metadata["logs"], "tmp/orchestration/r1/logs/plan-e2-1",
                         "where the stage's own logs are is what those counters were for")

    def test_each_phase_opens_its_node_once(self):
        import telemetry
        opened = []
        original = telemetry.open_phase
        telemetry.open_phase = lambda client, values, phase: opened.append(phase) or "%016x" % len(opened)
        try:
            a1, _ = codex_review_first("PATCH")
            run = self.drive([("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, a1),
                              ("plan-e1-2", 0, "p\n"), ("assess-e1-2", 0, codex_review_resumed("PASS")),
                              ("build-e2-1", 0, "b\n"), ("verify-e2-1", 0, codex_review_resumed("PATCH")),
                              ("build-e2-2", 0, "b\n"), ("verify-e2-2", 0, codex_review_resumed("PASS"))],
                             telemetry=Recorder())
            run.answer("yes")
        finally:
            telemetry.open_phase = original
        self.assertEqual(run.state["status"], "READY_FOR_HUMAN")
        self.assertEqual(opened, ["plan", "build"])
        self.assertEqual(sorted(run.state["trace_phases"]), ["build", "plan"])

    def test_rounds_keep_counting_across_a_guidance_restart(self):
        """Guidance resets the round budget, not the count a person reads."""
        import telemetry
        rounds = []
        original = telemetry.begin

        def begin(client, state, stage, role_name, role, **kwargs):
            rounds.append((telemetry.stage_name(stage, role_name), telemetry.phase_round(state)))
            return telemetry._Span()

        telemetry.begin = begin
        try:
            b1, _ = codex_review_first("BLOCKER")
            run = self.drive([("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, b1),
                              ("plan-e2-1", 0, "p\n"), ("assess-e2-1", 0, codex_review_resumed("PASS")),
                              ("build-e3-1", 0, "b\n"), ("verify-e3-1", 0, codex_review_resumed("PASS"))],
                             telemetry=Recorder())
            run.answer("use approach B")
            run.answer("yes")
        finally:
            telemetry.begin = original
        self.assertEqual(run.state["status"], "READY_FOR_HUMAN")
        self.assertEqual(rounds, [("engineer-plan", 1), ("architect-assess", 1), ("engineer-plan", 2),
                                  ("architect-assess", 2), ("engineer-build", 1), ("architect-verify", 1)])


class ApprovalSummary(Scenario):
    """At the plan's approval the operator reads a summary of what they are approving."""

    def test_the_approval_stop_shows_the_plan_summary(self):
        a1, _ = codex_review_first("PASS", "Direction: extend the existing seam.")
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1)])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli._report(run.status, run.run_id, None)
        self.assertEqual(code, 2)
        self.assertIn("summary:  Direction: extend the existing seam.", out.getvalue())
        self.assertNotIn("feedback:", out.getvalue())

    def test_each_answer_is_recorded_beside_the_stop_it_answers(self):
        import telemetry
        saved = telemetry.open_work_item, telemetry.open_phase
        telemetry.open_work_item = lambda *args, **kwargs: ("%032x" % 1, "a" * 16)
        telemetry.open_phase = lambda client, values, phase: {"plan": "b" * 16, "build": "c" * 16}[phase]
        client = _Events()
        try:
            b1, _ = codex_review_first("BLOCKER", "the premise is wrong")
            run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, b1),
                              ("plan-e2-1", 0, "replanned\n"),
                              ("assess-e2-1", 0, codex_review_resumed("PASS", "Direction: B.")),
                              ("build-e3-1", 0, "built\n"), ("verify-e3-1", 0, codex_review_resumed("PASS"))],
                             telemetry=client)
            run.answer("use approach B")
            run.answer("yes")
        finally:
            telemetry.open_work_item, telemetry.open_phase = saved
        stops = [(e["name"], e["metadata"]["gate_reason"]) for e in client.events if e["name"] in ("human-gate", "human-answer")]
        self.assertEqual(stops, [("human-gate", "blocker"), ("human-answer", "blocker"),
                                 ("human-gate", "approval"), ("human-answer", "approval")])
        answers = {e["metadata"]["gate_reason"]: e for e in client.events if e["name"] == "human-answer"}
        self.assertEqual(answers["blocker"]["output"], {"answer": "use approach B"})
        self.assertEqual(answers["blocker"]["trace_context"]["parent_span_id"], "b" * 16)
        self.assertEqual(answers["approval"]["output"], {"answer": "yes"})
        self.assertEqual(answers["approval"]["trace_context"]["parent_span_id"], "a" * 16)
        self.assertEqual(answers["approval"]["trace_context"]["trace_id"], "%032x" % 1)


class CodexUpload(unittest.TestCase):
    """The architect's upload is the Stop hook Codex itself would send.

    Regression for empty `Codex Turn` rows: a resumed session writes a record
    before its next turn starts, the plugin opens an id-less turn for it, and
    without the stopped turn's id in the payload it exports that empty turn.
    """

    def test_upload_names_the_turn_that_just_stopped(self):
        import subprocess as sp
        import telemetry
        tmp = tempfile.mkdtemp(prefix="orch-codex-upload-")
        saved = (telemetry.CODEX_PLUGIN, telemetry.CODEX_ROLLOUTS, sp.run)
        calls = []
        try:
            bundle = os.path.join(tmp, "plugin", "dist", "index.mjs")
            os.makedirs(os.path.dirname(bundle))
            with open(bundle, "w", encoding="utf-8") as fh:
                fh.write("LANGFUSE_CODEX_TRACEPARENT")
            rollout = os.path.join(tmp, "rollout-x-thread-1.jsonl")
            with open(rollout, "w", encoding="utf-8") as fh:
                for record in ({"type": "event_msg", "payload": {"type": "task_started", "turn_id": "turn-a"}},
                               {"type": "event_msg", "payload": {"type": "task_complete"}},
                               {"type": "event_msg", "payload": {"type": "thread_settings_applied"}},
                               {"type": "event_msg", "payload": {"type": "task_started", "turn_id": "turn-b"}},
                               {"type": "event_msg", "payload": {"type": "task_complete"}}):
                    fh.write(json.dumps(record) + "\n")
            telemetry.CODEX_PLUGIN = bundle
            telemetry.CODEX_ROLLOUTS = os.path.join(tmp, "rollout-*-%s.jsonl")
            sp.run = lambda *args, **kwargs: calls.append(kwargs) or sp.CompletedProcess(args, 0, "", "")
            telemetry.upload_codex_session(_Events(), {"brain": "codex"}, "thread-1",
                                           {"run_id": "r1", "label": "l"}, "verify", "architect",
                                           telemetry._Span(traceparent="00-%032x-%016x-01" % (1, 2)))
        finally:
            telemetry.CODEX_PLUGIN, telemetry.CODEX_ROLLOUTS, sp.run = saved
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(len(calls), 1)
        payload = json.loads(calls[0]["input"])
        self.assertEqual((payload["hook_event_name"], payload["turn_id"]), ("Stop", "turn-b"))
        self.assertEqual(calls[0]["env"]["LANGFUSE_CODEX_TRACEPARENT"], "00-%032x-%016x-01" % (1, 2))
        # The same few tags as every other row: never the run, the round or the stage.
        self.assertEqual(calls[0]["env"]["LANGFUSE_CODEX_TAGS"],
                         ",".join(telemetry.tags({"run_id": "r1", "label": "l"})))

    def test_upload_is_sent_to_the_configured_host(self):
        """The uploader is told the host, so no user-level file decides where a transcript goes.

        The plugin's own default is Langfuse Cloud, which is where an architect's
        transcript would go if `~/.codex/langfuse.json` stopped naming a host.
        """
        import subprocess as sp
        import telemetry
        tmp = tempfile.mkdtemp(prefix="orch-codex-host-")
        saved = (telemetry.CODEX_PLUGIN, telemetry.CODEX_ROLLOUTS, sp.run, os.environ.get("LANGFUSE_HOST"),
                 os.environ.get("LANGFUSE_TRACING_ENVIRONMENT"), os.environ.get("LANGFUSE_RELEASE"))
        calls = []
        try:
            bundle = os.path.join(tmp, "plugin", "dist", "index.mjs")
            os.makedirs(os.path.dirname(bundle))
            with open(bundle, "w", encoding="utf-8") as fh:
                fh.write("LANGFUSE_CODEX_TRACEPARENT finalizeTurnId")
            with open(os.path.join(tmp, "rollout-x-thread-1.jsonl"), "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"type": "event_msg",
                                     "payload": {"type": "task_started", "turn_id": "t"}}) + "\n")
            telemetry.CODEX_PLUGIN = bundle
            telemetry.CODEX_ROLLOUTS = os.path.join(tmp, "rollout-*-%s.jsonl")
            os.environ["LANGFUSE_HOST"] = "http://langfuse.test:3000"
            os.environ["LANGFUSE_TRACING_ENVIRONMENT"] = "dev"
            os.environ["LANGFUSE_RELEASE"] = "0123456789ab"
            sp.run = lambda *args, **kwargs: calls.append(kwargs) or sp.CompletedProcess(args, 0, "", "")
            telemetry.upload_codex_session(_Events(), {"brain": "codex"}, "thread-1",
                                           {"run_id": "r1"}, "verify", "architect")
        finally:
            telemetry.CODEX_PLUGIN, telemetry.CODEX_ROLLOUTS, sp.run, host, environment, release = saved
            for name, value in (("LANGFUSE_HOST", host), ("LANGFUSE_TRACING_ENVIRONMENT", environment),
                                ("LANGFUSE_RELEASE", release)):
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["env"].get("LANGFUSE_CODEX_BASE_URL"), "http://langfuse.test:3000")
        # The architect's rows record the run's environment and release from what the uploader inherits.
        self.assertEqual((calls[0]["env"].get("LANGFUSE_TRACING_ENVIRONMENT"), calls[0]["env"].get("LANGFUSE_RELEASE")),
                         ("dev", "0123456789ab"))

    def test_a_plugin_build_missing_either_change_is_reported(self):
        import subprocess as sp
        import telemetry
        tmp = tempfile.mkdtemp(prefix="orch-codex-caps-")
        saved = (telemetry.CODEX_PLUGIN, telemetry.CODEX_ROLLOUTS, sp.run, set(telemetry._warned))
        reports = {}
        try:
            bundle = os.path.join(tmp, "plugin", "dist", "index.mjs")
            os.makedirs(os.path.dirname(bundle))
            with open(os.path.join(tmp, "rollout-x-thread-1.jsonl"), "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"type": "event_msg",
                                     "payload": {"type": "task_started", "turn_id": "t"}}) + "\n")
            telemetry.CODEX_PLUGIN = bundle
            telemetry.CODEX_ROLLOUTS = os.path.join(tmp, "rollout-*-%s.jsonl")
            sp.run = lambda *args, **kwargs: sp.CompletedProcess(args, 0, "", "")
            for name, content in (("both", "LANGFUSE_CODEX_TRACEPARENT finalizeTurnId"),
                                  ("no turn fix", "LANGFUSE_CODEX_TRACEPARENT"),
                                  ("no parent", "finalizeTurnId")):
                with open(bundle, "w", encoding="utf-8") as fh:
                    fh.write(content)
                telemetry._warned.clear()
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    telemetry.upload_codex_session(_Events(), {"brain": "codex"}, "thread-1",
                                                   {"run_id": "r1"}, "verify", "architect")
                reports[name] = err.getvalue()
        finally:
            telemetry.CODEX_PLUGIN, telemetry.CODEX_ROLLOUTS, sp.run, warned = saved
            telemetry._warned.clear()
            telemetry._warned.update(warned)
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(reports["both"], "")
        self.assertIn("empty", reports["no turn fix"])
        self.assertNotIn("nest", reports["no turn fix"])
        self.assertIn("nest", reports["no parent"])


class TraceLink(unittest.TestCase):
    """A run prints a direct link to its trace, built by the client from the real project id."""

    def test_trace_url_comes_from_the_client_or_is_none(self):
        import telemetry

        class Client:
            def __init__(self):
                self.asked = []

            def get_trace_url(self, *, trace_id=None):
                self.asked.append(trace_id)
                return "http://lf/traces/%s" % trace_id

        client = Client()
        self.assertEqual(telemetry.trace_url(client, "abc"), "http://lf/traces/abc")
        self.assertEqual(client.asked, ["abc"])
        self.assertIsNone(telemetry.trace_url(None, "abc"), "no client, no link")
        self.assertIsNone(telemetry.trace_url(client, None), "no trace, no link")

        class Boom:
            def get_trace_url(self, *, trace_id=None):
                raise RuntimeError("no project id")

        warned = set(telemetry._warned)
        telemetry._warned.clear()
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertIsNone(telemetry.trace_url(Boom(), "abc"), "a failure degrades to no link")
        finally:
            telemetry._warned.clear()
            telemetry._warned.update(warned)

    def status(self, stop):
        return {"state": {"status": "READY_FOR_HUMAN", "worktree_path": "/w"}, "stop": stop, "lines": [],
                "timeline": [], "queue": "q"}

    def test_a_stop_prints_the_link_when_there_is_one(self):
        for reason, code in (("final", 0), ("approval", 2)):
            stop = {"id": "r1:1", "reason": reason, "phase": "plan", "todo": "/t", "feedback": "the summary",
                    "hint": "h", "actions": []}
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(cli._report(self.status(stop), "r1", "http://lf/traces/xyz"), code)
            self.assertIn("trace:    http://lf/traces/xyz", out.getvalue())

    def test_no_link_line_without_a_url(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli._report({"state": {"status": "ABORTED"}, "stop": None, "lines": [], "timeline": [], "queue": "q"},
                        "r1", None)
        self.assertNotIn("trace:", out.getvalue())


class TraceContract(Scenario):
    """The trace is an interface: saved views, the dashboard and the scores are built on its names and fields."""

    def _flow(self):
        """A round sent back, the approval, a build whose session was lost and rehydrated, a verified build."""
        client = _Events()
        run = self.drive([tuple(step) for step in trace_rows.script()], telemetry=client)
        run.answer("yes")
        self.assertEqual(run.stop["reason"], "final")
        return client

    def test_every_row_is_one_of_the_contracts_kinds_and_carries_its_version(self):
        import telemetry
        client = self._flow()
        names = [event["name"] for event in client.events]
        self.assertEqual(set(names), set(telemetry.ROW_NAMES))
        self.assertEqual(names.count("orchestration-run"), 1, "one work item per run")
        self.assertEqual({event.get("version") for event in client.events}, {telemetry.SCHEMA_VERSION})

    def test_quality_is_scored_where_it_is_judged(self):
        client = self._flow()
        verdicts = [score for score in client.scores if score["name"] == "architect_verdict"]
        self.assertEqual([score["value"] for score in verdicts], ["PATCH", "PASS", "PASS"])
        for score in verdicts:
            self.assertEqual(score["data_type"], "CATEGORICAL")
            self.assertTrue(score.get("observation_id"))
        outcomes = {score["name"]: score for score in client.scores if score["name"] != "architect_verdict"}
        self.assertEqual({name: score["value"] for name, score in outcomes.items()},
                         {"plan_first_pass": 0.0, "build_first_pass": 1.0, "final_verify_pass": 1.0})
        for name, score in outcomes.items():
            self.assertEqual(score["data_type"], "BOOLEAN", name)
            self.assertNotIn("observation_id", score, name)
            self.assertEqual(score["score_id"], "%s-%s" % (score["trace_id"], name))

    def test_a_lost_session_is_a_warning_on_a_stage_that_still_succeeded(self):
        client = self._flow()
        build = [event for event in client.events if event["name"] == "engineer-build"]
        self.assertEqual(len(build), 1)
        self.assertEqual((build[0].get("level"), build[0]["metadata"].get("error_type")), ("WARNING", "session_lost"))
        self.assertEqual(build[0]["output"], {
            "response": "built",
            "warning": "the engineer session to resume was not found; a fresh one was started "
                       "and given the whole task again"})
        self.assertEqual([event["name"] for event in client.events if event.get("level") == "ERROR"], ["final-diff"])

    def test_a_failed_stage_is_an_error_with_a_stable_type(self):
        failure = launch.RoleTimeout("role-run did not finish within 3600s")

        def runner(*args, **kwargs):
            raise failure

        client = _Events()
        E.host([], telemetry=client)
        E.hosts()[E.WSL_QUEUE].runner = runner
        run = E.Run()
        self.addCleanup(run.cleanup)
        self.assertEqual(run.stop["reason"], "failed")
        self.assertIn("timeout", run.stop["feedback"])
        stage = [event for event in client.events if event["name"] == "engineer-plan"][0]
        self.assertEqual((stage["level"], stage["metadata"]["error_type"]), ("ERROR", "timeout"))
        self.assertIn("did not finish within 3600s", stage["status_message"])
        self.assertEqual(stage["output"], {"error": stage["status_message"]})
        self.assertEqual(client.scores, [], "a stage that gave no verdict is not scored")

    def test_failures_are_classified_narrowly(self):
        import nodes as N
        cases = [(launch.RoleTimeout("late"), "timeout"),
                 (subprocess.TimeoutExpired(["agent"], 1), "timeout"),
                 (N.TransportError("rc=1"), "agent_exit"),
                 (N.ContentError("no verdict"), "malformed_output"),
                 (launch.ExecutorError("claude is not installed"), "executor"),
                 (A.GitViolation("staged"), "git_violation"),
                 (KeyError("phase"), "internal")]
        self.assertEqual([N.error_type(exc) for exc, _ in cases], [kind for _, kind in cases])

    def test_the_outcome_is_scored_once_known_and_a_stop_is_not(self):
        import telemetry
        for status, expected in (("READY_FOR_HUMAN", [1.0]), ("ABORTED", [0.0]), (None, [])):
            client = _Events()
            values = {"run_id": "r1", "trace_id": "f" * 32}
            if status:
                values["status"] = status
            telemetry.outcome_score(client, values)
            self.assertEqual([score["value"] for score in client.scores
                              if score["name"] == "final_verify_pass"], expected, status)

    def test_a_first_judgement_retried_after_a_crash_replaces_its_score(self):
        import telemetry
        client = _Events()
        for _ in range(2):
            span = telemetry._Span(_FakeContext(), _FakeSpan(), "00-%032x-%016x-01" % (1, 2),
                                   client=client, phase="build", round=1)
            telemetry.end(span, verdict="PASS")
        telemetry.end(telemetry._Span(_FakeContext(), _FakeSpan(), "00-%032x-%016x-01" % (1, 3),
                                      client=client, phase="build", round=1), response="built")
        first = [score for score in client.scores if score["name"] == "build_first_pass"]
        self.assertEqual((len(first), len({score["score_id"] for score in first})), (2, 1))
        self.assertEqual(len([score for score in client.scores if score["name"] == "architect_verdict"]), 2,
                         "an engineer's step is not a judgement")

    def test_tags_are_few_and_never_name_a_run(self):
        import telemetry
        tags = telemetry.tags({"repo": os.path.basename(REPO), "target": "wsl"})
        self.assertEqual([tag.split(":", 1)[0] for tag in tags], ["workflow", "repo", "target", "source"])
        self.assertEqual(tags[:2], ["workflow:feature", "repo:%s" % os.path.basename(REPO)])
        self.assertIn(tags[2], ("target:wsl", "target:linux", "target:windows", "target:macos"))
        self.assertEqual(tags[3], "source:manual")

    def test_every_emitter_shares_the_runs_environment_and_release(self):
        """Our client reads them, the Codex uploader inherits them, and a Claude role-run is handed them.

        The Claude plugin builds its own client inside the role-run, so it records
        only what that process's environment says.
        """
        import langfuse
        import telemetry
        names = ("LANGFUSE_TRACING_ENVIRONMENT", "LANGFUSE_RELEASE", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
        saved_env = {name: os.environ.get(name) for name in names}
        saved = (langfuse.Langfuse, telemetry._release, telemetry.SECRETS_FILE, telemetry._SECRETS)
        made = []

        class Client:
            def __init__(self, **kwargs):
                made.append(kwargs)

        tmp = tempfile.mkdtemp(prefix="orch-dimensions-")
        try:
            for name in names[:2]:
                os.environ.pop(name, None)
            os.environ.update(LANGFUSE_PUBLIC_KEY="pk-lf-test", LANGFUSE_SECRET_KEY="sk-lf-test")
            langfuse.Langfuse, telemetry._release = Client, (lambda: "0123456789ab-dirty")
            telemetry.SECRETS_FILE = os.path.join(tmp, "absent.env")
            self.assertIsInstance(telemetry.resolve(), Client)
            self.assertEqual((os.environ["LANGFUSE_TRACING_ENVIRONMENT"], os.environ["LANGFUSE_RELEASE"]),
                             ("dev", "0123456789ab-dirty"))
            self.assertIs(made[0].get("mask"), telemetry.mask, "what this component writes is masked")
            traceparent = "00-%032x-%016x-01" % (1, 2)
            self.assertEqual(telemetry.harness_env(POL["roles"]["engineer"], telemetry._Span(traceparent=traceparent),
                                                   {}, "plan", "engineer"),
                             {"CC_LANGFUSE_TRACEPARENT": traceparent,
                              "LANGFUSE_TRACING_ENVIRONMENT": "dev",
                              "LANGFUSE_RELEASE": "0123456789ab-dirty"})
            os.environ["LANGFUSE_TRACING_ENVIRONMENT"] = "ci"
            telemetry.resolve()
            self.assertEqual(os.environ["LANGFUSE_TRACING_ENVIRONMENT"], "ci", "an explicit choice wins")
        finally:
            langfuse.Langfuse, telemetry._release, telemetry.SECRETS_FILE, telemetry._SECRETS = saved
            for name, value in saved_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
            shutil.rmtree(tmp, ignore_errors=True)

    def test_the_release_names_the_orchestrator_code_that_ran(self):
        import telemetry
        tmp = tempfile.mkdtemp(prefix="orch-release-")
        saved_root, warned = telemetry.REPO_ROOT, set(telemetry._warned)
        code = os.path.join(tmp, "workflow.py")
        try:
            for path, text in ((code, "x = 1\n"), (os.path.join(tmp, "notes.txt"), "n\n")):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
            _git(tmp, "init", "-q")
            _git(tmp, "add", "-A")
            _git(tmp, "commit", "-q", "-m", "base")
            head = _git(tmp, "rev-parse", "--short=12", "HEAD").decode().strip()
            telemetry.REPO_ROOT = tmp
            self.assertEqual(telemetry._release(), head)
            # This repository is the orchestrator, so any change in it is a different release.
            with open(code, "w", encoding="utf-8") as fh:
                fh.write("x = 2\n")
            self.assertEqual(telemetry._release(), head + "-dirty")
            telemetry.REPO_ROOT = os.path.join(tmp, "missing")
            telemetry._warned.clear()
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertIsNone(telemetry._release(), "a release that could not be read is not reported as one")
            self.assertIn("release", err.getvalue())
        finally:
            telemetry.REPO_ROOT = saved_root
            telemetry._warned.clear()
            telemetry._warned.update(warned)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_secrets_are_masked_in_what_this_component_writes(self):
        import telemetry
        # Assembled at run time, so no secret-shaped literal lives in the repository.
        leaks = ["sk-lf-" + "0a1b2c3d-" * 3 + "0a1b",
                 "sk-ant-api03-" + "A1b2C3d4" * 4,
                 "ghp_" + "A1b2C3d4E5" * 4,
                 "github_pat_" + "A1b2C3d4E5" * 3,
                 "glpat-" + "A1b2C3d4E5" * 2,
                 "AKIA" + "ABCDEFGHIJKLMNOP",
                 "xoxb-" + "1234567890-abcdefghij",
                 "AIza" + "A1b2C3d4E5" * 3 + "A1b2C",
                 "Bearer " + "A1b2C3d4E5" * 3,
                 "-----BEGIN OPENSSH " + "PRIVATE KEY-----\nAAAA\n-----END OPENSSH " + "PRIVATE KEY-----",
                 "stack-database-password", "the-secret-key-from-the-environment"]
        benign = "scikit sk-learn | token = get_token() | an AKIA prefix | Bearer auth | ghp_short"
        tmp = tempfile.mkdtemp(prefix="orch-mask-")
        saved = (telemetry.SECRETS_FILE, telemetry._SECRETS, os.environ.get("LANGFUSE_SECRET_KEY"))
        try:
            telemetry.SECRETS_FILE = os.path.join(tmp, "langfuse.env")
            with open(telemetry.SECRETS_FILE, "w", encoding="utf-8") as fh:
                fh.write("POSTGRES_PASSWORD=stack-database-password\nREDIS_AUTH=short\n"
                         "CLICKHOUSE_USER=clickhouse\nLANGFUSE_PUBLIC_KEY=pk-lf-public-half-of-the-pair\n")
            os.environ["LANGFUSE_SECRET_KEY"] = "the-secret-key-from-the-environment"
            telemetry._remember_secrets()
            for secret in leaks:
                masked = telemetry.mask(data="before %s after" % secret)
                self.assertNotIn(secret, masked)
                self.assertTrue(masked.startswith("before ") and masked.endswith(" after"),
                                "only the secret goes, not its surroundings")
            nested = telemetry.mask(data={"output": [leaks[0], 3, None, True], "note": benign})
            self.assertEqual(nested["output"][1:], [3, None, True])
            self.assertNotIn(leaks[0], nested["output"][0])
            self.assertEqual(nested["note"], benign, "ordinary text is left alone")
            self.assertIn("clickhouse", telemetry.mask(data="the clickhouse user"),
                          "only the values of secret-named entries are secrets")
            self.assertIn("short", telemetry.mask(data="a short word"),
                          "a value too short to match safely is left alone")
            self.assertIn("pk-lf-public-half-of-the-pair", telemetry.mask(data="key pk-lf-public-half-of-the-pair"),
                          "the public key is public: the SDK itself writes it into every row's metadata")
        finally:
            telemetry.SECRETS_FILE, telemetry._SECRETS = saved[0], saved[1]
            if saved[2] is None:
                os.environ.pop("LANGFUSE_SECRET_KEY", None)
            else:
                os.environ["LANGFUSE_SECRET_KEY"] = saved[2]
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_diff_that_held_a_secret_is_redacted_and_says_so(self):
        import telemetry
        leak = "ghp_" + "A1b2C3d4E5" * 4
        client = _Events()
        for patch in ("+token = '%s'\n" % leak, "+plain\n"):
            read = lambda path, _patch=patch: {
                "base": "abc1234", "summary": " 1 file changed", "summary_total": 15,
                "patch": _patch, "offset": 0, "next": len(_patch), "total": len(_patch)}
            telemetry.final_diff(client, {"run_id": "r1", "status": "READY_FOR_HUMAN",
                                          "worktree_path": "/wt"}, read)
        leaked, plain = (event["output"] for event in client.events)
        self.assertNotIn(leak, leaked["patch"])
        self.assertEqual((leaked["redacted"], plain["redacted"]), (True, False))
        self.assertEqual(plain["patch"], "+plain\n", "a patch without a secret stays byte for byte")

    def test_a_failed_codex_upload_marks_its_stage_degraded(self):
        import subprocess as sp
        import telemetry
        tmp = tempfile.mkdtemp(prefix="orch-codex-degraded-")
        saved = (telemetry.CODEX_PLUGIN, telemetry.CODEX_ROLLOUTS, sp.run, set(telemetry._warned))
        levels = {}
        try:
            bundle = os.path.join(tmp, "plugin", "dist", "index.mjs")
            os.makedirs(os.path.dirname(bundle))
            with open(bundle, "w", encoding="utf-8") as fh:
                fh.write("LANGFUSE_CODEX_TRACEPARENT finalizeTurnId")
            with open(os.path.join(tmp, "rollout-x-thread-1.jsonl"), "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"type": "event_msg",
                                     "payload": {"type": "task_started", "turn_id": "t"}}) + "\n")
            telemetry.CODEX_PLUGIN = bundle
            telemetry.CODEX_ROLLOUTS = os.path.join(tmp, "rollout-*-%s.jsonl")
            for outcome, rc in (("uploaded", 0), ("failed", 1)):
                sp.run = lambda *args, _rc=rc, **kwargs: sp.CompletedProcess(args, _rc, "", "boom")
                span = _FakeSpan()
                telemetry._warned.clear()
                with contextlib.redirect_stderr(io.StringIO()):
                    telemetry.upload_codex_session(
                        _Events(), {"brain": "codex"}, "thread-1", {"run_id": "r1"}, "verify", "architect",
                        telemetry._Span(_FakeContext(), span, "00-%032x-%016x-01" % (1, 2)))
                levels[outcome] = [(update["level"], update["metadata"]["error_type"])
                                   for update in span.updates if "level" in update]
        finally:
            telemetry.CODEX_PLUGIN, telemetry.CODEX_ROLLOUTS, sp.run, warned = saved
            telemetry._warned.clear()
            telemetry._warned.update(warned)
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(levels, {"uploaded": [], "failed": [("WARNING", "telemetry_degraded")]})

    def test_the_dashboard_counts_only_what_the_trace_writes(self):
        """Each widget is valid for the API it is sent to, and filters on names the trace actually writes.

        A renamed row would otherwise leave a widget counting nothing, silently.
        """
        import telemetry
        from langfuse.api.unstable.dashboard_widgets.types import CreateDashboardWidgetRequest
        tools = os.path.join(PKG, "tools")
        sys.path.insert(0, tools)
        try:
            import langfuse_dashboard as dashboard
        finally:
            sys.path.remove(tools)
        known = {"observations": set(telemetry.ROW_NAMES)}
        for view in ("scores-numeric", "scores-boolean", "scores-categorical"):
            known[view] = set(telemetry.SCORE_NAMES)
        self.assertTrue(dashboard.WIDGETS)
        for widget in dashboard.WIDGETS:
            CreateDashboardWidgetRequest(**widget)
            for condition in widget["filters"]:
                if condition["column"] == "name":
                    value = condition["value"]
                    values = set(value) if isinstance(value, list) else {value}
                    self.assertTrue(values <= known[widget["view"]], (widget["name"], values))


if __name__ == "__main__":
    unittest.main()
