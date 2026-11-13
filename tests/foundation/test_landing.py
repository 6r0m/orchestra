import unittest

from app.foundation import landing


class Messages(unittest.TestCase):
    def test_only_a_valid_structured_final_proposes_messages(self):
        result = landing.draft('{"commit_message":{"subject":"Preserve terminal screens","body":"Keep confirmed cursors."},"closeout_summary":"Todo closed and checked."}')
        self.assertEqual(result['messages']['work'], 'Preserve terminal screens\n\nKeep confirmed cursors.')
        for value in ('', 'tool output: {"commit_message":{"subject":"wrong"}}', '{}', 'null',
                      '{"commit_message":{"subject":false}}',
                      'Closed out.\n```json\n{"commit_message":{"subject":"Valid text in invalid transport"}}\n```'):
            self.assertIn('unavailable', landing.draft(value))

    def test_manual_messages_validate_independently_of_proposal_availability(self):
        accepted = {'work': 'Correct DeepSeek pricing', 'merge': 'Merge pricing corrections\n\nPreserve recorded usage.'}
        self.assertEqual(landing.messages(accepted), accepted)
        for text in ('', ' bad', 'a' * 101, 'Bad\x00message', 'Good\nCo-Authored-By: anything',
                     'Good\nOrchestra-Merge: copied', 'Good\nGenerated with a tool'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                landing.messages(dict(accepted, work=text))

    def test_manual_text_cannot_bypass_tree_stop_or_protocol_checks(self):
        state = {'base_tip': 'base', 'final_tree': 'tree'}
        value = dict(version=1, branch='release', remote=None, basis='base', tree='tree',
                     messages={'work': 'Change one thing', 'merge': 'Merge that change'})
        self.assertEqual(landing.choice(value, state), value)
        for changed in (dict(value, tree='stale'), dict(value, version=True)):
            with self.assertRaises(ValueError):
                landing.choice(changed, state)
        with self.assertRaises(ValueError):
            landing.choice(value, dict(state, final_tree=None))

