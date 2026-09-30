"""Live agent terminals on this host, and a role turn run in one.

A run's role has one terminal on its target host, from its first turn until the run is
merged, discarded or otherwise ended. The terminal is this worker's: it records every byte the
agent draws to `tmp/orchestration/<run-id>/terminals/<role>.out`, and serves the record and
the live bytes on the worker's WebSocket, `ws://127.0.0.1:<terminal_port>/<run-id>/<role>`,
taking keystrokes back. Whoever holds the page can watch, press Esc and type at any time.

A controller turn replaces the agent process under the terminal: the previous one ends,
and the agent's CLI starts again in the worktree with the role's session resumed by exact id
and the prompt as its argument. That process runs under `ptyhost.py`, launched through
`launch.py`'s tree, so the turn's own failure ends it with everything it started and the
worker's death ends every terminal's agent. The turn ends on the agent's own completion of
that prompt, which its hooks write through `turn_hook.py` into the turn's own events file and
its kind's adapter reads there (`app.agents.adapters`): completions of anything the operator
typed, of a background task finishing later, or of a turn of the agent's own never end it;
neither does an interrupt, which completes nothing. A successful turn leaves the agent
running, live.
"""
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from http import HTTPStatus

from app.agents import adapters
from app.agents import launch
from app.foundation import paths
from app.foundation import policy as P
from app.foundation import stages

# Both are launched by path, by us and by the vendors' own hooks, and neither imports
# anything of ours: they are found beside this module, not through the checkout root.
HERE = os.path.dirname(os.path.abspath(__file__))
PTYHOST = os.path.join(HERE, "ptyhost.py")
TURN_HOOK = os.path.join(HERE, "turn_hook.py")
# The page's token, shared by the workbench and both workers through the one checkout.
TOKEN_FILE = os.path.join(paths.SECRETS, "workbench.token")
COLS, ROWS = 160, 48
TICK_SECONDS = 1.0
# The page's subprotocol. The token is offered beside it, in the handshake's own header, so it
# never appears in a URL the browser prints to its console or a proxy writes to a log.
PROTOCOL = "workbench.v1"
TOKEN_PROTOCOL = "token."
# A turn tried again in a fresh session, its first one lost, keeps its files under its name and this.
RETRIED = "-rehydrated"
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][0-9A-B]|\x1b[=>]")


def run_dir(run_id):
    return os.path.join(paths.RUNTIME_ROOT, run_id)


def record_path(run_id, role):
    return os.path.join(run_dir(run_id), "terminals", "%s.out" % role)


def turn_name(stage, episode, attempt):
    """The name a turn's files take in its run's logs: its stage, its episode, and its attempt — the round
    it is, from 1."""
    return "%s-e%d-%d" % (stage, episode, attempt)


def turn_files(rdir, name):
    """The files a turn named `name` leaves in the logs of the run at `rdir`, by what each holds: the prompt
    it was given, what it answered, its errors and its events."""
    logs = os.path.join(rdir, "logs")
    return {ext: os.path.join(logs, "%s.%s" % (name, ext)) for ext in ("prompt", "out", "err", "events")}


def token():
    """The workbench's token, made once: random, never logged, never in the repository's history."""
    try:
        with open(TOKEN_FILE, encoding="utf-8") as fh:
            value = fh.read().strip()
        if value:
            return value
    except FileNotFoundError:
        pass
    import secrets
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    try:
        fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # Another process made it first: that one is the token.
        return token()
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(secrets.token_urlsafe(32))
    return token()


def allowed_origins(workbench_port):
    return {"http://127.0.0.1:%d" % workbench_port, "http://localhost:%d" % workbench_port}


def plain(data):
    """What a terminal's bytes say, without the escape sequences that draw them."""
    return _ANSI.sub("", data.decode("utf-8", "replace")).replace("\r", "")


