"""The workflow's contract on Temporal, over the fake seams: routes, rounds, gates, sessions, failures.

Run on Temporal's time-skipping test server. With ORCHESTRA_WORKFLOW_UNDER_TEST=empty every
scenario fails: they prove the workflow, not the harness.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
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
from app.application import settings as S  # noqa: E402
from app.foundation import policy as policy_mod  # noqa: E402
from app.orchestration import workflow as WF  # noqa: E402


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
        # A policy already handed to a run with max_rounds keeps its per-episode boundary.
        legacy = dict(POLICY)
        legacy.pop("review_rounds", None)
        legacy["max_rounds"] = {"plan": 2, "build": 2}
        a1, _ = codex_review_first("PATCH", "fix A")
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1),
                          ("plan-e1-2", 0, "revised\n"), ("assess-e1-2", 0, codex_review_resumed("UNVERIFIED"))],
                         policy=legacy)
        self.assertEqual(run.stop["reason"], "exhausted")
        self.assertIn("fix A", self.agent.calls[2]["prompt"])

    def test_review_rounds_reflect_once_after_ten_and_exhaust_with_evidence_at_twenty(self):
        summaries = ("Unresolved: one concrete gap. Tried: two changes. Disputed: finding B, because test C "
                     "shows otherwise. Likely cause: implementation reasoning. Operator input: choose whether "
                     "to narrow the scope.")
        script = []
        for round_ in range(1, 21):
            engineer_name = "plan-e1-%d" % round_
            review_name = "assess-e1-%d" % round_
            engineer_out = "planned\n" if round_ == 1 else "revised\n"
            if round_ == 1:
                review_out = codex_review_first("PATCH", "fix round 1")[0]
            elif round_ == 20:
                review_out = codex_review_resumed("UNVERIFIED", summaries)
            else:
                review_out = codex_review_resumed("PATCH", "fix round %d" % round_)
            script.extend(((engineer_name, 0, engineer_out), (review_name, 0, review_out)))
        policy = dict(POLICY)
        policy["review_rounds"] = {phase: {"normal": 10, "extended": 10} for phase in ("plan", "build")}
        policy.pop("max_rounds", None)
        run = self.drive(script, policy=policy)
        self.assertEqual(run.stop["reason"], "exhausted")
        self.assertEqual(len(self.agent.calls), 40)
        self.assertIn("normal review budget of 10 iterations has elapsed", self.agent.calls[20]["prompt"])
        self.assertIn("normal review budget of 10 iterations has elapsed", self.agent.calls[21]["prompt"])
        self.assertNotIn("normal review budget of 10 iterations has elapsed", self.agent.calls[22]["prompt"])
        final_prompt = self.agent.calls[39]["prompt"]
        for term in ("what remains unresolved", "what was tried", "which findings are disputed",
                     "likely cause", "operator decision"):
            self.assertIn(term, final_prompt)
        self.assertEqual(run.stop["feedback"], summaries, "the exhausted stop presents the final review evidence")

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
        legacy = dict(POLICY)
        legacy.pop("review_rounds", None)
        legacy["max_rounds"] = {"plan": 2, "build": 2}
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1),
                          ("plan-e1-2", 0, "v2\n"), ("assess-e1-2", 0, codex_review_resumed("PATCH")),
                          ("plan-e2-1", 0, "v3\n"),        # the reset restarts attempts, in a new episode
                          ("assess-e2-1", 0, codex_review_resumed("PASS"))], policy=legacy)
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
        from app.agents.adapters import claude_code, codex
        argv = ["codex", "resume", "t1", "--sandbox", "read-only"]
        self.assertEqual(codex.host(argv, windows=True),
                         ["codex", "resume", "t1", "--sandbox", "read-only", "-c", 'windows.sandbox="unelevated"'],
                         "the override is added, and the sandbox policy stays")
        self.assertEqual(codex.host(argv, windows=False), argv)
        claude = ["claude", "--permission-mode", "plan"]
        self.assertEqual(claude_code.host(claude, windows=True, skills="/no/such/dir"), claude)
        skills = os.path.dirname(os.path.abspath(__file__))
        self.assertEqual(claude_code.host(claude, skills=skills), claude + ["--add-dir", skills],
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

    def test_a_brief_is_the_final_message_and_an_empty_one_is_no_answer(self):
        from app.agents import nodes as N
        claude, codex = {"brain": "claude"}, {"brain": "codex"}
        self.assertEqual(N.final_message(claude, "  Brief: one job.\n"), "Brief: one job.")
        self.assertEqual(N.final_message(codex, codex_first_out("Brief: one job.")[0]), "Brief: one job.")
        # A turn that said nothing gave no brief: neither its events nor its blank message are one.
        for silent in (codex_first_out("")[0], codex_first_out(" \n")[0], "no events at all\n"):
            with self.assertRaises(N.ContentError, msg=silent):
                N.final_message(codex, silent)
        with self.assertRaises(N.ContentError):
            N.final_message(claude, " \n")

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
        legacy = dict(POLICY)
        legacy.pop("review_rounds", None)
        legacy["max_rounds"] = {"plan": 2, "build": 2}
        run = self.drive([("plan-e1-1", 0, "v1\n"), ("assess-e1-1", 0, a1),
                          ("plan-e1-2", 0, "v2\n"), ("assess-e1-2", 0, codex_review_resumed("PATCH")),
                          ("plan-e2-1", 0, "v3\n"), ("assess-e2-1", 0, codex_review_resumed("PASS"))],
                         policy=legacy)
        run.answer("narrow it")
        names = self.names()
        self.assertEqual(len(names), 6)
        self.assertEqual(len(names), len(set(names)), "a reset episode must not overwrite earlier transcripts")

    def test_a_stage_skill_leads_the_prompt_only_where_the_policy_binds_one(self):
        """A host's own methodology is a binding, not something this component carries: named in the
        settings, and invoked as the role's kind invokes one."""
        from app.agents import nodes as N
        state = {"task": "t", "todo_path": "/w/todo/x.md", "run_id": "r1", "worktree_path": "/w",
                 "phase": "plan", "round": 0, "episode": 1, "feedback": "", "guidance": ""}
        roles = S.run_policy(temporal_env.SETTINGS)["roles"]
        bound = N.compose_prompt("plan", roles["engineer"], False, state, True, True,
                                 skills={"plan": "investigate-change"})
        self.assertTrue(bound.startswith("/investigate-change\n"),
                        "a bound skill invokes only as the prompt's first characters")
        self.assertTrue(N.compose_prompt("assess", roles["architect"], True, state, True, True,
                                         skills={"assess": "architect"}).startswith("$architect\n"),
                        "each kind invokes it its own way: Codex by `$name`")
        self.assertNotIn("/investigate-change",
                         N.compose_prompt("plan", roles["engineer"], False, state, True, True, skills=None),
                         "a prompt without its run policy does not invent a skill")
        self.assertEqual(S.load()["stage_skills"]["plan"], "investigate-change",
                         "the shared settings own the default binding")
        old = {"brain": "claude", "workspace_access": "write", "prompt_path": os.path.join(PKG, "roles", "engineer.md")}
        self.assertTrue(N.compose_prompt("plan", old, False, state, True, True,
                                         skills={"plan": "/investigate-change"}).startswith("/investigate-change\n"),
                        "a run started before agent profiles named it `/name`, and still invokes it")

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


