"""The flows a run may follow: the shipped ones hold, and each rule a flow must keep refuses the flow
that breaks it, saying which rule — a run never starts on it.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

from app.foundation import flows  # noqa: E402
from app.foundation import policy as P  # noqa: E402

CODE = ["engineer:plan", "architect:assess", "you:approve", "engineer:build", "architect:verify", "you:merge"]


class Shipped(unittest.TestCase):
    def test_both_shipped_flows_hold_and_the_policy_names_one_of_them(self):
        self.assertEqual(flows.load("engineer-code"), CODE)
        research = flows.load("architect-research")
        self.assertEqual(research[:2], ["architect:research", "you:approve"])
        self.assertEqual(research[2:], CODE)
        self.assertEqual(P.load()["default_flow"], "engineer-code")
        self.assertEqual([found["name"] for found in flows.available()], ["architect-research", "engineer-code"])

    def test_the_order_runs_took_before_flows_is_todays_and_itself_a_flow(self):
        self.assertEqual(list(flows.LEGACY_FLOW), CODE)
        flows.check(list(flows.LEGACY_FLOW))


class Rules(unittest.TestCase):
    def refused(self, steps, reason):
        with self.assertRaisesRegex(flows.InvalidFlow, reason):
            flows.check(steps)

    def test_flows_that_stop_short_of_a_build_hold(self):
        for steps in (["architect:research"], ["architect:research", "you:approve"],
                      ["engineer:plan", "architect:assess"], ["engineer:plan", "architect:assess", "you:approve"],
                      ["architect:research", "you:approve", "engineer:plan", "architect:assess"]):
            self.assertEqual(flows.check(steps), steps)

    def test_a_flow_holds_from_one_step_to_its_bound(self):
        self.refused([], "from 1 to %d steps" % flows.MAX_FLOW_STEPS)
        longest = ["architect:research", "you:approve"] * (flows.MAX_FLOW_STEPS // 2)
        self.assertEqual(len(flows.check(longest)), flows.MAX_FLOW_STEPS)
        self.refused(longest + ["architect:research"], "from 1 to %d steps, not %d"
                     % (flows.MAX_FLOW_STEPS, flows.MAX_FLOW_STEPS + 1))

    def test_a_step_is_a_known_action_of_the_role_the_contract_gives_it(self):
        self.refused(["engineer:dance"], "no such action")
        self.refused(["plan"], "no such action")
        self.refused(["architect:plan", "architect:assess"], "plan is the engineer's")
        self.refused(["engineer:research"], "research is the architect's")
        self.refused(["engineer:plan", "engineer:assess"], "assess is the architect's")
        self.refused(["you:wait"], "the operator's steps are you:approve, you:merge")
        self.refused("engineer:plan", "a list of steps")

    def test_an_engineers_work_goes_to_its_review_next(self):
        self.refused(["engineer:plan", "you:approve"], "goes to its review, assess, next")
        self.refused(CODE[:3] + ["engineer:build", "you:merge"], "goes to its review, verify, next")
        self.refused(["architect:assess"], "judges a plan right before it")
        self.refused(["architect:research", "architect:assess"], "judges a plan right before it")
        self.refused(CODE[:3] + ["architect:verify", "you:merge"], "judges a build right before it")

    def test_an_approval_follows_a_review_or_a_research(self):
        self.refused(["you:approve", "architect:research"], "an approval follows a review or a research")
        self.refused(["architect:research", "you:approve", "you:approve"], "an approval follows")

    def test_a_build_implements_a_plan_and_ends_at_the_merge(self):
        self.refused(["architect:research", "you:approve", "engineer:build", "architect:verify", "you:merge"],
                     "no plan comes before it")
        self.refused(CODE[:-1], "a flow that builds ends at the merge")
        self.refused(CODE[:3] + ["you:merge"], "the merge is the last step, right after a verify")
        self.refused(CODE + ["architect:research"], "the merge is the last step")

    def test_research_comes_before_any_plan(self):
        self.refused(CODE[:3] + ["architect:research", "you:approve"], "step 4, 'architect:research': research "
                     "comes before any plan")
        self.refused(["engineer:plan", "architect:assess", "architect:research"], "research comes before any plan")


class Files(unittest.TestCase):
    def setUp(self):
        root = tempfile.mkdtemp(prefix="orch-flows-")
        self.addCleanup(shutil.rmtree, root, True)
        self.addCleanup(setattr, flows, "FLOWS_DIR", flows.FLOWS_DIR)
        flows.FLOWS_DIR = os.path.join(root, "flows")
        os.makedirs(flows.FLOWS_DIR)

    def write(self, name, content):
        with open(os.path.join(flows.FLOWS_DIR, name), "w", encoding="utf-8") as fh:
            fh.write(content if isinstance(content, str) else json.dumps(content))

    def test_a_flow_is_its_file_named_for_it_and_a_broken_one_says_why(self):
        self.write("quick.json", ["engineer:plan", "architect:assess"])
        self.write("broken.json", ["engineer:plan"])
        self.write("garbled.json", "[\"engineer:plan\",")
        self.write("notes.txt", "not a flow")
        self.assertEqual(flows.load("quick"), ["engineer:plan", "architect:assess"])
        with self.assertRaisesRegex(flows.InvalidFlow, "flow 'broken': step 1, 'engineer:plan'"):
            flows.load("broken")
        with self.assertRaisesRegex(flows.InvalidFlow, "flow 'garbled' is not JSON"):
            flows.load("garbled")
        listed = {found["name"]: found for found in flows.available()}
        self.assertEqual(sorted(listed), ["broken", "garbled", "quick"], "only its .json files are flows")
        self.assertEqual(listed["quick"]["steps"], ["engineer:plan", "architect:assess"])
        self.assertIn("goes to its review", listed["broken"]["error"])

    def test_a_flow_that_cannot_be_read_is_refused_and_listed_so(self):
        self.write("quick.json", ["engineer:plan", "architect:assess"])
        with mock.patch.object(flows, "open", create=True, side_effect=PermissionError("denied")):
            with self.assertRaisesRegex(flows.InvalidFlow, "flow 'quick' could not be read: denied"):
                flows.load("quick")
            self.assertEqual(flows.available(), [{"name": "quick", "error": "flow 'quick' could not be read: denied"}])

    def test_a_name_never_reaches_outside_the_folder(self):
        # Flows that would hold, beside the folder and in a folder of it: only the name keeps them out.
        os.makedirs(os.path.join(flows.FLOWS_DIR, "sub"))
        for there in ("../outside.json", "sub/flow.json"):
            self.write(there, CODE)
        for name in ("missing", "../outside", "sub/flow", "..\\outside", "sub\\flow", "", None):
            with self.assertRaisesRegex(flows.InvalidFlow, "no flow"):
                flows.load(name)
        self.assertEqual(flows.available(), [], "a folder in it is no flow")


if __name__ == "__main__":
    unittest.main()
