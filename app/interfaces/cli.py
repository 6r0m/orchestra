"""Operator entrypoint: a Temporal client for runs, and the stack they run on. Six forms for a run,
the worktree view, and the stack:

    orchestrate "<task>" [--auto-proceed] [--repo NAME|PATH]
    orchestrate --resume <run-id> --answer "<answer>" [--confirm]
    orchestrate --continue <run-id>
    orchestrate --stop <run-id>
    orchestrate --force-terminate <run-id>
    orchestrate --show <run-id>
    orchestrate --worktrees [--repo NAME|PATH]
    orchestrate --stack status | start|stop|restart [temporal|wsl|windows]

A new run prints its run id, which is its Workflow Id. The run lives in
Temporal, so this process may exit at any stop and any later process answers it.
Each form that moves a run follows it, one line per stage transition, until the run
stops for the operator or ends. `--stack` goes through the stack's one owner, as `make up`,
`make down`, `make check` and the Workbench do.
"""
import argparse
import asyncio
import datetime
import os
import sys
import textwrap

from app.application import client as runs
from app.application import stack
from app.foundation import policy as policy_mod
from app.foundation import paths
from app.workspace import repos
from app.observability import telemetry
from app.orchestration import workflow as WF
from app.application.client import Refusal, preflight, work_item_label  # noqa: F401 - the CLI's names for them

# How long a follower waits between looks at a run.
FOLLOW_SECONDS = 1

# How an answer is typed here. Which answers a stop takes comes with the stop, and whether one is
# accepted is the workflow's; the command line owns only its shorthands, which answers are followed
# by your words, and which ask for --confirm.
SHORTHANDS = {"yes": "approve", "y": "approve"}
TAKES_WORDS = ("guide", "revise")
CONFIRMED = ("discard",)


def parse_answer(stop, text, confirm=False):
    """The operator's typed answer as one of the stop's published actions; None when it names none.

    `yes` approves; an action that takes your words is followed by them, a revise's role first when
    the stop publishes one per role; any other action is typed alone. At a stop that takes guidance,
    anything else typed is that guidance.
    """
    words = (text or "").strip()
    head, _, rest = words.partition(" ")
    offered = stop["actions"]
    name = SHORTHANDS.get(head.lower(), head.lower())
    role, _, after = rest.strip().partition(" ")
    answer = None
    if "%s:%s" % (name, role.lower()) in offered and after.strip():
        answer = {"action": "%s:%s" % (name, role.lower()), "text": after.strip()}
    elif name in offered and name in TAKES_WORDS:
        answer = {"action": name, "text": rest.strip()} if rest.strip() else None
    elif name in offered and not rest.strip():
        answer = {"action": name, "text": words}
    elif "guide" in offered and words:
        answer = {"action": "guide", "text": words}
    if answer is not None and confirm:
        answer["confirm"] = True
    return answer


def answer_line(stop):
    """The stop's answers as they are typed here."""
    def typed(action):
        if action == "approve":
            return '"yes"'
        if action == "guide":
            return '"<your guidance>"'
        spelled = action.replace(":", " ")
        if action.partition(":")[0] in TAKES_WORDS:
            spelled += " <feedback>"
        return '"%s"%s' % (spelled, " --confirm" if action in CONFIRMED else "")
    return " | ".join(typed(action) for action in stop["actions"])