# A run's policy as a run started before agent profiles carries it: a brain for each role, the access it
# stored, a persona file's path and where the policy was loaded, and each skill as `/name`.
OLD_SHAPE = dict(json.loads(json.dumps(POLICY)), _policy_path="policy.json",
                 roles={"engineer": {"brain": "claude", "workspace_access": "write", "prompt": "roles/engineer.md"},
                        "architect": {"brain": "codex", "workspace_access": "read", "prompt": "roles/architect.md",
                                      "model": "gpt-5.6-sol", "reasoning_effort": "high"}},
                 stage_skills={"plan": "/investigate-change", "assess": "/architect",
                               "build": "/implement-approved-change", "verify": "/architect"})


class ARunKeepsItsPersonas(Scenario):
    """A persona edited after a run started never reaches it: the run carries the text it started with."""

    def persona_file(self):
        folder = tempfile.mkdtemp(prefix="orchestra-persona-")
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "architect.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("Judge as first written.\n")
        return path

    def architects_prompt(self, policy, path):
        """The architect's first prompt, in a run whose persona file is rewritten while its engineer plans:
        after the run started, before the architect's session is born."""
        a1, _ = codex_review_first("PASS")
        self.host, self.agent = host([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1)])
        agent = self.host.runner

        def planning(worktree, argv, rdir, name, prompt, timeout, env, *, kind):
            if name.startswith("plan"):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("Judge as edited later.\n")
            return agent(worktree, argv, rdir, name, prompt, timeout, env, kind=kind)
        self.host.runner = planning
        run = Run(policy=policy)
        self.addCleanup(run.cleanup)
        self.assertEqual(run.stop["reason"], "approval")
        return self.agent.calls[1]["prompt"]

    def test_the_architect_is_given_the_persona_the_run_started_with(self):
        path = self.persona_file()
        settings = json.loads(json.dumps(temporal_env.SETTINGS))
        settings["roles"]["architect"]["persona_file"] = path
        prompt = self.architects_prompt(S.run_policy(settings), path)
        self.assertIn("Judge as first written.", prompt)
        self.assertNotIn("edited later", prompt)

    def test_control_a_run_started_before_agent_profiles_reads_its_persona_file_at_the_session(self):
        path = self.persona_file()
        old = json.loads(json.dumps(OLD_SHAPE))
        old["roles"]["architect"]["prompt"] = path
        self.assertIn("Judge as edited later.", self.architects_prompt(old, path))


