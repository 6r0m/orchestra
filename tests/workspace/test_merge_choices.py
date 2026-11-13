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
    def test_skill_catalog_reads_the_runs_worktree_instead_of_the_main_checkout(self):
        from app.application import activities as A
        from app.agents import adapters
        from app.agents.adapters import codex
        from fakes import FakeRepos

        path = self.worktree('skill-catalog', change=False)
        write(os.path.join(path, '.agents', 'skills', 'repo-only', 'SKILL.md'), 'Fixture skill.\n')
        repo = self.repo
        class Here(FakeRepos):
            def resolve(inner, selected, root):
                return dict(super().resolve(selected, root), repo_path=repo)
        with mock.patch.object(adapters, 'usable', return_value=[codex]), \
             mock.patch.object(codex, 'skill_roots', side_effect=lambda folder: [os.path.join(folder, '.agents', 'skills')]):
            result = A.Activities(git=W, repositories=Here()).worktree_view(
                {'repository': {}, 'worktree_root': self.root, 'skill_catalog': True, 'skill_root': path})
        self.assertEqual([row['name'] for row in result['skills']['codex']], ['repo-only'])
        self.assertEqual(result['skills']['codex'][0]['scope'], 'repository')
    def test_start_preview_lists_exact_cached_targets_without_moving_refs(self):
        from app.application import activities as A
        from fakes import FakeRepos

        git(self.repo, 'branch', 'release')
        repo = self.repo
        class Here(FakeRepos):
            def resolve(inner, selected, root):
                return dict(super().resolve(selected, root), repo_path=repo, base_branch='develop')
        refs = git(self.repo, 'show-ref')
        result = A.Activities(git=W, repositories=Here()).worktree_view(
            {'repository': {}, 'worktree_root': self.root, 'landing_preview': True})
        self.assertEqual(result['version'], 1)
        self.assertEqual({row['branch'] for row in result['choices']}, {'develop', 'release'})
        self.assertEqual(git(self.repo, 'show-ref'), refs)
    def test_a_selected_branch_conflict_reconciles_that_branch_without_moving_refs(self):
        from app.application import activities as A

        initial = W.started_from(self.repo)
        git(self.repo, 'branch', 'release')
        selected = os.path.join(self.tmp, 'release-checkout')
        git(self.repo, 'worktree', 'add', selected, 'release')
        write(os.path.join(selected, 'app.txt'), 'release version\n')
        write(os.path.join(selected, 'release-only.txt'), 'selected destination\n')
        git(selected, 'add', '-A')
        git(selected, 'commit', '-qm', 'Advance selected destination')
        release = git(self.repo, 'rev-parse', 'release').strip()
        path = self.worktree('conflicting-run')
        tree, before = W.work_tree(path), W.guard(path, 'conflicting-run')
        refs = git(self.repo, 'show-ref')
        result = W.merge(self.repo, path, 'conflicting-run', 'release', tree, None, None,
                         'Correct behavior', 'Merge behavior correction', tip=initial,
                         recovery=hashlib.sha256(b'conflicting-execution').hexdigest())
        self.assertEqual(result['result'], 'moved')
        self.assertEqual(git(self.repo, 'show-ref'), refs)
        self.assertEqual(W.guard(path, 'conflicting-run'), before)

        state = dict(run_id='conflicting-run', repo_path=self.repo, worktree_path=path,
                     base_branch='release', base_tip=initial)
        reconciled = A.Activities(git=W).reconcile({'state': state})
        self.assertTrue(reconciled['moved'])
        self.assertEqual(reconciled['base_tip'], release)
        self.assertIn('app.txt', reconciled['files'])
        self.assertEqual(git(path, 'rev-parse', 'MERGE_HEAD').strip(), release)
        self.assertTrue(os.path.isfile(os.path.join(path, 'release-only.txt')))
        protected = lambda listing: [line for line in listing.splitlines() if not line.endswith(' refs/heads/conflicting-run')]
        self.assertEqual(protected(git(self.repo, 'show-ref')), protected(refs))
        self.assertEqual(W.started_from(self.repo), initial)

    def test_identical_subjects_and_trees_cannot_adopt_another_executions_merge(self):
        from app.application import activities as A

        initial = W.started_from(self.repo)
        git(self.repo, 'branch', 'release')
        states = []
        for label in ('first-run', 'second-run'):
            path = self.worktree(label, change=False)
            write(os.path.join(path, 'app.txt'), 'one\nshared change\n')
            tree = W.work_tree(path)
            choice = dict(version=1, branch='release', remote=None, basis=initial, tree=tree,
                          messages={'work': 'Correct behavior', 'merge': 'Merge behavior correction'})
            states.append(dict(run_id=label, repo_path=self.repo, worktree_path=path, base_branch='release',
                               base_tip=initial, final_tree=tree, plan='todo/plan.md', todo_done_dir='todo/done',
                               task='Correct behavior', merge_choice=choice, merge_attempt='final-stop',
                               merge_execution='execution-' + label))
        self.assertEqual(states[0]['final_tree'], states[1]['final_tree'])
        host = A.Activities(git=W)
        first = host.merge({'state': states[0]})
        self.assertEqual(first['result'], 'merged')
        self.assertEqual(host.merge({'state': states[0]})['commit'], first['commit'])
        before = W.guard(states[1]['worktree_path'], states[1]['run_id'])
        refs = git(self.repo, 'show-ref')
        second = host.merge({'state': states[1]})
        self.assertEqual(second['result'], 'refused')
        self.assertIn('no change', second['reason'])
        self.assertEqual(W.guard(states[1]['worktree_path'], states[1]['run_id']), before)
        self.assertEqual(git(self.repo, 'show-ref'), refs)
        self.assertTrue(os.path.isdir(states[1]['worktree_path']))
        self.assertEqual(host.merge({'state': states[0]})['commit'], first['commit'])
        self.assertEqual(W.started_from(self.repo), initial)

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
