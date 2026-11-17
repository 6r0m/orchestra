"""Todo evidence is independent of the optional commit-message proposal."""
import json
import unittest

from app.foundation import closeout, landing


class Products(unittest.TestCase):
    def test_native_product_requires_unfinished_work_and_a_reason_for_deferral(self):
        for disposition in closeout.DISPOSITIONS:
            value = {'disposition': disposition, 'remaining': '' if disposition == 'completed' else 'Trial pending',
                     'reason': 'Operator deferred the experiment'}
            with self.subTest(disposition=disposition):
                final = json.dumps({'todo': value, 'commit_message': {'subject': 'Complete verified engineering'}})
                self.assertEqual(closeout.product(final), value)
                self.assertIn('messages', landing.draft(final))
        for final in ('', '{}', 'null', '[]', '{"todo":null}',
                      json.dumps({'todo': {'disposition': 'completed', 'remaining': 'Required', 'reason': ''}}),
                      json.dumps({'todo': {'disposition': 'backlog', 'remaining': 'Required', 'reason': ''}}),
                      json.dumps({'todo': {'disposition': 'active', 'remaining': 'x' * 16385, 'reason': ''}})):
            with self.subTest(final=final[:80]), self.assertRaises(ValueError):
                closeout.product(final)

    def test_valid_todo_does_not_require_a_valid_commit_draft(self):
        final = json.dumps({'todo': {'disposition': 'active', 'remaining': 'Live acceptance', 'reason': ''}})
        self.assertEqual(closeout.product(final)['disposition'], 'active')
        self.assertIn('unavailable', landing.draft(final))
