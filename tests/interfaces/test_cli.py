"""The command line types the answers a stop publishes. Which answers exist is the workflow's.

The command line owns only how an answer is typed — `yes`, guidance written as it is, a revise's
role spelled as a word — so an answer the workflow adds is typed by its name with no change here.
Its `--stack` forms, which the Makefile runs, only print what the stack's one owner read or did.
"""
import asyncio
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

from app.application import stack  # noqa: E402
from app.interfaces import cli  # noqa: E402


def stop(*actions):
    return {"reason": "any", "actions": list(actions)}


class ParsesWhatAStopPublishes(unittest.TestCase):
    def test_an_answer_the_command_line_has_no_word_for_is_typed_by_its_name(self):
        self.assertEqual(cli.parse_answer(stop("pause", "continue"), "pause"), {"action": "pause", "text": "pause"})

    def test_a_revise_names_its_role_as_the_stop_publishes_it(self):
        final = stop("merge", "revise:engineer", "revise:architect", "discard")
        self.assertEqual(cli.parse_answer(final, "revise architect re-check the error path"),
                         {"action": "revise:architect", "text": "re-check the error path"})
        self.assertIsNone(cli.parse_answer(final, "revise re-check the error path"), "a role is named")
        self.assertEqual(cli.parse_answer(stop("approve", "revise"), "revise plan it again"),
                         {"action": "revise", "text": "plan it again"})

    def test_guidance_is_written_as_it_is_and_only_where_a_stop_takes_it(self):
        blocker = stop("guide", "pause")
        self.assertEqual(cli.parse_answer(blocker, "pause the old approach, use B"),
                         {"action": "guide", "text": "pause the old approach, use B"},
                         "a sentence that starts with an answer's name is still guidance")
        self.assertEqual(cli.parse_answer(blocker, "pause"), {"action": "pause", "text": "pause"})
        self.assertIsNone(cli.parse_answer(stop("approve", "revise"), "maybe later"))

    def test_yes_approves_and_a_confirmation_travels_with_the_answer(self):
        self.assertEqual(cli.parse_answer(stop("approve", "revise"), "Yes"), {"action": "approve", "text": "Yes"})
        self.assertEqual(cli.parse_answer(stop("discard"), "discard", confirm=True),
                         {"action": "discard", "text": "discard", "confirm": True})
        self.assertEqual(cli.parse_answer(stop("discard"), "discard"), {"action": "discard", "text": "discard"},
                         "whether a discard is confirmed is the workflow's to refuse")

    def test_the_answers_it_lists_are_the_stops_own(self):
        listed = cli.answer_line(stop("merge", "revise:engineer", "pause"))
        self.assertEqual(listed, '"merge" | "revise engineer <feedback>" | "pause"')


class TheStack(unittest.TestCase):
    """`--stack`: what `make up`, `make down` and `make check` run, through the stack's one owner."""

    def test_it_takes_status_or_one_action_on_the_stack_or_one_part(self):
        for words in (["status"], ["start"], ["stop", "windows"], ["restart", "wsl"]):
            self.assertEqual(cli.parse_args(["--stack"] + words).stack, words)
        for words in (["status", "wsl"], ["delete"], ["start", "wsl", "windows"]):
            with self.assertRaises(SystemExit, msg=words), contextlib.redirect_stderr(io.StringIO()):
                cli.parse_args(["--stack"] + words)

    def run_stack(self, words):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.stack_command(words)
        return code, out.getvalue()

    def test_status_prints_each_part_and_fails_unless_what_it_manages_is_up(self):
        async def read(policy):
            return {"components": [
                {"name": "temporal", "managed": True, "state": "up", "pid": None, "detail": ""},
                {"name": "wsl", "managed": True, "state": "up", "pid": 42, "detail": "polls orchestration"},
                {"name": "windows", "managed": True, "state": "down", "pid": None, "detail": ""}]}
        self.addCleanup(setattr, stack, "read", stack.read)
        stack.read = read
        code, out = self.run_stack(["status"])
        self.assertEqual(code, 1, "a managed part is down")
        self.assertIn("wsl worker       up — pid 42; polls orchestration", out)
        self.assertIn("windows worker   DOWN", out)

    def test_an_action_prints_each_part_as_it_comes_and_fails_when_one_did(self):
        def stop(policy, component=None, progress=None):
            results = [{"component": "windows", "ok": True, "said": "stopped"},
                       {"component": "wsl", "ok": False, "said": "still running, pid 42"}]
            for result in results:
                progress(result)
            return results
        self.addCleanup(setattr, stack, "ACTIONS", stack.ACTIONS)
        stack.ACTIONS = dict(stack.ACTIONS, stop=stop)
        code, out = self.run_stack(["stop"])
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), ["windows worker   done — stopped",
                                            "wsl worker       FAILED — still running, pid 42"])



