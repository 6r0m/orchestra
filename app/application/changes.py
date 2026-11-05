"""A run's change, live, for the page that watches it: what the run's worktree on this host holds against the
base the run stands on now, read again only when something in the worktree moved.

The worker hands `ChangeFeed.poll` to its socket (`agents.terminal.serve`), which asks it on behalf of each
watcher. It reads, and keeps nothing but each watcher's memo: git owns the files, the run's workflow owns its
base and its worktree's path, and what it sends is the same snapshot a review reads (`worktrees.review_diff`),
so a file of it opens through the change's own reader. A run on another host, a worktree not made yet or gone,
and a status or a worktree that cannot be read now are each said as such, never guessed.
"""
import asyncio
import concurrent.futures
import datetime
import subprocess
import time

from temporalio.client import WorkflowQueryFailedError, WorkflowQueryRejectedError
from temporalio.service import RPCError

from app.application import client as runs
from app.workspace import worktrees

# How soon the next look comes: never sooner than FASTEST, and five times as long as the last read took, so a
# large worktree is read less often, up to SLOWEST.
FASTEST, SLOWEST, PACE = 2.0, 60.0, 5.0
# The run's worktree and base are asked of its workflow this often: a reconcile moves the base.
STATE_EVERY = 15.0
# After something could not be read, the next look.
RETRY = 15.0
# How long a status query may take before it is said to be unreadable.
QUERY_SECONDS = 10.0


class ChangeFeed:
    """The change of each run whose worktree is on this host — `target` — for its watchers."""

    def __init__(self, target, state=None):
        self.target = target
        # `run_id` -> the run's state as its workflow answers it, None for no such run; until the worker
        # has its client, none.
        self.state = state

    def bind(self, client, loop):
        """Ask each run's state of its workflow through `client`, on the worker's own event loop."""
        def state(run_id):
            asked = runs.status(client, run_id, timeout=datetime.timedelta(seconds=QUERY_SECONDS))
            current = asyncio.run_coroutine_threadsafe(asked, loop).result(QUERY_SECONDS + 5)
            return current and current["state"]
        self.state = state

    def poll(self, run_id, memo):
        """One look at `run_id`'s change for one watcher, whose `memo` this keeps between its looks: what to
        send it, None when nothing is new, and how long until the next look — None when there is nothing more
        to watch."""
        if self.state is None:
            return said(memo, {"error": "this host's worker is still starting"}), RETRY
        now = time.monotonic()
        if now >= memo.get("asked", 0.0) + STATE_EVERY:
            try:
                state = self.state(run_id)
            except (RPCError, WorkflowQueryFailedError, WorkflowQueryRejectedError, TimeoutError,
                    concurrent.futures.TimeoutError) as error:
                return said(memo, {"error": "the run's status cannot be read now: %s" % error}), RETRY
            if state is None:
                return {"gone": "Temporal holds no run %s" % run_id}, None
            if state.get("target") != self.target:
                return {"gone": "run %s works on the %s host, not this one" % (run_id, state.get("target"))}, None
            memo.update(asked=now, path=state.get("worktree_path"), base=state.get("base_tip"))
        if not memo.get("path"):
            # Asked again at the next look: the worktree is made in a moment.
            memo["asked"] = 0.0
            return said(memo, {"waiting": "the run has no worktree yet"}), FASTEST
        try:
            moved = worktrees.change_fingerprint(memo["path"])
            if moved == memo.get("fingerprint") and memo["base"] == memo.get("read_base"):
                return None, memo.get("pace", FASTEST)
            began = time.monotonic()
            read = worktrees.review_diff(memo["path"], base=memo["base"], files_from=0)
            took = time.monotonic() - began
        except worktrees.ChangeRefused as error:
            return {"gone": str(error)}, None
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
            return said(memo, {"error": "the change cannot be read now: %s" % error}), RETRY
        memo.update(fingerprint=moved, read_base=memo["base"], pace=min(SLOWEST, max(FASTEST, PACE * took)))
        sent = {"base": read["base"], "tree": read["tree"], "files": read["files"], "files_total": read["files_total"],
                "read": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
        memo["said"] = None
        return sent, memo["pace"]


def said(memo, message):
    """`message`, unless it is what this watcher was last told: a state it is in is said once."""
    if memo.get("said") == message:
        return None
    memo["said"] = message
    return message
