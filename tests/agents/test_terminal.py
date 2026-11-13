"""A role turn in a live terminal: it ends on its own prompt's completion only, and leaves nothing behind.

Runs against `fake_cli.py` standing in for `claude` and `codex` on PATH, through the real
`terminal.run_turn`, `ptyhost.py`, `turn_hook.py` and `launch.py` tree, on both hosts.
"""
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from unittest import mock
import uuid

# The suite's own folder, reached from this concern's folder inside it, and the
# checkout above both: the shared harness and the fixtures live at the suite root.
HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
for path in (PKG, HERE):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.application import activities  # noqa: E402
from app.application import settings as S  # noqa: E402
from app.agents import launch  # noqa: E402
from app.agents import nodes as N  # noqa: E402
from app.agents import terminal  # noqa: E402
from app.agents import adapters  # noqa: E402
from app.agents.adapters import claude_code, codex  # noqa: E402
from tests.agents.test_launch import alive, force_kill, gone_within  # noqa: E402
import fake_cli  # noqa: E402
import folders  # noqa: E402
import stand_in  # noqa: E402

WINDOWS = sys.platform.startswith("win")
FAKE = os.path.join(HERE, "fake_cli.py")


def install_fakes(directory):
    # Each program a kind runs, as `fake_cli.py` plays it.
    for program, plays in (("claude", "claude"), ("codex", "codex"), (stand_in.PROGRAM, "stand-in")):
        if WINDOWS:
            with open(os.path.join(directory, program + ".cmd"), "w", encoding="utf-8") as fh:
                fh.write('@"%s" "%s" %s %%*\r\n' % (sys.executable, FAKE, plays))
        else:
            path = os.path.join(directory, program)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('#!/bin/sh\nexec "%s" "%s" %s "$@"\n' % (sys.executable, FAKE, plays))
            os.chmod(path, 0o755)


