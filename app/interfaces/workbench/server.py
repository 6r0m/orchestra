"""The operator's workbench: one localhost page over every run and the stack they run on.

    python -m app.interfaces.workbench.server

It serves `static/` beside it and a small JSON API over `app.application` on `http://127.0.0.1:<workbench_port>`:
the stack's reading and its start, stop and restart; the runs and what each is doing now, a run's
status and timeline, its change; starting a run, answering its stop, stopping or force-terminating
it, and removing what a closed run kept. The page opens each run's agent terminals directly on the
worker of the run's host (`app.agents.terminal`). It holds no state of its own: stopping it changes
no run and stops no part of the stack. WSL's systemd runs it (`orchestra-workbench.service`); it
never manages its own process.

Every API request carries the page's token in `X-Workbench-Token`; a request whose Host is not
this server's loopback address, or whose Origin is another site, is refused, so neither another
page in the browser nor a DNS-rebound name can use it.
"""
import asyncio
import base64
import concurrent.futures
import datetime
import json
import os
import re
import sys
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.application import client as runs
from app.application import stack
from app.foundation import policy as P
from app.workspace import repos
from app.agents import terminal

# The page is this server's own, served from beside it.
PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
TEMPORAL_UI = os.environ.get("TEMPORAL_UI", "http://localhost:8080")
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8"),
          "/vendor/xterm.js": ("vendor/xterm/xterm.js", "text/javascript; charset=utf-8"),
          "/vendor/xterm.css": ("vendor/xterm/xterm.css", "text/css; charset=utf-8")}
RUN_ID = re.compile(r"^[\w-]{1,64}$")
MAX_BODY = 1 << 20
ANSWER_KEYS = {"stop", "action", "text", "confirm"}
# The page reads the stack three ways every few seconds, and a Windows worker's process takes about
# half a second to read: every request shares one reading at most this old, and a stack action drops it.
READING_SECONDS = 3
# A run's status is a query its own workflow worker answers; while that worker is down the page still
# shows the run, from its listing, after waiting this long for the answer.
STATUS_SECONDS = datetime.timedelta(seconds=5)


class Loop:
    """One event loop in a thread of its own, holding the Temporal client every request uses."""

    def __init__(self, connect=runs.connect):
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, name="workbench-temporal", daemon=True).start()
        self._connect, self._client = connect, None

    def call(self, work, timeout=120):
        async def attempt():
            if self._client is None:
                self._client = await self._connect()
            return await work(self._client)
        done = asyncio.run_coroutine_threadsafe(attempt(), self.loop)
        try:
            return done.result(timeout)
        except concurrent.futures.TimeoutError:
            # Its answer is no longer awaited, so the work is cancelled rather than left to finish unseen; a
            # call it already sent — a Stop, an answer — may still take effect in Temporal.
            done.cancel()
            raise


def trace_links():
    """A function from a trace id to its Langfuse page, when this machine has the keys; else None."""
    try:
        from app.observability import telemetry
        langfuse = telemetry.resolve()
    except Exception:                               # noqa: BLE001 - a link is optional
        return None
    if langfuse is None:
        return None
    return lambda trace_id: telemetry.trace_url(langfuse, trace_id)


