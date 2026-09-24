"""The Orchestra stack: one reading of it, and one owner that starts, stops and restarts it.

`make up|down|check`, the command line and the Workbench all come here. A stack is what one policy
runs: Temporal, one service on this machine, and a worker per target host, the WSL one also running
the policy's workflows. The checkout's own policy's stack manages all three. Another policy's
(`ORCH_POLICY`: the demo's, the acceptance's) is a stack of its own on the same Temporal and manages
only its WSL worker: Temporal is the deployment's, and the Windows host runs only its own copy of a
policy. The reading shows every part, managed or not.

The process mechanics are `workers.sh` and, for the Windows host, `workers.ps1`, one component at a
time; this orders them, proves each outcome and says what happened. It runs on WSL, where the
Makefile, the command line and the Workbench run. Nothing here prints.
"""
import asyncio
import contextlib
import datetime
import os
import re
import subprocess
import time

from temporalio.api.enums.v1 import TaskQueueType
from temporalio.service import RPCError

from app.application import client as runs
from app.foundation import paths
from app.foundation import policy as P

# Started in this order and stopped in the reverse: a worker exits at once without Temporal.
COMPONENTS = ("temporal", "wsl", "windows")
SCRIPT = os.path.join(paths.REPO, "workers.sh")
# One stack action at a time on this machine, whoever asked for it.
LOCK = os.path.join(paths.RUNTIME_ROOT, "stack.lock")
# Temporal from cold, its database first, answers within this long; a started worker polls within
# the other, or has exited — as it does at once when it cannot reach Temporal.
TEMPORAL_READY = 180
WORKER_READY = 90
# How long each script action may take: a first start pulls Temporal's images.
SCRIPT_SECONDS = {"start": 900, "stop": 90, "status": 60, "sweep": 120}


# WSL runs a Windows program with the token of whatever started WSL, and the Windows worker and its
# agents never run as an administrator: from an elevated side `workers.ps1` hands the start to the desktop's
# shell, which starts it as the user, and only with no shell to hand it to refuses it, saying so.
ELEVATED = ("Windows programs started from here run elevated, because WSL was started by an elevated "
            "process, and no desktop shell is there to start the Windows worker as you: start it from a "
            "normal terminal")


class Busy(runs.Refusal):
    """Another start, stop or restart of the stack is running; this one did nothing."""


def own(policy):
    """Whether `policy` is the checkout's own, the deployment's: its stack also manages Temporal and the
    Windows worker."""
    return policy.get("_policy_path") == P.origin(P.POLICY_FILE)


def managed(policy):
    """The components this policy's stack starts and stops."""
    return COMPONENTS if own(policy) else ("wsl",)


def worker_name(policy, target):
    """What a target host's worker of this policy is called on this machine — its pid file and log in
    the runtime root, and its systemd scope: one per policy and host."""
    return "worker-%s-%s" % (target, re.sub(r"[^A-Za-z0-9._-]", "-", policy["targets"][target]["host"]))


def pid_file(policy, target):
    """Where a worker records its process id while it runs; the lifecycle scripts read it there."""
    return os.path.join(paths.RUNTIME_ROOT, worker_name(policy, target) + ".pid")


def worker_queues(policy, target):
    """The queues a host's worker polls: its target's own, and the WSL one its policy's workflows' too."""
    own_queue = [(P.queue(policy, target), TaskQueueType.TASK_QUEUE_TYPE_ACTIVITY)]
    if target == runs.WORKFLOW_HOST:
        return [(P.workflow_queue(policy), TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW)] + own_queue
    return own_queue


def queues(policy):
    """Every queue the stack serves, and the kind of task on it."""
    return [pair for target in P.TARGETS for pair in worker_queues(policy, target)]


def mechanics(policy, component, action, *more):
    """One component's action through its host's script: (whether it did it, what it said)."""
    argv = (["bash", SCRIPT, component, action] + ([] if component == "temporal" else [worker_name(policy, component)])
            + [str(each) for each in more])
    env = dict(os.environ)
    env.pop("ORCH_POLICY", None)
    if not own(policy):
        origin = policy["_policy_path"]
        env["ORCH_POLICY"] = origin if os.path.isabs(origin) else os.path.join(paths.REPO, *origin.split("/"))
    try:
        done = subprocess.run(argv, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                              timeout=SCRIPT_SECONDS[action])
    except subprocess.TimeoutExpired:
        return False, "%s %s did not finish within %d s" % (component, action, SCRIPT_SECONDS[action])
    return done.returncode == 0, (done.stdout + done.stderr).strip()


def _process(said):
    """A script's word on a worker: its pid while it runs, None when it does not."""
    found = re.search(r"^running (\d+)$", said, re.MULTILINE)
    return int(found.group(1)) if found else None


def _elevated(said):
    """Whether the script said a worker started from here would run elevated, and so is refused."""
    return bool(re.search(r"^elevated$", said, re.MULTILINE))


