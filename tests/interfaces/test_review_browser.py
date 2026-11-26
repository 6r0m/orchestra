"""Real browser acceptance on disposable Git snapshots; no live stack, vendor or clipboard writes."""
import asyncio
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import AsyncMock, patch

from app.interfaces.workbench.server import PAGE, STATIC
from app.agents import terminal
from app.workspace import worktrees as W
from tests.workspace.test_worktrees import Repo, TARGET, git, write

EDGE = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe"


@unittest.skipUnless(sys.platform.startswith("win") and EDGE.is_file(), "the real browser acceptance runs on Windows")
class ReviewBrowser(Repo):
    def test_same_branch_in_two_git_repositories_only_links_the_recorded_worktree(self):
        import temporal_env as E
        from app.application import client as runs
        from tests.interfaces.test_workbench import request, settings_server

        settings = Path(self.tmp) / ".orchestra"
        settings.mkdir()
        (settings / "settings.json").write_text(json.dumps(E.SETTINGS), encoding="utf-8")
        at = settings_server(self, self.tmp, {}, call=lambda work, timeout=300: asyncio.run(work(None)))
        branch = "same-run-branch"
        real = self.worktree(branch, change=False)
        other = os.path.join(self.tmp, "other-repo")
        git(self.repo, "clone", "--local", self.repo, other)
        W.create(other, "develop", os.path.join(self.tmp, "other-worktrees"), branch, TARGET)
        queue = E.WINDOWS_QUEUE if TARGET == "windows" else E.WSL_QUEUE

        async def worktrees(_client, *, repo, **kwargs):
            return {"id": repo, "target": TARGET}, {"base_branch": "develop", "rows": W.view(repo, "develop"),
                                                    "target_queue": queue}

        with (patch.object(runs, "worktrees_of", side_effect=worktrees),
              patch.object(runs, "execution", return_value={"run_id": branch, "execution": "CANCELED"}),
              patch.object(runs, "status", return_value={"queue": queue,
                                                         "state": {"target": TARGET, "worktree_path": real}}),
              patch.object(runs, "removal", return_value=None)):
            for repo, expected in ((self.repo, ("CANCELED", True)), (other, (None, False))):
                status, body = request("GET", "/api/worktrees?repo=" + urllib.parse.quote(repo), at=at)
                self.assertEqual(status, 200, body)
                row = next(row for row in body["rows"] if row["branch"] == branch)
                self.assertEqual((row["run"], row["removable"]), expected)

    def test_git_canonicalizes_a_windows_worktree_path_before_listing_it(self):
        from app.application import activities, client as runs

        root = Path(self.tmp) / "WorktreeSpelling"
        root.mkdir()
        alternate = root.with_name(root.name.lower())
        if not alternate.is_dir():
            self.skipTest("the fixture directory has case-sensitive names")
        drive, rest = os.path.splitdrive(str(alternate))
        branch = "same-worktree"
        recorded = W.create(self.repo, "develop", drive.lower() + rest, branch, TARGET)
        shown = next(row["path"] for row in W.view(self.repo, "develop") if row["branch"] == branch)
        self.assertNotEqual(shown, recorded, "Git lists the filesystem spelling, not the requested spelling")
        self.assertTrue(os.path.samefile(shown, recorded))
        queue = "target:windows:fixture"
        current = {"queue": queue, "workflow_queue": "fixture",
                   "state": {"target": TARGET, "worktree_path": recorded}}
        displayed = {"path": shown, "target": TARGET, "queue": queue}
        worker = activities.Activities(runner=None, telemetry=None)

        async def on_worker(_workflow, args, **_):
            self.assertEqual(args["queue"], queue)
            return worker.worktree_view(args)

        client = AsyncMock()
        client.execute_workflow.side_effect = on_worker

        self.assertTrue(asyncio.run(runs.matches_worktree(client, current, displayed)))
        with patch.object(activities.os.path, "samefile", return_value=False):
            self.assertFalse(asyncio.run(runs.matches_worktree(client, current, displayed)),
                             "case-distinct native directories must stay distinct")

    def test_settings_workspace_keeps_jumps_and_validation_bound_to_the_draft(self):
        import temporal_env as E
        from tests.interfaces.test_workbench import settings_server

        settings = Path(self.tmp) / ".orchestra"
        settings.mkdir()
        config = dict(E.SETTINGS, default_flow="architect-auto", timeout_seconds=3600, stage_skills={})
        config["roles"] = dict(config["roles"], engineer=dict(config["roles"]["engineer"], persona="A shared persona."))
        (settings / "settings.json").write_text(json.dumps(config), encoding="utf-8")
        (settings / "settings.local.json").write_text(json.dumps({"agents": {"codex-engineer": None}}), encoding="utf-8")
        at = settings_server(self, self.tmp, {})
        script = Path(__file__).resolve().parents[2] / "tools/demo_press.py"
        engineer = E.SETTINGS["roles"]["engineer"]["agent"]
        runtime = E.SETTINGS["agents"][engineer]["kind"]
        with patch("app.application.settings.adapters.skill_names",
                   return_value={runtime: ["fixture-support", "investigate-change"], "pi": ["architect"]}):
            result = subprocess.run([sys.executable, str(script), "http://127.0.0.1:%d" % at,
                                     "page", "settings-workspace", "PASS"], capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        local = json.loads((settings / "settings.local.json").read_text(encoding="utf-8"))
        self.assertEqual(local, {
            "timeout_seconds": 172800,
            "agents": {
                engineer: {"model": "fixture-model"},
                "fixture-review": {"kind": "pi", "model": "review-model-edited", "effort": "high", "launcher": "pi-worker"},
            },
            "roles": {"architect": {"agent": "fixture-review"}, "engineer": {"persona": None}},
            "stage_skills": {"plan": ["investigate-change", "fixture-support"], "build": "remote-build",
                             "research": "architect", "assess": "architect", "verify": "architect"},
            "review_prompts": {"after_normal": {"engineer": "Check the evidence."}},
        })

    def test_repository_editor_saves_the_local_catalog_and_removes_only_the_entry(self):
        import temporal_env as E
        from app.application import client as runs
        from tests.interfaces.test_workbench import request, settings_server

        settings = Path(self.tmp) / ".orchestra"
        settings.mkdir()
        (settings / "settings.json").write_text(json.dumps(E.SETTINGS), encoding="utf-8")
        at = settings_server(self, self.tmp, {}, call=lambda work, timeout=300: asyncio.run(work(None)))
        endpoint = "/api/repos/editor"
        self.assertEqual(request("POST", endpoint, token=False, at=at)[0], 403)

        async def on_host(_client, *, repo, descriptors, **_):
            selected = runs.repos.select(repo, descriptors)
            self.assertEqual(selected["path"], self.repo)
            return selected, {"base_branch": "develop", "rows": [],
                              "target_queue": E.WINDOWS_QUEUE if selected["target"] == "windows" else E.WSL_QUEUE}

        script = Path(__file__).resolve().parents[2] / "tools/demo_press.py"
        worker = AsyncMock(side_effect=on_host)
        with patch.object(runs, "worktrees_of", worker):
            result = subprocess.run([sys.executable, str(script), "http://127.0.0.1:%d" % at,
                                     "page", "repository-editor", self.repo], capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertGreaterEqual(worker.await_count, 2, "Add and Edit validate the selected repository")
        self.assertEqual(json.loads((settings / "repos.json").read_text(encoding="utf-8")), {})
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_worktree_picker_binds_reads_to_the_current_repository(self):
        from tests.interfaces.test_workbench import port

        script = Path(__file__).resolve().parents[2] / "tools/demo_press.py"
        result = subprocess.run([sys.executable, str(script), "http://127.0.0.1:%d" % port(),
                                 "page", "worktree-picker", "PASS"], capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_home_distinguishes_idle_active_and_unavailable_runs(self):
        from tests.interfaces.test_workbench import port

        script = Path(__file__).resolve().parents[2] / "tools/demo_press.py"
        result = subprocess.run([sys.executable, str(script), "http://127.0.0.1:%d" % port(),
                                 "page", "workbench-home", "PASS"], capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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
        write(os.path.join(path, "transient.txt"), "ADDED_THEN_REMOVED\n")
        first = W.review_checkpoint(path, "ui", "s1", base)["tree"]
        os.remove(os.path.join(path, "transient.txt"))
        write(os.path.join(path, "app.txt"), "one\nSECOND_MILESTONE\n")
        write(os.path.join(path, "large.txt"), "".join("second milestone line %d for complete patch paging\n" % i
                                                    for i in range(25000)))
        second = W.review_checkpoint(path, "ui", "s2", base)["tree"]
        write(os.path.join(self.repo, 'upstream.txt'), 'INCOMING_BASE_CHANGE\n')
        git(self.repo, 'add', 'upstream.txt')
        git(self.repo, 'commit', '-qm', 'incoming base')
        moved = git(self.repo, 'rev-parse', 'HEAD').strip()
        write(os.path.join(self.repo, 'main-only.txt'), 'UNCOMMITTED_MAIN_ONLY\n')
        cross_path = self.worktree('review-cross', change=False)
        shutil.copytree(path, cross_path, dirs_exist_ok=True, ignore=shutil.ignore_patterns('.git'))
        write(os.path.join(cross_path, 'own-cross.txt'), 'OWN_CROSS_MILESTONE\n')
        third = W.review_checkpoint(cross_path, 'ui', 's3', moved)['tree']
        boundaries = [{"stop": "s1", "basis": base, "tree": first, "action": "revise", "role": "engineer",
                       "after": "assess:1:1", "at": "2026-11-12T09:00:00Z"},
                      {"stop": "s2", "basis": base, "tree": second, "action": "approve",
                       "after": "verify:2:2", "at": "2026-11-12T10:00:00Z"},
                      {"stop": "s3", "basis": moved, "tree": third, "action": "revise", "role": "architect",
                       "after": "build:3:1", "at": "2026-11-12T11:00:00Z"}]
        points = {"start": {"tree": base, "basis": base}, **{row["stop"]: row for row in boundaries}}
        turns = [{'stage': stage, 'role': role, 'episode': episode, 'round': round_number}
                 for stage, role, episode, round_number in [('plan', 'engineer', 1, 1), ('assess', 'architect', 1, 1),
                   ('build', 'engineer', 2, 1), ('verify', 'architect', 2, 1), ('build', 'engineer', 2, 2),
                   ('verify', 'architect', 2, 2), ('build', 'engineer', 3, 1)]]
        fixture = {"review": {"initial": base, "boundaries": boundaries[:2]}, "cross": boundaries[2], 'turns': turns,
                   'closed_total': git(path, 'diff', *W.DIFF, moved, third),
                   'cross_patch': git(path, 'diff', *W.DIFF, second, third, '--', 'own-cross.txt'),
                   "delta": git(path, "diff", *W.DIFF, first, second), "whole": git(path, "diff", *W.DIFF, base, second)}
        self.assertIn('transient.txt', fixture['delta'])
        self.assertNotIn('transient.txt', fixture['whole'])
        current_basis = [base]

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

            def do_POST(self):
                if self.path not in ("/advance", "/finalize"):
                    return self.send({"error": "isolated fixture"}, 404)
                write(os.path.join(path, "live-revision.txt" if self.path == "/advance" else "finished-revision.txt"),
                      "LIVE_AFTER_OPERATOR_REVISION\n")
                if self.path == '/finalize':
                    write(os.path.join(path, 'upstream.txt'), 'INCOMING_BASE_CHANGE\n')
                    current_basis[0] = moved
                snapshot = W.review_diff(path, base=second)
                self.send({"summary": W.change_summary(path, base), "patch": snapshot["patch"],
                           "whole": git(path, "diff", *W.DIFF, current_basis[0], snapshot["tree"])})

            def do_GET(self):
                url = urllib.parse.urlsplit(self.path)
                query = {key: rows[0] for key, rows in urllib.parse.parse_qs(url.query).items()}
                if url.path == "/cache-probe.js":
                    return self.send(Path(__file__).with_name("terminal_cache_probe.js").read_bytes(), kind="text/javascript")
                if url.path == "/fixture":
                    return self.send(fixture)
                if url.path.endswith("/milestone"):
                    start, end = query["from"], query["through"]
                    if start not in points or end != 'current' and end not in points:
                        return self.send({'error': 'checkpoint unavailable: no recorded tree'}, 400)
                    target_basis = current_basis[0] if end == 'current' else points[end]['basis']
                    alignment = {'from': points[start]['basis'], 'to': target_basis} if points[start]['basis'] != target_basis else None
                    result = W.review_diff(path, base=points[start]["tree"],
                                           tree=None if end == "current" else points[end]["tree"], alignment=alignment)
                    return self.send(dict(result, review_range={"from": list(points).index(start),
                        "through": len(points) if end == "current" else list(points).index(end),
                        "current": end == "current", 'base_updated':
                        points[start]['basis'] != (current_basis[0] if end == 'current' else points[end]['basis'])}))
                if url.path.endswith("/diff"):
                    return self.send(W.review_diff(path, int(query.get("offset", 0)), base=query.get("base", current_basis[0]),
                                                  tree=query.get("tree"), file=query.get("file")))
                if url.path in STATIC:
                    name, kind = STATIC[url.path]
                    data = (Path(PAGE) / name).read_bytes()
                    if name == "index.html":
                        data = data.replace(b'{{CONFIG}}', json.dumps({"token": "synthetic", "terminal_size": {
                            "cols": terminal.COLS, "rows": terminal.ROWS,
                            "min_rows": terminal.MIN_ROWS, "max_rows": terminal.MAX_ROWS},
                            "terminal_ports": {"windows": 1, "wsl": 1}}).encode())
                        data = data.replace(b'<script type="module" src="/app.js"></script>', b'')
                    return self.send(data, kind=kind)
                self.send({"error": "isolated fixture"}, 404)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        main_before = git(self.repo, 'status', '--porcelain')
        index_before = git(path, 'ls-files', '--stage')
        try:
            script = Path(__file__).resolve().parents[2] / "tools/demo_press.py"
            result = subprocess.run([sys.executable, str(script), "http://127.0.0.1:%d" % server.server_port,
                                     "page", "review-components", "PASS"], capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(git(self.repo, 'status', '--porcelain'), main_before)
            self.assertEqual(git(path, 'ls-files', '--stage'), index_before)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)
