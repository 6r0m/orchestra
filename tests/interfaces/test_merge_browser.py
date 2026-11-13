"""Normal final gate through Temporal, native Git and an isolated Edge profile; no model calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import uuid
from unittest.mock import patch

from app.application import client as runs, settings as S
from app.orchestration import workflow as WF
from app.workspace import worktrees as W
from tests.workspace.test_worktrees import Repo, TARGET, git, write

EDGE = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe'


@unittest.skipUnless(sys.platform.startswith('win') and EDGE.is_file(), 'native Edge acceptance runs on Windows')
class MergeBrowser(Repo):
    def test_the_normal_gate_preserves_messages_then_lands_on_the_selected_branch(self):
        import cast
        import temporal_env as E
        from fakes import FakeRepos, first_message_for, review_first_for, review_resumed_for
        from tests.interfaces.test_workbench import stack_as, port

        settings = cast.settings()
        repo, root = self.repo, self.root
        initial = W.started_from(repo)
        git(repo, 'branch', 'release')
        seen = {'engineer': 0, 'architect': 0}
        plan = W.plan_path('todo', '%Y-%m-%d_%H%M-{slug}', '2026-09-15T12:00', 'cache-screens')

        class DiskRepo(FakeRepos):
            def resolve(self, selected, worktree_root):
                return dict(super().resolve(selected, worktree_root), repo_path=repo, worktree_root=root)

        def runner(worktree, argv, directory, name, prompt, timeout, env, **kwargs):
            role = 'architect' if name.startswith(('assess-', 'verify-')) else 'engineer'
            if name.startswith('plan-'):
                write(os.path.join(worktree, plan), '**Status:** DRAFT\nKeep terminal screens.\n')
            if name.startswith('build-'):
                write(os.path.join(worktree, 'app.txt'), 'one\nPERSISTED_TERMINAL_SCREEN\n')
            if name.startswith('closeout-'):
                self.assertIn('commit_message', prompt)
                finished = os.path.join(worktree, 'todo', 'done', os.path.basename(plan))
                write(finished, '**Status:** PASS\nTerminal screens verified.\n')
                os.remove(os.path.join(worktree, plan))
            if role == 'architect':
                output = (review_first_for(settings, role, 'PASS')[0] if not seen[role]
                          else review_resumed_for(settings, role, 'PASS'))
            else:
                message = (json.dumps({'commit_message': {'subject': 'Retain terminal screens'}})
                           if name.startswith('closeout-') else 'Completed the requested work.')
                output = first_message_for(settings, role, message)[0]
            seen[role] += 1
            return 0, output

        stack_as(self)
        with E.env().auto_time_skipping_disabled(), patch('app.application.activities.trust.ensure', return_value=[]):
            host, _ = E.host([], git=W, repositories=DiskRepo(), queue=E.WINDOWS_QUEUE)
            host.runner = runner
            run_id = 'cache-screens-' + uuid.uuid4().hex[:8]
            start = E.start_input(run_id, auto=True, target=TARGET, queue=E.WINDOWS_QUEUE,
                                  policy=S.run_policy(settings), flow=['engineer:plan', 'architect:assess', 'you:approve',
                                  'engineer:build', 'architect:verify', 'engineer:closeout', 'you:merge'])
            start.update(short_name='cache-screens', merge_version=1)
            handle = E.run(E.client().start_workflow(WF.FeatureRun.run, start, id=run_id, task_queue=E.WORKFLOW_QUEUE))
            run = E.Run(handle=handle)
            self.addCleanup(run.cleanup)
            self.assertEqual(run.stop['reason'], 'final', run.status)
            final_tree = run.state['final_tree']

            async def listed(client, limit=200, cursor=None):
                return [runs._listed(await client.get_workflow_handle(run_id).describe())], None

            script = Path(__file__).resolve().parents[2] / 'tools/demo_press.py'
            with patch.object(runs, 'runs', listed):
                result = subprocess.run([sys.executable, str(script), 'http://127.0.0.1:%d' % port(), run_id,
                                         'merge-choice', 'release'], capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            state = E.run(handle.query(WF.FeatureRun.status))['state']
            self.assertEqual(state['status'], 'MERGED')
            self.assertEqual(state['base_branch'], 'release')
            self.assertEqual(W.started_from(repo), initial)
            self.assertEqual(git(repo, 'rev-parse', 'release^{tree}').strip(), final_tree)
            self.assertEqual(git(repo, 'show', '-s', '--format=%s', 'release').strip(), 'Merge retained terminal screens')
            self.assertFalse(os.path.exists(state['worktree_path']))
            history = E.run(runs.history(E.client(), run_id))
            self.assertEqual(history['answers'][-1]['action'], 'merge')
            self.assertEqual(history['review']['boundaries'][-1]['tree'], final_tree)
