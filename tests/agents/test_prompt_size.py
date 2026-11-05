"""A turn's prompt fits the command line it rides on: a part too long for it is attached as a file — written whole —
which the prompt names in its place, under that part's own heading, and which the agent may read."""
import os
import sys
import tempfile
import unittest

HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

from app.agents import nodes as N  # noqa: E402
from app.agents.adapters import claude_code, codex  # noqa: E402
import folders  # noqa: E402

ASK = {"part": "instructions", "text": "# Your stage\nWrite the plan."}
BRIEF = {"part": "brief", "text": "\n# The approved research brief\n" + "the brief says so.\n" * 470}
# An operator's note as one was pasted: a long audit, quotes and all — the quotes a Windows command line escapes.
GUIDANCE = {"part": "guidance", "text": "\n# Operator guidance\n" + "".join(
    "line %d of the audit — \"PATCH\", it says, and “why”\n" % n for n in range(700))}


class Attach(unittest.TestCase):
    def setUp(self):
        self.folder = os.path.join(tempfile.mkdtemp(prefix="orchestra-attach-"), "attachments")
        self.addCleanup(folders.remove, os.path.dirname(self.folder))

    def read(self, path):
        with open(path, encoding="utf-8", newline="") as fh:
            return fh.read()

    def test_a_prompt_that_fits_is_given_whole_and_attaches_nothing(self):
        parts = [ASK, BRIEF]
        self.assertEqual(N.attach(parts, self.folder, "plan-e1-1"), (parts, []))
        self.assertFalse(os.path.exists(self.folder))

    def test_a_part_too_long_is_attached_whole_and_named_in_its_place(self):
        self.assertGreater(N.cost(N.render([ASK, BRIEF, GUIDANCE])), 32767, "past what Windows takes")
        kept, attached = N.attach([ASK, BRIEF, GUIDANCE], self.folder, "plan-e4-1")
        self.assertLessEqual(N.cost(N.render(kept)), N.PROMPT_BUDGET)
        self.assertEqual(attached, [os.path.join(self.folder, "plan-e4-1-guidance.md")])
        self.assertEqual(self.read(attached[0]), GUIDANCE["text"], "whole, byte for byte")
        said = kept[2]["text"]
        self.assertEqual(kept[2]["part"], "guidance")
        self.assertIn("# Operator guidance", said, "under its own heading")
        self.assertIn(attached[0], said, "naming the file to read")
        self.assertEqual(kept[:2], [ASK, BRIEF], "what fits stays where it was")

    def test_only_as_many_as_it_takes_go_the_longest_first(self):
        skill = {"part": "skill", "text": "/plan-it"}
        findings = {"part": "findings", "text": "\n# Findings\n" + "f" * 20000}
        kept, attached = N.attach([skill, ASK, BRIEF, findings, GUIDANCE], self.folder, "plan-e2-1")
        self.assertEqual([os.path.basename(path) for path in attached], ["plan-e2-1-guidance.md", "plan-e2-1-findings.md"])
        self.assertEqual(kept[:3], [skill, ASK, BRIEF], "the brief fits once those two are attached")

    def test_neither_the_skill_nor_the_stages_ask_is_ever_attached(self):
        # The skill leads its prompt as itself, and the ask says what the turn is for.
        skill = {"part": "skill", "text": "/plan-it " + "s" * 30000}
        ask = {"part": "instructions", "text": "# Your stage\n" + "a" * 30000}
        kept, attached = N.attach([skill, ask, GUIDANCE], self.folder, "plan-e3-1")
        self.assertEqual([os.path.basename(path) for path in attached], ["plan-e3-1-guidance.md"])
        self.assertEqual(kept[:2], [skill, ask])


class Readable(unittest.TestCase):
    """The attachments' folder is outside the worktree: the agent must be able to read it there, unasked."""

    def test_claude_is_given_the_folder_as_one_it_reads_without_approval(self):
        folder = tempfile.mkdtemp(prefix="orchestra-attach-")
        self.addCleanup(folders.remove, folder)
        self.assertEqual(claude_code.readable(["claude", "--resume", "s"], [folder]),
                         ["claude", "--resume", "s", "--add-dir", os.path.realpath(folder)])

    def test_codex_needs_none_its_sandbox_bounds_writes_not_reads(self):
        self.assertFalse(hasattr(codex, "readable"))


if __name__ == "__main__":
    unittest.main()