class _Agent:
    """One agent process under a terminal, in its own contained tree."""

    def __init__(self, terminal, argv, cwd, env):
        self.tree = launch._Tree()
        self.proc = self.tree.start([sys.executable, PTYHOST, str(COLS), str(ROWS), "--"] + list(argv), cwd,
                                    subprocess.PIPE, subprocess.PIPE, subprocess.DEVNULL, env)
        self.output = bytearray()
        self.lock = threading.Lock()
        self.ended = False
        self.pump = threading.Thread(target=self._pump, args=(terminal,), daemon=True)
        self.pump.start()

    def _pump(self, terminal):
        while True:
            data = self.proc.stdout.read1(65536) if hasattr(self.proc.stdout, "read1") else self.proc.stdout.read(4096)
            if not data:
                break
            self.output += data
            terminal.emit(data)
        self.proc.stdout.close()
        self.proc.wait()
        # The agent is done; anything it left behind goes with it, and the terminal stops being live.
        terminal.agent_gone(self)

    def write(self, data):
        try:
            self.proc.stdin.write(data)
            self.proc.stdin.flush()
        except (OSError, ValueError):
            pass

    def returncode(self):
        return self.proc.poll()

    def end(self):
        with self.lock:
            if self.ended:
                return
            self.ended = True
        try:
            if self.proc.poll() is None:
                self.tree.stop(self.proc)
            self.tree.kill()
        finally:
            self.tree.close()
            try:
                self.proc.stdin.close()
            except OSError:
                pass


class Terminal:
    """A role's terminal: its record, its viewers, and the agent process currently under it."""

    def __init__(self, run_id, role):
        self.run_id, self.role = run_id, role
        self.path = record_path(run_id, role)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.lock = threading.Lock()
        self.viewers = []
        self.agent = None
        self.record = None

    def emit(self, data):
        with self.lock:
            if self.record is None:
                self.record = open(self.path, "ab")
            self.record.write(data)
            self.record.flush()
            viewers = list(self.viewers)
        for deliver in viewers:
            deliver(data)

    def announce(self):
        """Tell every viewer whether an agent is under this terminal now, so none is told it is live when it is not."""
        state = json.dumps({"live": self.live()})
        with self.lock:
            viewers = list(self.viewers)
        for deliver in viewers:
            deliver(state)

    def attach(self, deliver):
        """The record so far, and every later byte to `deliver`, with nothing lost or repeated between them."""
        with self.lock:
            try:
                with open(self.path, "rb") as fh:
                    backlog = fh.read()
            except FileNotFoundError:
                backlog = b""
            self.viewers.append(deliver)
        return backlog

    def detach(self, deliver):
        with self.lock:
            if deliver in self.viewers:
                self.viewers.remove(deliver)

    def type(self, data):
        agent = self.agent
        if agent is not None:
            agent.write(data)

    def start(self, argv, cwd, env):
        self.end_agent()
        self.agent = _Agent(self, argv, cwd, env)
        self.announce()
        return self.agent

    def end_agent(self):
        """End the agent under this terminal; an end its tree cannot prove is raised, after the terminal is
        told it has no agent."""
        agent, self.agent = self.agent, None
        if agent is not None:
            try:
                agent.end()
            finally:
                agent.pump.join(timeout=launch.GRACE_SECONDS)
                self.announce()

    def agent_gone(self, agent):
        """That agent's process ended by itself: it leaves the terminal, which stops being live."""
        if self.agent is agent:
            self.agent = None
        try:
            agent.end()
        finally:
            self.announce()

    def close(self):
        try:
            self.end_agent()
        finally:
            with self.lock:
                if self.record is not None:
                    self.record.close()
                    self.record = None
                viewers, self.viewers = list(self.viewers), []
            # Each viewer's connection closes, so a page attaches again to whatever terminal comes next.
            for deliver in viewers:
                deliver(None)

    def live(self):
        agent = self.agent
        return agent is not None and agent.returncode() is None


_terminals = {}
_terminals_lock = threading.Lock()


def get(run_id, role):
    with _terminals_lock:
        return _terminals.get((run_id, role))


