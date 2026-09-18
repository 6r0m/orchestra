"""Operator entrypoint: a Temporal client for runs. Four forms, and the worktree view:

    orchestrate "<task>" [--auto-proceed] [--repo NAME|PATH]
    orchestrate --resume <run-id> --answer "<answer>" [--confirm]
    orchestrate --continue <run-id>
    orchestrate --show <run-id>
    orchestrate --worktrees [--repo NAME|PATH]

A new run prints its run id, which is its Workflow Id. The run lives in
Temporal, so this process may exit at any stop and any later process answers it.
Each form that moves a run follows it, one line per stage transition, until the run
stops for the operator or ends.
"""
import argparse
import asyncio
import datetime
import os
import sys
import textwrap

import client as runs
import policy as policy_mod
import repos
import telemetry
import workflow as WF
from client import Refusal, preflight, work_item_label  # noqa: F401 - the CLI's names for them

RUNTIME_ROOT = os.path.join(repos.ORCHESTRATION_REPO, "tmp", "orchestration")
# The longest a follower waits between looks at a run when no history event wakes it.
FOLLOW_SECONDS = 2

# How the operator answers each stop, shown when a run stops.
ANSWERS = {
    "approval": ('"yes"', '"revise <feedback>"', '"abort"'),
    "blocker": ('"<your guidance>"', '"abort"'),
    "exhausted": ('"<your guidance>"', '"abort"'),
    "failed": ('"continue" (or --continue)', '"abort"'),
    "final": ('"merge"', '"revise engineer <feedback>"', '"revise architect <feedback>"',
              '"discard" --confirm'),
}


def parse_answer(stop, text, confirm=False):
    """The operator's typed answer as one of the stop's named actions; None when it names none.

    Parsing is this client's convenience only: the workflow's validator decides what
    it accepts.
    """
    words = (text or "").strip()
    head, _, rest = words.partition(" ")
    lowered, rest = head.lower(), rest.strip()
    reason = stop["reason"]
    if reason == "approval":
        if words.lower() in ("yes", "y", "approve"):
            return {"action": "approve", "text": words}
        if words.lower() == "abort":
            return {"action": "abort", "text": words}
        if lowered == "revise" and rest:
            return {"action": "revise", "text": rest}
        return None
    if reason in ("blocker", "exhausted"):
        if words.lower() == "abort":
            return {"action": "abort", "text": words}
        return {"action": "guide", "text": words} if words else None
    if reason == "failed":
        return {"action": words.lower(), "text": words} if words.lower() in ("continue", "abort") else None
    if reason == "final":
        if words.lower() == "merge":
            return {"action": "merge", "text": words}
        if words.lower() == "discard":
            return {"action": "discard", "text": words, "confirm": bool(confirm)}
        role, _, feedback = rest.partition(" ")
        if lowered == "revise" and role in ("engineer", "architect") and feedback.strip():
            return {"action": "revise", "role": role, "text": feedback.strip()}
    return None


async def follow(handle, printed=0, answered=None):
    """Print the run's new lines until it stops for the operator or ends; return its status.

    Woken by each new event in the run's history. A long poll that returns without one
    — the time-skipping test server does — falls back to a fresh look every
    FOLLOW_SECONDS, and whether the run has ended is asked of Temporal, never inferred
    from the event stream ending.
    """
    changed = asyncio.Event()

    async def watch():
        while True:
            async for _ in handle.fetch_history_events(wait_new_event=True):
                changed.set()
            await asyncio.sleep(FOLLOW_SECONDS)

    async def show():
        nonlocal printed
        status = await handle.query(WF.FeatureRun.status)
        for line in status["lines"][printed:]:
            print(line, flush=True)
        printed = len(status["lines"])
        return status

    watcher = asyncio.create_task(watch())
    try:
        while True:
            changed.clear()
            status = await show()
            if status["stop"] is not None and status["stop"]["id"] != answered:
                return status
            if (await handle.describe()).close_time is not None:
                return await show()
            try:
                await asyncio.wait_for(changed.wait(), timeout=FOLLOW_SECONDS)
            except asyncio.TimeoutError:
                pass
    finally:
        watcher.cancel()


