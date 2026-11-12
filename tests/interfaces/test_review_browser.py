"""Real browser acceptance on disposable Git snapshots; no live stack, vendor or clipboard writes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from app.interfaces.workbench.server import PAGE, STATIC
from app.workspace import worktrees as W
from tests.workspace.test_worktrees import Repo, TARGET, git, write

EDGE = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe"


@unittest.skipUnless(sys.platform.startswith("win") and EDGE.is_file(), "the real browser acceptance runs on Windows")
class ReviewBrowser(Repo):
    def test_discarded_run_keeps_historical_exports_on_its_normal_page_after_cleanup(self):
        import temporal_env as E
        from fakes import FakeRepos, FakeWorktrees
        from app.application import client as runs
        from tests.interfaces.test_workbench import port, request, stack_as
        from tests.orchestration.test_stops import to_ready

        repo, root = self.repo, self.root

        class DiskSnapshots(FakeWorktrees):
            def create(self, _repo, base, _root, run_id, target, *args):
                path = W.create(repo, base, root, run_id, TARGET)
                write(os.path.join(path, "app.txt"), "one\nRETAINED_AFTER_DISCARD\n")
                return path

            started_from = staticmethod(W.started_from)
            review_checkpoint = staticmethod(W.review_checkpoint)
            review_diff = staticmethod(W.review_diff)

            def discard(self, _repo, path, run_id):
                return W.discard(repo, path, run_id)

        class DiskRepo(FakeRepos):
            def resolve(self, selected, worktree_root):
                return dict(super().resolve(selected, worktree_root), repo_path=repo, worktree_root=root)

        stack_as(self)
        with E.env().auto_time_skipping_disabled(), patch("app.application.activities.trust.ensure", return_value=[]):
            E.host(to_ready(), git=DiskSnapshots(), repositories=DiskRepo())
            run = E.Run(auto=True)
            self.addCleanup(run.cleanup)
            path = run.state["worktree_path"]
            self.assertEqual(run.stop["reason"], "final")
            code, output = run.answer("discard", confirm=True)
            self.assertEqual(code, 0, output)
            self.assertTrue(run.closed(), "the native Temporal execution must actually be closed")
            self.assertEqual(run.state["status"], "DISCARDED")
            self.assertFalse(os.path.exists(path), "the real Git worktree must be removed")
            status, body = request("GET", "/api/runs/" + run.run_id)
            self.assertEqual(status, 200, body)
            self.assertEqual((body["view"]["state"], body["view"]["status"], body["view"]["kept"]),
                             ("closed", "DISCARDED", False))
            status, history = request("GET", "/api/runs/" + run.run_id + "/history")
            self.assertEqual(status, 200, history)
            boundary = history["review"]["boundaries"][-1]
            self.assertTrue(boundary.get("tree"), boundary)
            expected = W.review_diff(path, base=history["review"]["initial"], tree=boundary["tree"], repo=repo)["patch"]
            self.assertIn("RETAINED_AFTER_DISCARD", expected)
            # The time-skipping server has no visibility API; list the real execution description.
            async def listed(client, limit=200, cursor=None):
                return [runs._listed(await client.get_workflow_handle(run.run_id).describe())], None

            script = Path(__file__).resolve().parents[2] / "tools/demo_press.py"
            with patch.object(runs, "runs", listed):
                result = subprocess.run([sys.executable, str(script), "http://127.0.0.1:%d" % port(), run.run_id,
                                         "review-closed", expected], capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cached_xterms_and_milestone_exports_through_the_real_browser(self):
        path = self.worktree("review-browser", change=False)
        base = git(path, "rev-parse", "HEAD").strip()
        write(os.path.join(path, "first-only.txt"), "FIRST_MILESTONE\n")
        first = W.review_checkpoint(path, "ui", "s1", base)["tree"]
        write(os.path.join(path, "app.txt"), "one\nSECOND_MILESTONE\n")
        write(os.path.join(path, "large.txt"), "".join("second milestone line %d for complete patch paging\n" % i
                                                    for i in range(25000)))
        second = W.review_checkpoint(path, "ui", "s2", base)["tree"]
        boundaries = [{"stop": "s1", "basis": base, "tree": first, "action": "revise", "at": "2026-11-12T09:00:00Z"},
                      {"stop": "s2", "basis": base, "tree": second, "action": "approve", "at": "2026-11-12T10:00:00Z"},
                      {"stop": "s3", "basis": "another-base", "tree": second, "action": "revise", "at": "2026-11-12T11:00:00Z"}]
        points = {"start": {"tree": base, "basis": base}, **{row["stop"]: row for row in boundaries}}
        fixture = {"review": {"initial": base, "boundaries": boundaries},
                   "delta": git(path, "diff", *W.DIFF, first, second), "whole": git(path, "diff", *W.DIFF, base, second)}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send(self, value, status=200, kind="application/json"):
                data = value if isinstance(value, bytes) else json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                url = urllib.parse.urlsplit(self.path)
                query = {key: rows[0] for key, rows in urllib.parse.parse_qs(url.query).items()}
                if url.path == "/fixture":
                    return self.send(fixture)
                if url.path.endswith("/milestone"):
                    start, end = query["from"], query["through"]
                    if points[start]["basis"] != points[end]["basis"]:
                        return self.send({"error": "this range crosses a base update; select checkpoints within the same base"}, 400)
                    result = W.review_diff(path, base=points[start]["tree"], tree=points[end]["tree"])
                    return self.send(dict(result, review_range={"from": list(points).index(start),
                        "through": list(points).index(end), "current": False}))
                if url.path.endswith("/diff"):
                    return self.send(W.review_diff(path, int(query.get("offset", 0)), base=query.get("base", base),
                                                  tree=query.get("tree", second), file=query.get("file")))
                if url.path in STATIC:
                    name, kind = STATIC[url.path]
                    data = (Path(PAGE) / name).read_bytes()
                    if name == "index.html":
                        data = data.replace(b'{{CONFIG}}', json.dumps({"token": "synthetic", "terminal_size": {"cols": 160, "rows": 48},
                            "terminal_ports": {"windows": 1, "wsl": 1}}).encode())
                        data = data.replace(b'<script type="module" src="/app.js"></script>', b'')
                    return self.send(data, kind=kind)
                self.send({"error": "isolated fixture"}, 404)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            script = Path(__file__).resolve().parents[2] / "tools/demo_press.py"
            result = subprocess.run([sys.executable, str(script), "http://127.0.0.1:%d" % server.server_port,
                                     "page", "review-components", "PASS"], capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)
