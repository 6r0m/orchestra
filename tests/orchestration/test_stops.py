"""The stops a run makes and the guarantees around them, each with the control that shows the test can fail.

- Named answers: validated before they reach history, and one answer applied once.
- A role activity whose worker is lost is never attempted again.
- A role runs only on its target host's queue.
- A refused repository creates no worktree.
- The final gate: merge, revise to either role, a confirmed discard, a conflict handed back.
- A Stop ends a run from any open state and runs no git; a git side effect already running lands first.
- Force terminate closes a run at once, and cannot stop what its host is already doing.
"""
import asyncio
import contextlib
import datetime
import io
import json
import os
import shutil
import sys
import threading
import time
import unittest
import uuid

# The suite's own folder, reached from this concern's folder inside it, and the
# checkout above both: the shared harness and the fixtures live at the suite root.
HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

from temporalio.api.enums.v1 import EventType  # noqa: E402
from temporalio.client import WorkflowFailureError, WorkflowUpdateFailedError  # noqa: E402

import temporal_env as E  # noqa: E402
from fakes import FakeRepos, FakeWorktrees, codex_review_first, codex_review_resumed  # noqa: E402
from tests.orchestration.test_workflow import Scenario  # noqa: E402
import control_workflows  # noqa: E402
from app.agents import terminal  # noqa: E402
from app.orchestration import workflow as WF  # noqa: E402

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
        self.assertEqual(run.stop["reason"], "approval", "never read as another answer")

    def test_control_without_a_validator_or_with_fresh_ids_answers_are_written_and_applied_again(self):
        run_id = uuid.uuid4().hex[:12]
        handle = E.run(E.client().start_workflow(control_workflows.NoValidatorRun.run, {}, id=run_id,
                                                 task_queue=E.WORKFLOW_QUEUE))
        nonsense = {"stop": "x:1", "action": "nonsense"}
        E.run(handle.execute_update("answer", nonsense, id="answer:x:1"))
        E.run(handle.execute_update("answer", nonsense, id="answer:x:1"))
        E.run(handle.execute_update("answer", nonsense, id="fresh-%s" % uuid.uuid4().hex))
        E.run(handle.signal("finish"))
        answers = E.run(handle.result())
        self.assertEqual(len(answers), 2, "the unrecognised answer was written, and a fresh id applied it again")
        self.assertEqual([e.event_type for e in history(handle)].count(ACCEPTED), 2)


class AnswersAsPublished(unittest.TestCase):
    """The validator checks an answer against the actions its stop published, the role included."""

    @staticmethod
    def at(reason):
        run = WF.FeatureRun()
        run.state = {"run_id": "r"}
        run.stop = {"id": "r:1", "reason": reason, "actions": list(WF.ACTIONS[reason])}
        return run

    def test_a_revise_at_the_final_gate_names_a_role_the_gate_published(self):
        final = self.at("final")
        final._validate_answer({"stop": "r:1", "action": "revise", "role": "engineer", "text": "fix it"})
        for role in (None, "someone"):
            with self.assertRaises(ValueError, msg=role):
                final._validate_answer({"stop": "r:1", "action": "revise", "role": role, "text": "fix it"})

    def test_a_revise_at_the_plan_approval_names_no_role(self):
        approval = self.at("approval")
        approval._validate_answer({"stop": "r:1", "action": "revise", "text": "plan it again"})
        with self.assertRaises(ValueError):
            approval._validate_answer({"stop": "r:1", "action": "revise", "role": "engineer", "text": "x"})


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
            id="retry-%s" % uuid.uuid4().hex[:8], task_queue=E.WORKFLOW_QUEUE))
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

    def test_the_final_gate_publishes_a_revise_for_each_role(self):
        """A client shows what a stop publishes; the role a revise goes to is part of its name."""
        run = self.ready()
        self.assertEqual(run.stop["actions"], ["merge", "revise:engineer", "revise:architect", "discard"])

    def test_a_revise_named_as_published_reaches_its_role_through_the_shared_client(self):
        run = self.ready([("verify-e3-1", 0, codex_review_resumed("PASS"))])
        E.run(E.cli.runs.answer(E.client(), run.run_id, {"stop": run.stop["id"], "action": "revise:architect",
                                                         "text": "re-check the error path"}, check=False))
        run.status = E.run(E.cli.follow(run.handle))
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

    def test_a_failed_stage_takes_continue_alone_and_an_abort_is_refused(self):
        run = self.drive([("plan-e1-1", 1, "boom\n")])
        self.assertEqual((run.stop["reason"], run.stop["actions"]), ("failed", ["continue"]))
        code, out = run.answer("abort")
        self.assertEqual(code, 2, out)
        self.assertFalse(run.closed(), "a Stop is what ends a run; an abort ends nothing")