class AnyProfileUnderAnyRole(Scenario):
    """D9: any profile runs any role, both roles one profile included, each role with its own access; and a
    run started before agent profiles runs as it did."""

    def test_both_roles_on_one_profile_plan_review_and_build(self):
        settings = json.loads(json.dumps(temporal_env.SETTINGS))
        settings["roles"]["architect"]["agent"] = settings["roles"]["engineer"]["agent"]
        S.check(settings)
        verdict = '{"verdict": "PASS", "feedback": "sound"}\n'
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, verdict),
                          ("build-e2-1", 0, "built\n"), ("verify-e2-1", 0, verdict)],
                         auto=True, policy=S.run_policy(settings))
        self.assertEqual(run.state["status"], "READY_FOR_HUMAN")
        self.assertEqual({call["kind"] for call in self.agent.calls}, {"claude-code"})
        modes = {call["name"]: call["argv"][call["argv"].index("--permission-mode") + 1] for call in self.agent.calls}
        self.assertEqual(modes, {"plan-e1-1": "dontAsk", "assess-e1-1": "plan", "build-e2-1": "dontAsk",
                                 "verify-e2-1": "plan"}, "the reviewer reads only, whatever it runs")
        sessions = run.state["agent_sessions"]
        self.assertNotEqual(sessions["engineer"], sessions["architect"], "one profile, two sessions")

    def test_a_run_of_the_old_shape_runs_as_before(self):
        looked = []

        def which(program):
            looked.append(program)
            return "/fake/bin/%s" % program
        a1, _ = codex_review_first("PASS")
        self.host, self.agent = host([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, a1)], which=which)
        run = Run(policy=OLD_SHAPE)
        self.addCleanup(run.cleanup)
        self.assertEqual(run.stop["reason"], "approval")
        self.assertEqual(sorted(looked), ["claude", "codex"], "its brains' programs, found through their kinds")
        self.assertEqual([call["kind"] for call in self.agent.calls], ["claude-code", "codex"])
        self.assertTrue(self.agent.calls[0]["prompt"].startswith("/investigate-change\n"))
        self.assertTrue(self.agent.calls[1]["prompt"].startswith("$architect\n"),
                        "its `/name` skill is the skill `name`, invoked as the architect's kind does")
        with open(os.path.join(PKG, "roles", "engineer.md"), encoding="utf-8") as fh:
            self.assertIn(fh.readline().strip(), self.agent.calls[0]["prompt"], "its persona file, as it named it")


