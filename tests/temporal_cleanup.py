"""Delete from Temporal the runs a check on the live stack made, and prove them gone.

The Workbench lists every run Temporal retains, for 90 days, so `make demo` and the live
acceptance take back what they started: each run, and each read of its change — a `ReviewDiff`
workflow, which `client.review_diff` names after its run. Exact ids only, never a prefix a real
run could share.
"""
import asyncio
import time

from temporalio.api.common.v1 import WorkflowExecution
from temporalio.api.workflowservice.v1 import DeleteWorkflowExecutionRequest
from temporalio.service import RPCError, RPCStatusCode


def query(run_ids):
    """The listing's query for the runs and the reads of their changes."""
    for run_id in run_ids:
        if not run_id or "'" in run_id:
            raise ValueError("not a run id: %r" % run_id)
    return " OR ".join("WorkflowId = '%s' OR WorkflowId STARTS_WITH 'diff-%s-'" % (run_id, run_id)
                       for run_id in run_ids)


async def delete_runs(client, run_ids, seconds=60):
    """Delete the runs and the reads of their changes — an open run is terminated by its deletion,
    which Temporal completes on its own time — and wait up to `seconds` for it to finish.

    Returns the ids deleted, and those Temporal still holds, by themselves or in its listing.
    """
    if not run_ids:
        return [], []
    found = {execution.id: execution.run_id async for execution in client.list_workflows(query(run_ids))}
    for run_id in run_ids:
        try:
            # Each run by its own id as well: one that only just started may not be listed yet.
            found.setdefault(run_id, (await client.get_workflow_handle(run_id).describe()).run_id)
        except RPCError as error:
            if error.status != RPCStatusCode.NOT_FOUND:
                raise
    for workflow_id, execution in found.items():
        try:
            await client.workflow_service.delete_workflow_execution(DeleteWorkflowExecutionRequest(
                namespace=client.namespace,
                workflow_execution=WorkflowExecution(workflow_id=workflow_id, run_id=execution)))
        except RPCError as error:
            if error.status != RPCStatusCode.NOT_FOUND:
                raise
    deadline = time.monotonic() + seconds
    while True:
        kept = await held(client, run_ids, found)
        if not kept or time.monotonic() > deadline:
            return sorted(found), kept
        await asyncio.sleep(1)


async def held(client, run_ids, ids):
    """Which of `ids` Temporal still holds, by themselves or in the listing the Workbench reads."""
    listed = {execution.id async for execution in client.list_workflows(query(run_ids))}
    described = set()
    for workflow_id in ids:
        try:
            await client.get_workflow_handle(workflow_id).describe()
            described.add(workflow_id)
        except RPCError as error:
            if error.status != RPCStatusCode.NOT_FOUND:
                raise
    return sorted(listed | described)
