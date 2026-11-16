"""A static role-terminal archive through native Edge and the real recorded-byte socket."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from app.agents import terminal
from app.interfaces.workbench.server import PAGE, STATIC

EDGE = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe'


@unittest.skipUnless(sys.platform.startswith('win') and EDGE.is_file(), 'native Edge acceptance runs on Windows')
class TerminalHistory(unittest.TestCase):
    def test_full_archive_is_static_cached_and_cannot_type_or_resize_the_agent(self):
        import shutil
        run_id = 'terminal-history-fixture'
        self.addCleanup(shutil.rmtree, terminal.run_dir(run_id), True)
        self.addCleanup(terminal.close_run, run_id)
        term = terminal.open_terminal(run_id, 'engineer')
        initial = b'FIRST_INTERACTION\r\n' + b''.join(('history row %d\r\n' % i).encode() for i in range(9000))
        term.emit(initial + b'\x1b[3JLAST_RECORDED_INTERACTION\r\n')
        terminal.open_terminal(run_id, 'architect').emit(b'ARCHITECT_ONLY\r\n')
        with socket.socket() as available:
            available.bind(('127.0.0.1', 0))
            terminal_port = available.getsockname()[1]
        typed, resized = [], []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                path = self.path.split('?', 1)[0]
                if path == '/fixture/append':
                    term.emit(b'AFTER_SNAPSHOT_MUST_NOT_APPEAR\r\n')
                    body, kind = b'{}', 'application/json'
                elif path == '/api/runs/' + run_id:
                    body = json.dumps({'state': {'target': 'windows'},
                                       'view': {'host': 'windows', 'state': 'running'}}).encode()
                    kind = 'application/json'
                elif path in STATIC:
                    name, kind = STATIC[path]
                    body = (Path(PAGE) / name).read_bytes()
                    if name == 'index.html':
                        config = {'token': terminal.token(), 'terminal_ports': {'windows': terminal_port},
                                  'terminal_size': {'cols': terminal.COLS, 'rows': terminal.ROWS,
                                                    'min_rows': terminal.MIN_ROWS, 'max_rows': terminal.MAX_ROWS}}
                        body = body.replace(b'{{CONFIG}}', json.dumps(config).encode())
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header('Content-Type', kind)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        terminal.serve(terminal_port, server.server_port)
        before = Path(term.path).read_bytes()
        with patch.object(term, 'type', side_effect=typed.append), patch.object(term, 'resize', side_effect=resized.append):
            script = Path(__file__).resolve().parents[2] / 'tools/demo_press.py'
            url = 'http://127.0.0.1:%d/?terminal-history=%s&role=engineer&host=windows' % (server.server_port, run_id)
            result = subprocess.run([sys.executable, str(script), url, run_id, 'terminal-archive', ''],
                                    capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((typed, resized, term.rows), ([], [], terminal.ROWS))
        self.assertEqual(Path(term.path).read_bytes(), before + b'AFTER_SNAPSHOT_MUST_NOT_APPEAR\r\n')