def open_terminal(run_id, role):
    with _terminals_lock:
        terminal = _terminals.get((run_id, role))
        if terminal is None:
            terminal = _terminals[(run_id, role)] = Terminal(run_id, role)
        return terminal


def close_run(run_id):
    """End every terminal of a run on this host; their records stay. Each closes even when another's agent
    could not be proved ended, and that failure is raised once all have: what comes next — a merge, a
    discard — must not go on as though the worktree were free."""
    with _terminals_lock:
        closing = [_terminals.pop(key) for key in list(_terminals) if key[0] == run_id]
    failed = None
    for terminal in closing:
        try:
            terminal.close()
        except Exception as exc:                    # noqa: BLE001 - raised below, once every terminal is closed
            failed = failed or exc
    if failed is not None:
        raise failed


def end_agent(run_id, role):
    """End a role's agent on this host, keeping its terminal and record: its turn failed."""
    terminal = get(run_id, role)
    if terminal is not None:
        terminal.end_agent()


# ---- a role turn -------------------------------------------------------------------------

def sink(events, label, source):
    """The program an agent calls with each event of its turn: `turn_hook.py`, writing into the turn's own
    events file. `source` is where the agent puts the payload — `stdin`, or `argument`, its last."""
    return [sys.executable.replace("\\", "/"), TURN_HOOK.replace("\\", "/"), events.replace("\\", "/"), label,
            source]


def _events(path):
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except FileNotFoundError:
        return []
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    return events


def _activity_tick(name):
    from temporalio import activity
    from temporalio.exceptions import CancelledError
    if not activity.in_activity():
        return
    activity.heartbeat(name)
    if activity.is_cancelled():
        raise CancelledError("role-run %s cancelled" % name)


def run_turn(worktree, argv, rdir, name, prompt, timeout, env, on_tick=None, *, kind):
    """The execution seam: one role turn in the role's live terminal; returns (exit status, output).

    The turn is `kind`'s: its adapter wires the turn's end into the turn's own events file, reads the turn's
    completion from it, and says what the finished turn leaves for the role-run to read. Logs under the
    run's directory keep the prompt, that output, the turn's events, and — as its error text — what the
    terminal showed during the turn.
    """
    # The run already decided which agent this turn is; re-deriving it from the command would be a second
    # authority, and a kind this host cannot load is refused before the turn leaves anything behind.
    try:
        adapter = adapters.load(kind)
    except adapters.Refused as exc:
        raise launch.ExecutorError(str(exc)) from exc

    paths = turn_files(rdir, name)
    os.makedirs(os.path.dirname(paths["prompt"]), exist_ok=True)
    with open(paths["prompt"], "w", encoding="utf-8", newline="") as fh:
        fh.write(prompt)
    executable = shutil.which(argv[0])
    if not executable:
        raise launch.ExecutorError("%s is not installed on this host" % argv[0])
    if os.path.exists(paths["events"]):
        os.remove(paths["events"])
    argv = [executable] + list(argv[1:])
    session = adapter.session_in(argv)
    argv = adapter.wire(argv, paths["events"], lambda label, source: sink(paths["events"], label, source))
    # Options such as `--add-dir` take several values; `--` keeps the prompt from becoming one of them.
    argv += ["--", prompt]

    run_id = os.path.basename(os.path.normpath(rdir))
    role = stages.STAGE_ROLE[name.split("-")[0]]
    terminal = open_terminal(run_id, role)
    tick = on_tick or (lambda: _activity_tick(name))
    agent = terminal.start(argv, worktree, env)

    def finish(rc, out):
        with open(paths["out"], "w", encoding="utf-8", newline="") as fh:
            fh.write(out)
        with open(paths["err"], "w", encoding="utf-8", newline="") as fh:
            fh.write(plain(bytes(agent.output)))
        if rc != 0:
            # A failed turn is a failed step: its agent does not stay behind.
            terminal.end_agent()
        return rc, out

    try:
        deadline = time.monotonic() + timeout
        while True:
            done = adapter.completion(_events(paths["events"]), prompt, session)
            if done is not None:
                ok, message, session = done
                return finish(0 if ok else 1, adapter.output(message, session))
            rc = agent.returncode()
            if rc is not None:
                agent.pump.join(timeout=launch.GRACE_SECONDS)
                if adapter.completion(_events(paths["events"]), prompt, session) is None:
                    return finish(rc or 1, "")
                continue
            tick()
            if time.monotonic() >= deadline:
                finish(1, "")
                raise launch.RoleTimeout("role-run did not finish within %ds" % timeout)
            time.sleep(TICK_SECONDS)
    except BaseException:
        terminal.end_agent()
        raise


