"""Real Git and Temporal preserve todo outcomes through revision, failures and reconciliation."""
import json
import os
import uuid
from pathlib import Path
from unittest.mock import patch

from temporalio.worker import Replayer
from app.orchestration import workflow as WF
from app.workspace import worktrees as W
from tests.workspace.test_worktrees import Repo, TARGET, git, write


class TodoLifecycle(Repo):
    def scenario(self, disposition='parked', fail_once=False, new_remaining=False):
        import cast
        import temporal_env as E
        from fakes import FakeRepos, first_message_for, review_first_for, review_resumed_for
        settings, repo, root = cast.settings(), self.repo, self.root
        plan = 'todo/task.md'
        seen, calls = {'engineer': 0, 'architect': 0}, []
        class DiskRepo(FakeRepos):
            def resolve(self, selected, worktree_root):
                return dict(super().resolve(selected, worktree_root), repo_path=repo, worktree_root=root,
                            todo_name='task', todo_parked_dir='todo/parked', todo_backlog_dir='todo/backlog')
        def runner(worktree, argv, directory, name, prompt, timeout, env, **kwargs):
            calls.append((name, prompt))
            role = 'architect' if name.startswith(('assess-', 'verify-')) else 'engineer'
            if name.startswith('plan-'):
                write(os.path.join(worktree, plan), 'Approved increment\n' + (
                    '- [x] Existing acceptance completed\n' if new_remaining else '- [ ] Future live trial\n'))
            if name.startswith(('build-', 'verify-')):
                self.assertTrue(os.path.isfile(os.path.join(worktree, plan)), 'revision must restore the actual verified todo before either role')
            if name.startswith('build-'):
                write(os.path.join(worktree, 'app.txt'), 'one\nverified increment\n')
                write(os.path.join(worktree, 'todo/task/README.md'), 'Sanitized continuation index\n')
                write(os.path.join(worktree, 'todo/task/fixtures/incident.txt'), 'SYNTHETIC_INCIDENT_OBSERVATION\n')
            if name.startswith('closeout-'):
                target = os.path.join(worktree, 'todo', disposition, 'task.md')
                source = os.path.join(worktree, plan)
                if os.path.isfile(source):
                    original = Path(source).read_text(encoding='utf-8')
                    continuation = 'Remaining work: Future live trial\n\n' if 'Future live trial' not in original else ''
                    write(target, continuation + 'Operator deferred the trial\n\n' + original)
                    os.remove(source)
                    material_source = Path(worktree) / 'todo/task'
                    for material in material_source.rglob('*'):
                        if material.is_file():
                            moved = Path(os.path.splitext(target)[0]) / material.relative_to(material_source)
                            moved.parent.mkdir(parents=True, exist_ok=True)
                            material.replace(moved)
                final = json.dumps({'todo': {'disposition': disposition, 'remaining': 'Future live trial',
                                            'reason': 'Operator deferred the trial'}})
                if fail_once and sum(n.startswith('closeout-') for n, _ in calls) == 1:
                    final = '{}'
            else:
                final = 'Implemented the approved increment'
            if role == 'architect':
                output = (review_first_for(settings, role, 'PASS')[0] if not seen[role]
                          else review_resumed_for(settings, role, 'PASS'))
            else:
                output = first_message_for(settings, role, final)[0]
            seen[role] += 1
            return 0, output
        E.host([], git=W, repositories=DiskRepo(), queue=E.WINDOWS_QUEUE if TARGET == 'windows' else E.WSL_QUEUE)[0].runner = runner
        run_id = 'todo-test-' + uuid.uuid4().hex[:8]
        start = E.start_input(run_id, auto=True, target=TARGET, flow=['engineer:plan', 'architect:assess',
            'you:approve', 'engineer:build', 'architect:verify', 'engineer:closeout', 'you:merge'])
        start['closeout_version'] = 1
        with patch('app.application.activities.trust.ensure', return_value=[]):
            handle = E.run(E.client().start_workflow(WF.FeatureRun.run, start, id=run_id, task_queue=E.WORKFLOW_QUEUE))
            run = E.Run(handle=handle)
        self.addCleanup(run.cleanup)
        return run, calls, E

    def test_new_acceptance_work_survives_merge_and_worktree_cleanup_in_markdown(self):
        run, calls, E = self.scenario(new_remaining=True)
        run.answer('merge')
        self.assertEqual(run.state['status'], 'MERGED')
        landed = git(self.repo, 'show', 'develop:todo/parked/task.md')
        self.assertIn('- [x] Existing acceptance completed', landed)
        self.assertIn('Remaining work: Future live trial', landed)
        self.assertFalse(os.path.exists(run.state['worktree_path']))

    def test_each_revise_role_restores_the_todo_before_resuming(self):
        run, calls, E = self.scenario()
        for role in ('engineer', 'architect'):
            with self.subTest(role=role), patch('app.application.activities.trust.ensure', return_value=[]):
                run.answer('revise ' + role + ' Recheck the approved increment only.')
                run.status = E.run(E.cli.follow(run.handle))
                self.assertEqual(run.stop['reason'], 'final', run.status)
                self.assertEqual(run.state['todo_closeout']['disposition'], 'parked')
        run.answer('discard', confirm=True)
        E.run(Replayer(workflows=[WF.FeatureRun]).replay_workflow(E.run(run.handle.fetch_history())))

    def test_partial_closeout_failure_preserves_the_stop_until_continue(self):
        run, calls, E = self.scenario(fail_once=True)
        self.assertEqual(run.stop['reason'], 'failed')
        self.assertNotIn('todo_closeout', run.state)
        self.assertNotIn('final_tree', run.state)
        with patch('app.application.activities.trust.ensure', return_value=[]):
            run.answer('continue')
        run.status = E.run(E.cli.follow(run.handle))
        self.assertEqual(run.stop['reason'], 'final', run.status)
        self.assertEqual(run.state['todo_closeout']['disposition'], 'parked')
        run.answer('merge')
        self.assertEqual(run.state['status'], 'MERGED')
        self.assertIn('- [ ] Future live trial', git(self.repo, 'show', 'develop:todo/parked/task.md'))
        self.assertIn('SYNTHETIC_INCIDENT', git(self.repo, 'show', 'develop:todo/parked/task/fixtures/incident.txt'))
        self.assertFalse(os.path.exists(run.state['worktree_path']))

    def test_selected_base_conflict_reopens_unfinished_work_before_the_engineer(self):
        run, calls, E = self.scenario('backlog')
        write(os.path.join(self.repo, 'app.txt'), 'incoming conflict\n')
        git(self.repo, 'add', 'app.txt')
        git(self.repo, 'commit', '-qm', 'Advance base')
        with patch('app.application.activities.trust.ensure', return_value=[]):
            run.answer('merge')
            run.status = E.run(E.cli.follow(run.handle))
        self.assertEqual(run.stop['reason'], 'final', run.status)
        self.assertEqual(run.state['todo_closeout']['disposition'], 'backlog')
        self.assertIn('incoming conflict', git(self.repo, 'show', 'develop:app.txt'))
        self.assertGreater(sum(n.startswith('build-') for n, _ in calls), 1)
        run.answer('merge')
        self.assertEqual(run.state['status'], 'MERGED')
        self.assertIn('Future live trial', git(self.repo, 'show', 'develop:todo/backlog/task.md'))
        self.assertIn('SYNTHETIC_INCIDENT', git(self.repo, 'show', 'develop:todo/backlog/task/fixtures/incident.txt'))
        E.run(Replayer(workflows=[WF.FeatureRun]).replay_workflow(E.run(run.handle.fetch_history())))
