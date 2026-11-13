"""Run-scoped Merge preferences are validated before a workflow can be started."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.application import client as runs
from tests import cast


class Preferences(unittest.IsolatedAsyncioTestCase):
    async def test_existing_run_catalog_uses_its_worktree_and_current_engineer_kind(self):
        configured = runs.S.run_policy(cast.settings())
        initial = {'repository': {'id': 'fixture', 'path': '/fixture', 'target': 'wsl'}, 'policy': configured}
        current = {'queue': 'target', 'workflow_queue': 'workflow', 'state': {'worktree_path': '/fixture/worktree'},
                   'configuration': {'engineer': {'kind': 'pi'}}}
        client = SimpleNamespace(execute_workflow=AsyncMock(return_value={'version': 1, 'skills': {}}))
        with patch.object(runs, 'readable_status', AsyncMock(return_value=current)), \
             patch.object(runs, 'started', AsyncMock(return_value=initial)), \
             patch.object(runs, 'preflight', AsyncMock()):
            result = await runs.skill_catalog(client, run_id='fixture-run')
        self.assertEqual(result['roles']['engineer'], 'pi')
        self.assertEqual(client.execute_workflow.call_args.args[1]['skill_root'], '/fixture/worktree')

    async def test_preference_is_saved_without_replacing_the_repository_base(self):
        settings = cast.settings()
        selected = {'id': 'fixture', 'path': '/fixture', 'target': 'wsl', 'base_branch': 'develop'}
        preference = {'branch': 'release', 'remote': None}
        client = SimpleNamespace(execute_workflow=AsyncMock(return_value={'merge_version': 1, 'merge_preference_version': 1}),
                                 start_workflow=AsyncMock(return_value=SimpleNamespace(id='started')))
        with patch.object(runs.S, 'load', return_value=settings), patch.object(runs.repos, 'select', return_value=selected), \
             patch.object(runs, 'landing_options', AsyncMock(return_value={'choices': [preference]})):
            await runs.start(client, 'Complete operator instructions', flow='engineer-code', check=False,
                             short_name='short-name', merge_preference=preference)
            recorded = client.start_workflow.call_args.args[1]
            self.assertEqual(recorded['merge_preference'], preference)
            self.assertEqual(recorded['repository']['base_branch'], 'develop')
            client.execute_workflow.return_value = {'merge_version': 1}
            client.start_workflow.reset_mock()
            with self.assertRaisesRegex(runs.Refusal, 'Merge preferences'):
                await runs.start(client, 'Complete instructions', flow='engineer-code', check=False,
                                 short_name='short-name', merge_preference=preference)
            client.start_workflow.assert_not_awaited()

    async def test_unknown_destination_refuses_before_start(self):
        settings = cast.settings()
        client = SimpleNamespace(start_workflow=AsyncMock())
        with patch.object(runs.S, 'load', return_value=settings), \
             patch.object(runs.repos, 'select', return_value={'id': 'fixture', 'path': '/fixture', 'target': 'wsl'}), \
             patch.object(runs, 'landing_options', AsyncMock(return_value={'choices': []})):
            with self.assertRaisesRegex(runs.Refusal, 'unavailable'):
                await runs.start(client, 'Task', flow='engineer-code', check=False, short_name='name',
                                 merge_preference={'branch': 'missing', 'remote': None})
            client.start_workflow.assert_not_awaited()
