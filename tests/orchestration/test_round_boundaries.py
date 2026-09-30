"""Verdicts at both 10+10 review thresholds, through the real workflow and scripted turns."""
import os
import sys
import unittest

HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

from fakes import codex_review_first, codex_review_resumed  # noqa: E402
from temporal_env import POLICY, Run, host  # noqa: E402


class ReviewBoundaries(unittest.TestCase):
    def test_pass_and_blocker_outrank_the_budget_at_ten_and_twenty(self):
        policy = dict(POLICY)
        policy["review_rounds"] = {phase: {"normal": 10, "extended": 10} for phase in ("plan", "build")}
        policy.pop("max_rounds", None)
        for last_round, verdict, stop in ((10, "PASS", "approval"),
                                          (10, "BLOCKER", "blocker"),
                                          (20, "PASS", "approval"),
                                          (20, "BLOCKER", "blocker")):
            with self.subTest(round=last_round, verdict=verdict):
                script = []
                for round_ in range(1, last_round + 1):
                    review_verdict = verdict if round_ == last_round else "PATCH"
                    review = (codex_review_first(review_verdict)[0] if round_ == 1 else
                              codex_review_resumed(review_verdict))
                    script.extend((("plan-e1-%d" % round_, 0, "planned\n"),
                                   ("assess-e1-%d" % round_, 0, review)))
                _, agent = host(script)
                run = Run(policy=policy)
                self.addCleanup(run.cleanup)
                self.assertEqual(run.stop["reason"], stop)
                self.assertEqual(run.state["round"], last_round)
                self.assertEqual(len(agent.calls), last_round * 2)
                self.assertEqual(agent.calls[-1]["name"], "assess-e1-%d" % last_round)
                if last_round == 10:
                    self.assertNotIn("# Convergence reflection", agent.calls[-1]["prompt"])
                    self.assertNotIn("# Final budget handoff", agent.calls[-1]["prompt"])
                else:
                    self.assertIn("# Convergence reflection", agent.calls[20]["prompt"])
                    self.assertIn("# Final budget handoff", agent.calls[-2]["prompt"])
                    self.assertIn("# Final budget handoff", agent.calls[-1]["prompt"])
