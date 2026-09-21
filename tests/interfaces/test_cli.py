"""The command line types the answers a stop publishes. Which answers exist is the workflow's.

The command line owns only how an answer is typed — `yes`, guidance written as it is, a revise's
role spelled as a word — so an answer the workflow adds is typed by its name with no change here.
"""
import os
import sys
import unittest

HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

from app.interfaces import cli  # noqa: E402


def stop(*actions):
    return {"reason": "any", "actions": list(actions)}


class ParsesWhatAStopPublishes(unittest.TestCase):
    def test_an_answer_the_command_line_has_no_word_for_is_typed_by_its_name(self):
        self.assertEqual(cli.parse_answer(stop("pause", "abort"), "pause"), {"action": "pause", "text": "pause"})

    def test_a_revise_names_its_role_as_the_stop_publishes_it(self):
        final = stop("merge", "revise:engineer", "revise:architect", "discard")
        self.assertEqual(cli.parse_answer(final, "revise architect re-check the error path"),
                         {"action": "revise:architect", "text": "re-check the error path"})
        self.assertIsNone(cli.parse_answer(final, "revise re-check the error path"), "a role is named")
        self.assertEqual(cli.parse_answer(stop("approve", "revise", "abort"), "revise plan it again"),
                         {"action": "revise", "text": "plan it again"})

    def test_guidance_is_written_as_it_is_and_only_where_a_stop_takes_it(self):
        blocker = stop("guide", "abort")
        self.assertEqual(cli.parse_answer(blocker, "abort the old approach, use B"),
                         {"action": "guide", "text": "abort the old approach, use B"},
                         "a sentence that starts with an answer's name is still guidance")
        self.assertEqual(cli.parse_answer(blocker, "abort"), {"action": "abort", "text": "abort"})
        self.assertIsNone(cli.parse_answer(stop("approve", "revise", "abort"), "maybe later"))

    def test_yes_approves_and_a_confirmation_travels_with_the_answer(self):
        self.assertEqual(cli.parse_answer(stop("approve", "abort"), "Yes"), {"action": "approve", "text": "Yes"})
        self.assertEqual(cli.parse_answer(stop("discard"), "discard", confirm=True),
                         {"action": "discard", "text": "discard", "confirm": True})
        self.assertEqual(cli.parse_answer(stop("discard"), "discard"), {"action": "discard", "text": "discard"},
                         "whether a discard is confirmed is the workflow's to refuse")

    def test_the_answers_it_lists_are_the_stops_own(self):
        listed = cli.answer_line(stop("merge", "revise:engineer", "pause"))
        self.assertEqual(listed, '"merge" | "revise engineer <feedback>" | "pause"')


if __name__ == "__main__":
    unittest.main()