def _report(status, run_id, trace_url):
    state, stop = status["state"], status["stop"]
    if stop is not None:
        final = stop["reason"] == "final"
        print("\n== run %s %s ==" % (run_id, "is READY_FOR_HUMAN" if final else "stopped for you"))
        if trace_url:
            # The stop's own row in the trace carries what you are answering.
            print("trace:    %s" % trace_url)
        label = {"approval": "summary", "failed": "error", "final": "refused"}.get(stop["reason"], "feedback")
        for key, value in (("reason", stop["reason"]), ("phase", stop["phase"]), ("todo", stop["todo"]),
                           ("worktree", state.get("worktree_path") if final else None),
                           (label, stop["feedback"]), ("hint", stop["hint"])):
            if value:
                print("%-9s %s" % (key + ":", value))
        print("\nanswer with: orchestrate --resume %s --answer %s" % (run_id, " | ".join(ANSWERS[stop["reason"]])))
        return 0 if final else 2
    status_name = state.get("status", "?")
    print("\n== run %s finished: %s ==" % (run_id, status_name))
    if trace_url:
        print("trace:    %s" % trace_url)
    if state.get("refusal"):
        print("refused:  %s" % state["refusal"])
    if state.get("merge_commit"):
        print("merged:   %s into %s" % (state["merge_commit"], state.get("base_branch")))
    return 0 if status_name in ("MERGED", "DISCARDED") else 1


def _trace_url(tele, state):
    return telemetry.trace_url(tele, (state or {}).get("trace_id"))


async def _start(client, args, tele, check):
    handle = await runs.start(client, args.task, repo=args.repo, auto_proceed=args.auto_proceed,
                              policy_path=args.policy, check=check)
    run_id = handle.id
    print("run-id: %s" % run_id, flush=True)
    status = await follow(handle)
    return _report(status, run_id, _trace_url(tele, status["state"]))


async def _answer(client, run_id, text, confirm, tele, check, only=None):
    handle = client.get_workflow_handle(run_id)
    status = await runs.status(client, run_id)
    if status is None:
        print("error: no run %r — refusing" % run_id, file=sys.stderr)
        return 3
    stop = status["stop"]
    if stop is None or (only and stop["reason"] != only):
        print("error: run %s is not waiting for %s" % (run_id, "a %s answer" % only if only else "an answer"),
              file=sys.stderr)
        return 3
    answer = parse_answer(stop, text, confirm)
    if answer is None:
        print("error: %r does not answer a %s stop; answer %s" % (text, stop["reason"], " | ".join(ANSWERS[stop["reason"]])),
              file=sys.stderr)
        return 2
    answer["stop"] = stop["id"]
    try:
        await runs.answer(client, run_id, answer, check=check, only=only)
    except runs.NotWaiting as error:
        print("error: %s — refusing" % error, file=sys.stderr)
        return 3
    except runs.NotAccepted as error:
        print("error: not accepted: %s" % error, file=sys.stderr)
        return 2
    print("answered %s: %s" % (stop["reason"], answer["action"]), flush=True)
    status = await follow(handle, printed=len(status["lines"]), answered=stop["id"])
    return _report(status, run_id, _trace_url(tele, status["state"]))


def _elapsed(previous, current):
    """Wall time between two timeline entries, or '-' when it cannot be computed."""
    if not previous or not current:
        return "-"
    try:
        start = datetime.datetime.fromisoformat(previous.replace("Z", "+00:00"))
        end = datetime.datetime.fromisoformat(current.replace("Z", "+00:00"))
    except ValueError:
        return "-"
    seconds = int((end - start).total_seconds())
    if seconds < 0:
        return "-"
    return "%dm%02ds" % divmod(seconds, 60) if seconds >= 60 else "%ds" % seconds


def print_verdicts(timeline):
    """The architect's own words, one entry per judgement — why the run went as it did.

    Never deduplicated on text: an architect repeating a finding the engineer did not
    fix is exactly the evidence that the round achieved nothing.
    """
    judged = [entry for entry in timeline if entry.get("verdict")]
    if not judged:
        return
    print("\nwhat the architect said:")
    for entry in judged:
        print("\n  %s e%s r%s -> %s" % (entry["stage"], entry["episode"], entry["round"], entry["verdict"]))
        for line in textwrap.wrap(entry.get("feedback") or "", 92):
            print("    %s" % line)


