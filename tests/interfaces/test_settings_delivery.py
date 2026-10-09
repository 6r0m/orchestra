"""Settings applied through Workbench, delivered to scripted agent turns through Temporal."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

import temporal_env as E  # noqa: E402
import cast  # noqa: E402
from fakes import FakeWorktrees, first_message_for, review_first_for, review_resumed_for  # noqa: E402
from app.application import client as runs  # noqa: E402
from app.application import settings as S  # noqa: E402
from tests.interfaces.test_workbench import request, settings_server, stack_as  # noqa: E402


class SettingsDelivery(unittest.TestCase):
    def setUp(self):
        saved = runs.preflight

        async def no_preflight(client, needed):
            return None

        runs.preflight = no_preflight
        self.addCleanup(setattr, runs, "preflight", saved)
        stack_as(self)
        skipping = E.env().auto_time_skipping_disabled()
        skipping.__enter__()
        self.addCleanup(skipping.__exit__, None, None, None)
        self.repo = tempfile.mkdtemp(prefix="orchestra-settings-delivery-repo-")
        self.addCleanup(shutil.rmtree, self.repo, True)
        self.root = tempfile.mkdtemp(prefix="orchestra-settings-delivery-")
        self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, ".orchestra"))
        os.makedirs(os.path.join(self.root, "roles"))
        for role in ("engineer", "architect"):
            shutil.copyfile(os.path.join(PKG, "roles", role + ".md"),
                            os.path.join(self.root, "roles", role + ".md"))
        shared = {key: value for key, value in cast.settings().items() if not key.startswith("_")}
        with open(os.path.join(self.root, ".orchestra", "settings.json"), "w", encoding="utf-8") as fh:
            json.dump(shared, fh)
        self.at = settings_server(self, self.root, {}, lambda work, timeout=300: E.run(work(E.client()), timeout))

    def ask(self, method, path, body=None):
        return request(method, path, body, at=self.at)

    def apply(self, *changes):
        status, shown = self.ask("GET", "/api/settings")
        self.assertEqual(status, 200, shown)
        status, applied = self.ask("POST", "/api/settings",
                                   {"revision": shown["revision"], "changes": list(changes)})
        self.assertEqual(status, 200, applied)
        return applied["settings"]

    def wait_for(self, run_id, reason):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            status, body = self.ask("GET", "/api/runs/%s" % run_id)
            if status == 200 and body["stop"] and body["stop"]["reason"] == reason:
                return body
            if status == 200 and body["stop"] and body["stop"]["reason"] == "failed":
                self.fail("run %s failed: %s" % (run_id, body["stop"]["feedback"]))
            time.sleep(0.2)
        self.fail("run %s never reached %s" % (run_id, reason))

    def wait_until_discarded(self, run_id):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            status, body = self.ask("GET", "/api/runs/%s" % run_id)
            self.assertEqual(status, 200, body)
            if body["state"]["status"] == "DISCARDED":
                return body
            time.sleep(0.2)
        self.fail("run %s never finished Discard" % run_id)

    def start(self, script, flow=None):
        git = FakeWorktrees()
        host, agent = E.host(script, git=git)
        body = {"task": "settings delivery", "repo": self.repo}
        if flow is not None:
            body["flow"] = flow
        status, started = self.ask("POST", "/api/runs", body)
        self.assertEqual(status, 200, started)
        run_id = started["run_id"]
        self.addCleanup(lambda: E.Run.cleanup(type("R", (), {"run_id": run_id})()))
        return run_id, host, agent, git

    def answer(self, run_id, stop, action, **more):
        status, answer = self.ask("POST", "/api/runs/%s/answer" % run_id,
                                  dict(stop=stop["id"], action=action, **more))
        self.assertEqual(status, 200, answer)
        return answer

    def test_invalid_local_settings_refuse_start_before_a_role_turn(self):
        local = os.path.join(self.root, ".orchestra", "settings.local.json")
        with open(local, "w", encoding="utf-8") as fh:
            json.dump({"review_rounds": {"plan": {"normal": 0}}}, fh)
        _, agent = E.host([])
        status, answer = self.ask("POST", "/api/runs", {"task": "must refuse", "repo": self.repo})
        self.assertEqual(status, 400, answer)
        self.assertIn("/review_rounds/plan/normal", answer["error"])
        self.assertEqual(agent.calls, [])

    def test_applied_settings_reach_a_run_and_the_run_keeps_its_snapshot(self):
        ask, wait_for = self.ask, self.wait_for
        status, shown = ask("GET", "/api/settings")
        self.assertEqual(status, 200)
        changes = [
            {"pointer": "/roles/engineer/agent", "value": "codex-engineer"},
            {"pointer": "/roles/architect/agent", "value": "claude-architect"},
            {"pointer": "/agents/codex-engineer/model", "value": "smoke-engineer"},
            {"pointer": "/agents/claude-architect/model", "value": "smoke-architect"},
            {"pointer": "/roles/engineer/persona", "value": "Smoke engineer persona."},
            {"pointer": "/roles/architect/persona", "value": "Smoke architect persona."},
            {"pointer": "/stage_skills/plan", "value": "smoke-plan"},
            {"pointer": "/review_rounds/plan/normal", "value": 2},
            {"pointer": "/review_rounds/plan/extended", "value": 1},
            {"pointer": "/review_prompts/after_normal/engineer", "value": "SMOKE ENGINEER REFLECT"},
            {"pointer": "/review_prompts/after_normal/architect", "value": "SMOKE ARCHITECT REFLECT"},
            {"pointer": "/review_prompts/at_limit/engineer", "value": "SMOKE ENGINEER HANDOFF"},
            {"pointer": "/review_prompts/at_limit/architect", "value": "SMOKE ARCHITECT HANDOFF"},
            {"pointer": "/default_flow", "value": "architect-research"},
        ]
        status, applied = ask("POST", "/api/settings", {"revision": shown["revision"], "changes": changes})
        self.assertEqual(status, 200, applied)
        configured = applied["settings"]
        script = [("research-e1-1", 0, first_message_for(configured, "architect", "Research brief")[0]),
                  ("plan-e2-1", 0, first_message_for(configured, "engineer", "planned")[0])]
        for round_ in (1, 2, 3):
            if round_ > 1:
                script.append(("plan-e2-%d" % round_, 0, "revised\n"))
            script.append(("assess-e2-%d" % round_, 0,
                           review_resumed_for(configured, "architect", "PATCH", "fix round %d" % round_)))
        script.extend([("plan-e3-1", 0, "revised after guidance\n"),
                       ("assess-e3-1", 0, review_resumed_for(configured, "architect", "PASS")),
                       ("build-e4-1", 0, "built\n"),
                       ("verify-e4-1", 0, review_resumed_for(configured, "architect", "PASS")),
                       ("closeout-e5-1", 0, "closed out\n")])
        run_id, self.host, self.agent, git = self.start(script)
        research = wait_for(run_id, "approval")
        self.assertEqual(research["view"]["flow"]["name"], "architect-research")
        status, changed = ask("POST", "/api/settings", {
            "revision": applied["revision"],
            "changes": [{"pointer": "/roles/engineer/agent", "revert": True},
                        {"pointer": "/roles/architect/agent", "revert": True},
                        {"pointer": "/agents/codex-engineer/model", "revert": True},
                        {"pointer": "/agents/claude-architect/model", "revert": True},
                        {"pointer": "/roles/engineer/persona", "revert": True},
                        {"pointer": "/roles/architect/persona", "revert": True},
                        {"pointer": "/stage_skills/plan", "revert": True},
                        {"pointer": "/review_rounds/plan/normal", "value": 1},
                        {"pointer": "/review_rounds/plan/extended", "value": 0}],
        })
        self.assertEqual(status, 200, changed)
        self.assertEqual({role: bound["agent"] for role, bound in changed["settings"]["roles"].items()},
                         cast.ROLES, "reverted to the profiles its checkout's shared settings bind")
        self.assertEqual(changed["settings"]["review_rounds"]["plan"], {"normal": 1, "extended": 0})
        status, answer = ask("POST", "/api/runs/%s/answer" % run_id,
                             {"stop": research["stop"]["id"], "action": "approve"})
        self.assertEqual(status, 200, answer)
        exhausted = wait_for(run_id, "exhausted")
        self.assertEqual(exhausted["state"]["round"], 3)
        self.assertEqual([call["name"] for call in self.agent.calls[:7]],
                         ["research-e1-1", "plan-e2-1", "assess-e2-1", "plan-e2-2", "assess-e2-2",
                          "plan-e2-3", "assess-e2-3"])
        self.assertEqual([call["kind"] for call in self.agent.calls[:3]],
                         ["claude-code", "codex", "claude-code"])
        self.assertIn("smoke-architect", self.agent.calls[0]["argv"])
        self.assertIn("smoke-engineer", self.agent.calls[1]["argv"])
        self.assertIn("--effort", self.agent.calls[0]["argv"])
        self.assertIn('model_reasoning_effort="%s"' % configured["agents"]["codex-engineer"]["effort"],
                      self.agent.calls[1]["argv"])
        self.assertIn("Smoke architect persona.", self.agent.calls[0]["prompt"])
        self.assertIn("Smoke engineer persona.", self.agent.calls[1]["prompt"])
        self.assertTrue(self.agent.calls[1]["prompt"].startswith("$smoke-plan\n"))
        self.assertIn("SMOKE ENGINEER REFLECT", self.agent.calls[5]["prompt"])
        self.assertIn("SMOKE ARCHITECT REFLECT", self.agent.calls[6]["prompt"])
        self.assertIn("SMOKE ENGINEER HANDOFF", self.agent.calls[5]["prompt"])
        self.assertIn("SMOKE ARCHITECT HANDOFF", self.agent.calls[6]["prompt"])

        status, answer = ask("POST", "/api/runs/%s/answer" % run_id,
                             {"stop": exhausted["stop"]["id"], "action": "guide", "text": "resolve the gap"})
        self.assertEqual(status, 200, answer)
        approval = wait_for(run_id, "approval")
        self.assertIn("resolve the gap", self.agent.calls[7]["prompt"])
        status, answer = ask("POST", "/api/runs/%s/answer" % run_id,
                             {"stop": approval["stop"]["id"], "action": "approve"})
        self.assertEqual(status, 200, answer)
        final = wait_for(run_id, "final")
        self.assertEqual([call["name"] for call in self.agent.calls[-3:]],
                         ["build-e4-1", "verify-e4-1", "closeout-e5-1"])
        self.assertEqual([call["kind"] for call in self.agent.calls[-3:]], ["codex", "claude-code", "codex"])
        for at, model in ((-3, "smoke-engineer"), (-2, "smoke-architect"), (-1, "smoke-engineer")):
            self.assertIn(model, self.agent.calls[at]["argv"])
        status, answer = ask("POST", "/api/runs/%s/answer" % run_id,
                             {"stop": final["stop"]["id"], "action": "discard", "confirm": True})
        self.assertEqual(status, 200, answer)
        self.wait_until_discarded(run_id)
        self.assertIn(("discard", run_id), git.calls)
        self.assertFalse([call for call in git.calls if call[0] == "merge"])

    def test_new_profiles_and_each_stage_skill_reach_both_flows(self):
        changes = [
            {"pointer": "/agents/smoke-claude",
             "value": {"kind": "claude-code", "model": "smoke-claude", "effort": "medium"}},
            {"pointer": "/agents/smoke-codex",
             "value": {"kind": "codex", "model": "smoke-codex", "effort": "high"}},
            {"pointer": "/roles/engineer/agent", "value": "smoke-claude"},
            {"pointer": "/roles/architect/agent", "value": "smoke-codex"},
            {"pointer": "/default_flow", "value": "architect-research"},
        ] + [{"pointer": "/stage_skills/" + stage, "value": "smoke-" + stage}
             for stage in ("research", "plan", "assess", "build", "verify", "closeout")]
        configured = self.apply(*changes)
        self.assertEqual(configured["default_flow"], "architect-research")

        for selected in ("engineer-code", None):
            with self.subTest(flow=selected or "default"):
                if selected:
                    script = [("plan-e1-1", 0, "planned\n"),
                              ("assess-e1-1", 0, review_first_for(configured, "architect", "PASS")[0]),
                              ("build-e2-1", 0, "built\n"),
                              ("verify-e2-1", 0, review_resumed_for(configured, "architect", "PASS")),
                              ("closeout-e3-1", 0, "closed out\n")]
                else:
                    script = [("research-e1-1", 0, first_message_for(configured, "architect", "brief")[0]),
                              ("plan-e2-1", 0, "planned\n"),
                              ("assess-e2-1", 0, review_resumed_for(configured, "architect", "PASS")),
                              ("build-e3-1", 0, "built\n"),
                              ("verify-e3-1", 0, review_resumed_for(configured, "architect", "PASS")),
                              ("closeout-e4-1", 0, "closed out\n")]
                run_id, _, agent, git = self.start(script, flow=selected)
                if selected is None:
                    research = self.wait_for(run_id, "approval")
                    self.assertEqual(research["view"]["flow"]["name"], "architect-research")
                    self.assertEqual(research["state"]["brief"], "brief")
                    self.answer(run_id, research["stop"], "approve")
                approval = self.wait_for(run_id, "approval")
                self.assertEqual(approval["view"]["flow"]["name"], selected or "architect-research")
                self.answer(run_id, approval["stop"], "approve")
                final = self.wait_for(run_id, "final")
                expected = ["plan", "assess", "build", "verify", "closeout"] if selected else [
                    "research", "plan", "assess", "build", "verify", "closeout"]
                self.assertEqual([call["name"].split("-")[0] for call in agent.calls], expected)
                for call in agent.calls:
                    stage = call["name"].split("-")[0]
                    architect = stage in ("research", "assess", "verify")
                    self.assertEqual(call["kind"], "codex" if architect else "claude-code")
                    self.assertTrue(call["prompt"].startswith(
                        ("$" if architect else "/") + "smoke-" + stage + "\n"), stage)
                    self.assertIn("smoke-codex" if architect else "smoke-claude", call["argv"])
                    if architect:
                        self.assertIn('model_reasoning_effort="high"', call["argv"])
                        self.assertEqual(call["argv"][call["argv"].index("--sandbox") + 1], "read-only")
                    else:
                        self.assertEqual(call["argv"][call["argv"].index("--effort") + 1], "medium")
                        self.assertEqual(call["argv"][call["argv"].index("--permission-mode") + 1], "dontAsk")
                self.answer(run_id, final["stop"], "discard", confirm=True)
                self.wait_until_discarded(run_id)
                self.assertIn(("discard", run_id), git.calls)

        restored = self.apply({"pointer": "/roles/engineer/agent", "revert": True},
                              {"pointer": "/roles/architect/agent", "revert": True},
                              {"pointer": "/agents/smoke-claude", "remove": True},
                              {"pointer": "/agents/smoke-codex", "remove": True})
        self.assertNotIn("smoke-claude", restored["agents"])
        self.assertNotIn("smoke-codex", restored["agents"])
        reverted_script = [("plan-e1-1", 0, "planned\n"),
                           ("assess-e1-1", 0, review_first_for(restored, "architect", "PASS")[0]),
                           ("build-e2-1", 0, "built\n"),
                           ("verify-e2-1", 0, review_resumed_for(restored, "architect", "PASS")),
                           ("closeout-e3-1", 0, "closed out\n")]
        run_id, _, agent, git = self.start(reverted_script, flow="engineer-code")
        approval = self.wait_for(run_id, "approval")
        self.answer(run_id, approval["stop"], "approve")
        final = self.wait_for(run_id, "final")
        for call in agent.calls:
            role = "architect" if call["name"].startswith(("assess", "verify")) else "engineer"
            profile = restored["agents"][restored["roles"][role]["agent"]]
            self.assertEqual(call["kind"], profile["kind"])
            self.assertIn(profile["model"], call["argv"])
            if profile["kind"] == "codex":
                self.assertIn('model_reasoning_effort="%s"' % profile["effort"], call["argv"])
            else:
                self.assertEqual(call["argv"][call["argv"].index("--effort") + 1], profile["effort"])
        self.answer(run_id, final["stop"], "discard", confirm=True)
        self.wait_until_discarded(run_id)
        self.assertIn(("discard", run_id), git.calls)

    def test_build_budget_and_both_roles_guidance_reach_later_turns(self):
        configured = self.apply(
            {"pointer": "/review_rounds/build/normal", "value": 2},
            {"pointer": "/review_rounds/build/extended", "value": 1},
            {"pointer": "/review_prompts/after_normal/engineer", "value": "BUILD ENGINEER REFLECT"},
            {"pointer": "/review_prompts/after_normal/architect", "value": "BUILD ARCHITECT REFLECT"},
            {"pointer": "/review_prompts/at_limit/engineer", "value": "BUILD ENGINEER HANDOFF"},
            {"pointer": "/review_prompts/at_limit/architect", "value": "BUILD ARCHITECT HANDOFF"},
        )
        script = [("plan-e1-1", 0, "planned\n"),
                  ("assess-e1-1", 0, review_first_for(configured, "architect", "PASS")[0])]
        for round_ in (1, 2, 3):
            script.extend((("build-e2-%d" % round_, 0, "built\n"),
                           ("verify-e2-%d" % round_, 0,
                            review_resumed_for(configured, "architect", "PATCH", "build gap"))))
        script.extend((("build-e3-1", 0, "revised\n"),
                       ("verify-e3-1", 0, review_resumed_for(configured, "architect", "PASS")),
                       ("closeout-e4-1", 0, "closed out\n")))
        run_id, _, agent, git = self.start(script)
        approval = self.wait_for(run_id, "approval")
        self.assertEqual(approval["state"]["phase"], "plan")
        changed = self.apply({"pointer": "/review_rounds/build/normal", "value": 1},
                             {"pointer": "/review_rounds/build/extended", "value": 0})
        self.assertEqual(changed["review_rounds"]["build"], {"normal": 1, "extended": 0})
        self.answer(run_id, approval["stop"], "approve")
        exhausted = self.wait_for(run_id, "exhausted")
        self.assertEqual((exhausted["state"]["phase"], exhausted["state"]["round"]), ("build", 3))
        self.assertEqual([call["name"] for call in agent.calls[:8]],
                         ["plan-e1-1", "assess-e1-1", "build-e2-1", "verify-e2-1",
                          "build-e2-2", "verify-e2-2", "build-e2-3", "verify-e2-3"])
        for early in agent.calls[2:6]:
            self.assertNotIn("BUILD ENGINEER REFLECT", early["prompt"])
            self.assertNotIn("BUILD ARCHITECT REFLECT", early["prompt"])
        for at, role in ((6, "ENGINEER"), (7, "ARCHITECT")):
            self.assertIn("BUILD %s REFLECT" % role, agent.calls[at]["prompt"])
            self.assertIn("BUILD %s HANDOFF" % role, agent.calls[at]["prompt"])
            self.assertIn("diagnose why this phase has not converged", agent.calls[at]["prompt"])
        self.answer(run_id, exhausted["stop"], "guide", text="fix the build gap")
        final = self.wait_for(run_id, "final")
        self.assertEqual([call["name"] for call in agent.calls[-3:]],
                         ["build-e3-1", "verify-e3-1", "closeout-e4-1"])
        self.assertIn("fix the build gap", agent.calls[-3]["prompt"])
        self.assertNotIn("BUILD ENGINEER REFLECT", agent.calls[-3]["prompt"])
        for said in ("fix the build gap", "BUILD ENGINEER REFLECT", "BUILD ENGINEER HANDOFF", "# Final budget handoff"):
            self.assertNotIn(said, agent.calls[-1]["prompt"], "a closeout is no turn of the build's budgeted loop")
        self.answer(run_id, final["stop"], "discard", confirm=True)
        self.wait_until_discarded(run_id)
        self.assertIn(("discard", run_id), git.calls)

    def test_applied_ten_plus_ten_reaches_both_prompt_boundaries(self):
        configured = self.apply(
            {"pointer": "/review_rounds/plan/normal", "value": 10},
            {"pointer": "/review_rounds/plan/extended", "value": 10},
            {"pointer": "/review_prompts/after_normal/engineer", "value": "TEN ENGINEER REFLECT"},
            {"pointer": "/review_prompts/after_normal/architect", "value": "TEN ARCHITECT REFLECT"},
            {"pointer": "/review_prompts/at_limit/engineer", "value": "TWENTY ENGINEER HANDOFF"},
            {"pointer": "/review_prompts/at_limit/architect", "value": "TWENTY ARCHITECT HANDOFF"},
        )
        self.assertEqual(configured["review_rounds"]["plan"], {"normal": 10, "extended": 10})
        script = []
        for round_ in range(1, 21):
            review = (review_first_for(configured, "architect", "PATCH")[0] if round_ == 1 else
                      review_resumed_for(configured, "architect", "PATCH"))
            script.extend((("plan-e1-%d" % round_, 0, "planned\n"),
                           ("assess-e1-%d" % round_, 0, review)))
        script.extend((("plan-e2-1", 0, "revised\n"),
                       ("assess-e2-1", 0, review_resumed_for(configured, "architect", "PASS")),
                       ("build-e3-1", 0, "built\n"),
                       ("verify-e3-1", 0, review_resumed_for(configured, "architect", "PASS")),
                       ("closeout-e4-1", 0, "closed out\n")))
        run_id, _, agent, git = self.start(script, flow="engineer-code")
        exhausted = self.wait_for(run_id, "exhausted")
        self.assertEqual((exhausted["state"]["phase"], exhausted["state"]["round"]), ("plan", 20))
        self.assertEqual(len(agent.calls), 40)
        for at, role in ((18, "ENGINEER"), (19, "ARCHITECT")):
            self.assertNotIn("TEN %s REFLECT" % role, agent.calls[at]["prompt"])
            self.assertNotIn("TWENTY %s HANDOFF" % role, agent.calls[at]["prompt"])
        for at, role in ((20, "ENGINEER"), (21, "ARCHITECT")):
            prompt = agent.calls[at]["prompt"]
            self.assertIn("normal review budget of 10 iterations has elapsed", prompt)
            self.assertEqual(prompt.count("diagnose why this phase has not converged"), 1)
            self.assertIn("TEN %s REFLECT" % role, prompt)
            self.assertNotIn("TWENTY %s HANDOFF" % role, prompt)
        for at, role in ((22, "ENGINEER"), (23, "ARCHITECT")):
            self.assertNotIn("TEN %s REFLECT" % role, agent.calls[at]["prompt"])
            self.assertNotIn("TWENTY %s HANDOFF" % role, agent.calls[at]["prompt"])
        for at, role in ((38, "ENGINEER"), (39, "ARCHITECT")):
            prompt = agent.calls[at]["prompt"]
            self.assertIn("TWENTY %s HANDOFF" % role, prompt)
            self.assertIn("# Final budget handoff", prompt)
            self.assertNotIn("TEN %s REFLECT" % role, prompt)

        self.answer(run_id, exhausted["stop"], "guide", text="finish the plan")
        approval = self.wait_for(run_id, "approval")
        self.assertIn("finish the plan", agent.calls[40]["prompt"])
        self.assertNotIn("TEN ENGINEER REFLECT", agent.calls[40]["prompt"])
        self.answer(run_id, approval["stop"], "approve")
        final = self.wait_for(run_id, "final")
        self.answer(run_id, final["stop"], "discard", confirm=True)
        self.wait_until_discarded(run_id)
        self.assertIn(("discard", run_id), git.calls)

    def test_applied_build_ten_plus_ten_reaches_both_prompt_boundaries(self):
        configured = self.apply(
            {"pointer": "/review_rounds/build/normal", "value": 10},
            {"pointer": "/review_rounds/build/extended", "value": 10},
            {"pointer": "/review_prompts/after_normal/engineer", "value": "TEN ENGINEER REFLECT"},
            {"pointer": "/review_prompts/after_normal/architect", "value": "TEN ARCHITECT REFLECT"},
            {"pointer": "/review_prompts/at_limit/engineer", "value": "TWENTY ENGINEER HANDOFF"},
            {"pointer": "/review_prompts/at_limit/architect", "value": "TWENTY ARCHITECT HANDOFF"},
        )
        self.assertEqual(configured["review_rounds"]["build"], {"normal": 10, "extended": 10})
        script = [("plan-e1-1", 0, "planned\n"),
                  ("assess-e1-1", 0, review_first_for(configured, "architect", "PASS")[0])]
        for round_ in range(1, 21):
            script.extend((("build-e2-%d" % round_, 0, "built\n"),
                           ("verify-e2-%d" % round_, 0,
                            review_resumed_for(configured, "architect", "PATCH"))))
        script.extend((("build-e3-1", 0, "revised\n"),
                       ("verify-e3-1", 0, review_resumed_for(configured, "architect", "PASS")),
                       ("closeout-e4-1", 0, "closed out\n")))
        run_id, _, agent, git = self.start(script, flow="engineer-code")
        approval = self.wait_for(run_id, "approval")
        self.answer(run_id, approval["stop"], "approve")
        exhausted = self.wait_for(run_id, "exhausted")
        self.assertEqual((exhausted["state"]["phase"], exhausted["state"]["round"]), ("build", 20))
        self.assertEqual(len(agent.calls), 42)
        for at, role in ((20, "ENGINEER"), (21, "ARCHITECT")):
            self.assertNotIn("TEN %s REFLECT" % role, agent.calls[at]["prompt"])
            self.assertNotIn("TWENTY %s HANDOFF" % role, agent.calls[at]["prompt"])
        for at, role in ((22, "ENGINEER"), (23, "ARCHITECT")):
            prompt = agent.calls[at]["prompt"]
            self.assertIn("normal review budget of 10 iterations has elapsed", prompt)
            self.assertEqual(prompt.count("diagnose why this phase has not converged"), 1)
            self.assertIn("TEN %s REFLECT" % role, prompt)
            self.assertNotIn("TWENTY %s HANDOFF" % role, prompt)
        for at, role in ((24, "ENGINEER"), (25, "ARCHITECT")):
            self.assertNotIn("TEN %s REFLECT" % role, agent.calls[at]["prompt"])
            self.assertNotIn("TWENTY %s HANDOFF" % role, agent.calls[at]["prompt"])
        for at, role in ((40, "ENGINEER"), (41, "ARCHITECT")):
            self.assertIn("# Final budget handoff", agent.calls[at]["prompt"])
            self.assertIn("TWENTY %s HANDOFF" % role, agent.calls[at]["prompt"])
            self.assertNotIn("TEN %s REFLECT" % role, agent.calls[at]["prompt"])
        self.answer(run_id, exhausted["stop"], "guide", text="finish the build")
        final = self.wait_for(run_id, "final")
        self.assertIn("finish the build", agent.calls[42]["prompt"])
        self.assertNotIn("TEN ENGINEER REFLECT", agent.calls[42]["prompt"])
        self.answer(run_id, final["stop"], "discard", confirm=True)
        self.wait_until_discarded(run_id)
        self.assertIn(("discard", run_id), git.calls)
