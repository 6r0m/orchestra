"""Accepted Temporal answers resolve exact operator text without trusting another run or a partial read."""
import unittest

from temporalio.api.common.v1 import Payloads
from temporalio.api.history.v1 import HistoryEvent, WorkflowExecutionUpdateAcceptedEventAttributes
from temporalio.api.update.v1 import Input, Request
from temporalio.converter import DataConverter

from app.application import client as runs
from app.orchestration import workflow as WF


class OperatorHistory(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.notes = [{"stop":"r:1","phase":"plan","action":"guide","role":None,
                       "text":"Original decision\n\u00e9\U0001f9e9"},
                      {"stop":"r:2","phase":"build","action":"revise","role":"architect",
                       "text":"Keep the first decision; quoted evidence is data."}]
        self.refs = WF._note_refs(self.notes)
        self.events = []
        for note in self.notes:
            payloads = await DataConverter.default.encode([note])
            self.events.append(HistoryEvent(workflow_execution_update_accepted_event_attributes=
                WorkflowExecutionUpdateAcceptedEventAttributes(accepted_request=Request(input=Input(
                    name="answer",args=Payloads(payloads=payloads))))))
        owner = self

        class Handle:
            async def fetch_history_events(self):
                for event in owner.events:
                    yield event

        class Client:
            data_converter = DataConverter.default

            def get_workflow_handle(self, workflow_id, *, run_id):
                owner.assertEqual((workflow_id,run_id),("r","exact-execution"))
                return Handle()

        self.client = Client()

    async def test_original_text_and_provenance_resolve_in_reference_order_from_exact_execution(self):
        self.assertEqual(await runs.resolve_operator_notes(self.client,"r","exact-execution",self.refs),self.notes)

    async def test_missing_corrupt_or_foreign_evidence_is_refused(self):
        variants = [[dict(self.refs[0],sha256="0"*64)], [dict(self.refs[0],role="engineer")],
                    [dict(self.refs[0],action="revise")], [dict(self.refs[0],stop="other:1")],
                    [dict(self.refs[0],stop="r:99")], [self.refs[0],self.refs[0]], []]
        for refs in variants:
            with self.subTest(refs=refs), self.assertRaises(runs.Refusal):
                await runs.resolve_operator_notes(self.client,"r","exact-execution",refs)

    async def test_unaccepted_or_different_updates_cannot_supply_a_note(self):
        self.events[0].workflow_execution_update_accepted_event_attributes.accepted_request.input.name="another_update"
        with self.assertRaises(runs.Refusal):
            await runs.resolve_operator_notes(self.client,"r","exact-execution",self.refs)