class Forms(unittest.TestCase):
    def test_a_run_names_its_flow_and_one_that_ended_without_a_build_succeeded(self):
        self.assertEqual(cli.parse_args(["a task", "--flow", "architect-research"]).flow, "architect-research")
        self.assertIsNone(cli.parse_args(["a task"]).flow, "none named: the policy's default")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli._report({"state": {"status": "DONE"}, "stop": None}, "run-1", None), 0)
        self.assertIn("finished: DONE", out.getvalue())

    def test_a_flow_that_does_not_hold_starts_nothing_and_says_why(self):
        from app.foundation import flows
        folder = tempfile.mkdtemp(prefix="orch-flows-")
        self.addCleanup(shutil.rmtree, folder, True)
        self.addCleanup(setattr, flows, "FLOWS_DIR", flows.FLOWS_DIR)
        flows.FLOWS_DIR = folder
        with open(os.path.join(folder, "broken.json"), "w", encoding="utf-8") as fh:
            json.dump(["engineer:plan", "you:approve"], fh)
        for name, said in (("no-such-flow", "no flow 'no-such-flow'"),
                           ("broken", "flow 'broken': step 1, 'engineer:plan': the engineer's work goes to its "
                                      "review, assess, next")):
            out = io.StringIO()
            with contextlib.redirect_stderr(out):
                # A client that can start nothing: the flow is refused before one is needed.
                code = asyncio.run(cli.run(["a task", "--flow", name], client=object(), tele=object(), check=False))
            self.assertEqual(code, 4, name)
            self.assertIn(said, out.getvalue())

    def test_the_stack_is_not_a_runs_form(self):
        """`--stack` is `main`'s own command; a caller of the run forms is refused it, never sent to a start."""
        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            code = asyncio.run(cli.run(["--stack", "status"], client=object(), tele=object()))
        self.assertEqual(code, 4)
        self.assertIn("--stack runs as its own command", out.getvalue())


class Follow(unittest.TestCase):
    """Following a run leaves nothing of Temporal's behind when it returns."""

    def test_no_call_to_temporal_is_still_in_flight_when_it_returns(self):
        """The SDK's native runtime answers a call even after its caller stopped waiting, and one answered
        while the process exits needs the interpreter as it shuts down: the process never exits — its
        runtime's thread parked in pause(), the main thread waiting on that thread (measured)."""

        class Handle:
            """A run that works a moment, then stops, as the SDK serves it: a call once sent stays in flight
            until Temporal answers it, whatever becomes of whoever awaited it — and no event ever comes for a
            long poll. The first look finds it working, so the follow waits between looks at least once."""
            sent = answered = looks = 0

            async def query(self, query):
                self.sent += 1
                await asyncio.sleep(0)              # a call to Temporal yields while it is answered
                self.answered += 1
                self.looks += 1
                if self.looks == 1:
                    return {"lines": ["[plan e1 r1] engineer started"], "stop": None, "state": {}}
                return {"lines": ["[plan e1 r1] engineer started", "stopped: approval"],
                        "stop": {"id": "r:1", "reason": "approval"}, "state": {}}

            async def describe(self):
                self.sent += 1
                await asyncio.sleep(0)
                self.answered += 1
                return type("Description", (), {"close_time": None})()

            def fetch_history_events(self, **kwargs):
                handle = self

                class Poll:
                    def __aiter__(self):
                        handle.sent += 1
                        return self

                    async def __anext__(self):
                        await asyncio.Event().wait()
                        handle.answered += 1
                return Poll()

        async def followed(handle):
            status = await cli.follow(handle)
            await asyncio.sleep(0.1)                # whatever it started has had its moment to start
            return status

        handle = Handle()
        with contextlib.redirect_stdout(io.StringIO()):
            status = asyncio.run(followed(handle))
        self.assertEqual(status["stop"]["reason"], "approval")
        self.assertGreaterEqual(handle.looks, 2, "it waited between looks")
        self.assertEqual(handle.sent, handle.answered, "a call to Temporal still in flight when it returned")


if __name__ == "__main__":
    unittest.main()
