"""Worker reload: refusal paths and native SDK activity draining, without the live stack."""
import asyncio
import concurrent.futures
import contextlib
import datetime
import os
import sys
import tempfile
import threading
import unittest
import uuid
from unittest import mock

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker, UnsandboxedWorkflowRunner

from app.application import client as runs, stack
from app.foundation import policy as P
from app.interfaces import worker as entry
from tests.application import test_stack


@workflow.defn
class ReloadProbe:
    @workflow.query
    def phase(self):
        return "running"

    @workflow.run
    async def run(self, queue: str):
        for number in (1, 2):
            await workflow.execute_activity(
                "reload_probe", number, task_queue=queue, start_to_close_timeout=datetime.timedelta(seconds=40),
                heartbeat_timeout=datetime.timedelta(seconds=5), retry_policy=RetryPolicy(maximum_attempts=1))


class Probe:
    def __init__(self):
        self.entered, self.release, self.cancelled = threading.Event(), threading.Event(), threading.Event()
        self.calls = []

    @activity.defn(name="reload_probe")
    def run(self, number: int):
        self.calls.append((number, activity.info().attempt))
        if number == 1:
            self.entered.set()
            try:
                while not self.release.wait(0.02):
                    activity.heartbeat()
                    if activity.is_cancelled():
                        self.cancelled.set()
                        raise RuntimeError("activity was cancelled")
            except BaseException:
                self.cancelled.set()
                raise


class DrainFiles(unittest.TestCase):
    def test_a_concurrent_capability_reader_does_not_prevent_draining(self):
        with tempfile.TemporaryDirectory() as folder:
            record = os.path.join(folder, "worker.pid")
            stack.drain_ready(record, 123)
            stack.request_drain(record, 123)
            with open(record + ".ready"):
                self.assertTrue(stack.drain_requested(record, 123))
            with open(record + ".drain"):
                stack.request_drain(record, 123)

    def test_wrong_pid_request_is_ignored_and_repeated_requests_are_safe(self):
        with tempfile.TemporaryDirectory() as folder:
            record = os.path.join(folder, "worker.pid")
            stack.drain_ready(record, 123)
            stack.request_drain(record, 123)
            self.assertFalse(stack.drain_requested(record, 456))
            self.assertTrue(stack.drain_requested(record, 123))
            stack.request_drain(record, 123)
            self.assertTrue(stack.drain_requested(record, 123))
            stack.drain_ready(record, 456)
            self.assertFalse(stack.drain_requested(record, 456), "fresh startup discards obsolete requests")

    def test_missing_or_wrong_pid_capability_refuses_without_writing_a_request(self):
        self.assertTrue(hasattr(stack, "request_drain"), "workers do not yet support a safe drain request")
        with tempfile.TemporaryDirectory() as folder:
            record = os.path.join(folder, "worker.pid")
            for capability in (None, "999 ready", "123 unknown"):
                if capability is not None:
                    with open(record + ".ready", "w") as fh:
                        fh.write(capability)
                with self.assertRaises(runs.Refusal):
                    stack.request_drain(record, 123)
                self.assertFalse(os.path.exists(record + ".drain"))