class Turns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bin = tempfile.mkdtemp(prefix="orchestra-fake-cli-")
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
        self.worktree = tempfile.mkdtemp(prefix="orchestra-term-wt-")
        self.addCleanup(folders.remove, self.worktree)
        self.addCleanup(shutil.rmtree, self.rdir, True)
        self.addCleanup(terminal.close_run, self.run_id)
        # Codex's config, where it records the hooks it trusts, and the record of what was trusted: this test's own.
        home = tempfile.mkdtemp(prefix="orchestra-codex-home-")
        self.addCleanup(shutil.rmtree, home, True)
        saved = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = home
        self.addCleanup(lambda: os.environ.pop("CODEX_HOME") if saved is None else os.environ.update(CODEX_HOME=saved))
        # The orchestra's Codex hooks trusted, as the operator trusts them once on a host.
        self.ours = codex.hook_flags(lambda label, source, events="-": terminal.sink(events, label, source))
        fake_cli.codex_trust(self.ours)

    def turn(self, prompt, kind="claude-code", stage="build", resume=None, timeout=60, name=None):
        if kind == "claude-code":
            argv = ["claude", "--resume" if resume else "--session-id", resume or str(uuid.uuid4()),
                    "--permission-mode", "dontAsk", "--allowedTools", "Edit(./**)"]
        else:
            argv = ["codex", "resume", resume] if resume else ["codex"]
            argv += ["--sandbox", "read-only", "--ask-for-approval", "never"]
        return terminal.run_turn(self.worktree, argv, self.rdir, name or "%s-e1-1" % stage, prompt, timeout,
                                 activities.agent_env({}), kind=kind)

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

    def test_a_prompt_past_the_command_line_starts_once_its_long_part_is_attached(self):
        # An operator's note as long as an audit pasted whole: given whole, it is past what Windows takes.
        parts = [{"part": "instructions", "text": "complete this"},
                 {"part": "guidance", "text": "\n# Operator guidance\n" + "an audit pasted whole, \"PATCH\" and all\n" * 1200}]
        kept, attached = N.attach(parts, os.path.join(self.rdir, "attachments"), "plan-e4-1")
        self.assertEqual(len(attached), 1)

        def launched(prompt):
            """A process given `prompt` as its last argument, through the launch every agent takes."""
            tree = launch._Tree()
            try:
                return tree.start([sys.executable, "-c", "pass", prompt], self.worktree, subprocess.DEVNULL,
                                  subprocess.DEVNULL, subprocess.DEVNULL, None).wait(60)
            finally:
                tree.kill()
                tree.close()
        if WINDOWS:
            with self.assertRaises(OSError) as refused:
                launched(N.render(parts))
            self.assertEqual(refused.exception.errno, 206, "the control: Windows refuses the command line itself")
        self.assertEqual(launched(N.render(kept)), 0, "the prompt with its long part attached is launched")
        if WINDOWS:
            self.skipTest("the fake runs through a .cmd wrapper, which cannot carry a newline in an argument")
        self.assertEqual(self.turn(N.render(kept), name="plan-e4-1"), (0, "done complete"))

    def test_the_prompt_survives_an_option_that_takes_several_values(self):
        worktree_skills = tempfile.mkdtemp(prefix="orchestra-skills-")
        self.addCleanup(shutil.rmtree, worktree_skills, True)
        argv = ["claude", "--session-id", str(uuid.uuid4()), "--add-dir", worktree_skills]
        rc, out = terminal.run_turn(self.worktree, argv, self.rdir, "build-e1-1", "complete this", 60,
                                    activities.agent_env({}), kind="claude-code")
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
        rc, out = self.turn("foreign then mine", kind="codex", stage="verify")
        self.assertEqual(rc, 0)
        lines = [json.loads(line) for line in out.splitlines()]
        self.assertEqual(lines[1]["item"]["text"], "done foreign")

    def test_a_stop_with_a_background_task_running_does_not_end_the_turn(self):
        self.assertEqual(self.turn("background task"), (0, "done background"))

    def test_a_lost_session_says_so_for_rehydration(self):
        for kind, stage in (("claude-code", "build"), ("codex", "verify")):
            resume = str(uuid.uuid4())
            rc, out = self.turn("lost it", kind=kind, stage=stage, resume=resume, name="%s-e1-9" % stage)
            with open(os.path.join(self.rdir, "logs", "%s-e1-9.err" % stage), encoding="utf-8") as fh:
                err = fh.read()
            self.assertEqual(N.classify_failure({"kind": kind}, resume, rc, out, err), "session_lost", kind)

    def test_control_the_matcher_refuses_what_a_first_event_rule_would_accept(self):
        session, mine, other = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        events = [{"_hook": "Stop", "session_id": session, "prompt_id": other, "last_assistant_message": "theirs"},
                  {"_hook": "UserPromptSubmit", "session_id": session, "prompt_id": mine, "prompt": "p"}]
        self.assertEqual(events[0]["last_assistant_message"], "theirs", "a first-Stop rule would end the turn here")
        self.assertIsNone(claude_code.completion(events, "p", session))
        events.append({"_hook": "Stop", "session_id": "elsewhere", "prompt_id": mine, "last_assistant_message": "x"})
        self.assertIsNone(claude_code.completion(events, "p", session))
        events.append({"_hook": "Stop", "session_id": session, "prompt_id": mine, "last_assistant_message": "wait",
                       "background_tasks": [{"status": "running"}]})
        self.assertIsNone(claude_code.completion(events, "p", session), "a background task still runs")
        events.append({"_hook": "Stop", "session_id": session, "prompt_id": mine, "last_assistant_message": "mine"})
        self.assertEqual(claude_code.completion(events, "p", session), (True, "mine", session))
        redirected = [events[1], {"_hook": "UserPromptSubmit", "session_id": session, "prompt_id": other,
                                  "prompt": "do this instead"},
                      {"_hook": "Stop", "session_id": session, "prompt_id": other, "last_assistant_message": "steered"}]
        self.assertEqual(claude_code.completion(redirected, "p", session), (True, "steered", session),
                         "a prompt submitted after ours in this turn completes it")
        self.assertIsNone(claude_code.completion(redirected[1:], "p", session), "not before ours")
        # Codex: its UserPromptSubmit names the turn our prompt began in its thread; that turn's Stop ends ours.
        def asked(thread, turn, prompt):
            return {"_hook": "UserPromptSubmit", "session_id": thread, "turn_id": turn, "prompt": prompt}

        def stopped(thread, turn, said):
            return {"_hook": "Stop", "session_id": thread, "turn_id": turn, "last_assistant_message": said}
        side = [asked("t9", "x1", "Write a brief catch-up"), stopped("t9", "x1", "{}")]
        self.assertIsNone(codex.completion(side, "p", None), "a thread of its own")
        ours = [asked("t2", "u1", "p"), stopped("t2", "u1", "ok")]
        self.assertIsNone(codex.completion(ours, "p", "t1"), "another thread when resuming")
        self.assertEqual(codex.completion(side + ours, "p", None), (True, "ok", "t2"))
        self.assertEqual(codex.completion(ours, "p", "t2"), (True, "ok", "t2"))
        self.assertIsNone(codex.completion([stopped("t2", "u0", "earlier"), ours[0]], "p", "t2"),
                          "a turn not begun by our prompt")
        steered = [ours[0], asked("t2", "u2", "do this instead"), stopped("t2", "u2", "steered")]
        self.assertEqual(codex.completion(steered, "p", "t2"), (True, "steered", "t2"),
                         "a prompt submitted after ours in this turn completes it")
        self.assertIsNone(codex.completion(steered[1:], "p", "t2"), "not before ours")

    def test_the_codex_thread_comes_from_its_turn_and_resumes_by_it(self):
        rc, out = self.turn("complete first", kind="codex", stage="assess")
        thread = N.extract_session({"kind": "codex"}, None, None, rc, out)
        self.assertNotEqual(thread, None)
        rc, out = self.turn("complete again", kind="codex", stage="verify", resume=thread, name="verify-e2-1")
        self.assertEqual(rc, 0)
        self.assertIn("done complete", out)

    def codex_turn(self, name, timeout=20):
        return self.turn("complete this", kind="codex", stage="verify", name=name, timeout=timeout)

    def config(self):
        try:
            with open(codex.config_path(), encoding="utf-8") as fh:
                return fh.read()
        except FileNotFoundError:
            return ""

    def test_a_codex_start_held_at_its_review_of_hooks_is_never_answered_here_and_fails_saying_so(self):
        saved, terminal.BEGIN_SECONDS = terminal.BEGIN_SECONDS, 2
        self.addCleanup(setattr, terminal, "BEGIN_SECONDS", saved)
        # The orchestra's own, on a host where the operator has not trusted them yet, and a repository's beside.
        os.remove(codex.config_path())
        os.makedirs(os.path.join(self.worktree, ".codex"))
        with open(os.path.join(self.worktree, ".codex", "hooks.json"), "w", encoding="utf-8") as fh:
            json.dump({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo theirs"}]}]}}, fh)
        began = time.monotonic()
        with self.assertRaises(launch.ExecutorError) as held:
            self.codex_turn("verify-e1-1")
        self.assertLess(time.monotonic() - began, 12, "failed once it should have begun, not at the turn's limit")
        self.assertIn("3 hook(s)", str(held.exception))
        self.assertIn("Review hooks", str(held.exception))
        self.assertFalse(terminal.get(self.run_id, "architect").live())
        self.assertNotIn("hooks.state", self.config(), "Trust all never answered: nothing trusted, whoever's")
        # The operator's own trusted, then a repository's hook new since: that one waits, and is never trusted here.
        fake_cli.codex_trust(self.ours)
        with self.assertRaises(launch.ExecutorError) as held:
            self.codex_turn("verify-e1-2")
        self.assertIn("1 hook(s)", str(held.exception))
        self.assertNotIn("hooks.json", self.config())
        # Reviewed — here, removed — and continued: the turn runs.
        shutil.rmtree(os.path.join(self.worktree, ".codex"))
        self.assertEqual(self.codex_turn("verify-e1-3")[0], 0)

    def test_the_operator_trusts_codexs_hooks_at_its_review_in_the_roles_terminal(self):
        os.remove(codex.config_path())
        done = []
        thread = threading.Thread(target=lambda: done.append(self.codex_turn("verify-e1-1")), daemon=True)
        thread.start()
        deadline = time.monotonic() + 30
        while "Hooks need review" not in self.record("architect") and time.monotonic() < deadline:
            time.sleep(0.2)
        self.assertIn("2 hooks are new or changed", self.record("architect"), "the orchestra's own two")
        # Its second choice, Trust all, typed into the role's terminal as the page types it.
        terminal.get(self.run_id, "architect").type(b"2\r")
        thread.join(30)
        self.assertEqual(done[0][0], 0, "the prompt went once they were trusted, and the turn ended on them")
        self.assertIn("hooks.state", self.config())
        self.assertEqual(self.codex_turn("verify-e1-2")[0], 0, "trusted once: the next turn asks nothing")

    def test_stop_failure_and_exit_without_completion_fail_and_leave_no_agent(self):
        rc, _ = self.turn("failure please")
        self.assertEqual(rc, 1)
        self.assertFalse(terminal.get(self.run_id, "engineer").live())
        rc, _ = self.turn("exit now", name="build-e1-2")
        self.assertEqual(rc, 3)
        self.assertIn("giving up", self.record())
        with open(os.path.join(self.rdir, "logs", "build-e1-2.err"), encoding="utf-8") as fh:
            self.assertIn("giving up", fh.read(), "the terminal's text is the turn's error log")

    def test_a_claude_turn_stopped_at_its_context_limit_fails_once_quiet_not_at_its_limit(self):
        saved, terminal.HALT_SECONDS = terminal.HALT_SECONDS, 2
        self.addCleanup(setattr, terminal, "HALT_SECONDS", saved)
        began = time.monotonic()
        with self.assertRaises(launch.ExecutorError) as halted:
            self.turn("full context", timeout=20)
        self.assertLess(time.monotonic() - began, 12, "failed once quiet, not at the turn's limit")
        self.assertIn("context limit", str(halted.exception))
        self.assertFalse(terminal.get(self.run_id, "engineer").live())

    def test_a_working_claude_whose_tool_prints_that_line_is_never_ended_for_it(self):
        # The line as a long tool's output, while its spinner goes on and no hook fires for longer than the quiet
        # the stop is read after: the turn runs to its own end.
        saved, terminal.HALT_SECONDS = terminal.HALT_SECONDS, 2
        self.addCleanup(setattr, terminal, "HALT_SECONDS", saved)
        self.assertEqual(self.turn("quoted context", timeout=30), (0, "done quoted"))

    def test_a_resize_reaches_the_agent_and_the_next_turn_starts_at_it(self):
        def resized(name, says, rows):
            done = []
            thread = threading.Thread(target=lambda: done.append(self.turn("size please", name=name)), daemon=True)
            thread.start()
            deadline = time.monotonic() + 30
            while self.record().count(says) < 1 and time.monotonic() < deadline:
                time.sleep(0.2)
            terminal.get(self.run_id, "engineer").resize(rows)
            thread.join(30)
            return done[0]
        self.assertEqual(resized("build-e1-1", "size 160 48", 100), (0, "done size 160 100"),
                         "the agent's PTY took the rows")
        self.assertEqual(resized("build-e1-2", "size 160 100", 48), (0, "done size 160 48"),
                         "the next turn began at them; Restore put back 48")
        with open(terminal.record_path(self.run_id, "engineer"), "rb") as fh:
            marks = re.findall(rb"\x1b\]5379;(\d+);(\d+)\x07", fh.read())
        self.assertEqual(marks, [(b"160", b"48"), (b"160", b"100"), (b"160", b"100"), (b"160", b"48")],
                         "each turn's size and each change, where it began")

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
        for kind, stage in (("claude-code", "build"), ("codex", "verify")):
            with self.subTest(kind=kind):
                self.steer(kind, stage)

    def steer(self, kind, stage):
        result = {}
        role = "engineer" if stage == "build" else "architect"
        resume = str(uuid.uuid4()) if kind == "codex" else None
        worker = threading.Thread(target=lambda: result.update(
            value=self.turn("interrupt me", kind=kind, stage=stage, resume=resume, timeout=60)))
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


class AssignedWorktree(unittest.TestCase):
    def test_codex_fresh_and_resume_receive_the_assigned_directory_explicitly(self):
        class Started(Exception):
            pass

        with tempfile.TemporaryDirectory(prefix="orchestra-cwd-") as root:
            worktree = os.path.join(root, "Mixed Case worktree")
            os.mkdir(worktree)
            for session in (None, "saved-thread"):
                with self.subTest(session=session):
                    argv, _ = codex.command({"workspace_access": "read"}, session)
                    captured = {}

                    def start(command, cwd, env):
                        captured.update(argv=command, cwd=cwd)
                        raise Started()

                    with mock.patch.object(terminal.shutil, "which", return_value="codex"), \
                         mock.patch.object(terminal, "open_terminal") as opened:
                        opened.return_value.start.side_effect = start
                        with self.assertRaises(Started):
                            terminal.run_turn(worktree, argv, os.path.join(root, "run"),
                                              "assess-e1-1", "review", 10, {}, kind="codex")
                    command = captured["argv"]
                    self.assertIn("--cd", command)
                    self.assertEqual(command[command.index("--cd") + 1], worktree)
                    self.assertEqual(captured["cwd"], worktree)
                    self.assertEqual(codex.session_in(command), session)
                    self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
                    self.assertFalse(any("bypass" in part for part in command))


class ANewKind(unittest.TestCase):
    """A kind of agent is its module alone: one planted for the test runs through the real terminal as the
    shipped kinds do — typed into, ended by its own signal, resumed — and its review is read by the one
    parser every kind shares."""

    @classmethod
    def setUpClass(cls):
        cls.bin = tempfile.mkdtemp(prefix="orchestra-fake-cli-")
        install_fakes(cls.bin)
        cls.path = os.environ["PATH"]
        os.environ["PATH"] = cls.bin + os.pathsep + cls.path

    @classmethod
    def tearDownClass(cls):
        os.environ["PATH"] = cls.path
        shutil.rmtree(cls.bin, ignore_errors=True)

    def setUp(self):
        # Beside it, the same kind with nothing wired to say its turn ended.
        stand_in.plant(self, {stand_in.MODULE: stand_in.SOURCE,
                              "silent_stand_in": stand_in.variant(wire="def wire(argv, events, sink):\n"
                                                                       "    return list(argv)\n")})
        self.role = {"kind": stand_in.KIND}
        self.run_id = "test-terminal-%s" % uuid.uuid4().hex[:8]
        self.rdir = terminal.run_dir(self.run_id)
        self.worktree = tempfile.mkdtemp(prefix="orchestra-term-wt-")
        self.addCleanup(folders.remove, self.worktree)
        self.addCleanup(shutil.rmtree, self.rdir, True)
        self.addCleanup(terminal.close_run, self.run_id)

    def turn(self, prompt, resume=None, name="build-e1-1", timeout=60, kind=stand_in.KIND):
        adapter = adapters.load(kind)
        argv, _ = adapter.command({"workspace_access": "write"}, resume)
        return terminal.run_turn(self.worktree, adapter.host(argv), self.rdir, name, prompt, timeout,
                                 activities.agent_env({}), kind=kind)

    def record(self):
        try:
            with open(terminal.record_path(self.run_id, "engineer"), "rb") as fh:
                return terminal.plain(fh.read())
        except FileNotFoundError:
            return ""

    def _wait_for(self, check, seconds=30):
        return Turns._wait_for(self, check, seconds)

    def test_it_ends_its_turn_on_its_own_signal_and_resumes_its_session(self):
        rc, out = self.turn("complete this")
        self.assertEqual((rc, N.final_message(self.role, out)), (0, "done complete"))
        self.assertIn("fake stand-in ready", self.record(), "its own program ran in the role's terminal")
        thread = N.extract_session(self.role, None, None, rc, out)
        rc, out = self.turn("complete again", resume=thread, name="build-e1-2")
        self.assertEqual((rc, adapters.load(stand_in.KIND).session(out, None)), (0, thread),
                         "the second turn went on in the first one's session")

    def test_it_takes_typed_keys(self):
        result = {}
        worker = threading.Thread(target=lambda: result.update(value=self.turn("interrupt me")))
        worker.start()
        term = self._wait_for(lambda: terminal.get(self.run_id, "engineer"))
        self._wait_for(lambda: "working" in self.record())
        term.type(b"\x1b")
        self._wait_for(lambda: "Interrupted" in self.record())
        term.type(b"go on\r")
        worker.join(30)
        rc, out = result["value"]
        self.assertEqual((rc, N.final_message(self.role, out)), (0, "resumed with go on"))

    def test_control_a_kind_that_never_signals_its_end_times_out(self):
        with self.assertRaises(launch.RoleTimeout):
            self.turn("complete this", timeout=3, kind="silent-stand-in")
        self.assertFalse(terminal.get(self.run_id, "engineer").live())

    def test_its_review_is_read_by_the_one_parser_which_refuses_text_after_the_verdict(self):
        adapter = adapters.load(stand_in.KIND)
        verdict = '{"verdict": "PASS", "feedback": "sound"}'
        self.assertEqual(N.parse_review(self.role, 0, adapter.output("Reasoning first.\n" + verdict, "t1")),
                         ("PASS", "sound"))
        written_past = verdict + "\nOn second thought, the tests are missing."
        with self.assertRaises(N.ContentError):
            N.parse_review(self.role, 0, adapter.output(written_past, "t1"))
        # The control: a parser of the kind's own, taking the first object it finds, lets that answer through.
        message = adapter.message_of(json.loads(adapter.output(written_past, "t1")))
        self.assertEqual(json.JSONDecoder().raw_decode(message)[0]["verdict"], "PASS")


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
                          kind="claude-code")
    print("ready", flush=True)
    time.sleep(600)
""")


class OwnerDeath(unittest.TestCase):
    """The worker's death ends a live terminal's agent and everything it started."""

    def setUp(self):
        self.bin = tempfile.mkdtemp(prefix="orchestra-fake-cli-")
        install_fakes(self.bin)
        self.work = tempfile.mkdtemp(prefix="orchestra-term-owner-")
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


class Resize(unittest.TestCase):
    """A terminal's rows follow a maximized page, as a console window's do: its PTY host takes the size in its stdin
    as a sequence no key makes, the worker's terminal holds it, marks it in the record and announces it."""

    def setUp(self):
        self.run_id = "test-resize-%s" % uuid.uuid4().hex[:8]
        self.addCleanup(shutil.rmtree, terminal.run_dir(self.run_id), True)
        self.addCleanup(terminal.close_run, self.run_id)

    def test_the_size_marker_precedes_output_caused_by_the_resize(self):
        term = terminal.open_terminal(self.run_id, "engineer")
        told = []
        term.attach(told.append)
        pump = threading.Thread(target=lambda: None)
        pump.start()
        term.agent = type("Agent", (), {
            "resize": lambda self, rows: term.emit(b"redrawn at 138 rows"),
            "returncode": lambda self: None, "end": lambda self: None, "pump": pump})()
        term.resize(138)
        expected = [terminal.SIZE_MARK % (terminal.COLS, 138), b"redrawn at 138 rows"]
        self.assertEqual(told[:2], expected, "viewers resize before the agent's new-size output")
        with open(term.path, "rb") as fh:
            self.assertEqual(fh.read(), b"".join(expected), "replay keeps the same causal order")

    def test_the_pty_host_reads_a_size_whole_across_reads_and_passes_every_key(self):
        from app.agents import ptyhost
        split = lambda *chunks: list(ptyhost.split(iter(chunks)))   # noqa: E731
        self.assertEqual(split(b"ab\x1b_orch", b"estra-size;100;160\x1b\\cd"),
                         [(b"ab", None), (None, (100, 160)), (b"cd", None)], "cut across two reads")
        self.assertEqual(split(b"\x1b"), [(b"\x1b", None)], "the Esc key, at once")
        self.assertEqual(split(b"\x1b[A", b"q"), [(b"\x1b[A", None), (b"q", None)])
        self.assertEqual(split(b"x\x1b_or", b"ange"), [(b"x", None), (b"\x1b_orange", None)],
                         "what was held, not a size, goes on as it came")
        self.assertEqual(split(b"\x1b_orchestra-size;x\x1b\\k"), [(b"k", None)], "begun as a size: never a key")

    def test_a_size_is_held_bounded_given_to_the_agent_marked_and_announced(self):
        term = terminal.open_terminal(self.run_id, "engineer")
        written, told = [], []
        pump = threading.Thread(target=lambda: None)
        pump.start()
        term.agent = type("Agent", (), {"write": lambda self, data: written.append(data),
                                        "resize": lambda self, rows: written.append(terminal.RESIZE % (rows, 160)),
                                        "returncode": lambda self: None, "end": lambda self: None,
                                        "pump": pump})()
        term.viewers.append(told.append)
        for wrong in (23, 201, "100", True, None):
            with self.assertRaises(ValueError):
                term.resize(wrong)
        self.assertEqual((term.rows, written, told), (48, [], []), "refused, the size kept")
        term.resize(100)
        self.assertEqual(term.rows, 100)
        self.assertEqual(written, [b"\x1b_orchestra-size;100;160\x1b\\"])
        self.assertEqual(told[0], b"\x1b]5379;160;100\x07", "every viewer draws it where it begins")
        self.assertEqual(json.loads(told[1])["size"], [160, 100])
        with open(terminal.record_path(self.run_id, "engineer"), "rb") as fh:
            self.assertIn(b"\x1b]5379;160;100\x07", fh.read(), "and the record keeps it")
        term.type(b"a key \x1b_orchestra-size;24;160\x1b\\")
        self.assertEqual(len(written), 1, "no key carries a size")


class Socket(unittest.TestCase):
    """The terminal's WebSocket: the workbench's token and origin, the record, then live bytes."""

    PORT, WORKBENCH = 18391, 18390
    # What the feed this socket is handed answers, look by look, in the test now running: a message or None and
    # how long until the next look — None to end — or an exception it raises. Each look is kept.
    script = []
    looks = []

    @classmethod
    def setUpClass(cls):
        terminal.serve(cls.PORT, cls.WORKBENCH, feeds={"change": cls.feed})

    @classmethod
    def feed(cls, run_id, memo):
        cls.looks.append((run_id, dict(memo)))
        memo["looked"] = memo.get("looked", 0) + 1
        step = cls.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    def setUp(self):
        self.run_id = "test-terminal-%s" % uuid.uuid4().hex[:8]
        self.addCleanup(shutil.rmtree, terminal.run_dir(self.run_id), True)
        self.addCleanup(terminal.close_run, self.run_id)

    def connect(self, origin="http://127.0.0.1:%d" % WORKBENCH, token=None, path=None, in_url=False, stream=False):
        from websockets.asyncio.client import connect
        token = terminal.token() if token is None else token
        url = "ws://127.0.0.1:%d/%s" % (self.PORT, path or "%s/engineer" % self.run_id)
        if in_url:
            # What the page must never do: a URL is printed to the browser's console and written to logs.
            return connect(url + "?token=" + token, origin=origin, max_size=None,
                           subprotocols=[terminal.PROTOCOL])
        return connect(url, origin=origin, max_size=None,
                       subprotocols=(["workbench.v2"] if stream else []) + [terminal.PROTOCOL, terminal.TOKEN_PROTOCOL + token])

    def test_streaming_is_bounded_by_viewer_reads_and_resumes_at_the_confirmed_cursor(self):
        term = terminal.open_terminal(self.run_id, "engineer")
        data = b"recorded\r\n" * 30000
        term.emit(data)

        async def talk():
            async with self.connect(stream=True) as ws:
                self.assertEqual(ws.subprotocol, "workbench.v2")
                await ws.recv()
                await ws.send(json.dumps({"read": 7}).encode())
                first = await ws.recv()
                self.assertLessEqual(len(first), 65536)
                self.assertEqual(first, data[7:7 + len(first)])
                term.emit(b"live\r\n")
                with self.assertRaises(asyncio.TimeoutError):
                    await asyncio.wait_for(ws.recv(), .05)
                cursor = 7 + len(first)
                received = first
                while cursor < len(data) + 6:
                    await ws.send(json.dumps({"read": cursor}).encode())
                    part = await asyncio.wait_for(ws.recv(), 5)
                    self.assertLessEqual(len(part), 65536)
                    received += part
                    cursor += len(part)
                self.assertEqual(received, (data + b"live\r\n")[7:])
            async with self.connect(stream=True) as ws:
                await ws.recv()
                await ws.send(json.dumps({"read": cursor}).encode())
                term.emit(b"later")
                self.assertEqual(await asyncio.wait_for(ws.recv(), 5), b"later")
        asyncio.run(talk())

    def test_bad_stream_cursors_cannot_type_to_the_agent_or_resize_or_change_its_record(self):
        from websockets.exceptions import ConnectionClosedError
        term = terminal.open_terminal(self.run_id, "engineer")
        term.emit(b"record")
        typed = []
        with mock.patch.object(term, "type", side_effect=typed.append):
            async def talk():
                for cursor in (True, -1, 100, "0"):
                    async with self.connect(stream=True) as ws:
                        await ws.recv()
                        await ws.send(json.dumps({"read": cursor}).encode())
                        with self.assertRaises(ConnectionClosedError):
                            await asyncio.wait_for(ws.recv(), 5)
            asyncio.run(talk())
        self.assertEqual((typed, term.rows), ([], terminal.ROWS))
        with open(term.path, "rb") as stream:
            self.assertEqual(stream.read(), b"record")

    def test_a_paused_stream_still_accepts_keys_resize_state_and_close(self):
        term = terminal.open_terminal(self.run_id, "engineer")
        term.emit(b"recorded")
        typed = []
        pump = threading.Thread(target=lambda: None)
        pump.start()
        term.agent = type("Agent", (), {"write": lambda self, data: typed.append(data),
            "resize": lambda self, rows: None, "returncode": lambda self: None,
            "end": lambda self: None, "pump": pump})()

        async def talk():
            from websockets.exceptions import ConnectionClosedOK
            async with self.connect(stream=True) as ws:
                self.assertTrue(json.loads(await ws.recv())["live"])
                await ws.send("operator-key")
                await ws.send(json.dumps({"rows": 100}).encode())
                told = json.loads(await asyncio.wait_for(ws.recv(), 5))
                self.assertEqual(told["size"], [160, 100])
                self.assertEqual(typed, [b"operator-key"])
                terminal.close_run(self.run_id)
                await ws.send(json.dumps({"read": 0}).encode())
                got = b""
                while True:
                    message = await asyncio.wait_for(ws.recv(), 5)
                    if isinstance(message, bytes):
                        got += message
                        break
                with open(term.path, "rb") as record:
                    self.assertEqual(got, record.read(), "closing must preserve the unread final output")
                await ws.send(json.dumps({"read": len(got)}).encode())
                with self.assertRaises(ConnectionClosedOK):
                    while True:
                        await asyncio.wait_for(ws.recv(), 5)
        asyncio.run(talk())

    def test_a_record_without_a_loaded_terminal_streams_to_eof(self):
        data = b"recorded\r\n" * 30000
        term = terminal.open_terminal(self.run_id, "engineer")
        term.emit(data)
        terminal.close_run(self.run_id)

        async def talk():
            from websockets.exceptions import ConnectionClosedOK
            async with self.connect(stream=True) as ws:
                self.assertFalse(json.loads(await ws.recv())["live"])
                got = b""
                while len(got) < len(data):
                    await ws.send(json.dumps({"read": len(got)}).encode())
                    got += await asyncio.wait_for(ws.recv(), 5)
                self.assertEqual(got, data)
                await ws.send(json.dumps({"read": len(got)}).encode())
                with self.assertRaises(ConnectionClosedOK):
                    await asyncio.wait_for(ws.recv(), 5)
        asyncio.run(talk())

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
                self.assertEqual(json.loads(await ws.recv()), {"live": True, "size": [160, 48]})
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

    def test_a_binary_frame_resizes_the_terminal_and_no_key_does(self):
        term = terminal.open_terminal(self.run_id, "engineer")
        written = []
        pump = threading.Thread(target=lambda: None)
        pump.start()
        term.agent = type("Agent", (), {"write": lambda self, data: written.append(data),
                                        "resize": lambda self, rows: written.append(("rows", rows)),
                                        "returncode": lambda self: None, "end": lambda self: None,
                                        "pump": pump})()

        async def talk():
            async with self.connect() as ws:
                self.assertEqual(json.loads(await ws.recv())["size"], [160, 48], "it names its size: it takes one")
                await ws.send(json.dumps({"rows": 100}).encode("utf-8"))
                marked = await asyncio.wait_for(ws.recv(), 5)
                told = json.loads(await asyncio.wait_for(ws.recv(), 5))
                await ws.send("\x1b_orchestra-size;24;160\x1b\\")
                await ws.send(json.dumps({"rows": 9999}).encode("utf-8"))
                await asyncio.sleep(0.5)
                return marked, told
        marked, told = asyncio.run(talk())
        self.assertEqual((marked, told), (b"\x1b]5379;160;100\x07", {"live": True, "size": [160, 100]}))
        self.assertEqual((written, term.rows), ([("rows", 100)], 100),
                         "a key carrying a size, and rows out of bounds, change nothing")

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
                self.assertEqual(json.loads(await ws.recv()), {"live": True, "size": [160, 48]})
                self.assertEqual(await ws.recv(), b"the turn\r\n")
                terminal.end_agent(self.run_id, "engineer")
                return json.loads(await asyncio.wait_for(ws.recv(), 5))
        self.assertEqual(asyncio.run(talk()), {"live": False, "size": [160, 48]}, "the viewer watching is told")
        self.assertEqual(self.exchange()[0], {"live": False, "size": [160, 48]},
        "and so is a page that attaches afterwards")

    def test_closing_a_run_closes_its_viewers_so_they_reattach(self):
        term = terminal.open_terminal(self.run_id, "engineer")
        term.emit(b"turn one\r\n")

        async def talk():
            async with self.connect() as ws:
                self.assertEqual(json.loads(await ws.recv()), {"live": False, "size": [160, 48]},
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

    def watch(self, path=None):
        """Every message the feed sends one watcher, and whether the socket then closed of itself."""
        from websockets.exceptions import ConnectionClosedOK

        async def talk():
            got = []
            async with self.connect(path=path or "%s/change" % self.run_id) as ws:
                try:
                    while True:
                        got.append(json.loads(await asyncio.wait_for(ws.recv(), 5)))
                except ConnectionClosedOK:
                    return got, True
                except asyncio.TimeoutError:
                    return got, False
        return asyncio.run(talk())

    def test_a_feed_sends_what_each_look_finds_and_ends_when_it_says(self):
        Socket.script = [({"files": 1}, 0.05), (None, 0.05), ({"files": 2}, None)]
        Socket.looks = []
        self.assertEqual(self.watch(), ([{"files": 1}, {"files": 2}], True),
                         "a look that finds nothing new sends nothing, and the last one ends the watch")
        self.assertEqual([run for run, _ in Socket.looks], [self.run_id] * 3)
        self.assertEqual([memo.get("looked", 0) for _, memo in Socket.looks], [0, 1, 2],
                         "one memo per watcher, kept from one look to the next")

    def test_a_feed_that_fails_says_so_and_ends(self):
        Socket.script = [RuntimeError("git broke")]
        self.assertEqual(self.watch(), ([{"error": "RuntimeError: git broke"}], True))

    def test_a_feed_takes_the_token_and_origin_a_terminal_does_and_only_the_names_it_was_handed(self):
        self.assertEqual(self.refused(path="%s/change" % self.run_id, token="wrong"), 403)
        self.assertEqual(self.refused(path="%s/change" % self.run_id, origin="http://evil.example"), 403)
        self.assertEqual(self.refused(path="%s/changes" % self.run_id), 404)

    def test_a_look_in_flight_never_holds_the_worker_open_once_it_ends(self):
        # A look is a read with nothing to finish: one still running a command — git, here a child that sleeps — must
        # neither keep the process alive past what its stop waits for, nor leave that command running after it.
        pidfile = os.path.join(tempfile.mkdtemp(prefix="orchestra-look-"), "child.pid")
        self.addCleanup(shutil.rmtree, os.path.dirname(pidfile), True)
        script = textwrap.dedent("""\
            import asyncio, os, sys, threading, time
            sys.path.insert(0, %r)
            from app.agents import launch, terminal
            child = "import os, sys, time; open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(60)"
            def feed(run_id, memo):
                launch.read([sys.executable, "-c", child, %r], 120)
                return None, 60
            terminal.serve(%d, %d, feeds={"change": feed})
            async def watch():
                from websockets.asyncio.client import connect
                async with connect("ws://127.0.0.1:%d/r1/change", origin="http://127.0.0.1:%d",
                                   subprotocols=[terminal.PROTOCOL, terminal.TOKEN_PROTOCOL + terminal.token()]):
                    await asyncio.sleep(60)
            threading.Thread(target=lambda: asyncio.run(watch()), daemon=True).start()
            while not (os.path.exists(%r) and open(%r).read()):
                time.sleep(0.05)
            """) % (PKG, pidfile, self.PORT + 3, self.WORKBENCH, self.PORT + 3, self.WORKBENCH, pidfile, pidfile)
        began = time.monotonic()
        subprocess.run([sys.executable, "-c", script], check=True, timeout=60, capture_output=True)
        self.assertLess(time.monotonic() - began, 8, "the process ended without waiting for the look")
        self.assertTrue(gone_within(int(open(pidfile).read()), 5), "the look's command ended with the process")

    def test_a_feed_may_not_take_a_roles_name(self):
        with self.assertRaises(ValueError):
            terminal.serve(self.PORT + 2, self.WORKBENCH, feeds={"engineer": self.feed})

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

    def test_an_agent_end_not_proved_stops_a_merge_or_discard_before_git_and_every_terminal_closes(self):
        from fakes import FakeWorktrees
        state = {"run_id": self.run_id, "plan": "todo/x.md", "task": "t", "repo_path": "/r", "worktree_path": "/w",
                 "base_branch": "develop", "verified_tree": "v", "todo_done_dir": "todo/done"}
        git = FakeWorktrees()
        host = activities.Activities(runner=None, git=git, telemetry=None)

        def unproved(agent):
            raise TimeoutError("the agent's process tree did not end within 5s of its kill")
        for action in ("merge", "discard"):
            # The terminal whose end fails is closed first, so the other shows it was closed all the same.
            pump = threading.Thread(target=lambda: None)
            pump.start()
            engineer = terminal.open_terminal(self.run_id, "engineer")
            engineer.agent = type("Agent", (), {"end": unproved, "returncode": lambda self: None,
                                                "write": lambda self, data: None, "pump": pump})()
            told = []
            engineer.attach(told.append)
            ended = self.live("architect")
            with self.assertRaisesRegex(TimeoutError, "did not end", msg=action):
                getattr(host, action)({"state": state})
            self.assertEqual(ended, ["architect"], action)
            self.assertEqual([terminal.get(self.run_id, role) for role in ("engineer", "architect")], [None, None])
            self.assertEqual(told[-2:], [json.dumps({"live": False, "size": [160, 48]}), None],
            "its page is told, then let go")
        self.assertEqual(git.calls, [], "no git after an end not proved")

    def test_a_change_while_the_architect_judges_fails_the_step_and_is_never_the_verified_tree(self):
        from app.workspace import worktrees
        repo = tempfile.mkdtemp(prefix="orchestra-verify-")
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
        policy = json.loads(json.dumps(S.run_policy(S.load())))
        state = {"run_id": self.run_id, "task": "t", "phase": "build", "round": 0, "episode": 2,
                 "worktree_path": repo, "todo_path": os.path.join(repo, "todo.md"),
                 "agent_sessions": {"architect": "thread-1"}}

        def review(stage, edit, verdict="PASS"):
            def runner(*args, **kwargs):
                if edit:
                    with open(os.path.join(repo, "app.txt"), "a") as fh:
                        fh.write("typed while the architect judged\n")
                return 0, codex_review_resumed(verdict)
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
            self.assertEqual(passed["judged_tree"], before, "the tree it judged, kept for the run's history")
            with self.assertRaises(Exception) as caught:
                review(stage, edit=True)
            self.assertIn("changed while", str(caught.exception), stage)
            # Any other verdict routes as it always has, but names a tree only when it is the one the architect read.
            with open(os.path.join(repo, "app.txt"), "w") as fh:
                fh.write("one\nverified\n")
            sent_back = review(stage, edit=True, verdict="PATCH")
            self.assertEqual(sent_back["verdict"], "PATCH", "a change while it judged does not fail the step")
            self.assertNotIn("judged_tree", sent_back, "a tree that moved under the review is not what it judged")
            with open(os.path.join(repo, "app.txt"), "w") as fh:
                fh.write("one\nverified\n")
            self.assertEqual(review(stage, edit=False, verdict="PATCH")["judged_tree"], before,
                             "control: an untouched worktree's tree is the one it judged")

    def test_a_step_failed_by_its_checks_leaves_no_agent(self):
        ended = self.live("architect")
        policy = json.loads(json.dumps(S.run_policy(S.load())))
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
    def test_attention_events_keep_only_status_not_tool_input_or_notification_text(self):
        events = os.path.join(tempfile.mkdtemp(prefix="orchestra-hook-"), "turn.events")
        self.addCleanup(shutil.rmtree, os.path.dirname(events), True)
        for label, payload in (("Notification", {"session_id": "s1", "notification_type": "permission_prompt",
                                                 "message": "private"}),
                               ("PostToolUse", {"session_id": "s1", "tool_name": "Read",
                                                "tool_input": {"file_path": "private"}, "tool_response": "private"}),
                               ("PostToolUseFailure", {"tool_name": "Bash", "tool_input": {"command": "private"},
                                                       "error": "private"})):
            done = subprocess.run([sys.executable, terminal.TURN_HOOK, events, label, "stdin"],
                                  input=json.dumps(payload).encode("utf-8"), capture_output=True)
            self.assertEqual(done.returncode, 0)
        with open(events, encoding="utf-8") as stream:
            self.assertEqual([unstamped(json.loads(line)) for line in stream],
                             [{"_hook": "Notification", "session_id": "s1", "notification_type": "permission_prompt"},
                              {"_hook": "PostToolUse", "session_id": "s1"},
                              {"_hook": "PostToolUseFailure"}])

    def test_a_payload_on_stdin_is_read_as_utf8_whatever_the_locale(self):
        # Claude pipes its hook payload as UTF-8; a Windows locale such as cp1251 would decode it wrongly.
        events = os.path.join(tempfile.mkdtemp(prefix="orchestra-hook-"), "turn.events")
        self.addCleanup(shutil.rmtree, os.path.dirname(events), True)
        payload = {"session_id": "s", "prompt_id": "p", "prompt": "plan — then build \u00e9"}
        done = subprocess.run([sys.executable, terminal.TURN_HOOK, events, "UserPromptSubmit", "stdin"],
                              input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                              env=dict(os.environ, PYTHONIOENCODING="cp1251"), capture_output=True)
        self.assertEqual(done.returncode, 0)
        with open(events, encoding="utf-8") as fh:
            self.assertEqual(json.loads(fh.readline())["prompt"], payload["prompt"])

    def test_a_payload_given_as_the_last_argument_is_read_from_there_and_labelled(self):
        # Codex appends its notification to the command it is given; nothing arrives on stdin.
        events = os.path.join(tempfile.mkdtemp(prefix="orchestra-hook-"), "turn.events")
        self.addCleanup(shutil.rmtree, os.path.dirname(events), True)
        payload = {"type": "agent-turn-complete", "last-assistant-message": "done é"}
        done = subprocess.run([sys.executable, terminal.TURN_HOOK, events, "notify", "argument",
                               json.dumps(payload, ensure_ascii=False)], stdin=subprocess.DEVNULL,
                              capture_output=True)
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, b"", b""))
        with open(events, encoding="utf-8") as fh:
            self.assertEqual(unstamped(json.loads(fh.readline())), dict(payload, _hook="notify"))

    def test_the_events_file_may_be_named_by_the_environment(self):
        # One hook definition on every turn — the turn's file comes in the environment — so Codex, which trusts a
        # hook by its exact definition, trusts it once.
        events = os.path.join(tempfile.mkdtemp(prefix="orchestra-hook-"), "turn.events")
        self.addCleanup(shutil.rmtree, os.path.dirname(events), True)
        done = subprocess.run([sys.executable, terminal.TURN_HOOK, "-", "Stop", "stdin"],
                              input=json.dumps({"session_id": "s"}).encode("utf-8"), capture_output=True,
                              env=dict(os.environ, **{terminal.TURN_EVENTS: events}))
        self.assertEqual(done.returncode, 0)
        with open(events, encoding="utf-8") as fh:
            self.assertEqual(unstamped(json.loads(fh.readline())), {"session_id": "s", "_hook": "Stop"})

    def test_each_event_is_stamped_with_when_it_was_recorded(self):
        # Two roles' records are compared by when each answered, never by when their files last changed.
        events = os.path.join(tempfile.mkdtemp(prefix="orchestra-hook-"), "turn.events")
        self.addCleanup(shutil.rmtree, os.path.dirname(events), True)
        before = time.time()
        for label in ("UserPromptSubmit", "Stop"):
            subprocess.run([sys.executable, terminal.TURN_HOOK, events, label, "stdin"],
                           input=json.dumps({"session_id": "s"}).encode("utf-8"), capture_output=True, check=True)
        after = time.time()
        with open(events, encoding="utf-8") as fh:
            stamps = [json.loads(line)["_at"] for line in fh]
        self.assertEqual(len(stamps), 2)
        self.assertTrue(before <= stamps[0] <= stamps[1] <= after, (before, stamps, after))


def unstamped(event):
    """An event as its agent gave it and labelled, without the time its hook recorded it."""
    return {key: value for key, value in event.items() if key != "_at"}


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
