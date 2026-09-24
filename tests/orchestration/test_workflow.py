"""The workflow's contract on Temporal, over the fake seams: routes, rounds, gates, sessions, failures.

Run on Temporal's time-skipping test server. With ORCH_WORKFLOW_UNDER_TEST=empty every
scenario fails: they prove the workflow, not the harness.
"""
import json
import os
import subprocess
import sys
import unittest

# The suite's own folder, reached from this concern's folder inside it, and the
# checkout above both: the shared harness and the fixtures live at the suite root.
HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

from temporal_env import POLICY, Run, client, host  # noqa: E402
import temporal_env  # noqa: E402
from fakes import codex_first_out, codex_review_first, codex_review_resumed  # noqa: E402

from app.application import client as runs  # noqa: E402
from app.foundation import policy as policy_mod  # noqa: E402


class Scenario(unittest.TestCase):
    """Runs `script` through a real workflow and the real activities, with only the world faked."""

    def drive(self, script, git=None, repositories=None, telemetry=None, **kwargs):
        self.host, self.agent = host(script, git=git, repositories=repositories, telemetry=telemetry)
        run = Run(**kwargs)
        self.addCleanup(run.cleanup)
        return run

    def names(self):
        return [call["name"] for call in self.agent.calls]


class Routing(Scenario):
    def test_engineer_output_always_reaches_architect_full_pass(self):
        assess1, _ = codex_review_first("PASS")
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, assess1),
                          ("build-e2-1", 0, "built\n"), ("verify-e2-1", 0, codex_review_resumed("PASS"))],
                         auto=True)
        self.assertEqual((run.stop["reason"], run.state["status"]), ("final", "READY_FOR_HUMAN"))
        self.assertEqual(self.names(), ["plan-e1-1", "assess-e1-1", "build-e2-1", "verify-e2-1"])

    def test_patch_and_unverified_loop_bounded_then_human(self):
        # max_rounds.plan == 2: round 1 PATCH -> engineer again; round 2 UNVERIFIED == max -> exhausted.
        a1, _ = codex_review_first("PATCH", "fix A")
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1),
                          ("plan-e1-2", 0, "revised\n"), ("assess-e1-2", 0, codex_review_resumed("UNVERIFIED"))])
        self.assertEqual(run.stop["reason"], "exhausted")
        self.assertIn("fix A", self.agent.calls[2]["prompt"])

    def test_blocker_reaches_human_only_via_architect(self):
        a1, _ = codex_review_first("BLOCKER", "premise wrong")
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1)])
        self.assertEqual(run.stop["reason"], "blocker")

    def test_pass_without_auto_proceed_asks_approval(self):
        a1, _ = codex_review_first("PASS")
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1)])
        self.assertEqual(run.stop["reason"], "approval")

    def test_malformed_architect_output_is_error_never_verdict(self):
        garbage, _ = codex_first_out("Looks good, PASS from me!")      # not schema JSON
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, garbage)])
        self.assertEqual(run.stop["reason"], "failed")
        self.assertIn("malformed_output", run.stop["feedback"])
        self.assertNotIn("verdict", run.state)

    def test_broken_stream_is_transport_error(self):
        # A codex first call with no thread.started at all is a broken transport, not content.
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, "Looks good, PASS from me!\n")])
        self.assertEqual(run.stop["reason"], "failed")
        self.assertIn("agent_exit", run.stop["feedback"])

    def test_gate_resume_reexecutes_no_cli(self):
        a1, _ = codex_review_first("PASS")
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1),
                          ("build-e2-1", 0, "built\n"), ("verify-e2-1", 0, codex_review_resumed("PASS"))])
        self.assertEqual(len(self.agent.calls), 2)
        code, _ = run.answer("yes")
        self.assertEqual(code, 0)
        self.assertEqual(run.state["status"], "READY_FOR_HUMAN")
        self.assertEqual(self.names()[2:], ["build-e2-1", "verify-e2-1"])

    def test_guidance_reentry_resets_round(self):
        a1, _ = codex_review_first("PATCH")
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1),
                          ("plan-e1-2", 0, "v2\n"), ("assess-e1-2", 0, codex_review_resumed("PATCH")),
                          ("plan-e2-1", 0, "v3\n"),        # the reset restarts attempts, in a new episode
                          ("assess-e2-1", 0, codex_review_resumed("PASS"))])
        self.assertEqual(run.stop["reason"], "exhausted")
        run.answer("narrow the scope to X")
        self.assertEqual(run.stop["reason"], "approval")
        self.assertIn("narrow the scope to X", self.agent.calls[4]["prompt"])

    def test_a_plan_changed_after_its_pass_is_assessed_again_before_any_build(self):
        """The operator approves the plan the architect passed; typing into a live terminal is not approval."""
        from fakes import FakeWorktrees
        a1, _ = codex_review_first("PASS", "Direction: A.")

        class Changing(FakeWorktrees):
            tree = "plan-A"

            def work_tree(inner, path):
                return inner.tree

        git = Changing()
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1),
                          # the plan the operator typed, judged again before anything is built
                          ("assess-e2-1", 0, codex_review_resumed("PASS", "Direction: B.")),
                          ("build-e3-1", 0, "built\n"), ("verify-e3-1", 0, codex_review_resumed("PASS"))],
                         git=git)
        self.assertEqual(run.stop["reason"], "approval")
        git.tree = "plan-B"                      # typed into the idle engineer at the approval stop
        run.answer("yes")
        self.assertEqual(self.names(), ["plan-e1-1", "assess-e1-1", "assess-e2-1"],
                         "no build ran on a plan the architect had not passed")
        self.assertEqual(run.stop["reason"], "approval", "the new plan is offered for approval again")
        run.answer("yes")
        self.assertEqual(self.names()[-2:], ["build-e3-1", "verify-e3-1"], "the approved plan is built")

    def test_no_stop_offers_abort_and_one_sent_is_refused(self):
        """Ending a run is a Stop, from any state; no stop's answers include ending it."""
        a1, _ = codex_review_first("BLOCKER")
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1)])
        self.assertEqual((run.stop["reason"], run.stop["actions"]), ("blocker", ["guide"]))
        with self.assertRaises(runs.NotAccepted):
            temporal_env.run(runs.answer(client(), run.run_id, {"stop": run.stop["id"], "action": "abort"},
                                         check=False))
        self.assertFalse(run.closed(), "an abort sent anyway ended nothing")
        self.assertEqual(run.stop["reason"], "blocker", "and the run still waits for guidance")