def _serving(found, pid, since):
    """Whether one of the pollers `found` polled since `since` as process `pid` — a worker names itself
    `<pid>@<host>` — or, for a process this stack cannot know (`pid` None), as any worker."""
    return any(poller["polled"] >= since and (pid is None or poller["identity"].split("@")[0] == str(pid))
               for poller in found)


async def status(policy, client=None, error=None):
    """The stack's reading. `client` None: Temporal cannot be reached, and `error` says why.

    Temporal is up while it answers. A worker this stack manages is up while its process runs and
    polls every queue of its own, starting while it runs and does not yet, down when it does not run,
    and running — no more is known — while Temporal cannot be asked. One it does not manage is up
    while a worker polls its queues. A host is up only while its worker is. Reading it changes nothing.
    """
    parts = managed(policy)
    pollers = None
    if client is not None:
        try:
            pollers = {name: await runs.pollers(client, name, kind) for name, kind in queues(policy)}
        except RPCError as exc:                     # it stopped answering between two calls
            error = "Temporal did not answer: %s" % exc
    asked = [target for target in P.TARGETS if target in parts]
    if pollers is None and "temporal" in parts:
        asked.append("temporal")
    said = dict(zip(asked, await asyncio.gather(
        *(asyncio.to_thread(mechanics, policy, part, "status") for part in asked))))
    since = datetime.datetime.now(datetime.timezone.utc) - runs.POLLING
    components = [{"name": "temporal", "managed": "temporal" in parts, "startable": "temporal" in parts,
                   "state": "down" if pollers is None else "up", "pid": None, "detail": error or ""}]
    if "temporal" in said:
        components[0]["detail"] += " — its containers: %s" % said["temporal"][1]
    rows = []
    for target in P.TARGETS:
        mine = target in parts
        # A read that failed says nothing of the process: never "down", which offers to start another.
        unread = mine and not said[target][0]
        pid = _process(said[target][1]) if mine else None
        polls = None if pollers is None else all(
            _serving(pollers[name], pid if mine else None, since) for name, _ in worker_queues(policy, target))
        startable = mine and not unread and not _elevated(said[target][1])
        if unread:
            state = "unknown"
        elif mine and pid is None:
            state = "down"
        elif polls is None:
            state = "running" if mine else "unknown"
        else:
            state = "up" if polls else ("starting" if mine else "down")
        detail = ("its process could not be read: %s" % said[target][1] if unread else
                  "polls " + ", ".join(name for name, _ in worker_queues(policy, target)) if state == "up" else "")
        if mine and not unread and not startable:
            detail = "; ".join(filter(None, [detail, ELEVATED]))
        components.append({"name": target, "managed": mine, "startable": startable, "state": state, "pid": pid,
                           "detail": detail})
        rows += [{"queue": name, "host": target,
                  "polled": None if pollers is None else _serving(pollers[name], None, since)}
                 for name, _ in worker_queues(policy, target)]
    return {"temporal": components[0]["state"], "error": error, "components": components, "queues": rows,
            "hosts": {part["name"]: {"up": "up", "down": "down", "starting": "down"}.get(part["state"], "unknown")
                      for part in components[1:]}}


async def read(policy):
    """The reading through a connection of its own, for a caller that holds none."""
    try:
        client = await runs.connect()
    except runs.Refusal as exc:
        return await status(policy, None, str(exc))
    return await status(policy, client)