async def _show(client, run_id):
    """A run's history from its workflow: the stage table, the architect's words, the event history."""
    handle = client.get_workflow_handle(run_id)
    status = await runs.status(client, run_id)
    if status is None:
        print("error: no run %r — refusing" % run_id, file=sys.stderr)
        return 3
    events = 0
    async for _ in handle.fetch_history_events():
        events += 1
    state, timeline = status["state"], status["timeline"]
    print("run %s — %s, %d history events" % (run_id, state.get("status", "?"), events))
    print("%-7s %-6s %-3s %-3s %-9s %-10s %-19s %s" % ("stage", "phase", "ep", "r", "verdict", "gate", "when", "gap"))
    for index, entry in enumerate(timeline):
        gap = _elapsed(timeline[index - 1]["at"] if index else None, entry["at"])
        print("%-7s %-6s %-3s %-3s %-9s %-10s %-19s %s" % (
            entry["stage"], entry["phase"], entry["episode"], entry["round"], entry.get("verdict") or "-",
            entry.get("gate") or "-", entry["at"][:19], gap))
    if status["stop"]:
        print("\nwaiting at: %s (%s)" % (status["stop"]["reason"], status["stop"]["hint"]))
    print_verdicts(timeline)
    print("\nlogs: %s" % os.path.join(RUNTIME_ROOT, run_id, "logs"))
    return 0


async def _worktrees(client, args, check):
    selected, view = await runs.worktrees_of(client, args.repo, args.policy, check)
    print("%s — merged means merged into the local %s" % (selected["id"], view["base_branch"]))
    for row in view["rows"]:
        print("%-9s %-24s %s" % (row["state"], row["branch"] or "-", row["path"]))
    return 0


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="orchestrate")
    parser.add_argument("task", nargs="?", help="task description (new run)")
    parser.add_argument("--auto-proceed", action="store_true", help="skip the plan approval stop")
    parser.add_argument("--repo", metavar="NAME|PATH", help="repository to run on (default: this one)")
    parser.add_argument("--resume", metavar="RUN_ID", help="answer the stop this run waits at")
    parser.add_argument("--answer", metavar="TEXT")
    parser.add_argument("--confirm", action="store_true", help="confirm a discard")
    parser.add_argument("--continue", dest="continue_", metavar="RUN_ID",
                        help="run a failed stage again once you have fixed its cause")
    parser.add_argument("--show", metavar="RUN_ID", help="print this run's history and stop")
    parser.add_argument("--worktrees", action="store_true", help="list the repository's worktrees")
    parser.add_argument("--policy", metavar="PATH")
    args = parser.parse_args(argv)
    if sum(map(bool, (args.task, args.resume, args.continue_, args.show, args.worktrees))) != 1:
        parser.error("give exactly one of: a task, --resume <run-id>, --continue <run-id>, --show <run-id>, "
                     "--worktrees")
    if args.resume and args.answer is None:
        parser.error("--resume requires --answer")
    if not args.resume and args.answer is not None:
        parser.error("--answer belongs to --resume")
    return args


async def run(argv=None, client=None, tele=None, check=True):
    """The entry point's body. Tests pass their own client and switch the preflight off."""
    args = parse_args(argv)
    try:
        if client is None:
            client = await runs.connect()
        if tele is None and check and not args.show and not args.worktrees:
            tele = telemetry.resolve()
        if args.show:
            return await _show(client, args.show)
        if args.worktrees:
            return await _worktrees(client, args, check)
        if args.resume:
            return await _answer(client, args.resume, args.answer, args.confirm, tele, check)
        if args.continue_:
            return await _answer(client, args.continue_, "continue", False, tele, check, only="failed")
        return await _start(client, args, tele, check)
    except (Refusal, repos.Refused, policy_mod.InvalidPolicy) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 4


def main(argv=None):
    return asyncio.run(run(argv))


if __name__ == "__main__":
    sys.exit(main())