class Sessions(Scenario):
    def _run_to_ready(self):
        a1, _ = codex_review_first("PATCH", "fix A")
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1),
                          ("plan-e1-2", 0, "revised\n"), ("assess-e1-2", 0, codex_review_resumed("PASS")),
                          ("build-e2-1", 0, "built\n"),
                          ("verify-e2-1", 0, codex_review_resumed("PATCH", "fix B")),
                          ("build-e2-2", 0, "fixed\n"), ("verify-e2-2", 0, codex_review_resumed("PASS"))],
                         auto=True)
        self.assertEqual(run.state["status"], "READY_FOR_HUMAN")
        return run

    def test_two_sessions_exact_resume_cross_stage_continuity(self):
        sessions = self._run_to_ready().state["agent_sessions"]
        self.assertEqual(set(sessions), {"engineer", "architect"})
        self.assertEqual(len(set(sessions.values())), 2)
        by_name = {call["name"]: call for call in self.agent.calls}
        # The engineer's session persists plan -> build (claude exact-id resume).
        self.assertIn("--resume %s" % sessions["engineer"], by_name["plan-e1-2"]["command"])
        self.assertIn("--resume %s" % sessions["engineer"], by_name["build-e2-1"]["command"])
        # The architect's persists assess -> verify (codex exact-id resume).
        self.assertIn("codex resume %s" % sessions["architect"], by_name["assess-e1-2"]["command"])
        self.assertIn("codex resume %s" % sessions["architect"], by_name["verify-e2-1"]["command"])
        for call in self.agent.calls:
            self.assertNotIn("--last", call["argv"])

    def test_architect_readonly_engineer_write(self):
        self._run_to_ready()
        for call in self.agent.calls:
            argv = call["argv"]
            if call["name"].startswith(("assess", "verify")):
                # A fresh and a resumed Codex both take the flag, and never ask before a command.
                self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
                self.assertEqual(argv[argv.index("--ask-for-approval") + 1], "never")
                self.assertIn('web_search="live"', argv)
            else:
                # Never waits on a prompt, and may edit only inside its worktree.
                self.assertEqual(argv[argv.index("--permission-mode") + 1], "dontAsk")
                self.assertEqual(argv[argv.index("--allowedTools") + 1], "Edit(./**)")

    def test_a_windows_host_runs_codex_in_the_unelevated_sandbox(self):
        from app.application import activities
        codex = ["codex", "resume", "t1", "--sandbox", "read-only"]
        self.assertEqual(activities.host_argv(codex, "codex", windows=True),
                         ["codex", "resume", "t1", "--sandbox", "read-only", "-c", 'windows.sandbox="unelevated"'],
                         "the override is added, and the sandbox policy stays")
        self.assertEqual(activities.host_argv(codex, "codex", windows=False), codex)
        claude = ["claude", "--permission-mode", "plan"]
        self.assertEqual(activities.host_argv(claude, "claude", windows=True, skills="/no/such/dir"), claude)
        skills = os.path.dirname(os.path.abspath(__file__))
        self.assertEqual(activities.host_argv(claude, "claude", skills=skills), claude + ["--add-dir", skills],
                         "a Claude role reads its skills' references without a prompt")

    def test_stage_template_reanchors_on_stage_switch(self):
        self._run_to_ready()
        by_name = {call["name"]: call for call in self.agent.calls}
        self.assertTrue(by_name["build-e2-1"]["prompt"].startswith("/implement-approved-change"),
                        "the build stage must invoke its skill as the prompt's first characters")
        self.assertIn("git diff", by_name["verify-e2-1"]["prompt"])

    def test_the_architect_judges_from_the_change_and_never_runs_tests(self):
        from app.application import activities
        run = self._run_to_ready()
        logs = os.path.join(activities.run_dir(run.run_id), "logs")
        asks = [call for call in self.agent.calls if "Independently" in call["prompt"]]
        self.assertEqual([call["name"] for call in asks], ["assess-e1-1", "verify-e2-1"],
                         "each review stage's first turn carries the stage ask")
        for call in asks:
            self.assertIn("Do not run tests or builds", call["prompt"])
            self.assertIn(logs, call["prompt"], "the engineer's reports are named where they are")
        for call in self.agent.calls:
            if call["name"].startswith(("plan", "build")):
                self.assertNotIn("Do not run tests", call["prompt"])

    def test_a_verdict_is_read_from_the_final_message(self):
        from app.agents import nodes as N
        claude = {"brain": "claude"}
        text = 'Checked the diff.\n```json\n{"verdict": "PATCH", "feedback": "fix {a} in b"}\n```'
        self.assertEqual(N.parse_review(claude, 0, text), ("PATCH", "fix {a} in b"))
        two = '{"verdict": "PASS", "feedback": "draft"} then revised: {"verdict": "BLOCKER", "feedback": "no"}'
        self.assertEqual(N.parse_review(claude, 0, two), ("BLOCKER", "no"), "the last verdict given is the one")
        for bad in ("Looks good, PASS from me!", '{"verdict": "GREAT", "feedback": "x"}', '{"verdict": "PASS"}',
                    # The ask is one object and nothing after it; a verdict written past is not the answer.
                    '{"verdict": "PASS", "feedback": "ok"}\nActually, I could not check the tests.'):
            with self.assertRaises(N.ContentError):
                N.parse_review(claude, 0, bad)

    def test_plan_pass_is_written_as_the_approval_summary(self):
        # D18: the operator approves implementation from this text alone.
        assess1, _ = codex_review_first("PASS")
        self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, assess1),
                    ("build-e2-1", 0, "built\n"), ("verify-e2-1", 0, codex_review_resumed("PASS"))], auto=True)
        assess, verify = self.agent.calls[1]["prompt"], self.agent.calls[3]["prompt"]
        for phrase in ("chosen direction", "blast radius", "reused versus newly built"):
            self.assertIn(phrase, assess)
            self.assertNotIn(phrase, verify)
        self.assertIn("short confirmation on PASS", verify)

    def test_architect_session_loss_midloop_rehydrates_completely(self):
        # A session lost on round 2 comes back independently executable: task, persona,
        # the current stage ask and the findings it is asked to re-check.
        a1, _ = codex_review_first("PATCH", "fix the DNS guard in module A")
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1),
                          ("plan-e1-2", 0, "revised\n"),
                          ("assess-e1-2", 1, "ERROR: No saved session found with ID 01a0-bogus. Run `codex resume` without an ID\n"),
                          ("assess-e1-2-rehydrated", 0, codex_review_first("PASS")[0])])
        self.assertEqual(run.stop["reason"], "approval")
        call = self.agent.calls[-1]
        prompt = call["prompt"]
        self.assertIn("# Task", prompt)
        self.assertIn("You are the architect", prompt)
        self.assertIn("Independently assess the todo", prompt)
        self.assertIn("End your final message with exactly one JSON object", prompt)
        self.assertIn("fix the DNS guard in module A", prompt)
        self.assertNotIn("stage instructions are unchanged", prompt)
        self.assertNotIn("resume", call["argv"])

    def test_engineer_session_loss_in_build_rehydrates_with_build_anchor(self):
        a1, _ = codex_review_first("PASS")
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1),
                          ("build-e2-1", 0, "built\n"),
                          ("verify-e2-1", 0, codex_review_resumed("PATCH", "tighten the guard")),
                          ("build-e2-2", 1, "Error: No conversation found with session ID: dead\n"),
                          ("build-e2-2-rehydrated", 0, "rebuilt\n"),
                          ("verify-e2-2", 0, codex_review_resumed("PASS"))], auto=True)
        self.assertEqual(run.state["status"], "READY_FOR_HUMAN")
        prompt = next(c for c in self.agent.calls if c["name"] == "build-e2-2-rehydrated")["prompt"]
        self.assertIn("# Task", prompt)
        self.assertIn("You are the engineer", prompt)
        self.assertTrue(prompt.startswith("/implement-approved-change"), prompt[:40])
        self.assertIn("Implement the approved todo at", prompt)
        self.assertNotIn("write the reviewable todo", prompt)
        self.assertIn("tighten the guard", prompt)

    def test_guidance_survives_worker_and_reaches_architect(self):
        a1, _ = codex_review_first("BLOCKER", "premise wrong")
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1),
                          ("plan-e2-1", 0, "v2\n"), ("assess-e2-1", 0, codex_review_resumed("PASS"))])
        run.answer("use approach B instead")
        by_name = {call["name"]: call for call in self.agent.calls}
        self.assertIn("use approach B instead", by_name["plan-e2-1"]["prompt"])
        self.assertIn("use approach B instead", by_name["assess-e2-1"]["prompt"],
                      "the architect must judge with the operator's decision in hand")

    def test_log_names_survive_a_human_reset_episode(self):
        a1, _ = codex_review_first("PATCH")
        run = self.drive([("plan-e1-1", 0, "v1\n"), ("assess-e1-1", 0, a1),
                          ("plan-e1-2", 0, "v2\n"), ("assess-e1-2", 0, codex_review_resumed("PATCH")),
                          ("plan-e2-1", 0, "v3\n"), ("assess-e2-1", 0, codex_review_resumed("PASS"))])
        run.answer("narrow it")
        names = self.names()
        self.assertEqual(len(names), 6)
        self.assertEqual(len(names), len(set(names)), "a reset episode must not overwrite earlier transcripts")

    def test_a_stage_skill_leads_the_prompt_only_where_the_policy_binds_one(self):
        """A host's own methodology is a binding, not something this component carries."""
        from app.agents import nodes as N
        from app.foundation import policy as P
        state = {"task": "t", "todo_path": "/w/todo/x.md", "run_id": "r1", "worktree_path": "/w",
                 "phase": "plan", "round": 0, "episode": 1, "feedback": "", "guidance": ""}
        role = dict(P.load()["roles"]["engineer"], prompt_path=os.path.join(PKG, "roles", "engineer.md"))
        bound = N.compose_prompt("plan", role, False, state, True, True,
                                 skills={"plan": "/investigate-change"})
        self.assertTrue(bound.startswith("/investigate-change\n"),
                        "a bound skill invokes only as the prompt's first characters")
        self.assertNotIn("/investigate-change",
                         N.compose_prompt("plan", role, False, state, True, True, skills=None),
                         "and the shipped policy binds none, so no invocation appears")
        self.assertEqual(P.load().get("stage_skills"), None, "nothing is bound by default")

    def test_prompt_files_reach_composed_prompts(self):
        a1, _ = codex_review_first("PASS")
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1)])
        self.assertEqual(run.stop["reason"], "approval")
        self.assertTrue(self.agent.calls[0]["prompt"].startswith("/investigate-change"))
        # The plan is named by the repository's todo convention, from the run's start time.
        self.assertIn(os.path.join("todo", "2026-09-15_1200-toy_task.md"), self.agent.calls[0]["prompt"])
        self.assertIn("your verdict is the only thing that routes", self.agent.calls[1]["prompt"])
        self.assertIn("Independently assess the todo", self.agent.calls[1]["prompt"])