class Policy(unittest.TestCase):
    """Settings are validated whole: here their shape and references, and each kind's own values through its
    adapter (`application/test_settings.py`)."""

    def _raw(self):
        return json.loads(json.dumps(temporal_env.SETTINGS))

    def test_both_roles_may_run_one_profile(self):
        """D9: whether the reviewer is another model is the operator's choice, and no rule of this one."""
        raw = self._raw()
        raw["roles"]["architect"]["agent"] = raw["roles"]["engineer"]["agent"]
        S.check(policy_mod.validate(raw))

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

    def test_shipped_role_profiles_pin_the_models_and_effort(self):
        settings = S.load()
        self.assertEqual((settings["roles"]["engineer"]["agent"], settings["roles"]["architect"]["agent"]),
                         ("claude-engineer", "claude-architect"))
        expected = {
            "claude-engineer": ("claude-code", "claude-opus-5", "max"),
            "claude-architect": ("claude-code", "claude-fable-5", "high"),
            "codex-engineer": ("codex", "gpt-6-luna", "xhigh"),
            "codex-architect": ("codex", "gpt-5.6-sol", "high"),
        }
        self.assertEqual({name: (profile["kind"], profile.get("model"), profile.get("effort"))
                          for name, profile in settings["agents"].items()}, expected)

    def test_missing_persona_file_rejected(self):
        raw = self._raw()
        raw["roles"]["engineer"]["persona_file"] = "roles/does-not-exist.md"
        with self.assertRaisesRegex(policy_mod.InvalidPolicy, "persona file missing") as raised:
            policy_mod.validate(raw)
        self.assertEqual(raised.exception.pointer, "/roles/engineer/persona_file")

    def test_unknown_keys_rejected_top_and_role(self):
        raw = self._raw()
        raw["max_round"] = 2
        with self.assertRaisesRegex(policy_mod.InvalidPolicy, "unknown setting") as raised:
            policy_mod.validate(raw)
        self.assertEqual(raised.exception.pointer, "/max_round")
        raw = self._raw()
        raw["roles"]["engineer"]["modle"] = "x"
        with self.assertRaisesRegex(policy_mod.InvalidPolicy, "unknown setting") as raised:
            policy_mod.validate(raw)
        self.assertEqual(raised.exception.pointer, "/roles/engineer/modle")

    def test_git_triple_must_be_false(self):
        raw = self._raw()
        raw["target_repo"]["push_allowed"] = True
        with self.assertRaises(policy_mod.InvalidPolicy):
            policy_mod.validate(raw)

    def test_bad_rounds_rejected(self):
        for bad in (0, -1, "2", True):
            raw = self._raw()
            raw["review_rounds"]["plan"]["normal"] = bad
            with self.assertRaises(policy_mod.InvalidPolicy):
                policy_mod.validate(raw)

    def test_a_stops_cleanup_bound_is_optional_and_may_only_shorten_the_minute(self):
        """A Stop's cleanup waits a minute at most: a policy may shorten that, never lengthen it."""
        policy_mod.validate(self._raw())
        raw = self._raw()
        for good in (1, 5, 60):
            raw["stop_cleanup_seconds"] = good
            policy_mod.validate(raw)
        for bad in (0, -1, "2", True, 1.5, 61, 3600):
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

    def test_the_default_flow_is_optional_and_names_one(self):
        raw = self._raw()
        raw.pop("default_flow", None)
        policy_mod.validate(raw)
        raw["default_flow"] = "engineer-code"
        policy_mod.validate(raw)
        # A flow's name by the flows' own grammar: one the policy takes can always name a file in flows/.
        for bad in (3, "", "../policy", None, "engineer:code"):
            raw["default_flow"] = bad
            with self.assertRaisesRegex(policy_mod.InvalidPolicy, "default_flow", msg=repr(bad)):
                policy_mod.validate(raw)


