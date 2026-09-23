"""The suite's own harness: a process that used the Temporal test environment exits once its tests are
done, even with an activity still running on one of its workers.

The interpreter joins every thread pool's threads before it runs a single atexit handler, and an
activity runs on one of those threads until its worker's shutdown cancels it. So the harness stops its
workers as the interpreter begins to shut down, ahead of that join — or a turn left running would hold
the process at exit for good.
"""
import os
import queue
import signal
import subprocess
import sys
import textwrap
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
# Well past a worker's shutdown and the test server's, and well short of a turn's budget.
EXIT_SECONDS = 60

# A test process that ends with a run's turn still at work, as one would if a test left its run open:
# the turn heartbeats, as a real one does, and ends only once it is cancelled.
LEFT_RUNNING = textwrap.dedent("""\
    import sys, threading, time, uuid
    sys.path[:0] = [%r, %r]
    import temporal_env as E
    from app.agents import terminal
    from app.orchestration import workflow as WF

    started = threading.Event()

    def turn(worktree, argv, rdir, name, prompt, timeout, env, *, brain):
        started.set()
        while True:
            terminal._activity_tick(name)
            time.sleep(0.2)

    host, _ = E.host([])
    host.runner = turn
    run_id = uuid.uuid4().hex[:12]
    E.run(E.client().start_workflow(WF.FeatureRun.run, E.start_input(run_id), id=run_id,
                                    task_queue=E.WORKFLOW_QUEUE))
    assert started.wait(60), "the turn never started"
    print("left running", flush=True)
""") % (PKG, HERE)


def end_tree(child):
    """End a process and every process it started — the test server among them."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], capture_output=True)
    else:
        os.killpg(child.pid, signal.SIGKILL)


class Exit(unittest.TestCase):
    def test_a_process_whose_turn_is_still_running_exits_once_its_tests_are_done(self):
        child = subprocess.Popen([sys.executable, "-c", LEFT_RUNNING], cwd=PKG, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, start_new_session=os.name != "nt")
        self.addCleanup(lambda: child.poll() is None and end_tree(child))
        lines = queue.Queue()
        threading.Thread(target=lambda: [lines.put(line) for line in child.stdout], daemon=True).start()
        # Until its main thread is done: the server's and the workers' start are not the exit's to count.
        before, deadline = [], time.monotonic() + 120
        while not before or before[-1].strip() != "left running":
            try:
                before.append(lines.get(timeout=max(0.1, deadline - time.monotonic())))
            except queue.Empty:
                end_tree(child)
                self.fail("its turn never got running: %s" % "".join(before)[-2000:])
        done = time.monotonic()
        try:
            child.wait(timeout=EXIT_SECONDS)
        except subprocess.TimeoutExpired:
            end_tree(child)
            self.fail("still running %d s after its main thread was done" % EXIT_SECONDS)
        self.assertEqual(child.returncode, 0, "".join(before)[-2000:])
        self.assertLess(time.monotonic() - done, EXIT_SECONDS)


if __name__ == "__main__":
    unittest.main()