def make_handler(call, policy, token, links=None):
    port = policy["workbench_port"]
    # What a run that Temporal no longer runs said the last time it was read: it says nothing else now,
    # and the list is read again every few seconds.
    finished = {}
    reading = {"at": None, "value": None}
    reading_lock = threading.Lock()

    def stack_reading():
        """The stack's reading, shared by the requests of a few seconds."""
        with reading_lock:
            if reading["at"] is None or time.monotonic() - reading["at"] > READING_SECONDS:
                try:
                    reading["value"] = call(lambda client: stack.status(policy, client))
                except runs.Refusal as exc:
                    # No Temporal to ask; the processes are still read.
                    reading["value"] = asyncio.run(stack.status(policy, None, str(exc)))
                reading["at"] = time.monotonic()
            return reading["value"]

    hosts = {"127.0.0.1:%d" % port, "localhost:%d" % port}
    origins = terminal.allowed_origins(port)
    config = {"token": token, "temporal_ui": TEMPORAL_UI,
              "terminal_ports": {name: target["terminal_port"] for name, target in policy["targets"].items()}}

    class Handler(BaseHTTPRequestHandler):
        server_version = "workbench"

        def log_message(self, fmt, *args):
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

        def _send(self, status, body, kind="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; connect-src 'self' ws://127.0.0.1:* ws://localhost:*; "
                             "style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def _refused(self, api):
            if self.headers.get("Host") not in hosts:
                return "unknown host"
            origin = self.headers.get("Origin")
            if origin is not None and origin not in origins:
                return "origin not allowed"
            if api and self.headers.get("X-Workbench-Token") != token:
                return "token required"
            return None

        def _error(self, exc):
            if isinstance(exc, (runs.NotWaiting, stack.Busy)):
                return self._send(HTTPStatus.CONFLICT, {"error": str(exc)})
            if isinstance(exc, (runs.Refusal, repos.Refused, P.InvalidPolicy)):
                return self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            self.log_error("request failed: %r", exc)
            return self._send(HTTPStatus.BAD_GATEWAY, {"error": "%s: %s" % (type(exc).__name__, exc)})

        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            api = path.startswith("/api/")
            refusal = self._refused(api)
            if refusal:
                return self._send(HTTPStatus.FORBIDDEN, {"error": refusal})
            if not api:
                if path not in STATIC:
                    return self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
                name, kind = STATIC[path]
                with open(os.path.join(PAGE, name), "rb") as fh:
                    data = fh.read()
                if name == "index.html":
                    data = data.replace(b"{{CONFIG}}", json.dumps(config).replace("<", "\\u003c").encode("utf-8"))
                return self._send(HTTPStatus.OK, data, kind)
            parts = [part for part in path.split("/") if part][1:]
            try:
                if parts == ["health"]:
                    return self._send(HTTPStatus.OK, stack_reading())
                if parts == ["runs"]:
                    query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                    return self._send(HTTPStatus.OK, self._run_page((query.get("cursor") or [None])[0]))
                if parts == ["worktrees"]:
                    query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                    return self._send(HTTPStatus.OK, self._worktrees((query.get("repo") or [None])[0]))
                if parts == ["repos"]:
                    return self._send(HTTPStatus.OK, [{"id": name, "target": entry.get("target") or (
                        "windows" if repos.windows_path(entry["path"]) else "wsl")}
                        for name, entry in repos.load().items()])
                if len(parts) >= 2 and parts[0] == "runs" and RUN_ID.match(parts[1]):
                    run_id = parts[1]
                    if len(parts) == 2:
                        return self._send(*self._run(run_id))
                    if parts[2:] == ["diff"]:
                        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                        asked = (query.get("offset") or ["0"])[0]
                        if not asked.isdigit():
                            return self._send(HTTPStatus.BAD_REQUEST, {"error": "offset must be a whole number"})
                        return self._send(HTTPStatus.OK,
                                          call(lambda client: runs.review_diff(client, run_id, int(asked))))
                return self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
            except Exception as exc:                # noqa: BLE001 - every failure is answered
                return self._error(exc)

        def do_POST(self):
            path = urllib.parse.urlsplit(self.path).path
            refusal = self._refused(True)
            if refusal:
                return self._send(HTTPStatus.FORBIDDEN, {"error": refusal})
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                return self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "too large"})
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("a JSON object is expected")
            except ValueError as exc:
                return self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            parts = [part for part in path.split("/") if part][1:]
            try:
                if parts == ["runs"]:
                    task = (body.get("task") or "").strip()
                    if not task:
                        return self._send(HTTPStatus.BAD_REQUEST, {"error": "a task is required"})
                    handle = call(lambda client: runs.start(client, task, repo=body.get("repo") or None,
                                                            auto_proceed=bool(body.get("auto_proceed"))))
                    return self._send(HTTPStatus.OK, {"run_id": handle.id})
                if len(parts) == 3 and parts[0] == "runs" and RUN_ID.match(parts[1]) and parts[2] == "answer":
                    answer = {key: value for key, value in body.items() if key in ANSWER_KEYS}
                    if not answer.get("stop"):
                        return self._send(HTTPStatus.BAD_REQUEST, {"error": "the answer names the stop it is for"})
                    stop = call(lambda client: runs.answer(client, parts[1], answer))
                    return self._send(HTTPStatus.OK, {"answered": stop["id"], "action": answer.get("action")})
                if len(parts) == 3 and parts[0] == "runs" and RUN_ID.match(parts[1]) and parts[2] == "stop":
                    call(lambda client: runs.stop(client, parts[1]))
                    return self._send(HTTPStatus.OK, {"stopping": parts[1]})
                if len(parts) == 3 and parts[0] == "runs" and RUN_ID.match(parts[1]) and parts[2] == "terminate":
                    if body.get("confirm") is not True:
                        return self._send(HTTPStatus.BAD_REQUEST, {"error": "force terminate ends the run with no "
                                                                            "cleanup, so it must be confirmed"})
                    call(lambda client: runs.force_terminate(client, parts[1], "force terminated from the Workbench"))
                    return self._send(HTTPStatus.OK, {"terminated": parts[1]})
                if len(parts) == 3 and parts[0] == "runs" and RUN_ID.match(parts[1]) and parts[2] == "remove":
                    if body.get("confirm") is not True:
                        return self._send(HTTPStatus.BAD_REQUEST, {"error": "removing what a run kept deletes its "
                                                                            "unmerged work, so it must be confirmed"})
                    call(lambda client: runs.remove_worktree(client, parts[1]),
                         timeout=runs.REMOVAL.total_seconds() + 60)
                    return self._send(HTTPStatus.OK, {"removed": parts[1]})
                if parts == ["stack"]:
                    action = body.get("action")
                    if action not in stack.ACTIONS:
                        return self._send(HTTPStatus.BAD_REQUEST, {"error": "the action is one of: %s"
                                                                            % ", ".join(stack.ACTIONS)})
                    try:
                        results = stack.ACTIONS[action](policy, body.get("component") or None)
                    finally:
                        with reading_lock:
                            reading["at"] = None
                    return self._send(HTTPStatus.OK, {"results": results, "health": stack_reading()})
                return self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
            except runs.NotAccepted as exc:
                return self._send(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
            except Exception as exc:                # noqa: BLE001 - every failure is answered
                return self._error(exc)

        def _run_page(self, cursor):
            """One page of runs with each one's state, and the cursor for the page of older runs."""
            try:
                # Strictly, so a cursor this page did not hand out is refused here rather than
                # reaching Temporal, which answers a bad page token with an opaque retry error.
                token = base64.urlsafe_b64decode(cursor.encode("ascii")) if cursor else None
                if cursor and base64.urlsafe_b64encode(token).decode() != cursor:
                    raise ValueError(cursor)
            except Exception:                       # noqa: BLE001 - a cursor we did not write
                raise runs.Refusal("that is not a cursor this page handed out")

            health = stack_reading()

            async def read(client):
                listed, older = await runs.runs(client, cursor=token)

                async def one(run):
                    if run["run_id"] in finished:
                        return finished[run["run_id"]]   # a finished run's state never changes again
                    try:
                        shown = runs.view(run, await runs.status(client, run["run_id"], STATUS_SECONDS), health)
                    except Exception:               # noqa: BLE001 - a run whose status fails still lists
                        return runs.view(run, None, health)
                    if run["execution"] != "RUNNING":
                        finished[run["run_id"]] = shown
                    return shown
                return (list(await asyncio.gather(*(one(run) for run in listed))), older)

            shown, older = call(read)
            return {"runs": shown, "cursor": base64.urlsafe_b64encode(older).decode() if older else None}

        def _worktrees(self, repo):
            """Every worktree of one repository and its merge state, read by that repository's own host,
            with the run each belongs to — its branch is the run's id — and whether that run has closed,
            so that what it kept can be removed."""
            async def read(client):
                selected, view = await runs.worktrees_of(client, repo)
                rows = []
                for row in view["rows"]:
                    listed = (await runs.execution(client, row["branch"])
                              if row["branch"] and RUN_ID.match(row["branch"]) else None)
                    kept = False
                    if listed and listed["execution"] != "RUNNING":
                        try:
                            kept = runs.not_kept(listed, await runs.status(client, row["branch"], STATUS_SECONDS),
                                                 await runs.removal(client, row["branch"])) is None
                        except Exception:           # noqa: BLE001 - its worker down: removable is not known
                            kept = False
                    rows.append(dict(row, run=listed and listed["execution"], removable=kept))
                return selected, view, rows
            selected, view, rows = call(read)
            return {"repo": selected["id"], "base_branch": view["base_branch"], "rows": rows}

        def _run(self, run_id):
            health = stack_reading()

            async def read(client):
                execution = await runs.execution(client, run_id)
                try:
                    return await runs.status(client, run_id, STATUS_SECONDS), execution, None
                except Exception as exc:            # noqa: BLE001 - its workflow worker down, or not answering
                    return None, execution, "its status cannot be read now: %s" % exc
            status, execution, unreadable = call(read)
            if status is None and (execution is None or unreadable is None):
                return HTTPStatus.NOT_FOUND, {"error": "no run %r" % run_id}
            removal = None
            if execution and execution["execution"] != "RUNNING" and not unreadable:
                removal = call(lambda client: runs.removal(client, run_id))
            # A run whose worker is down is still shown, from its listing: what blocks it is the point.
            status = status or {"state": {}, "stop": None, "lines": [], "timeline": [], "queue": None}
            status["unreadable"] = unreadable
            status["view"] = runs.view(execution or {"run_id": run_id, "execution": None, "started": None,
                                                     "closed": None, "task_queue": None},
                                       None if unreadable else status, health)
            status["view"]["kept"] = not unreadable and runs.not_kept(execution, status, removal) is None
            trace_id = status["state"].get("trace_id")
            status["links"] = {"temporal": "%s/namespaces/%s/workflows/%s" % (TEMPORAL_UI, runs.NAMESPACE, run_id),
                               "trace": links(trace_id) if links and trace_id else None}
            return HTTPStatus.OK, status

    return Handler


def serve(policy, call, links=None, host="127.0.0.1"):
    server = ThreadingHTTPServer((host, policy["workbench_port"]),
                                 make_handler(call, policy, terminal.token(), links))
    server.daemon_threads = True
    return server


def main():
    policy = P.load()
    server = serve(policy, Loop().call, trace_links())
    print("workbench on http://127.0.0.1:%d" % policy["workbench_port"], flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