class Continue(Scenario):
    """A stage fails for an external reason; the operator fixes it and continues the same run."""

    def test_continue_reruns_only_the_failed_stage(self):
        a1, _ = codex_review_first("PASS")
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 1, "Error: usage limit reached\n"),
                          ("assess-e1-1", 0, a1), ("build-e2-1", 0, "built\n"),
                          ("verify-e2-1", 0, codex_review_resumed("PASS"))], auto=True)
        self.assertEqual(run.stop["reason"], "failed")
        self.assertIn("assess", run.stop["feedback"])                  # the failing stage is named
        out = temporal_env.io.StringIO()
        with temporal_env.contextlib.redirect_stdout(out):
            code = temporal_env.run(temporal_env.cli._answer(client(), run.run_id, "continue", False, None,
                                                             False, only="failed"))
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("READY_FOR_HUMAN", out.getvalue())
        self.assertEqual(self.names().count("plan-e1-1"), 1, "the successful stage must not run again")
        self.assertEqual(self.names().count("assess-e1-1"), 2, "only the failed stage runs again")


DRIVER = ("import sys, asyncio; sys.path[:0]=[%r,%r]; from app.interfaces import cli; "
          "sys.exit(asyncio.run(cli.run(sys.argv[1:], check=False)))" % (PKG, HERE))