@unittest.skipIf(sys.platform.startswith("win"), "stack orchestration runs on WSL")
class ReloadOwner(unittest.TestCase):
    setUp = test_stack.Owner.setUp
    use = test_stack.Owner.use

    def test_success_exit_with_unrecognized_status_is_not_proof_of_death(self):
        mechanics = self.use(test_stack.Mechanics(running=("wsl",)))
        with mock.patch.object(stack, "mechanics", return_value=(True, "status unavailable")):
            [result] = stack.reload(P.load(), "wsl")
        self.assertFalse(result["ok"])
        self.assertEqual(mechanics.calls, [])

    def test_worker_appearing_before_cleanup_is_never_stopped(self):
        mechanics = self.use(test_stack.Mechanics(running=()))
        statuses = iter(((True, "stopped"), (True, "running 5252")))

        def raced(policy, target, action, *more):
            if action == "status":
                return next(statuses)
            return mechanics(policy, target, action, *more)

        with mock.patch.object(stack, "mechanics", raced):
            [result] = stack.reload(P.load(), "wsl")
        self.assertFalse(result["ok"])
        self.assertEqual(mechanics.calls, [])

    def test_reload_waits_for_original_process_after_its_record_was_removed(self):
        mechanics = self.use(test_stack.Mechanics(running=("temporal", "wsl")))
        looked, waited = [], []

        def retiring(policy, target, action, *more):
            if action == "drain":
                return True, "requested"
            if action == "status" and more:
                looked.append(more)
                if len(looked) == 1:
                    return True, "running 4242"
                mechanics.running.discard(target)
                return True, "stopped"
            return mechanics(policy, target, action, *more)

        with mock.patch.object(stack, "mechanics", retiring), mock.patch.object(stack.time, "sleep", waited.append):
            [result] = stack.reload(P.load(), "wsl")
        self.assertTrue(result["ok"], result)
        self.assertEqual(looked, [(4242,), (4242,)])
        self.assertEqual(len(waited), 1)
        self.assertIn(("wsl", "stop"), mechanics.calls)

    def test_temporal_reload_is_refused_without_mutation(self):
        mechanics = self.use(test_stack.Mechanics(running=("temporal",)))
        with self.assertRaises(runs.Refusal):
            stack.reload(P.load(), "temporal")
        self.assertEqual(mechanics.calls, [])

    def test_interrupted_or_unreadable_drain_never_stops_or_replaces_the_worker(self):
        for interrupt in (True, False):
            with self.subTest(interrupt=interrupt):
                mechanics = self.use(test_stack.Mechanics(running=("wsl",)))

                def busy(policy, target, action, *more):
                    if action == "drain":
                        mechanics.calls.append((target, action))
                        return True, "requested"
                    if more:
                        if interrupt:
                            raise KeyboardInterrupt()
                        return False, "cannot sample process"
                    return mechanics(policy, target, action, *more)

                with mock.patch.object(stack, "mechanics", busy):
                    if interrupt:
                        with self.assertRaises(KeyboardInterrupt):
                            stack.reload(P.load(), "wsl")
                    else:
                        [result] = stack.reload(P.load(), "wsl")
                        self.assertFalse(result["ok"])
                self.assertFalse(any(action in ("stop", "start", "sweep") for _, action in mechanics.calls))

    def test_reload_never_touches_temporal_and_waits_before_stopping(self):
        self.assertIn("reload", stack.ACTIONS, "there is no non-destructive worker update operation")
        mechanics = self.use(test_stack.Mechanics(running=("temporal", "wsl", "windows")))
        calls = mechanics.calls

        def draining(policy, target, action, *more):
            if action == "drain":
                calls.append((target, action))
                mechanics.running.discard(target)
                return True, "drained"
            if action == "stop":
                self.assertEqual(more, ("idle",), "reload may only request cleanup without worker signals")
            return mechanics(policy, target, action, *more)

        with mock.patch.object(stack, "mechanics", draining):
            results = stack.reload(P.load())
        self.assertTrue(all(row["ok"] for row in results), results)
        self.assertFalse(any(target == "temporal" for target, _ in calls))
        for target in ("wsl", "windows"):
            self.assertLess(calls.index((target, "drain")), calls.index((target, "stop")))
            self.assertLess(calls.index((target, "sweep")), calls.index((target, "start")))
        self.assertEqual(mechanics.swept, [(4242,), (4242,)])

    def test_reload_refuses_unknown_elevated_or_unsupported_workers_without_stop(self):
        self.assertIn("reload", stack.ACTIONS, "there is no non-destructive worker update operation")
        for options in ({"unreadable": ("windows",)}, {"elevated": ("windows",)}, {}):
            with self.subTest(options=options):
                mechanics = self.use(test_stack.Mechanics(running=("windows",), **options))

                def unsupported(policy, target, action, *more):
                    if action == "drain":
                        mechanics.calls.append((target, action))
                        return False, "worker does not support drain"
                    return mechanics(policy, target, action, *more)

                with mock.patch.object(stack, "mechanics", unsupported):
                    [result] = stack.reload(P.load(), "windows")
                self.assertFalse(result["ok"], result)
                self.assertFalse(any(action in ("stop", "start", "sweep") for _, action in mechanics.calls))