class Flows(Scenario):
    """A run follows the flow it was started with, one step after another; a run started before flows
    follows the order those runs took."""

    CODE = ["engineer:plan", "architect:assess", "you:approve", "engineer:build", "architect:verify", "you:merge"]
    RESEARCH = ["architect:research", "you:approve"] + CODE
    LOST = "ERROR: No saved session found with ID 01a0-bogus. Run `codex resume` without an ID\n"

    def watched(self):
        from fakes import FakeWorktrees

        class Watched(FakeWorktrees):
            def __init__(inner):
                super().__init__()
                inner.judged = []

            def work_tree(inner, path):
                inner.judged.append(path)
                return "verified-tree"
        return Watched()

    def test_a_run_started_before_flows_follows_the_order_those_runs_took(self):
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, codex_review_first("PASS")[0])])
        self.assertEqual(run.state["flow"], {"name": None, "steps": self.CODE})
        self.assertEqual((run.stop["reason"], run.state["step"]), ("approval", 2))
        self.assertEqual(run.stop["hint"], WF.HINTS["approval"], "a plan's approval reads as it always has")

    def test_research_first_hands_its_brief_to_the_plan_and_merges(self):
        brief, _ = codex_first_out("Brief: use the platform's scheduler.\nAbstract todo: add one job.")
        git = self.watched()
        run = self.drive([("research-e1-1", 0, brief),
                          ("research-e2-1", 0, codex_first_out("Brief v2: the scheduler, narrowed to one queue.")[0]),
                          ("plan-e3-1", 0, "planned\n"), ("assess-e3-1", 0, codex_review_resumed("PASS")),
                          ("build-e4-1", 0, "built\n"), ("verify-e4-1", 0, codex_review_resumed("PASS"))],
                         git=git, flow=self.RESEARCH)
        # The brief is the research step's answer: no verdict read from it, no tree judged for it.
        self.assertEqual((run.stop["reason"], run.state["step"]), ("approval", 1))
        self.assertEqual(run.state["brief"], "Brief: use the platform's scheduler.\nAbstract todo: add one job.")
        self.assertIn("Abstract todo: add one job.", run.stop["feedback"], "the approval shows the brief")
        self.assertEqual(run.stop["hint"], "approve to go on to the plan, or revise with feedback for new research")
        self.assertNotIn("verdict", run.state)
        self.assertEqual(git.judged, [], "research judges no tree")
        self.assertEqual(run.status["timeline"][-1]["brief"], run.state["brief"])
        research = self.agent.calls[0]["argv"]
        self.assertEqual(research[research.index("--sandbox") + 1], "read-only", "the architect researches read-only")
        # Revised: the research runs again, with the operator's words.
        # The command line's code 2 is a run stopped for you again, 0 one at its final gate or finished.
        code, out = run.answer("revise narrow it to one queue")
        self.assertEqual((code, run.stop["reason"]), (2, "approval"), out)
        self.assertIn("narrow it to one queue", self.agent.calls[1]["prompt"])
        self.assertEqual(run.state["brief"], "Brief v2: the scheduler, narrowed to one queue.")
        # Approved: the engineer plans from the brief, on the code; the words were the research's own.
        code, out = run.answer("yes")
        self.assertEqual((code, run.stop["reason"], run.state["step"]), (2, "approval", 4), out)
        plan = self.agent.calls[2]["prompt"]
        self.assertIn("Brief v2: the scheduler, narrowed to one queue.", plan)
        self.assertNotIn("narrow it to one queue", plan)
        code, out = run.answer("yes")
        self.assertEqual((code, run.stop["reason"], run.state["step"]), (0, "final", 7), out)
        code, out = run.answer("merge")
        self.assertEqual((code, run.state["status"]), (0, "MERGED"), out)
        self.assertEqual(self.names(), ["research-e1-1", "research-e2-1", "plan-e3-1", "assess-e3-1",
                                        "build-e4-1", "verify-e4-1"])
        self.assertIn(("merge", run.run_id, "verified-tree"), [call[:3] for call in git.calls])

    def test_a_research_session_born_again_is_given_the_brief_its_feedback_is_about(self):
        brief, _ = codex_first_out("Brief: use the platform's scheduler.")
        run = self.drive([("research-e1-1", 0, brief), ("research-e2-1", 1, self.LOST),
                          ("research-e2-1-rehydrated", 0, codex_first_out("Brief v2.")[0])],
                         flow=self.RESEARCH)
        code, out = run.answer("revise narrow it to one queue")
        self.assertEqual((code, run.stop["reason"], run.state["brief"]), (2, "approval", "Brief v2."), out)
        prompt = self.agent.calls[-1]["prompt"]
        for said in ("# Task", "You are the architect", "# Your previous brief", "Brief: use the platform's scheduler.",
                     "narrow it to one queue"):
            self.assertIn(said, prompt)

    def test_research_alone_ends_done_once_its_brief_is_approved_and_closes_its_terminals(self):
        from unittest import mock
        brief, _ = codex_first_out("Brief: nothing to build.")
        with mock.patch("app.agents.terminal.close_run") as closed:
            run = self.drive([("research-e1-1", 0, brief)], flow=["architect:research", "you:approve"])
            self.assertEqual(run.stop["hint"], "approve to end the run, or revise with feedback for new research")
            code, out = run.answer("yes")
        self.assertEqual((code, run.state["status"]), (0, "DONE"), out)
        self.assertTrue(run.closed())
        closed.assert_called_once_with(run.run_id)

    def test_a_flow_without_a_build_ends_done_keeping_its_worktree(self):
        from fakes import FakeWorktrees
        git = FakeWorktrees()
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, codex_review_first("PASS")[0])],
                         git=git, flow=["engineer:plan", "architect:assess"])
        self.assertTrue(run.closed())
        self.assertEqual(run.state["status"], "DONE")
        self.assertTrue(run.state["worktree_path"], "its worktree is kept")
        self.assertEqual([call[0] for call in git.calls], ["create"], "nothing merged, nothing discarded")

    def test_an_approval_says_where_it_goes_and_a_blocker_keeps_its_own_hint(self):
        twice = self.CODE[:5] + ["you:approve", "engineer:build", "architect:verify", "you:merge"]
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, codex_review_first("PASS")[0]),
                          ("build-e2-1", 0, "built\n"), ("verify-e2-1", 0, codex_review_resumed("PASS", "half done")),
                          ("build-e3-1", 0, "built on\n"), ("verify-e3-1", 0, codex_review_resumed("BLOCKER", "no"))],
                         flow=twice)
        self.assertEqual(run.stop["hint"], WF.HINTS["approval"])
        run.answer("yes")
        self.assertEqual((run.stop["reason"], run.state["step"], run.stop["feedback"]), ("approval", 5, "half done"))
        self.assertEqual(run.stop["hint"], "approve to go on to the build, or revise with feedback for a new build")
        code, out = run.answer("yes")
        self.assertEqual((code, run.stop["reason"], run.state["step"]), (2, "blocker", 7), out)
        self.assertEqual(run.stop["hint"], WF.HINTS["blocker"], "the flow's last part says no more than its stop")

    def test_skipping_approvals_never_skips_an_emergency_stop_or_the_final_gate(self):
        brief, _ = codex_first_out("Brief.")
        run = self.drive([("research-e1-1", 0, brief),
                          ("plan-e2-1", 0, "planned\n"), ("assess-e2-1", 0, codex_review_resumed("BLOCKER", "no")),
                          ("plan-e3-1", 0, "replanned\n"), ("assess-e3-1", 0, codex_review_resumed("PASS")),
                          ("build-e4-1", 0, "built\n"), ("verify-e4-1", 0, codex_review_resumed("PASS"))],
                         flow=self.RESEARCH, auto=True)
        self.assertEqual(run.stop["reason"], "blocker", "no approval stopped it, the blocker does")
        code, out = run.answer("go on with the queue")
        self.assertEqual((code, run.stop["reason"]), (0, "final"), out)
        self.assertEqual(self.names(), ["research-e1-1", "plan-e2-1", "assess-e2-1", "plan-e3-1", "assess-e3-1",
                                        "build-e4-1", "verify-e4-1"])

    def test_skipping_approvals_never_skips_a_spent_round_budget(self):
        run = self.drive([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, codex_review_first("PATCH", "fix A")[0]),
                          ("plan-e1-2", 0, "revised\n"), ("assess-e1-2", 0, codex_review_resumed("PATCH", "fix B"))],
                         auto=True)
        self.assertEqual((run.stop["reason"], run.stop["feedback"]), ("exhausted", "fix B"))

    def test_a_run_handed_a_flow_it_cannot_follow_is_refused_before_any_step(self):
        """Whatever shape a start past the client hands it: the flow is taken as given, never made into one."""
        from temporalio.api.enums.v1 import EventType
        for handed, said in (
                # Its keys, in whatever order they arrive, would make a flow that holds.
                ({"name": "mine", "steps": {"architect:research": "first"}},
                 "its flow: a flow is a list of steps, each `role:action`"),
                ({"name": "mine", "steps": ["engineer:plan", "you:approve"]},
                 "its flow: step 1, 'engineer:plan': the engineer's work goes to its review, assess, next"),
                ("engineer-code", "its flow: a run is handed its flow as {name, steps}"),
                # A flow given as null is given, and is no run from before flows, which had none at all.
                (None, "its flow: a run is handed its flow as {name, steps}"),
                ({"name": "mine"}, "its flow: a run is handed its flow as {name, steps}"),
                ({"name": "../mine", "steps": self.CODE}, "its flow: '../mine' is not a flow's name")):
            run = self.drive([], handed=handed)
            self.assertTrue(run.closed(), handed)
            self.assertEqual((run.state["status"], run.state["refusal"]), ("REFUSED", said))
            self.assertNotIn("flow", run.state, "a flow it cannot follow is never shown as the run's")
            history = temporal_env.run(run.handle.fetch_history())
            self.assertEqual([event for event in history.events
                              if event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED], [],
                             "no step, no worktree: %r" % (handed,))

    def test_a_run_started_through_the_client_keeps_its_flow_when_its_file_changes(self):
        import shutil
        import tempfile
        from app.foundation import flows
        folder = tempfile.mkdtemp(prefix="orchestra-flows-")
        self.addCleanup(shutil.rmtree, folder, True)
        self.addCleanup(setattr, flows, "FLOWS_DIR", flows.FLOWS_DIR)
        flows.FLOWS_DIR = folder
        mine = os.path.join(folder, "mine.json")
        with open(mine, "w", encoding="utf-8") as fh:
            json.dump(self.CODE, fh)
        repo = tempfile.mkdtemp(prefix="orchestra-flow-repo-")
        self.addCleanup(shutil.rmtree, repo, True)
        self.host, self.agent = host([("plan-e1-1", 0, "planned\n"), ("assess-e1-1", 0, codex_review_first("PASS")[0]),
                                      ("build-e2-1", 0, "built\n"), ("verify-e2-1", 0, codex_review_resumed("PASS"))])
        run = Run(handle=temporal_env.run(runs.start(client(), "a flow of my own", repo=repo, flow="mine",
                                                     check=False)))
        self.addCleanup(run.cleanup)
        self.assertEqual((run.state["flow"], run.stop["reason"]), ({"name": "mine", "steps": self.CODE}, "approval"))
        # The file now plans again after the approval; the run goes on with the steps it was handed.
        with open(mine, "w", encoding="utf-8") as fh:
            json.dump(self.CODE[:3] + ["engineer:plan", "architect:assess"], fh)
        code, out = run.answer("yes")
        self.assertEqual((code, run.stop["reason"]), (0, "final"), out)
        self.assertEqual(self.names(), ["plan-e1-1", "assess-e1-1", "build-e2-1", "verify-e2-1"])


if __name__ == "__main__":
    unittest.main()