class AnotherProcess(Scenario):
    """The run lives in Temporal: a process that exits at a stop loses nothing, and another answers it."""

    def cli(self, *args):
        target = client().service_client.config.target_host
        env = dict(os.environ, TEMPORAL_ADDRESS=target, TEMPORAL_NAMESPACE=client().namespace)
        return subprocess.run([sys.executable, "-c", DRIVER] + list(args), capture_output=True,
                              text=True, env=env, timeout=120)

    def test_an_answer_from_another_process_continues_the_run_and_an_unknown_id_is_refused(self):
        a1, _ = codex_review_first("PASS")
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1),
                          ("build-e2-1", 0, "built\n"), ("verify-e2-1", 0, codex_review_resumed("PASS"))])
        self.assertEqual(run.stop["reason"], "approval")
        self.assertEqual(self.names(), ["plan-e1-1", "assess-e1-1"])
        answered = self.cli("--resume", run.run_id, "--answer", "yes")
        self.assertEqual(answered.returncode, 0, answered.stdout + answered.stderr)
        self.assertIn("READY_FOR_HUMAN", answered.stdout)
        self.assertEqual(self.names(), ["plan-e1-1", "assess-e1-1", "build-e2-1", "verify-e2-1"])

        # No such run: refused, and nothing executes.
        refused = self.cli("--resume", "does-not-exist", "--answer", "yes")
        self.assertEqual(refused.returncode, 3, refused.stdout + refused.stderr)
        self.assertIn("refusing", refused.stderr)
        self.assertEqual(len(self.agent.calls), 4, "the refused resume must execute nothing")


