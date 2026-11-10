"""Native worker admission keeps overflow queued before its heartbeat clock starts."""
import asyncio
import contextlib
import datetime
import os
import tempfile
import threading
import unittest
import uuid
from unittest import mock

from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import TimeoutType
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker, UnsandboxedWorkflowRunner

from app.application import stack
from app.foundation import policy as P
from app.interfaces import worker as entry


@workflow.defn
class AdmissionWorkflow:
    @workflow.run
    async def run(self, request):
        return await workflow.execute_activity(
            "admission_probe", request["number"], task_queue=request["queue"],
            start_to_close_timeout=datetime.timedelta(seconds=60),
            heartbeat_timeout=datetime.timedelta(seconds=5), retry_policy=RetryPolicy(maximum_attempts=1))


class HeldActivities:
    def __init__(self):
        self.release = threading.Event()
        self.lock = threading.Lock()
        self.entered = set()

    @activity.defn(name="admission_probe")
    def run(self, number: int):
        with self.lock:
            self.entered.add(number)
        while not self.release.wait(0.05):
            activity.heartbeat(number)
        return number


class NativeAdmission(unittest.IsolatedAsyncioTestCase):
    async def scenario(self, target, overadmit=False):
        probe, queue = HeldActivities(), "admission-" + uuid.uuid4().hex
        pools = []
        async with await WorkflowEnvironment.start_time_skipping() as env, contextlib.AsyncExitStack() as lifetimes:
            lifetimes.enter_context(env.auto_time_skipping_disabled())
            with tempfile.TemporaryDirectory() as folder:
                record = os.path.join(folder, "worker.pid")

                def native(client, **kwargs):
                    if "activities" in kwargs:
                        pools.append(kwargs["activity_executor"])
                        kwargs.update(task_queue=queue,
                                      max_heartbeat_throttle_interval=datetime.timedelta(milliseconds=100))
                        if overadmit:
                            kwargs["max_concurrent_activities"] = None
                    else:
                        kwargs.update(task_queue=queue + "-workflow", workflows=[AdmissionWorkflow],
                                      workflow_runner=UnsandboxedWorkflowRunner(), max_cached_workflows=0)
                    return Worker(client, **kwargs)

                if target == "windows":
                    await lifetimes.enter_async_context(Worker(
                        env.client, task_queue=queue + "-workflow", workflows=[AdmissionWorkflow],
                        workflow_runner=UnsandboxedWorkflowRunner(), max_cached_workflows=0))
                host = mock.Mock()
                host.all.return_value = [probe.run]
                with mock.patch.object(entry.settings, "load", return_value=P.load()), \
                        mock.patch.object(entry, "sweep"), mock.patch.object(entry.terminal, "serve"), \
                        mock.patch.object(entry.stack, "pid_file", return_value=record), \
                        mock.patch.object(entry.runs, "connect", new=mock.AsyncMock(return_value=env.client)), \
                        mock.patch.object(entry.activities, "Activities", return_value=host), \
                        mock.patch.object(entry, "Worker", side_effect=native):
                    running = asyncio.create_task(entry.main(target))
                    handles = []
                    try:
                        async def ready():
                            while not os.path.exists(record + ".ready"):
                                if running.done():
                                    await running
                                await asyncio.sleep(0.02)
                        await asyncio.wait_for(ready(), 15)
                        capacity = pools[0]._max_workers
                        for number in range(capacity):
                            handles.append(await env.client.start_workflow(
                                AdmissionWorkflow.run, {"queue": queue, "number": number},
                                id=queue + "-" + str(number), task_queue=queue + "-workflow"))
                        async def full():
                            while len(probe.entered) != capacity:
                                await asyncio.sleep(0.02)
                        await asyncio.wait_for(full(), 15)
                        extra = await env.client.start_workflow(
                            AdmissionWorkflow.run, {"queue": queue, "number": capacity},
                            id=queue + "-overflow", task_queue=queue + "-workflow")
                        handles.append(extra)
                        # Longer than the heartbeat deadline while every execution thread is held.
                        await asyncio.sleep(7)
                        history = await extra.fetch_history()
                        timeouts = [event.activity_task_timed_out_event_attributes.failure.timeout_failure_info.timeout_type
                                    for event in history.events if event.HasField("activity_task_timed_out_event_attributes")]
                        self.assertEqual(timeouts, [TimeoutType.HEARTBEAT] if overadmit else [],
                                         "overflow must wait in Temporal, never time out behind an occupied thread pool")
                        self.assertEqual(probe.entered, set(range(capacity)))
                        probe.release.set()
                        results = await asyncio.wait_for(asyncio.gather(
                            *(handle.result() for handle in handles), return_exceptions=True), 45)
                        if overadmit:
                            self.assertEqual(sum(isinstance(value, BaseException) for value in results), 1)
                        else:
                            self.assertEqual(results, list(range(capacity + 1)))
                    finally:
                        probe.release.set()
                        for handle in handles:
                            with contextlib.suppress(Exception):
                                await handle.cancel()
                        stack.request_drain(record, os.getpid())
                        await asyncio.wait_for(running, 45)
                        for pool in pools:
                            pool.shutdown(wait=True, cancel_futures=True)

    async def test_saturated_workers_queue_overflow_without_starting_its_heartbeat_clock(self):
        for target in P.TARGETS:
            with self.subTest(target=target):
                await self.scenario(target)

    async def test_known_bad_sdk_default_times_out_queued_work_behind_the_same_pool(self):
        await self.scenario("windows", overadmit=True)