@contextlib.contextmanager
def _exclusive():
    """Hold the stack for one action. The lock is the kernel's, so an owner that dies lets it go."""
    import fcntl                                    # on WSL, where every stack action runs
    os.makedirs(paths.RUNTIME_ROOT, exist_ok=True)
    with open(LOCK, "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Busy("another start, stop or restart of the stack is running; try again once it has finished")
        yield


def _chosen(policy, component):
    parts = managed(policy)
    if component is None:
        return parts
    if component not in COMPONENTS:
        raise runs.Refusal("no component %r: the stack's are %s" % (component, ", ".join(COMPONENTS)))
    if component not in parts:
        raise runs.Refusal("this stack does not manage %s: %s" % (
            component, "Temporal is the deployment's" if component == "temporal"
            else "the Windows host runs only its own copy of a policy"))
    return (component,)


async def _answering(policy, seconds):
    """Whether Temporal answers for this stack — its workflow queue can be read — within `seconds`."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            client = await runs.connect()
            await runs.pollers(client, P.workflow_queue(policy), TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW)
            return True
        except (runs.Refusal, RPCError):            # not answering yet
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(2)


async def _polling(policy, target, since):
    """The worker's pid once the process its pid file names polls every queue of its own since
    `since`; None if it does not within WORKER_READY."""
    deadline = time.monotonic() + WORKER_READY
    client = None
    while time.monotonic() < deadline:
        pid = _process((await asyncio.to_thread(mechanics, policy, target, "status"))[1])
        if pid is not None:
            try:
                client = client or await runs.connect()
                found = [await runs.pollers(client, name, kind) for name, kind in worker_queues(policy, target)]
                if all(_serving(each, pid, since) for each in found):
                    return pid
            except (runs.Refusal, RPCError):        # Temporal busy or restarting: look again
                client = None
        await asyncio.sleep(2)
    return None


def _log_tail(policy, target, lines=6):
    try:
        with open(os.path.join(paths.RUNTIME_ROOT, worker_name(policy, target) + ".log"), encoding="utf-8",
                  errors="replace") as fh:
            return " | ".join(line.strip() for line in fh.readlines()[-lines:] if line.strip()) or "empty"
    except OSError:
        return "none"


def _result(component, ok, said):
    return {"component": component, "ok": ok, "said": said}


def _start_one(policy, component):
    if component == "temporal":
        ok, said = mechanics(policy, "temporal", "start")
        if not ok:
            return _result(component, False, said)
        if not asyncio.run(_answering(policy, TEMPORAL_READY)):
            return _result(component, False, "its containers started, but it did not answer within %d s"
                           % TEMPORAL_READY)
        return _result(component, True, "started; it answers")
    if not asyncio.run(_answering(policy, 0)):
        return _result(component, False, "not started: Temporal does not answer, and a worker exits without it")
    since = datetime.datetime.now(datetime.timezone.utc)
    ok, said = mechanics(policy, component, "start")
    if not ok:
        return _result(component, False, said)
    already = _process(said)
    pid = asyncio.run(_polling(policy, component, since - runs.POLLING if already else since))
    if pid is None:
        return _result(component, False, "it did not poll within %d s; its log ends: %s"
                       % (WORKER_READY, _log_tail(policy, component)))
    return _result(component, True, "%s; pid %d polls %s" % (
        "already running" if already else "started", pid,
        ", ".join(name for name, _ in worker_queues(policy, component))))


def _stop_one(policy, component):
    if component == "temporal":
        ok, said = mechanics(policy, "temporal", "stop")
        if not ok:
            return _result(component, False, said)
        if asyncio.run(_answering(policy, 0)):
            return _result(component, False, "its containers stopped, but it still answers")
        return _result(component, True, "stopped; its data stays on its volume")
    looked, said = mechanics(policy, component, "status")
    before = _process(said) if looked else None
    ok, said = mechanics(policy, component, "stop")
    if not ok:
        return _result(component, False, said)
    # Proven gone before anything it left is taken: the script's own word, then a second look.
    looked, said = mechanics(policy, component, "status")
    if not looked:
        return _result(component, False, "stopped, but whether it is gone could not be read: %s" % said)
    pid = _process(said)
    if pid is not None:
        return _result(component, False, "still running, pid %d" % pid)
    # A stage it was running made settings holding the trace store's key, which only that stage's
    # own end removes; they go now, not when a worker next starts on this host — its own by its pid,
    # which may already be another process's.
    swept, said = mechanics(policy, component, "sweep", *([before] if before else []))
    if not swept:
        return _result(component, False, "stopped, but what its stages left was not swept: %s" % said)
    removed = len(re.findall(r"^removed ", said, re.MULTILINE))
    return _result(component, True, "stopped" + ("; removed the settings %d of its stages left" % removed
                                                  if removed else ""))


def _each(parts, act, progress):
    results = []
    for part in parts:
        results.append(act(part))
        if progress:
            progress(results[-1])
    return results


def start(policy, component=None, progress=None):
    """Start the stack, or one component: Temporal first, a worker only while Temporal answers. Each
    is proven up — Temporal answering, a worker polling as the process its pid file names — or said
    not to be. Returns one result per component, `component`, `ok` and `said`, each passed to
    `progress` as it comes."""
    chosen = _chosen(policy, component)
    with _exclusive():
        return _each([part for part in COMPONENTS if part in chosen], lambda part: _start_one(policy, part),
                     progress)


def stop(policy, component=None, progress=None):
    """Stop the stack, or one component, the workers before Temporal. A worker is stopped only once its
    process is proven gone; then what its stages left on that host is swept."""
    chosen = _chosen(policy, component)
    with _exclusive():
        return _each([part for part in reversed(COMPONENTS) if part in chosen],
                     lambda part: _stop_one(policy, part), progress)


def restart(policy, component=None, progress=None):
    """Stop, then start: the stack, or one component. A Windows worker this side could not start again
    is left as it is, never stopped only to stay down."""
    chosen = _chosen(policy, component)
    with _exclusive():
        held = [part for part in chosen if part == "windows" and _elevated(mechanics(policy, part, "status")[1])]
        kept = _each(held, lambda part: _result(part, False, "left as it is: %s" % ELEVATED), progress)
        chosen = [part for part in chosen if part not in held]
        return (kept + _each([part for part in reversed(COMPONENTS) if part in chosen],
                             lambda part: _stop_one(policy, part), progress)
                + _each([part for part in COMPONENTS if part in chosen],
                        lambda part: _start_one(policy, part), progress))


ACTIONS = {"start": start, "stop": stop, "restart": restart}