class Policy(unittest.TestCase):
    def _raw(self):
        return json.loads(json.dumps(POLICY))

    def test_d3_same_model_rejected(self):
        raw = self._raw()
        raw["roles"]["architect"]["brain"] = "claude"
        raw["roles"]["architect"].pop("model", None)
        with self.assertRaisesRegex(policy_mod.InvalidPolicy, "D3"):
            policy_mod.validate(raw)
        raw["roles"]["engineer"]["model"] = "some-model"
        raw["roles"]["architect"]["model"] = "some-model"
        with self.assertRaisesRegex(policy_mod.InvalidPolicy, "D3"):
            policy_mod.validate(raw)

    def test_d3_same_brain_different_models_accepted(self):
        raw = self._raw()
        raw["roles"]["architect"]["brain"] = "claude"
        raw["roles"]["engineer"]["model"] = "model-a"
        raw["roles"]["architect"]["model"] = "model-b"
        policy_mod.validate(raw)

    def test_d3_default_model_is_not_a_wildcard(self):
        raw = self._raw()
        raw["roles"]["architect"]["brain"] = "claude"
        raw["roles"]["architect"].pop("model", None)
        raw["roles"]["engineer"]["model"] = "model-a"
        policy_mod.validate(raw)

    def test_model_and_effort_are_plain_tokens(self):
        for key, bad in (("model", "a b"), ("model", "x;rm"), ("reasoning_effort", "high'"),
                         ("reasoning_effort", "")):
            raw = self._raw()
            raw["roles"]["architect"][key] = bad
            with self.assertRaises(policy_mod.InvalidPolicy, msg=(key, bad)):
                policy_mod.validate(raw)
        raw = self._raw()
        raw["roles"]["engineer"]["reasoning_effort"] = "medium"
        policy_mod.validate(raw)

    def test_the_workflow_queue_is_required_and_a_plain_token(self):
        """No default: a policy that forgot its own would join the deployment's queue, and its runs."""
        for bad in (None, "", "two words", "orchestration;x", 7):
            raw = self._raw()
            if bad is None:
                raw.pop("workflow_queue")
            else:
                raw["workflow_queue"] = bad
            with self.assertRaisesRegex(policy_mod.InvalidPolicy, "workflow_queue", msg=repr(bad)):
                policy_mod.validate(raw)
        raw = self._raw()
        raw["workflow_queue"] = "orchestration:demo1a2b3c"
        policy_mod.validate(raw)

    def test_shipped_architect_pins_model_and_effort(self):
        architect = POLICY["roles"]["architect"]
        self.assertTrue(architect.get("model"))
        self.assertTrue(architect.get("reasoning_effort"))

    def test_architect_must_be_readonly(self):
        raw = self._raw()
        raw["roles"]["architect"]["workspace_access"] = "write"
        with self.assertRaises(policy_mod.InvalidPolicy):
            policy_mod.validate(raw)

    def test_missing_prompt_file_rejected(self):
        raw = self._raw()
        raw["roles"]["engineer"]["prompt"] = "roles/does-not-exist.md"
        with self.assertRaisesRegex(policy_mod.InvalidPolicy, "prompt file missing"):
            policy_mod.validate(raw)

    def test_unknown_keys_rejected_top_and_role(self):
        raw = self._raw()
        raw["max_round"] = 2
        with self.assertRaisesRegex(policy_mod.InvalidPolicy, "unknown policy keys"):
            policy_mod.validate(raw)
        raw = self._raw()
        raw["roles"]["engineer"]["modle"] = "x"
        with self.assertRaisesRegex(policy_mod.InvalidPolicy, "unknown keys"):
            policy_mod.validate(raw)

    def test_git_triple_must_be_false(self):
        raw = self._raw()
        raw["target_repo"]["push_allowed"] = True
        with self.assertRaises(policy_mod.InvalidPolicy):
            policy_mod.validate(raw)

    def test_bad_rounds_rejected(self):
        for bad in (0, -1, "2", True):
            raw = self._raw()
            raw["max_rounds"]["plan"] = bad
            with self.assertRaises(policy_mod.InvalidPolicy):
                policy_mod.validate(raw)

    def test_a_stops_cleanup_bound_is_optional_and_a_whole_number_of_seconds(self):
        policy_mod.validate(self._raw())
        raw = self._raw()
        raw["stop_cleanup_seconds"] = 5
        policy_mod.validate(raw)
        for bad in (0, -1, "2", True, 1.5):
            raw["stop_cleanup_seconds"] = bad
            with self.assertRaisesRegex(policy_mod.InvalidPolicy, "stop_cleanup_seconds", msg=repr(bad)):
                policy_mod.validate(raw)

    def test_each_target_host_has_its_own_queue(self):
        self.assertEqual((policy_mod.queue(POLICY, "wsl"), policy_mod.queue(POLICY, "windows")),
                         ("target:wsl:local", "target:windows:local"))
        raw = self._raw()
        del raw["targets"]["windows"]
        with self.assertRaisesRegex(policy_mod.InvalidPolicy, "targets"):
            policy_mod.validate(raw)


if __name__ == "__main__":
    unittest.main()