async def follow(handle, printed=0, answered=None):
    """Print the run's new lines until it stops for the operator or ends; return its status.

    It looks every FOLLOW_SECONDS, and whether the run has ended is asked of Temporal. Each call it
    makes is answered before it goes on, so none is still in flight when it returns: the SDK's native
    runtime answers a call even after its caller stopped waiting — a history long poll, say — and one
    answered while the process exits needs the interpreter as it shuts down, which parks the runtime's
    thread for good, and the process never exits.
    """
    async def show():
        nonlocal printed
        status = await handle.query(WF.FeatureRun.status)
        for line in status["lines"][printed:]:
            print(line, flush=True)
        printed = len(status["lines"])
        return status

    while True:
        status = await show()
        if status["stop"] is not None and status["stop"]["id"] != answered:
            return status
        if (await handle.describe()).close_time is not None:
            return await show()
        await asyncio.sleep(FOLLOW_SECONDS)


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
        print("\nanswer with: orchestrate --resume %s --answer %s" % (run_id, answer_line(stop)))
        print("or end it:   orchestrate --stop %s" % run_id)
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
    # Read only once a worker can answer: with none the query would wait for one.
    status = await (runs.readable_status(client, run_id) if check else runs.status(client, run_id))
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
        print("error: %r does not answer a %s stop; answer %s" % (text, stop["reason"], answer_line(stop)),
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


async def _stop(client, run_id, tele, check=True):
    """Stop the run and follow it until it ends; 0 once it has, whatever git decided on the way. Temporal
    records a Stop with no worker polling, so it is recorded first; while no worker of the run's workflow
    queue polls to end the run, that is said, and 2."""
    try:
        await runs.stop(client, run_id)
    except runs.NotWaiting as error:
        print("error: %s — refusing" % error, file=sys.stderr)
        return 3
    print("stopping %s" % run_id, flush=True)
    try:
        status = await (runs.readable_status(client, run_id) if check else runs.status(client, run_id))
    except Refusal as error:
        print("the Stop is recorded, and the run ends once a worker hears it: %s" % error, flush=True)
        return 2
    handle = client.get_workflow_handle(run_id)
    stop = status["stop"]
    status = await follow(handle, printed=len(status["lines"]), answered=stop and stop["id"])
    code = _report(status, run_id, _trace_url(tele, status["state"]))
    return 0 if (await handle.describe()).close_time is not None else code


async def _force_terminate(client, run_id):
    try:
        await runs.force_terminate(client, run_id, "force terminated from the command line")
    except runs.NotWaiting as error:
        print("error: %s — refusing" % error, file=sys.stderr)
        return 3
    print("terminated %s — anything its host was already doing goes on: a merge or discard already running "
          "may still change the repository" % run_id)
    return 0


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
    print("\nlogs: %s" % os.path.join(paths.RUNTIME_ROOT, run_id, "logs"))
    return 0


async def _worktrees(client, args, check):
    selected, view = await runs.worktrees_of(client, args.repo, args.policy, check)
    print("%s — merged means merged into the local %s" % (selected["id"], view["base_branch"]))
    for row in view["rows"]:
        print("%-9s %-24s %s" % (row["state"], row["branch"] or "-", row["path"]))
    return 0


# How each part of the stack is named on the command line.
PARTS = {"temporal": "temporal", "wsl": "wsl worker", "windows": "windows worker"}


def _said(result):
    print("%-16s %s — %s" % (PARTS[result["component"]], "done" if result["ok"] else "FAILED", result["said"]),
          flush=True)


def stack_command(words, policy_path=None):
    """The stack's reading, or a start, stop or restart of it or one part, through its one owner.
    0 when every part it manages is up, or every action did what it was asked."""
    try:
        policy = policy_mod.load(policy_path)
        if words == ["status"]:
            reading = asyncio.run(stack.read(policy))
            for part in reading["components"]:
                state = part["state"] if part["state"] == "up" else part["state"].upper()
                detail = "; ".join(filter(None, ["pid %d" % part["pid"] if part["pid"] else "", part["detail"],
                                                 "" if part["managed"] else "not this stack's to start or stop"]))
                print("%-16s %s%s" % (PARTS[part["name"]], state, " — " + detail if detail else ""))
            return 0 if all(part["state"] == "up" for part in reading["components"] if part["managed"]) else 1
        results = stack.ACTIONS[words[0]](policy, words[1] if len(words) > 1 else None, progress=_said)
        return 0 if all(result["ok"] for result in results) else 1
    except (Refusal, policy_mod.InvalidPolicy) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 4


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
    parser.add_argument("--stop", metavar="RUN_ID", help="stop this run, keeping its worktree and branch")
    parser.add_argument("--force-terminate", metavar="RUN_ID",
                        help="close this run at once, with no cleanup, for a run a stop cannot finish; what its "
                             "host is already doing goes on, and a merge or discard running may still land")
    parser.add_argument("--show", metavar="RUN_ID", help="print this run's history and stop")
    parser.add_argument("--worktrees", action="store_true", help="list the repository's worktrees")
    parser.add_argument("--stack", nargs="+", metavar="ACTION",
                        help="the stack: `status`, or `start`, `stop` or `restart` — all of it, or one of "
                             "temporal, wsl, windows")
    parser.add_argument("--policy", metavar="PATH")
    args = parser.parse_args(argv)
    if sum(map(bool, (args.task, args.resume, args.continue_, args.stop, args.force_terminate, args.show,
                      args.worktrees, args.stack))) != 1:
        parser.error("give exactly one of: a task, --resume <run-id>, --continue <run-id>, --stop <run-id>, "
                     "--force-terminate <run-id>, --show <run-id>, --worktrees, --stack")
    if args.stack and not (args.stack == ["status"] or (args.stack[0] in stack.ACTIONS and len(args.stack) <= 2)):
        parser.error("--stack takes `status`, or start, stop or restart and at most one of temporal, wsl, windows")
    if args.resume and args.answer is None:
        parser.error("--resume requires --answer")
    if not args.resume and args.answer is not None:
        parser.error("--answer belongs to --resume")
    return args


async def run(argv=None, client=None, tele=None, check=True):
    """The entry point's body. Tests pass their own client and switch the preflight off."""
    args = parse_args(argv)
    if args.stack:
        # The stack's forms are `main`'s, outside any event loop: its owner runs its own.
        print("error: --stack runs as its own command, not inside another", file=sys.stderr)
        return 4
    try:
        if client is None:
            client = await runs.connect()
        if tele is None and check and not args.show and not args.worktrees and not args.force_terminate:
            tele = telemetry.resolve()
        if args.show:
            return await _show(client, args.show)
        if args.worktrees:
            return await _worktrees(client, args, check)
        if args.stop:
            return await _stop(client, args.stop, tele, check)
        if args.force_terminate:
            return await _force_terminate(client, args.force_terminate)
        if args.resume:
            return await _answer(client, args.resume, args.answer, args.confirm, tele, check)
        if args.continue_:
            return await _answer(client, args.continue_, "continue", False, tele, check, only="failed")
        return await _start(client, args, tele, check)
    except (Refusal, repos.Refused, policy_mod.InvalidPolicy) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 4


def main(argv=None):
    args = parse_args(argv)
    if args.stack:
        # Not inside an event loop: the owner waits on the stack's components in its own.
        return stack_command(args.stack, args.policy)
    return asyncio.run(run(argv))


if __name__ == "__main__":
    sys.exit(main())