class Lifecycle(Scenario):
    """Runs ended from outside them, as the Workbench and the command line end them."""

    def setUp(self):
        self.release = threading.Event()
        self.addCleanup(self.release.set)

    def policy(self):
        # A working role hears of the Stop at its next heartbeat; a short one keeps the test short.
        return dict(E.POLICY, heartbeat_seconds=2)

    def start(self, **kwargs):
        """A run started and not followed: its stage does not finish by itself."""
        run_id = uuid.uuid4().hex[:12]
        handle = E.run(E.client().start_workflow(WF.FeatureRun.run, E.start_input(run_id, **kwargs),
                                                 id=run_id, task_queue=E.WORKFLOW_QUEUE))
        self.addCleanup(shutil.rmtree, E.A.run_dir(run_id), True)
        self.addCleanup(self.close, handle)
        return handle

    @staticmethod
    def close(handle):
        """Whatever a failing test left open ends here, so its stage never runs on a later test's fakes."""
        if E.run(handle.describe()).close_time is None:
            E.run(handle.terminate("the test is over"))

    def stopped(self, handle, answered=None):
        """Stop the run as the Workbench does, and follow it until it ends."""
        E.run(handle.cancel())
        status = E.run(E.cli.follow(handle, answered=answered))
        self.assertIsNotNone(E.run(handle.describe()).close_time, "the run ended: %s" % status["stop"])
        return status

    def until(self, handle, reached, seconds=60):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            status = E.run(handle.query(WF.FeatureRun.status))
            if reached(status):
                return status
            time.sleep(0.2)
        self.fail("the run never reached the expected state: %s" % status["state"].get("status"))

    def working(self, started, ended):
        """An agent at work: its turn heartbeats and honours a cancellation, as a real turn does."""
        def runner(worktree, argv, rdir, name, prompt, timeout, env, *, brain):
            started.set()
            try:
                while not self.release.is_set():
                    terminal._activity_tick(name)
                    time.sleep(0.1)
                return 1, ""
            finally:
                ended.set()
        return runner

    def gated(self, merge_results=None):
        """At the final gate, with a merge that runs until the test lets it land."""
        merging, land = threading.Event(), threading.Event()
        self.addCleanup(land.set)

        class Held(FakeWorktrees):
            def merge(self, *args):
                merging.set()
                land.wait(60)
                return super().merge(*args)
        self.git = Held(merge_results)
        run = self.drive(to_ready(), git=self.git, auto=True)
        self.assertEqual(run.stop["reason"], "final")
        return run, merging, land

    def git_run(self):
        return [call[0] for call in self.git.calls]


