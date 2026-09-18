"""The stops a run makes and the guarantees around them, each with the control that shows the test can fail.

- Named answers: validated before they reach history, and one answer applied once.
- A role activity whose worker is lost is never attempted again.
- A role runs only on its target host's queue.
- A refused repository creates no worktree.
- The final gate: merge, revise to either role, a confirmed discard, a conflict handed back.
"""
import json
import os
import sys
import threading
import time
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

from temporalio.api.enums.v1 import EventType  # noqa: E402
from temporalio.client import WorkflowUpdateFailedError  # noqa: E402

import temporal_env as E  # noqa: E402
from fakes import FakeRepos, FakeWorktrees, codex_review_first, codex_review_resumed  # noqa: E402
from test_workflow import Scenario  # noqa: E402
import control_workflows  # noqa: E402
import workflow as WF  # noqa: E402

ACCEPTED = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_UPDATE_ACCEPTED


def history(handle):
    async def collect():
        return [event async for event in handle.fetch_history_events()]
    return E.run(collect())


def to_ready():
    a1, _ = codex_review_first("PASS")
    return [("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1),
            ("build-e2-1", 0, "built\n"), ("verify-e2-1", 0, codex_review_resumed("PASS"))]


class NamedAnswers(Scenario):
    """A stop takes only its named answers, and applies one answer once."""

    def blocked(self):
        b1, _ = codex_review_first("BLOCKER", "premise wrong")
        return self.drive([("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, b1),
                           ("plan-e2-1", 0, "p2\n"), ("assess-e2-1", 0, codex_review_resumed("PASS"))])

    def send(self, run, answer, update_id):
        return E.run(run.handle.execute_update(WF.FeatureRun.answer, answer, id=update_id))

    def test_an_answer_the_stop_does_not_offer_is_rejected_and_leaves_no_event(self):
        run = self.blocked()
        stop = run.stop
        before = [e.event_type for e in history(run.handle)].count(ACCEPTED)
        for answer in ({"stop": stop["id"], "action": "discard", "confirm": True},
                       {"stop": stop["id"], "action": "guide", "text": "  "},
                       {"stop": "%s:99" % run.run_id, "action": "guide", "text": "use B"}):
            with self.assertRaises(WorkflowUpdateFailedError, msg=answer):
                self.send(run, answer, "answer:%s" % answer["stop"])
        # The test server records the workflow task that ran each validator; what must never be
        # written is an accepted answer. On a real server even that task leaves no event (the live acceptance).
        self.assertEqual([e.event_type for e in history(run.handle)].count(ACCEPTED), before,
                         "a rejected answer is never written")
        self.assertEqual(E.run(run.handle.query(WF.FeatureRun.status))["stop"]["id"], stop["id"])
        self.assertEqual(len(self.agent.calls), 2, "and nothing ran")

    def test_the_same_answer_sent_twice_is_applied_once(self):
        run = self.blocked()
        answer = {"stop": run.stop["id"], "action": "guide", "text": "use B"}
        first = self.send(run, answer, "answer:%s" % answer["stop"])
        second = self.send(run, answer, "answer:%s" % answer["stop"])
        self.assertEqual(first, second)
        run.status = E.run(E.cli.follow(run.handle, answered=answer["stop"]))
        self.assertEqual(run.stop["reason"], "approval")
        self.assertEqual([e.event_type for e in history(run.handle)].count(ACCEPTED), 1)
        self.assertEqual([c["name"] for c in self.agent.calls].count("plan-e2-1"), 1)

    def test_an_unrecognised_answer_through_the_cli_is_asked_again(self):
        a1, _ = codex_review_first("PASS")
        run = self.drive([("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, a1)])
        code, out = run.answer("maybe later")
        self.assertEqual(code, 2)
        self.assertIn("does not answer", out)
        self.assertEqual(run.stop["reason"], "approval", "never read as abort")

    def test_control_without_a_validator_or_with_fresh_ids_answers_are_written_and_applied_again(self):
        run_id = uuid.uuid4().hex[:12]
        handle = E.run(E.client().start_workflow(control_workflows.NoValidatorRun.run, {}, id=run_id,
                                                 task_queue=WF.TASK_QUEUE))
        nonsense = {"stop": "x:1", "action": "nonsense"}
        E.run(handle.execute_update("answer", nonsense, id="answer:x:1"))
        E.run(handle.execute_update("answer", nonsense, id="answer:x:1"))
        E.run(handle.execute_update("answer", nonsense, id="fresh-%s" % uuid.uuid4().hex))
        E.run(handle.signal("finish"))
        answers = E.run(handle.result())
        self.assertEqual(len(answers), 2, "the unrecognised answer was written, and a fresh id applied it again")
        self.assertEqual([e.event_type for e in history(handle)].count(ACCEPTED), 2)


class SingleAttempt(Scenario):
    """A role whose activity is lost is not launched again; Continue launches one more."""

    def setUp(self):
        self.release = threading.Event()
        self.addCleanup(self.release.set)

    def hanging(self, launches):
        def runner(worktree, argv, rdir, name, prompt, timeout, env, *, brain):
            launches.append(name)
            # A worker that stopped heartbeating: the activity is lost to Temporal.
            self.release.wait(60)
            return 1, ""
        return runner

    def policy(self):
        return dict(E.POLICY, heartbeat_seconds=2)

    def test_a_lost_role_stops_for_the_operator_after_one_launch(self):
        launches = []
        self.host, self.agent = E.host([])
        self.host.runner = self.hanging(launches)
        run = E.Run(policy=self.policy())
        self.addCleanup(run.cleanup)
        self.assertEqual(run.stop["reason"], "failed")
        self.assertIn("heartbeat", run.stop["feedback"].lower())
        time.sleep(3)
        self.assertEqual(launches, ["plan-e1-1"], "exactly one launch")

    def test_control_the_default_retry_policy_launches_it_again(self):
        launches = []
        E.host([])
        E.hosts()[E.WSL_QUEUE].runner = self.hanging(launches)
        state = {"run_id": "retry-control", "task": "t", "phase": "plan", "round": 0, "episode": 1,
                 "worktree_path": "/fake/worktree/x", "todo_path": "/fake/worktree/x/todo/t.md",
                 "agent_sessions": {}}
        handle = E.run(E.client().start_workflow(
            control_workflows.RetryControl.run,
            {"stage": "plan", "state": state, "policy": self.policy(), "queue": E.WSL_QUEUE},
            id="retry-%s" % uuid.uuid4().hex[:8], task_queue=WF.TASK_QUEUE))
        self.addCleanup(lambda: E.run(handle.terminate("control done")))
        deadline = time.monotonic() + 60
        while len(launches) < 2 and time.monotonic() < deadline:
            time.sleep(0.5)
        self.assertGreaterEqual(len(launches), 2, "Temporal's default retries launch the role again")


class HostRouting(Scenario):
    """A role runs on its target host's queue and no other."""

    def test_a_windows_target_runs_only_on_the_windows_host(self):
        a1, _ = codex_review_first("PASS")
        self.host, self.agent = E.host([("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, a1)], queue=E.WINDOWS_QUEUE)
        run = E.Run(target="windows")
        self.addCleanup(run.cleanup)
        self.assertEqual(run.stop["reason"], "approval",
                         "any role on the WSL host would have failed the run: it is set to refuse")
        self.assertEqual(len(self.agent.calls), 2)

    def test_control_a_windows_target_routed_to_the_wsl_queue_runs_on_the_wsl_host(self):
        a1, _ = codex_review_first("PASS")
        self.host, self.agent = E.host([("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, a1)], queue=E.WSL_QUEUE)
        run = E.Run(target="windows", queue=E.WSL_QUEUE)
        self.addCleanup(run.cleanup)
        self.assertEqual(len(self.agent.calls), 2, "the queue, not the target's name, decides the host")


class Refusal(Scenario):
    """A run refused on its target host has created nothing."""

    def test_a_refused_repository_creates_no_worktree(self):
        git = FakeWorktrees()
        run = self.drive([], git=git, repositories=FakeRepos(refusal="codex is not installed on the wsl host"))
        self.assertEqual(run.state["status"], "REFUSED")
        self.assertIn("codex is not installed", run.state["refusal"])
        self.assertEqual(git.calls, [])
        self.assertTrue(run.closed())


class FinalGate(Scenario):
    """Merge, revise to a role, discard, and a conflict handed back into the run."""

    def ready(self, extra=(), merge_results=None):
        self.git = FakeWorktrees(merge_results)
        run = self.drive(to_ready() + list(extra), git=self.git, auto=True)
        self.assertEqual((run.stop["reason"], run.state["status"]), ("final", "READY_FOR_HUMAN"))
        return run

    def test_merge_commits_the_verified_change_and_ends(self):
        run = self.ready()
        code, out = run.answer("merge")
        self.assertEqual(code, 0, out)
        self.assertEqual(run.state["status"], "MERGED")
        self.assertEqual(self.git.calls[-1], ("merge", run.run_id, "verified-tree",
                                              "2026-09-15_1200-toy_task: toy task", "Merge 2026-09-15_1200-toy_task"))
        self.assertTrue(run.closed())

    def test_revise_to_the_engineer_builds_and_verifies_again(self):
        run = self.ready([("build-e3-1", 0, "tightened\n"), ("verify-e3-1", 0, codex_review_resumed("PASS"))])
        run.answer("revise engineer tighten the guard")
        run.status = E.run(E.cli.follow(run.handle))
        self.assertEqual(run.stop["reason"], "final")
        by_name = {call["name"]: call for call in self.agent.calls}
        self.assertIn("tighten the guard", by_name["build-e3-1"]["prompt"])
        self.assertIn("tighten the guard", by_name["verify-e3-1"]["prompt"])

    def test_revise_to_the_architect_verifies_again_without_building(self):
        run = self.ready([("verify-e3-1", 0, codex_review_resumed("PASS"))])
        run.answer("revise architect re-check the error path")
        run.status = E.run(E.cli.follow(run.handle))
        self.assertEqual(run.stop["reason"], "final")
        self.assertEqual([c["name"] for c in self.agent.calls][-1], "verify-e3-1")
        self.assertIn("re-check the error path", self.agent.calls[-1]["prompt"])

    def test_discard_needs_confirmation(self):
        run = self.ready()
        code, out = run.answer("discard")
        self.assertEqual(code, 2)
        self.assertIn("confirmed", out)
        self.assertEqual(run.stop["reason"], "final")
        self.assertNotIn("discard", [call[0] for call in self.git.calls])
        code, _ = run.answer("discard", confirm=True)
        self.assertEqual((code, run.state["status"]), (0, "DISCARDED"))
        self.assertEqual(self.git.calls[-1], ("discard", run.run_id))

    def test_a_conflict_goes_back_to_the_engineer_and_the_merge_is_offered_again(self):
        run = self.ready([("build-e3-1", 0, "resolved\n"), ("verify-e3-1", 0, codex_review_resumed("PASS"))],
                         merge_results=[{"result": "conflict", "files": ["app.txt"]},
                                        {"result": "merged", "commit": "abc123"}])
        run.answer("merge")
        run.status = E.run(E.cli.follow(run.handle))
        self.assertEqual(run.stop["reason"], "final", "resolved, verified, and offered to the operator again")
        self.assertIn("app.txt", {call["name"]: call for call in self.agent.calls}["build-e3-1"]["prompt"])
        code, _ = run.answer("merge")
        self.assertEqual((code, run.state["status"], run.state["merge_commit"]), (0, "MERGED", "abc123"))

    def test_a_refused_merge_stays_at_the_gate_and_says_why(self):
        run = self.ready(merge_results=[{"result": "refused", "reason": "the worktree no longer matches"}])
        code, out = run.answer("merge")
        self.assertEqual(code, 0)
        self.assertEqual((run.stop["reason"], run.stop["feedback"]), ("final", "the worktree no longer matches"))

    def test_revise_at_plan_approval_plans_again_with_the_feedback(self):
        a1, _ = codex_review_first("PASS")
        run = self.drive([("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, a1),
                          ("plan-e2-1", 0, "p2\n"), ("assess-e2-1", 0, codex_review_resumed("PASS"))])
        run.answer("revise split the change in two")
        self.assertEqual(run.stop["reason"], "approval")
        self.assertIn("split the change in two", self.agent.calls[2]["prompt"])

    def test_abort_at_a_failed_stage_ends_the_run(self):
        run = self.drive([("plan-e1-1", 1, "boom\n")])
        self.assertEqual(run.stop["reason"], "failed")
        run.answer("abort")
        self.assertEqual(run.state["status"], "ABORTED")


if __name__ == "__main__":
    unittest.main()