class NativeDrain(unittest.IsolatedAsyncioTestCase):
    async def scenario(self, force, target="windows", cancel=False):
        self.assertTrue(hasattr(stack, "request_drain"), "workers do not yet support a safe drain request")
        probe, queue = Probe(), "reload-" + uuid.uuid4().hex
        async with await WorkflowEnvironment.start_time_skipping() as env, contextlib.AsyncExitStack() as lifetimes:
            with tempfile.TemporaryDirectory() as folder:
                record = os.path.join(folder, "worker.pid")
                policy = P.load()

                def native(client, **kwargs):
                    kwargs.update(task_queue=queue,
                                  max_heartbeat_throttle_interval=datetime.timedelta(milliseconds=10))
                    if "workflows" in kwargs:
                        # The legacy time-skipping server does not expire the retired worker's
                        # sticky queue reliably. Disable caching for this test-owned workflow.
                        kwargs.update(task_queue=queue + "-workflow", workflows=[ReloadProbe],
                                      workflow_runner=UnsandboxedWorkflowRunner(), max_cached_workflows=0)
                    if force:
                        kwargs["graceful_shutdown_timeout"] = datetime.timedelta()
                    return Worker(client, **kwargs)

                if target == "windows":
                    await lifetimes.enter_async_context(Worker(
                        env.client, task_queue=queue + "-workflow", workflows=[ReloadProbe],
                        workflow_runner=UnsandboxedWorkflowRunner(), max_cached_workflows=0))

                host = mock.Mock()
                host.all.return_value = [probe.run]
                with mock.patch.object(entry.settings, "load", return_value=policy), \
                        mock.patch.object(entry, "sweep"), \
                        mock.patch.object(entry.terminal, "serve"), \
                        mock.patch.object(entry.stack, "pid_file", return_value=record), \
                        mock.patch.object(entry.runs, "connect", new=mock.AsyncMock(return_value=env.client)), \
                        mock.patch.object(entry.activities, "Activities", return_value=host), \
                        mock.patch.object(entry, "Worker", side_effect=native):
                    running = asyncio.create_task(entry.main(target))
                    try:
                        async def ready():
                            while not os.path.exists(record + ".ready"):
                                if running.done():
                                    await running
                                await asyncio.sleep(0.02)
                        await asyncio.wait_for(ready(), 15)
                        handle = await env.client.start_workflow(ReloadProbe.run, queue, id=queue,
                                                                 task_queue=queue + "-workflow")
                        self.assertTrue(await asyncio.to_thread(probe.entered.wait, 10))
                        stack.request_drain(record, os.getpid())
                        if force:
                            self.assertTrue(await asyncio.to_thread(probe.cancelled.wait, 10),
                                            "known-bad zero-grace control must interrupt the activity")
                        else:
                            await asyncio.sleep(2)
                            self.assertFalse(probe.cancelled.is_set())
                            self.assertFalse(running.done(), "reload must wait for the active activity")
                            self.assertEqual(probe.calls, [(1, 1)])
                            if target == "wsl":
                                self.assertEqual(await asyncio.wait_for(handle.query(ReloadProbe.phase), 3),
                                                 "running", "workflow control must remain available during drain")
                            if cancel:
                                await handle.cancel()
                                self.assertTrue(await asyncio.to_thread(probe.cancelled.wait, 10),
                                                "operator cancellation must still reach the activity")
                    finally:
                        probe.release.set()
                        await asyncio.wait_for(running, 25)
                    self.assertFalse(os.path.exists(record))
                    self.assertFalse(os.path.exists(record + ".ready"))
                    self.assertFalse(os.path.exists(record + ".drain"))
                if not force and not cancel:
                    self.assertEqual(probe.calls, [(1, 1)], "queued work must wait for the replacement")
                    replacement = await Client.connect(env.client.service_client.config.target_host,
                                                       namespace=env.client.namespace,
                                                       identity="replacement-" + uuid.uuid4().hex)
                    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                        async with contextlib.AsyncExitStack() as next_workers:
                            if target == "wsl":
                                await next_workers.enter_async_context(Worker(
                                    replacement, task_queue=queue + "-workflow", workflows=[ReloadProbe],
                                    workflow_runner=UnsandboxedWorkflowRunner(), max_cached_workflows=0))
                            await next_workers.enter_async_context(Worker(
                                replacement, task_queue=queue, activities=[probe.run], activity_executor=executor))
                            try:
                                await asyncio.wait_for(handle.result(), 20)
                            except TimeoutError:
                                history = await handle.fetch_history()
                                self.fail("replacement did not resume; calls=%r, events=%r, last=%s" % (
                                    probe.calls, [event.event_type for event in history.events], history.events[-1]))
                    self.assertEqual(probe.calls, [(1, 1), (2, 1)], "no activity was retried or duplicated")

    async def test_native_drain_preserves_current_activity_and_replacement_resumes_queued_work(self):
        await self.scenario(False)

    async def test_known_bad_zero_grace_interrupts_the_same_activity(self):
        await self.scenario(True)

    async def test_cohosted_workflow_and_activity_workers_drain_and_resume(self):
        await self.scenario(False, "wsl")

    async def test_operator_cancellation_still_reaches_a_draining_activity(self):
        await self.scenario(False, "wsl", cancel=True)
