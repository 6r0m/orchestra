"""A role turn in a live terminal: it ends on its own prompt's completion only, and leaves nothing behind.

Runs against `fake_cli.py` standing in for `claude` and `codex` on PATH, through the real
`terminal.run_turn`, `ptyhost.py`, `turn_hook.py` and `launch.py` tree, on both hosts.
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
import uuid

# The suite's own folder, reached from this concern's folder inside it, and the
# checkout above both: the shared harness and the fixtures live at the suite root.
HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
for path in (PKG, HERE):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.application import activities  # noqa: E402
from app.agents import launch  # noqa: E402
from app.agents import nodes as N  # noqa: E402
from app.agents import terminal  # noqa: E402
from tests.agents.test_launch import alive, force_kill, gone_within  # noqa: E402
import folders  # noqa: E402

WINDOWS = sys.platform.startswith("win")
FAKE = os.path.join(HERE, "fake_cli.py")


def install_fakes(directory):
    for brain in ("claude", "codex"):
        if WINDOWS:
            with open(os.path.join(directory, brain + ".cmd"), "w", encoding="utf-8") as fh:
                fh.write('@"%s" "%s" %s %%*\r\n' % (sys.executable, FAKE, brain))
        else:
            path = os.path.join(directory, brain)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('#!/bin/sh\nexec "%s" "%s" %s "$@"\n' % (sys.executable, FAKE, brain))
            os.chmod(path, 0o755)


class Turns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bin = tempfile.mkdtemp(prefix="orch-fake-cli-")
        install_fakes(cls.bin)
        cls.path = os.environ["PATH"]
        os.environ["PATH"] = cls.bin + os.pathsep + cls.path

    @classmethod
    def tearDownClass(cls):
        os.environ["PATH"] = cls.path
        shutil.rmtree(cls.bin, ignore_errors=True)

    def setUp(self):
        self.run_id = "test-terminal-%s" % uuid.uuid4().hex[:8]
        self.rdir = terminal.run_dir(self.run_id)
        self.worktree = tempfile.mkdtemp(prefix="orch-term-wt-")
        self.addCleanup(folders.remove, self.worktree)
        self.addCleanup(shutil.rmtree, self.rdir, True)
        self.addCleanup(terminal.close_run, self.run_id)

    def turn(self, prompt, brain="claude", stage="build", resume=None, timeout=60, name=None):
        if brain == "claude":
            argv = ["claude", "--resume" if resume else "--session-id", resume or str(uuid.uuid4()),
                    "--permission-mode", "dontAsk", "--allowedTools", "Edit(./**)"]
        else:
            argv = ["codex", "resume", resume] if resume else ["codex"]
            argv += ["--sandbox", "read-only", "--ask-for-approval", "never"]
        return terminal.run_turn(self.worktree, argv, self.rdir, name or "%s-e1-1" % stage, prompt, timeout,
                                 activities.agent_env({}), brain=brain)

    def record(self, role="engineer"):
        try:
            with open(terminal.record_path(self.run_id, role), "rb") as fh:
                return terminal.plain(fh.read())
        except FileNotFoundError:
            return ""

    def test_claude_turn_ends_on_its_completion_and_stays_live(self):
        rc, out = self.turn("complete this")
        self.assertEqual((rc, out), (0, "done complete"))
        self.assertIn("answer for complete", self.record())
        self.assertTrue(terminal.get(self.run_id, "engineer").live(), "a finished turn leaves its agent running")
        logs = os.path.join(self.rdir, "logs")
        for ext in ("prompt", "out", "err", "events"):
            self.assertTrue(os.path.exists(os.path.join(logs, "build-e1-1.%s" % ext)), ext)

    def test_the_prompt_survives_an_option_that_takes_several_values(self):
        worktree_skills = tempfile.mkdtemp(prefix="orch-skills-")
        self.addCleanup(shutil.rmtree, worktree_skills, True)
        argv = ["claude", "--session-id", str(uuid.uuid4()), "--add-dir", worktree_skills]
        rc, out = terminal.run_turn(self.worktree, argv, self.rdir, "build-e1-1", "complete this", 60,
                                    activities.agent_env({}), brain="claude")
        self.assertEqual((rc, out), (0, "done complete"))

    def test_a_multiline_prompt_reaches_the_agent_whole(self):
        if WINDOWS:
            self.skipTest("the fake runs through a .cmd wrapper, which cannot carry a newline in an argument")
        prompt = '/implement-approved-change\n\n# Task\ncomplete "quoted" $HOME `x` ; done'
        rc, out = self.turn(prompt)
        self.assertEqual(rc, 0)
        with open(os.path.join(self.rdir, "logs", "build-e1-1.events"), encoding="utf-8") as fh:
            submitted = [json.loads(line) for line in fh if '"UserPromptSubmit"' in line]
        self.assertEqual(submitted[0]["prompt"], prompt)

    def test_completions_of_anything_else_never_end_the_turn(self):
        rc, out = self.turn("foreign then mine")
        self.assertEqual((rc, out), (0, "done foreign"))
        rc, out = self.turn("foreign then mine", brain="codex", stage="verify")
        self.assertEqual(rc, 0)
        lines = [json.loads(line) for line in out.splitlines()]
        self.assertEqual(lines[1]["item"]["text"], "done foreign")

    def test_a_stop_with_a_background_task_running_does_not_end_the_turn(self):
        self.assertEqual(self.turn("background task"), (0, "done background"))

    def test_a_lost_session_says_so_for_rehydration(self):
        for brain, stage in (("claude", "build"), ("codex", "verify")):
            resume = str(uuid.uuid4())
            rc, out = self.turn("lost it", brain=brain, stage=stage, resume=resume, name="%s-e1-9" % stage)
            with open(os.path.join(self.rdir, "logs", "%s-e1-9.err" % stage), encoding="utf-8") as fh:
                err = fh.read()
            self.assertEqual(N.classify_failure({"brain": brain}, resume, rc, out, err), "session_lost", brain)

    def test_control_the_matcher_refuses_what_a_first_event_rule_would_accept(self):
        session, mine, other = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        events = [{"_hook": "Stop", "session_id": session, "prompt_id": other, "last_assistant_message": "theirs"},
                  {"_hook": "UserPromptSubmit", "session_id": session, "prompt_id": mine, "prompt": "p"}]
        self.assertEqual(events[0]["last_assistant_message"], "theirs", "a first-Stop rule would end the turn here")
        self.assertIsNone(terminal.completion("claude", events, "p", session))
        events.append({"_hook": "Stop", "session_id": "elsewhere", "prompt_id": mine, "last_assistant_message": "x"})
        self.assertIsNone(terminal.completion("claude", events, "p", session))
        events.append({"_hook": "Stop", "session_id": session, "prompt_id": mine, "last_assistant_message": "wait",
                       "background_tasks": [{"status": "running"}]})
        self.assertIsNone(terminal.completion("claude", events, "p", session), "a background task still runs")
        events.append({"_hook": "Stop", "session_id": session, "prompt_id": mine, "last_assistant_message": "mine"})
        self.assertEqual(terminal.completion("claude", events, "p", session), (True, "mine", session))
        redirected = [events[1], {"_hook": "UserPromptSubmit", "session_id": session, "prompt_id": other,
                                  "prompt": "do this instead"},
                      {"_hook": "Stop", "session_id": session, "prompt_id": other, "last_assistant_message": "steered"}]
        self.assertEqual(terminal.completion("claude", redirected, "p", session), (True, "steered", session),
                         "a prompt submitted after ours in this turn completes it")
        self.assertIsNone(terminal.completion("claude", redirected[1:], "p", session), "not before ours")
        title = {"_hook": "notify", "type": "agent-turn-complete", "thread-id": "t1",
                 "input-messages": ["Generate a title: p"], "last-assistant-message": "{}"}
        self.assertIsNone(terminal.completion("codex", [title], "p", None))
        resumed = dict(title, **{"thread-id": "t2", "input-messages": ["p"], "last-assistant-message": "ok"})
        self.assertIsNone(terminal.completion("codex", [resumed], "p", "t1"), "another thread when resuming")
        self.assertEqual(terminal.completion("codex", [title, resumed], "p", None), (True, "ok", "t2"))
        later = dict(resumed, **{"input-messages": ["earlier", "p", "steer"]})
        self.assertEqual(terminal.completion("codex", [later], "p", "t2"), (True, "ok", "t2"),
                         "a thread's inputs are cumulative")

    def test_the_codex_thread_comes_from_its_turn_and_resumes_by_it(self):
        rc, out = self.turn("complete first", brain="codex", stage="assess")
        thread = N.extract_session({"brain": "codex"}, None, None, rc, out)
        self.assertNotEqual(thread, None)
        rc, out = self.turn("complete again", brain="codex", stage="verify", resume=thread, name="verify-e2-1")
        self.assertEqual(rc, 0)
        self.assertIn("done complete", out)

    def test_stop_failure_and_exit_without_completion_fail_and_leave_no_agent(self):
        rc, _ = self.turn("failure please")
        self.assertEqual(rc, 1)
        self.assertFalse(terminal.get(self.run_id, "engineer").live())
        rc, _ = self.turn("exit now", name="build-e1-2")
        self.assertEqual(rc, 3)
        self.assertIn("giving up", self.record())
        with open(os.path.join(self.rdir, "logs", "build-e1-2.err"), encoding="utf-8") as fh:
            self.assertIn("giving up", fh.read(), "the terminal's text is the turn's error log")

    def test_a_timeout_ends_the_agent(self):
        with self.assertRaises(launch.RoleTimeout):
            self.turn("hang forever", timeout=3)
        self.assertFalse(terminal.get(self.run_id, "engineer").live())

    def test_the_next_turn_replaces_the_agent_and_appends_to_the_record(self):
        session = str(uuid.uuid4())
        self.turn("complete one", resume=None)
        first = terminal.get(self.run_id, "engineer").agent
        self.turn("complete two", resume=session, name="build-e1-2")
        self.assertIsNotNone(first.returncode(), "the previous agent process ended")
        text = self.record()
        self.assertLess(text.index("answer for complete"), text.rindex("answer for complete"))
        self.assertEqual(text.count("fake claude ready"), 2)

    def test_esc_and_typing_reach_the_agent_and_an_interrupt_completes_nothing(self):
        for brain, stage in (("claude", "build"), ("codex", "verify")):
            with self.subTest(brain=brain):
                self.steer(brain, stage)

    def steer(self, brain, stage):
        result = {}
        role = "engineer" if stage == "build" else "architect"
        resume = str(uuid.uuid4()) if brain == "codex" else None
        worker = threading.Thread(target=lambda: result.update(
            value=self.turn("interrupt me", brain=brain, stage=stage, resume=resume, timeout=60)))
        worker.start()
        term = self._wait_for(lambda: terminal.get(self.run_id, role))
        self._wait_for(lambda: "working" in self.record(role))
        term.type(b"\x1b")
        self._wait_for(lambda: "Interrupted" in self.record(role))
        time.sleep(2)
        self.assertTrue(worker.is_alive(), "Esc must not end the turn")
        term.type(b"go on\r")
        worker.join(30)
        rc, out = result["value"]
        self.assertEqual(rc, 0)
        self.assertIn("resumed with go on", out, "the operator's redirect completes the controller's turn")

    def test_closing_the_run_ends_its_agents_and_their_descendants(self):
        pid_file = os.path.join(self.worktree, "descendant.pid")
        self.turn("complete detach:%s" % pid_file)
        pid = int(open(pid_file).read())
        self.addCleanup(force_kill, pid)
        self.assertTrue(alive(pid))
        terminal.close_run(self.run_id)
        self.assertTrue(gone_within(pid, 15), "a detached descendant outlived its run's close")
        self.assertIsNone(terminal.get(self.run_id, "engineer"))

    def _wait_for(self, check, seconds=30):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            value = check()
            if value:
                return value
            time.sleep(0.1)
        self.fail("timed out")


OWNER = textwrap.dedent("""
    import os, sys, time, uuid
    sys.path[:0] = [%(pkg)r]
    from app.application import activities
    from app.agents import terminal
    os.environ["PATH"] = %(bin)r + os.pathsep + os.environ["PATH"]
    run_id, worktree, pid_file, uncontained = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] == "uncontained"
    if uncontained:
        # The control: the same descendant started outside any terminal's tree.
        import subprocess
        code = "import os, sys, time\\nopen(sys.argv[1], 'w').write(str(os.getpid()))\\ntime.sleep(600)\\n"
        # As fake_cli.detach does: a console of its own with no window, never none, which would be shown.
        flags = ({"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
                 if sys.platform.startswith("win") else {"start_new_session": True})
        subprocess.Popen([sys.executable, "-c", code, pid_file], **flags)
        while not os.path.exists(pid_file) or not open(pid_file).read():
            time.sleep(0.05)
    else:
        terminal.run_turn(worktree, ["claude", "--session-id", str(uuid.uuid4())], terminal.run_dir(run_id),
                          "build-e1-1", "complete detach:" + pid_file, 60, activities.agent_env({}),
                          brain="claude")
    print("ready", flush=True)
    time.sleep(600)
""")


class OwnerDeath(unittest.TestCase):
    """The worker's death ends a live terminal's agent and everything it started."""

    def setUp(self):
        self.bin = tempfile.mkdtemp(prefix="orch-fake-cli-")
        install_fakes(self.bin)
        self.work = tempfile.mkdtemp(prefix="orch-term-owner-")
        self.addCleanup(shutil.rmtree, self.bin, True)
        self.addCleanup(shutil.rmtree, self.work, True)

    def survives_owner_death(self, mode):
        run_id = "test-terminal-%s" % uuid.uuid4().hex[:8]
        self.addCleanup(shutil.rmtree, terminal.run_dir(run_id), True)
        pid_file = os.path.join(self.work, "%s.pid" % mode)
        owner = subprocess.Popen([sys.executable, "-c", OWNER % {"pkg": PKG, "bin": self.bin},
                                  run_id, self.work, pid_file, mode], stdout=subprocess.PIPE)
        self.assertEqual(owner.stdout.readline().strip(), b"ready")
        pid = int(open(pid_file).read())
        self.addCleanup(force_kill, pid)
        owner.kill()
        owner.wait()
        return not gone_within(pid, 15)

    def test_a_worker_killed_with_a_live_terminal_leaves_nothing(self):
        self.assertFalse(self.survives_owner_death("contained"))

    def test_control_a_descendant_outside_the_terminal_survives(self):
        self.assertTrue(self.survives_owner_death("uncontained"))


class Socket(unittest.TestCase):
    """The terminal's WebSocket: the workbench's token and origin, the record, then live bytes."""

    PORT, WORKBENCH = 18391, 18390

    @classmethod
    def setUpClass(cls):
        terminal.serve(cls.PORT, cls.WORKBENCH)

    def setUp(self):
        self.run_id = "test-terminal-%s" % uuid.uuid4().hex[:8]
        self.addCleanup(shutil.rmtree, terminal.run_dir(self.run_id), True)
        self.addCleanup(terminal.close_run, self.run_id)

    def connect(self, origin="http://127.0.0.1:%d" % WORKBENCH, token=None, path=None, in_url=False):
        from websockets.asyncio.client import connect
        token = terminal.token() if token is None else token
        url = "ws://127.0.0.1:%d/%s" % (self.PORT, path or "%s/engineer" % self.run_id)
        if in_url:
            # What the page must never do: a URL is printed to the browser's console and written to logs.
            return connect(url + "?token=" + token, origin=origin, max_size=None,
                           subprotocols=[terminal.PROTOCOL])
        return connect(url, origin=origin, max_size=None,
                       subprotocols=[terminal.PROTOCOL, terminal.TOKEN_PROTOCOL + token])

    def exchange(self, **kwargs):
        async def talk():
            async with self.connect(**kwargs) as ws:
                status = json.loads(await ws.recv())
                data = b""
                try:
                    while True:
                        data += await asyncio.wait_for(ws.recv(), 1)
                except (asyncio.TimeoutError, Exception):
                    pass
                return status, data
        return asyncio.run(talk())

    def refused(self, **kwargs):
        from websockets.exceptions import InvalidStatus
        with self.assertRaises(InvalidStatus) as caught:
            self.exchange(**kwargs)
        return caught.exception.response.status_code

    def test_another_origin_or_a_missing_token_is_refused(self):
        self.assertEqual(self.refused(origin="http://evil.example"), 403)
        self.assertEqual(self.refused(token="wrong"), 403)
        self.assertEqual(self.refused(path="%s/nobody" % self.run_id), 404)
        self.assertEqual(self.refused(in_url=True), 403,
                         "the token is read from the handshake's header only, so a URL never carries it")

    def test_a_live_terminal_sends_its_record_then_its_bytes_and_takes_keystrokes(self):
        term = terminal.open_terminal(self.run_id, "engineer")
        term.emit(b"before\r\n")
        typed = []
        pump = threading.Thread(target=lambda: None)
        pump.start()
        term.agent = type("Agent", (), {"write": lambda self, data: typed.append(data),
                                        "returncode": lambda self: None, "end": lambda self: None,
                                        "pump": pump})()

        async def talk():
            async with self.connect() as ws:
                self.assertEqual(json.loads(await ws.recv()), {"live": True})
                self.assertEqual(await ws.recv(), b"before\r\n")
                term.emit(b"after\r\n")
                self.assertEqual(await asyncio.wait_for(ws.recv(), 5), b"after\r\n")
                await ws.send("\x1b")
                for _ in range(50):
                    if typed:
                        break
                    await asyncio.sleep(0.1)
        asyncio.run(talk())
        self.assertEqual(typed, [b"\x1b"])

    def test_a_viewer_is_told_when_the_agent_under_the_terminal_goes(self):
        # A failed step keeps the terminal and its record but ends its agent: what is typed reaches nobody.
        term = terminal.open_terminal(self.run_id, "engineer")
        term.emit(b"the turn\r\n")
        pump = threading.Thread(target=lambda: None)
        pump.start()
        term.agent = type("Agent", (), {"write": lambda self, data: None, "returncode": lambda self: None,
                                        "end": lambda self: None, "pump": pump})()

        async def talk():
            async with self.connect() as ws:
                self.assertEqual(json.loads(await ws.recv()), {"live": True})
                self.assertEqual(await ws.recv(), b"the turn\r\n")
                terminal.end_agent(self.run_id, "engineer")
                return json.loads(await asyncio.wait_for(ws.recv(), 5))
        self.assertEqual(asyncio.run(talk()), {"live": False}, "the viewer watching is told")
        self.assertEqual(self.exchange()[0], {"live": False}, "and so is a page that attaches afterwards")

    def test_closing_a_run_closes_its_viewers_so_they_reattach(self):
        term = terminal.open_terminal(self.run_id, "engineer")
        term.emit(b"turn one\r\n")

        async def talk():
            async with self.connect() as ws:
                self.assertEqual(json.loads(await ws.recv()), {"live": False},
                                 "a terminal between turns is not live, and takes no keystrokes")
                await ws.recv()
                terminal.close_run(self.run_id)
                try:
                    while True:
                        await asyncio.wait_for(ws.recv(), 10)
                except asyncio.TimeoutError:
                    return "still open"
                except Exception:
                    return "closed"
        self.assertEqual(asyncio.run(talk()), "closed")

    def test_a_closed_terminal_replays_its_record_read_only(self):
        term = terminal.open_terminal(self.run_id, "architect")
        term.emit(b"what it said\r\n")
        terminal.close_run(self.run_id)
        status, data = self.exchange(path="%s/architect" % self.run_id)
        self.assertEqual((status, data), ({"live": False}, b"what it said\r\n"))


class Lifecycle(unittest.TestCase):
    """The activities around a run's terminals: no agent at a merge or discard, none after a failed step."""

    def setUp(self):
        self.run_id = "test-terminal-%s" % uuid.uuid4().hex[:8]
        self.addCleanup(shutil.rmtree, terminal.run_dir(self.run_id), True)
        self.addCleanup(terminal.close_run, self.run_id)

    def live(self, role):
        ended = []
        pump = threading.Thread(target=lambda: None)
        pump.start()
        term = terminal.open_terminal(self.run_id, role)
        term.agent = type("Agent", (), {"end": lambda self: ended.append(role), "returncode": lambda self: None,
                                        "write": lambda self, data: None, "pump": pump})()
        return ended

    def test_merge_and_discard_start_with_no_agent_left(self):
        from fakes import FakeWorktrees
        state = {"run_id": self.run_id, "plan": "todo/x.md", "task": "t", "repo_path": "/r", "worktree_path": "/w",
                 "base_branch": "develop", "verified_tree": "v", "todo_done_dir": "todo/done"}
        seen = []

        class Watching(FakeWorktrees):
            def merge(inner, *args):
                seen.append(("merge", [terminal.get(self.run_id, role) for role in ("engineer", "architect")]))
                return FakeWorktrees.merge(inner, *args)

            def discard(inner, *args):
                seen.append(("discard", [terminal.get(self.run_id, role) for role in ("engineer", "architect")]))

        host = activities.Activities(runner=None, git=Watching(), telemetry=None)
        for action in ("merge", "discard"):
            engineer, architect = self.live("engineer"), self.live("architect")
            getattr(host, action)({"state": state})
            self.assertEqual(engineer + architect, ["engineer", "architect"], action)
        self.assertEqual(seen, [("merge", [None, None]), ("discard", [None, None])])

    def test_a_change_while_the_architect_judges_fails_the_step_and_is_never_the_verified_tree(self):
        from app.workspace import worktrees
        repo = tempfile.mkdtemp(prefix="orch-verify-")
        self.addCleanup(folders.remove, repo)
        for args in (["init", "-q", "-b", "develop"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
            subprocess.run(["git", "-C", repo] + args, check=True)
        with open(os.path.join(repo, "app.txt"), "w") as fh:
            fh.write("one\n")
        subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
        subprocess.run(["git", "-C", repo, "commit", "-q", "-m", "base"], check=True)
        with open(os.path.join(repo, "app.txt"), "w") as fh:
            fh.write("one\nverified\n")
        from fakes import codex_review_resumed
        policy = json.loads(json.dumps(activities.P.load()))
        state = {"run_id": self.run_id, "task": "t", "phase": "build", "round": 0, "episode": 2,
                 "worktree_path": repo, "todo_path": os.path.join(repo, "todo.md"),
                 "agent_sessions": {"architect": "thread-1"}}

        def review(stage, edit):
            def runner(*args, **kwargs):
                if edit:
                    with open(os.path.join(repo, "app.txt"), "a") as fh:
                        fh.write("typed while the architect judged\n")
                return 0, codex_review_resumed("PASS")
            host = activities.Activities(runner=runner, git=worktrees, telemetry=None)
            return host.run_role({"stage": stage, "state": state, "policy": policy})

        # Both review stages: a PASS must describe the tree the architect actually read — the plan it
        # assessed as much as the change it verified — whoever typed into the live terminals meanwhile.
        for stage in ("assess", "verify"):
            with open(os.path.join(repo, "app.txt"), "w") as fh:      # the tree the last edit left
                fh.write("one\nverified\n")
            before = worktrees.work_tree(repo)
            passed = review(stage, edit=False)
            self.assertEqual(passed["verdict"], "PASS", "control: an untouched worktree passes")
            self.assertEqual(passed.get("verified_tree"), before if stage == "verify" else None,
                             "only the verified change is what a merge may commit")
            with self.assertRaises(Exception) as caught:
                review(stage, edit=True)
            self.assertIn("changed while", str(caught.exception), stage)

    def test_a_step_failed_by_its_checks_leaves_no_agent(self):
        ended = self.live("architect")
        policy = json.loads(json.dumps(activities.P.load()))
        state = {"run_id": self.run_id, "task": "t", "phase": "plan", "round": 0, "episode": 1,
                 "worktree_path": "/fake/worktree", "todo_path": "/fake/worktree/todo/x.md", "agent_sessions": {}}
        from fakes import FakeWorktrees, codex_first_out
        out, _ = codex_first_out("no verdict here")
        host = activities.Activities(runner=lambda *args, **kwargs: (0, out), git=FakeWorktrees(), telemetry=None)
        with self.assertRaises(Exception):
            host.run_role({"stage": "assess", "state": state, "policy": policy})
        self.assertTrue(terminal.get(self.run_id, "architect").agent is None)
        self.assertEqual(ended, ["architect"])


class Hook(unittest.TestCase):
    def test_a_payload_on_stdin_is_read_as_utf8_whatever_the_locale(self):
        # Claude pipes its hook payload as UTF-8; a Windows locale such as cp1251 would decode it wrongly.
        events = os.path.join(tempfile.mkdtemp(prefix="orch-hook-"), "turn.events")
        self.addCleanup(shutil.rmtree, os.path.dirname(events), True)
        payload = {"session_id": "s", "prompt_id": "p", "prompt": "plan — then build \u00e9"}
        done = subprocess.run([sys.executable, terminal.TURN_HOOK, events, "UserPromptSubmit"],
                              input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                              env=dict(os.environ, PYTHONIOENCODING="cp1251"), capture_output=True)
        self.assertEqual(done.returncode, 0)
        with open(events, encoding="utf-8") as fh:
            self.assertEqual(json.loads(fh.readline())["prompt"], payload["prompt"])


class Environment(unittest.TestCase):
    def test_an_agent_never_inherits_a_parent_claude_session(self):
        markers = {"CLAUDECODE": "1", "CLAUDE_CODE_CHILD_SESSION": "1", "CLAUDE_CODE_SESSION_ID": "x",
                   "CLAUDE_PID": "1"}
        saved = {key: os.environ.get(key) for key in markers}
        os.environ.update(markers)
        try:
            env = activities.agent_env({})
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        self.assertFalse(set(markers) & set(env))
        self.assertIn("PATH", env)


if __name__ == "__main__":
    unittest.main()
