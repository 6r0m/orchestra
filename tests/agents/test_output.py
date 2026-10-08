"""What a kind reads out of a finished turn's output.

Codex is the only kind whose output is a stream to read at all. Its two readers take a line for an event
only when it begins with `{`, so valid JSON of any other shape among the events is noise: never an event,
and never a session, however much one looks like one.
"""
import os
import sys
import unittest

# The suite's own folder, reached from this concern's folder inside it, and the
# checkout above both: the shared harness and the fixtures live at the suite root.
HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

from app.agents.adapters import codex  # noqa: E402
from fakes import codex_first_out  # noqa: E402

# Every line a reader must pass over: valid JSON that is no object, an object that does not parse, and
# plain prose. The array carries a well-formed `thread.started` of its own and is indented, so a reader
# that parsed a line before it looked at it, or looked before it stripped it, would answer "spoof".
NOISE = "\n".join(['[1, 2]',
                   '3',
                   '"hi"',
                   'true',
                   'null',
                   '  [{"type": "thread.started", "thread_id": "spoof"}]  ',
                   '{"type": "thread.started"',
                   'thinking...']) + "\n"


class CodexOutput(unittest.TestCase):
    def test_valid_json_that_is_not_an_object_is_never_an_event(self):
        events, thread = codex_first_out("the answer", "t-real")
        out = NOISE + events
        self.assertEqual((codex.session(out, None), codex.final_message(out)), (thread, "the answer"))

    def test_noise_alone_names_no_session_and_no_answer(self):
        """`nodes.extract_session` makes a turn that named no session its own refusal, so a reader that
        found none answers nothing rather than raising."""
        self.assertEqual((codex.session(NOISE, None), codex.final_message(NOISE)), (None, ""))


if __name__ == "__main__":
    unittest.main()