# ---- the WebSocket ---------------------------------------------------------------------

def serve(port, workbench_port, host="127.0.0.1"):
    """Serve this host's terminals on `ws://127.0.0.1:<port>/<run-id>/<role>`, in a thread of its own.

    A connection needs the workbench page's origin and its token, offered as the subprotocol
    `token.<token>` beside `workbench.v1`: in the handshake's own header, never in the URL. It first
    receives whether an agent is under the terminal now and the terminal's record, then its live bytes,
    and is told again whenever an agent starts or ends; what it sends is typed into the terminal. A run
    with no terminal on this host — closed, or the worker restarted — is sent its record and closed.
    Returns once the socket listens; the server ends with this process.
    """
    from websockets.asyncio.server import serve as ws_serve
    ready, failure = threading.Event(), []
    origins = allowed_origins(workbench_port)
    expected = token()

    def check(connection, request):
        parsed = urllib.parse.urlsplit(request.path)
        if request.headers.get("Origin") not in origins:
            return connection.respond(HTTPStatus.FORBIDDEN, "origin not allowed\n")
        offered = [part.strip() for part in (request.headers.get("Sec-WebSocket-Protocol") or "").split(",")]
        if TOKEN_PROTOCOL + expected not in offered:
            return connection.respond(HTTPStatus.FORBIDDEN, "token required\n")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 2 or parts[1] not in P.ROLES or not re.fullmatch(r"[\w-]+", parts[0]):
            return connection.respond(HTTPStatus.NOT_FOUND, "no such terminal\n")
        return None

    async def handler(connection):
        parsed = urllib.parse.urlsplit(connection.request.path)
        run_id, role = [part for part in parsed.path.split("/") if part]
        terminal = get(run_id, role)
        if terminal is None:
            await connection.send(json.dumps({"live": False}))
            try:
                with open(record_path(run_id, role), "rb") as fh:
                    await connection.send(fh.read())
            except FileNotFoundError:
                pass
            return
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()

        def deliver(data):
            loop.call_soon_threadsafe(queue.put_nowait, data)

        backlog = terminal.attach(deliver)
        # Live is whether an agent is under the terminal now: between turns and after a failed step
        # the terminal is the run's, but what is typed into it would reach nobody.
        await connection.send(json.dumps({"live": terminal.live()}))
        if backlog:
            await connection.send(backlog)

        async def send():
            while True:
                data = await queue.get()
                if data is None:
                    await connection.close()
                    return
                await connection.send(data)

        sender = asyncio.create_task(send())
        try:
            async for message in connection:
                terminal.type(message.encode("utf-8") if isinstance(message, str) else message)
        finally:
            sender.cancel()
            terminal.detach(deliver)

    def main():
        async def run():
            try:
                server = await ws_serve(handler, host, port, process_request=check, max_size=2 ** 20,
                                        # Answer with the page's own subprotocol, never the token beside it.
                                        select_subprotocol=lambda connection, offered:
                                        PROTOCOL if PROTOCOL in offered else None)
            except OSError as exc:
                failure.append(exc)
                ready.set()
                return
            ready.set()
            await server.serve_forever()
        asyncio.run(run())

    threading.Thread(target=main, name="terminal-websocket", daemon=True).start()
    ready.wait()
    if failure:
        raise failure[0]
