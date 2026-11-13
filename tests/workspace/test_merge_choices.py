"""Explicit public names and compatible destinations against disposable Git repositories."""
import os
import hashlib
import unittest
from unittest import mock

from app.workspace import worktrees as W
from tests.workspace.test_worktrees import Repo, TARGET, git, write


class Names(unittest.TestCase):
    def test_explicit_name_preserves_the_whole_slug_without_using_task_words(self):
        for name in ('terminal-cache', 'fix-42', 'API-caching'):
            with self.subTest(name=name):
                run = W.run_id('bro please inspect this very long task', name=name)
                self.assertRegex(run, '^' + name.lower() + '-[0-9a-f]{8}$')
        for name in ('', ' ', 'a' * 17, '../other', 'two words', 'résumé', '-name', 'name-'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                W.run_id('a complete task', name=name)
        self.assertTrue(W.plan_path('todo', '%Y-%m-%d-{slug}', '2026-11-13', 'the whole original task',
                                    name='a-b-c-d-e-f-g').endswith('a_b_c_d_e_f_g.md'))


class Choices(Repo):
    def test_configured_remote_names_with_slashes_are_not_guessed_from_ref_segments(self):
        remote = os.path.join(self.tmp, 'remote.git')
        git(self.repo, 'clone', '--bare', self.repo, remote)
        git(self.repo, 'remote', 'add', 'gateway/team', remote)
        git(self.repo, 'fetch', 'gateway/team')
        pins = W.landing_pins(self.repo)
        rows = W.merge_destinations(self.repo, W.started_from(self.repo), pins=pins)
        self.assertTrue(any(row['remote'] == 'gateway/team' and row['branch'] == 'develop'
                            for row in rows['choices']))

    def test_a_selected_pinned_remote_lands_only_on_that_existing_branch(self):
        original = W.started_from(self.repo)
        git(self.repo, 'branch', 'release')
        remote = os.path.join(self.tmp, 'remote.git')
        git(self.repo, 'clone', '--bare', self.repo, remote)
        git(self.repo, 'remote', 'add', 'origin', remote)
        pins = W.landing_pins(self.repo)['origin']
        path = self.worktree('remote-choice')
        final = W.work_tree(path)
        binding = hashlib.sha256(b'run:stop:origin/release:base:tree').hexdigest()
        result = W.merge(self.repo, path, 'remote-choice', 'release', final, None, None,
                         'Preserve terminal screens', 'Merge persistent terminal screens', tip=original,
                         remote='origin', pinned=pins['endpoint'], gate=pins['gate'], recovery=binding)
        self.assertEqual(git(remote, 'rev-parse', 'release').strip(), result['commit'])
        self.assertEqual(git(remote, 'rev-parse', 'release^{tree}').strip(), final)
        self.assertEqual(git(remote, 'rev-parse', 'develop').strip(), original)
        self.assertEqual(W.started_from(self.repo), original)

    def test_discovery_refuses_older_history_and_unknown_compatibility(self):
        git(self.repo, 'branch', 'old')
        write(os.path.join(self.repo, 'app.txt'), 'new base\n')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-qm', 'Advance the base')
        rows = W.merge_destinations(self.repo, W.started_from(self.repo))
        self.assertEqual([row['branch'] for row in rows['choices']], ['develop'])
        self.assertEqual(rows['unavailable'][0]['branch'], 'old')
        with self.assertRaisesRegex(W.MergeRefused, 'could not establish'):
            W.merge_destinations(self.repo, 'unreadable-base')

    def test_selected_compatible_branch_lands_without_moving_the_original_default(self):
        original = W.started_from(self.repo)
        git(self.repo, 'branch', 'release')
        path = self.worktree('chosen-target')
        tree = W.work_tree(path)
        binding = hashlib.sha256(b'run:stop:release:base:tree').hexdigest()
        result = W.merge(self.repo, path, 'chosen-target', 'release', tree, None, None,
                         'Preserve terminal screens', 'Merge persistent terminal screens', tip=original,
                         recovery=binding)
        self.assertEqual(result['result'], 'merged')
        self.assertEqual(W.started_from(self.repo), original)
        self.assertEqual(git(self.repo, 'rev-parse', 'release^{tree}').strip(), tree)
        self.assertIn('Orchestra-Merge: ' + binding, git(self.repo, 'show', '-s', '--format=%B', 'release'))
        resumed = W.merge(self.repo, path, 'chosen-target', 'release', tree, None, None,
                          'Preserve terminal screens', 'Merge persistent terminal screens', tip=original,
                          recovery=binding)
        self.assertEqual(resumed['commit'], result['commit'])
        with self.assertRaises(W.MergeRefused):
            W.merge(self.repo, path, 'chosen-target', 'develop', tree, None, None,
                    'Preserve terminal screens', 'Merge persistent terminal screens', tip=original,
                    recovery=hashlib.sha256(b'another-target').hexdigest())

    def test_pinned_remote_discovery_is_cached_and_endpoint_changes_disable_it(self):
        from app.application import activities as A
        remote = os.path.join(self.tmp, 'remote.git')
        git(self.repo, 'clone', '--bare', self.repo, remote)
        git(self.repo, 'remote', 'add', 'origin', remote)
        git(self.repo, 'fetch', 'origin')
        pins = W.landing_pins(self.repo)
        original = pins['origin']
        legacy = {'repo_path': self.repo, 'base_tip': W.started_from(self.repo), 'run_id': 'legacy',
                  'remote': 'origin', 'remote_id': original['endpoint'], 'prepush_id': original['gate']}
        legacy_choices = A.Activities(git=W).worktree_view({'merge_state': legacy})
        self.assertTrue(any(row['remote'] == 'origin' for row in legacy_choices['choices']))
        self.assertEqual(A._merge_pins(dict(legacy, remote_id=None)), {})
        result = W.merge_destinations(self.repo, W.started_from(self.repo), pins=pins)
        self.assertTrue(any(row['remote'] == 'origin' and row['cached'] for row in result['choices']))
        git(self.repo, 'remote', 'set-url', 'origin', os.path.join(self.tmp, 'different.git'))
        result = W.merge_destinations(self.repo, W.started_from(self.repo), pins=pins)
        self.assertFalse(any(row['remote'] for row in result['choices']))
        self.assertTrue(any('changed' in row['reason'] for row in result['unavailable']))

    def test_choices_only_offer_compatible_refs_and_do_not_reach_remotes(self):
        tip = W.started_from(self.repo)
        git(self.repo, 'branch', 'release')
        path = self.worktree('private-run', change=False)
        before = W.guard(path, 'private-run')
        choices = W.merge_destinations(self.repo, tip, 'private-run', {})
        self.assertEqual({row['branch'] for row in choices['choices']}, {'develop', 'release'})
        self.assertTrue(all(row['remote'] is None for row in choices['choices']))
        self.assertTrue(choices['identity_ready'])
        self.assertEqual(W.guard(path, 'private-run'), before)

    def test_missing_identity_refuses_before_the_controller_stages_anything(self):
        path = self.worktree('identity-check')
        tree, tip = W.work_tree(path), W.started_from(path)
        before = W.guard(path, 'identity-check')
        environment = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        for key in ('GIT_AUTHOR_NAME', 'GIT_AUTHOR_EMAIL', 'GIT_COMMITTER_NAME', 'GIT_COMMITTER_EMAIL', 'EMAIL'):
            environment.pop(key, None)
        git(self.repo, 'config', '--unset', 'user.name')
        git(self.repo, 'config', '--unset', 'user.email')
        git(self.repo, 'config', 'user.useConfigOnly', 'true')
        with mock.patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(W.MergeRefused, 'identity'):
                W.merge(self.repo, path, 'identity-check', 'develop', tree, None, None,
                        'Check identity before committing', 'Merge identity checks', tip=tip)
        self.assertEqual(W.guard(path, 'identity-check'), before)
        self.assertEqual(git(path, 'diff', '--cached').strip(), '')