class Stop(Lifecycle):
    """A Stop — Temporal's cancellation of the run — ends it from any open state, stopped, and runs no
    git: its worktree and branch stay as they are. A git side effect already running is let land, and
    what git did decides how the run ends."""

    def test_a_run_waiting_at_a_stop_ends_stopped(self):
        a1, _ = codex_review_first("PASS")
        self.git = FakeWorktrees()
        run = self.drive([("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, a1)], git=self.git)
        self.assertEqual(run.stop["reason"], "approval")
        status = self.stopped(run.handle, answered=run.stop["id"])
        self.assertEqual((status["state"]["status"], status["stop"]), ("STOPPED", None))
        self.assertEqual(self.git_run(), ["create"], "the Stop ran no git: the worktree and branch stay")
        self.assertEqual(E.run(run.handle.describe()).status.name, "CANCELED", "Temporal's own record of it")

    def test_a_run_at_a_failed_stage_ends_stopped(self):
        self.git = FakeWorktrees()
        run = self.drive([("plan-e1-1", 1, "boom\n")], git=self.git)
        self.assertEqual(run.stop["reason"], "failed")
        status = self.stopped(run.handle, answered=run.stop["id"])
        self.assertEqual(status["state"]["status"], "STOPPED")
        self.assertEqual(self.git_run(), ["create"])

    def test_a_run_at_its_final_gate_ends_stopped_with_nothing_merged_or_discarded(self):
        self.git = FakeWorktrees()
        run = self.drive(to_ready(), git=self.git, auto=True)
        self.assertEqual(run.stop["reason"], "final")
        status = self.stopped(run.handle, answered=run.stop["id"])
        self.assertEqual(status["state"]["status"], "STOPPED")
        self.assertEqual(self.git_run(), ["create"])

    def test_a_run_whose_agent_works_ends_stopped_and_its_agent_with_it(self):
        started, ended = threading.Event(), threading.Event()
        self.git = FakeWorktrees()
        self.host, self.agent = E.host([], git=self.git)
        self.host.runner = self.working(started, ended)
        handle = self.start(policy=self.policy())
        self.assertTrue(started.wait(60), "the engineer is at work")
        status = self.stopped(handle)
        self.assertEqual(status["state"]["status"], "STOPPED")
        self.assertTrue(ended.wait(30), "its agent ended, and nothing of it runs on")
        self.assertEqual(self.git_run(), ["create"])

    def test_a_run_whose_host_has_no_worker_ends_stopped_without_waiting_for_one(self):
        # No worker polls this host's queue: the run waits for it from its first step, and the Stop's
        # cleanup there waits its policy's bound, here a short one, never for a worker.
        handle = self.start(target="windows", queue="target:windows:gone",
                            policy=dict(E.POLICY, stop_cleanup_seconds=2))
        began = time.monotonic()
        E.run(handle.cancel())
        with self.assertRaises(WorkflowFailureError, msg="Temporal records the run cancelled"):
            E.run(handle.result())
        self.assertLess(time.monotonic() - began, 30, "the cleanup waited its policy's bound, not a minute")
        status = E.run(handle.query(WF.FeatureRun.status))
        self.assertEqual(status["state"]["status"], "STOPPED")
        self.assertIn("the windows host's cleanup did not run", "\n".join(status["lines"]))

    def test_a_stops_cleanup_is_bound_to_a_minute_when_its_policy_sets_none(self):
        """Every shipped policy, and every run recorded before a policy could set one, carries no bound of its
        own: the cleanup is then scheduled to close within the workflow's minute, as `approval_stop.json`
        records it."""
        handle = self.start(target="windows", queue="target:windows:gone")
        E.run(handle.cancel())
        scheduled, deadline = None, time.monotonic() + 30
        while scheduled is None and time.monotonic() < deadline:
            for event in history(handle):
                attributes = event.activity_task_scheduled_event_attributes
                if (event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED
                        and attributes.activity_type.name == "finish_trace"):
                    scheduled = attributes
            time.sleep(0.2)
        self.assertIsNotNone(scheduled, "the Stop's cleanup was scheduled")
        self.assertEqual(scheduled.schedule_to_close_timeout.ToTimedelta(), datetime.timedelta(minutes=1))

    def merge_with_its_worker_gone(self, heartbeat_seconds=2):
        """A run at its final gate on a host of the test's own, whose worker goes away just as the merge is
        answered — the preflight still counts a worker dead for under a minute and a half as polling."""
        queue = "target:wsl:gone-%s" % uuid.uuid4().hex[:8]
        self.git = FakeWorktrees()
        _, worker_goes = E.own_host(self, queue, to_ready(), git=self.git)
        handle = self.start(queue=queue, auto=True,
                            policy=dict(E.POLICY, heartbeat_seconds=heartbeat_seconds, stop_cleanup_seconds=2))
        stop = self.until(handle, lambda status: status["stop"] and status["stop"]["reason"] == "final", 120)["stop"]
        worker_goes()
        E.run(E.cli.runs.answer(E.client(), handle.id, {"stop": stop["id"], "action": "merge"}, check=False))
        self.until(handle, lambda status: (status["state"].get("current") or {}).get("stage") == "merge")
        return queue, handle

    def test_a_stop_while_a_git_step_waits_for_a_worker_that_is_gone_ends_the_run_stopped(self):
        """The Stop ends the run stopped once the merge has waited a heartbeat interval for a worker — never
        waiting for one to come back — and git never runs that merge, not even when a worker does come back."""
        # Long enough that the Stop meets the merge still waiting, however loaded the host.
        queue, handle = self.merge_with_its_worker_gone(heartbeat_seconds=15)
        E.run(handle.cancel())
        with self.assertRaises(WorkflowFailureError):
            E.run(handle.result())
        self.assertEqual(E.run(handle.describe()).status.name, "CANCELED", "ended by the Stop, not timed out")
        status = E.run(handle.query(WF.FeatureRun.status))
        self.assertEqual(status["state"]["status"], "STOPPED")
        self.assertIn("no worker of the run's host took this step", "\n".join(status["lines"]))
        self.assertNotIn("stopped: failed", status["lines"], "the Stop met the merge while it waited")
        E.own_host(self, queue, [], git=self.git)
        time.sleep(3)                               # a worker polling the queue again, for a while
        self.assertNotIn("merge", self.git_run(), "git never ran it")

    def test_a_merge_no_worker_took_stops_for_the_operator_and_continue_merges(self):
        """Without a Stop the merge fails as any step does, saying no worker took it, and Continue merges
        once a worker is back."""
        queue, handle = self.merge_with_its_worker_gone()
        failed = self.until(handle, lambda status: status["stop"] and status["stop"]["reason"] == "failed", 60)
        self.assertIn("no worker of the run's host took this step", failed["stop"]["feedback"])
        self.assertNotIn("merge", self.git_run())
        E.own_host(self, queue, [], git=self.git)
        E.run(E.cli.runs.answer(E.client(), handle.id, {"stop": failed["stop"]["id"], "action": "continue"},
                                check=False))
        merged = self.until(handle, lambda status: status["state"]["status"] == "MERGED", 60)
        self.assertEqual(self.git_run().count("merge"), 1, "merged once, by the worker that came back")
        self.assertIsNone(merged["stop"])

    def test_a_stop_while_a_trace_write_runs_ends_the_run_stopped(self):
        """A trace write is best-effort and never the Stop's to wait for: one still running is let go."""
        writing, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def held(client, state, stop):
            writing.set()
            release.wait(60)
        self.addCleanup(setattr, E.A.T, "gate_event", E.A.T.gate_event)
        E.A.T.gate_event = held
        a1, _ = codex_review_first("PASS")
        self.git = FakeWorktrees()
        run = self.drive([("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, a1)], git=self.git)
        self.assertEqual(run.stop["reason"], "approval")
        self.assertTrue(writing.wait(30), "the stop's trace row is being written")
        E.run(run.handle.cancel())
        status = self.until(run.handle, lambda status: status["state"]["status"] == "STOPPED", 30)
        self.assertIsNone(status["stop"])

    def test_a_stop_during_a_merge_lets_it_land_and_the_run_ends_merged(self):
        run, merging, land = self.gated()
        E.run(E.cli.runs.answer(E.client(), run.run_id, {"stop": run.stop["id"], "action": "merge"}, check=False))
        self.assertTrue(merging.wait(30), "the merge is running")
        E.run(run.handle.cancel())
        self.until(run.handle, lambda status: status["state"]["status"] == "STOPPING")
        self.assertIsNone(E.run(run.handle.describe()).close_time, "not reported stopped while the merge can land")
        land.set()
        status = E.run(E.cli.follow(run.handle, answered=run.stop["id"]))
        self.assertEqual(status["state"]["status"], "MERGED", "what git did decides how the run ends")
        self.assertEqual(E.run(run.handle.describe()).status.name, "COMPLETED")

    def test_a_stop_during_a_merge_git_refuses_ends_the_run_stopped(self):
        run, merging, land = self.gated([{"result": "refused", "reason": "the worktree no longer matches"}])
        E.run(E.cli.runs.answer(E.client(), run.run_id, {"stop": run.stop["id"], "action": "merge"}, check=False))
        self.assertTrue(merging.wait(30), "the merge is running")
        E.run(run.handle.cancel())
        self.until(run.handle, lambda status: status["state"]["status"] == "STOPPING")
        land.set()
        status = E.run(E.cli.follow(run.handle, answered=run.stop["id"]))
        self.assertEqual((status["state"]["status"], status["stop"]), ("STOPPED", None),
                         "stopped, not back at its gate")

    def worker_gone(self):
        """The run's workflow worker gone, as the command line meets it: no worker polls, and a query waits.
        Returns the runs whose status was asked."""
        asked = []

        async def unanswered(client, run_id, timeout=None):
            asked.append(run_id)
            await asyncio.sleep(30)                 # as a query no worker answers waits

        async def nobody(client, needed):
            raise E.cli.runs.Refusal("no worker is polling %s — the wsl worker is not running" % needed[0][0])
        for name, stand_in in (("status", unanswered), ("preflight", nobody)):
            self.addCleanup(setattr, E.cli.runs, name, getattr(E.cli.runs, name))
            setattr(E.cli.runs, name, stand_in)
        return asked

    def test_the_command_line_refuses_an_answer_at_once_while_no_worker_can_read_the_run(self):
        a1, _ = codex_review_first("PASS")
        run = self.drive([("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, a1)], git=FakeWorktrees())
        asked = self.worker_gone()
        out, began = io.StringIO(), time.monotonic()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = E.run(E.cli.run(["--resume", run.run_id, "--answer", "yes"], client=E.client(), tele=object()))
        self.assertEqual(code, 4, out.getvalue())
        self.assertIn("the wsl worker is not running", out.getvalue())
        self.assertEqual(asked, [], "its status was never asked")
        self.assertLess(time.monotonic() - began, 10)

    def test_the_command_line_records_a_stop_at_once_while_no_worker_can_read_the_run(self):
        """With the run's workflow worker gone the Stop is still Temporal's to take: the command line records
        it first and says the run ends once a worker hears it — never waiting on a query no worker answers."""
        a1, _ = codex_review_first("PASS")
        run = self.drive([("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, a1)], git=FakeWorktrees())
        asked = self.worker_gone()
        out, began = io.StringIO(), time.monotonic()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = E.run(E.cli.run(["--stop", run.run_id], client=E.client(), tele=object()))
        self.assertEqual(code, 2, out.getvalue())
        self.assertIn("the Stop is recorded", out.getvalue())
        self.assertIn("the wsl worker is not running", out.getvalue())
        self.assertEqual(asked, [], "its status was never asked")
        self.assertLess(time.monotonic() - began, 10)
        deadline = time.monotonic() + 60
        while E.run(run.handle.describe()).close_time is None and time.monotonic() < deadline:
            time.sleep(0.2)
        self.assertEqual(E.run(run.handle.describe()).status.name, "CANCELED", "the Stop it recorded ended the run")

    def test_the_command_line_stops_a_run_and_says_how_it_ended(self):
        a1, _ = codex_review_first("PASS")
        run = self.drive([("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, a1)], git=FakeWorktrees())
        self.assertEqual(E.cli.parse_args(["--stop", run.run_id]).stop, run.run_id)
        code, out = command(["--stop", run.run_id])
        self.assertEqual(code, 0, out)
        self.assertIn("finished: STOPPED", out)
        code, out = command(["--stop", run.run_id])
        self.assertEqual(code, 3, "a closed run is not stopped again: %s" % out)


class ForceTerminate(Lifecycle):
    """Force terminate — Temporal's termination — closes a run at once, with no cleanup of its own, and
    cannot stop what the run's host is already doing."""

    def test_a_terminated_runs_working_agent_ends_at_its_next_heartbeat(self):
        started, ended = threading.Event(), threading.Event()
        self.host, self.agent = E.host([], git=FakeWorktrees())
        self.host.runner = self.working(started, ended)
        handle = self.start(policy=self.policy())
        self.assertTrue(started.wait(60), "the engineer is at work")
        self.assertFalse(ended.wait(3), "the control: an agent at work does not end by itself")
        E.run(handle.terminate("force terminate"))
        self.assertTrue(ended.wait(30), "its turn heard at its next heartbeat that the run is gone, and ended")

    def test_a_git_side_effect_already_running_goes_on_after_a_force_terminate(self):
        """Termination closes the run but cannot stop an activity already running: a merge, which does
        not heartbeat, finishes on its host afterwards — what the Workbench's confirmation warns of."""
        run, merging, land = self.gated()
        E.run(E.cli.runs.answer(E.client(), run.run_id, {"stop": run.stop["id"], "action": "merge"}, check=False))
        self.assertTrue(merging.wait(30), "the merge is running")
        E.run(E.cli.runs.force_terminate(E.client(), run.run_id, "the test"))
        self.assertEqual(E.run(run.handle.describe()).status.name, "TERMINATED")
        self.assertNotIn("merge", self.git_run(), "the control: nothing had merged when the run closed")
        land.set()
        deadline = time.monotonic() + 30
        while "merge" not in self.git_run() and time.monotonic() < deadline:
            time.sleep(0.2)
        self.assertIn("merge", self.git_run(), "the merge went on to its end after the run was closed")

    def test_what_a_terminated_run_kept_is_not_removed_while_its_merge_still_runs(self):
        """The merge a force terminate could not stop still changes the run's worktree on its host: a
        removal is refused there, saying so, until the merge has landed."""
        run, merging, land = self.gated()
        E.run(E.cli.runs.answer(E.client(), run.run_id, {"stop": run.stop["id"], "action": "merge"}, check=False))
        self.assertTrue(merging.wait(30), "the merge is running")
        E.run(E.cli.runs.force_terminate(E.client(), run.run_id, "the test"))

        async def polled(client, needed):
            return None                             # the test server lists no pollers
        self.addCleanup(setattr, E.cli.runs, "preflight", E.cli.runs.preflight)
        E.cli.runs.preflight = polled
        with E.env().auto_time_skipping_disabled():
            with self.assertRaises(E.cli.runs.Refusal) as refused:
                E.run(E.cli.runs.remove_worktree(E.client(), run.run_id))
            self.assertIn("busy: its merge is still running", str(refused.exception))
            self.assertNotIn("discard", self.git_run(), "nothing was removed under the merge")
            land.set()
            deadline = time.monotonic() + 30
            while run.run_id in self.host._git_busy and time.monotonic() < deadline:
                time.sleep(0.1)
            self.assertIn("merge", self.git_run())
            E.run(E.cli.runs.remove_worktree(E.client(), run.run_id))
        self.assertEqual(self.git_run().count("discard"), 1, "once it had landed, the removal ran")

    def test_a_removal_no_worker_of_its_host_takes_is_refused_within_its_bound_and_never_runs(self):
        """A target host's worker dead for under a minute and a half still counts as polling: a removal it
        never takes is refused once its bound is out, naming that host — never waited on for the page's
        minutes — and git never removes anything, not even when a worker does come back."""
        queue = "target:wsl:gone-%s" % uuid.uuid4().hex[:8]
        self.git = FakeWorktrees()
        _, worker_goes = E.own_host(self, queue, to_ready(), git=self.git)
        handle = self.start(queue=queue, auto=True, policy=dict(E.POLICY, heartbeat_seconds=2))
        self.until(handle, lambda status: status["stop"] and status["stop"]["reason"] == "final", 120)
        E.run(handle.cancel())
        with self.assertRaises(WorkflowFailureError):
            E.run(handle.result())
        worker_goes()

        async def polled(client, needed):
            return None                             # as the preflight counts a worker dead for under POLLING
        for name, stand_in in (("preflight", polled), ("TAKEN", datetime.timedelta(seconds=2))):
            self.addCleanup(setattr, E.cli.runs, name, getattr(E.cli.runs, name))
            setattr(E.cli.runs, name, stand_in)
        began = time.monotonic()
        with E.env().auto_time_skipping_disabled():
            with self.assertRaises(E.cli.runs.Refusal) as refused:
                E.run(E.cli.runs.remove_worktree(E.client(), handle.id))
        self.assertLess(time.monotonic() - began, 30, "refused once its bound was out")
        self.assertIn("no wsl worker took the removal", str(refused.exception))
        E.own_host(self, queue, [], git=self.git)
        time.sleep(3)                               # a worker polling the queue again, for a while
        self.assertNotIn("discard", self.git_run(), "nothing ran once a worker came back")

    def test_the_command_line_force_terminates_a_run(self):
        a1, _ = codex_review_first("PASS")
        run = self.drive([("plan-e1-1", 0, "p\n"), ("assess-e1-1", 0, a1)], git=FakeWorktrees())
        self.assertEqual(E.cli.parse_args(["--force-terminate", run.run_id]).force_terminate, run.run_id)
        code, out = command(["--force-terminate", run.run_id])
        self.assertEqual(code, 0, out)
        self.assertEqual(E.run(run.handle.describe()).status.name, "TERMINATED")
        code, out = command(["--force-terminate", run.run_id])
        self.assertEqual(code, 3, "a closed run is not terminated again: %s" % out)


def command(argv):
    """The command line as the operator runs it, over the test server; its exit code and output."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = E.run(E.cli.run(argv, client=E.client(), check=False))
    return code, out.getvalue()


if __name__ == "__main__":
    unittest.main()
