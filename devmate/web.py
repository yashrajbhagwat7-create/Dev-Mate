"""Built-in Local Web Dashboard & REST API Server for Dev-Mate.
Provides a luxury web interface and real-time project control center
without requiring external frameworks (built strictly on Python standard library).
"""

import json
import os
import sys
import urllib.parse
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional

from .ui import badge, style, panel, Color


class DevMateWebHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Dev-Mate web dashboard and JSON API."""

    # Injected by server factory
    toolbox = None
    agent = None
    config = None

    def log_message(self, format, *args):
        # Clean terminal logging
        sys.stdout.write(f"  {badge('HTTP', 'dim')} {self.command} {self.path}\n")
        sys.stdout.flush()

    def _send_json(self, data, status: int = 200):
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_content: str, status: int = 200):
        body = html_content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # Serve Dashboard HTML
        if path in {"/", "/dashboard", "/index.html"}:
            dash_path = self.config.root / "examples" / "dashboard.html"
            if not dash_path.exists():
                dash_path = Path(__file__).resolve().parent.parent / "examples" / "dashboard.html"
            if dash_path.exists():
                self._send_html(dash_path.read_text(encoding="utf-8", errors="replace"))
            else:
                self._send_html("<h1>Dev-Mate Dashboard not found in examples/</h1>", status=404)
            return

        # API: Doctor health check
        if path == "/api/doctor":
            health = self.toolbox.run_doctor()
            self._send_json(health)
            return

        # API: Git status
        if path == "/api/status":
            st_raw = self.toolbox.git_status()
            try:
                st = json.loads(st_raw)
            except Exception:
                st = {"stdout": st_raw}
            self._send_json(st)
            return

        # API: Git diff
        if path == "/api/diff":
            diff_raw = self.toolbox.git_diff()
            try:
                df = json.loads(diff_raw)
            except Exception:
                df = {"stdout": diff_raw}
            self._send_json(df)
            return

        # API: Dependency analysis
        if path == "/api/deps":
            p_arg = query.get("path", [None])[0]
            deps_raw = self.toolbox.analyze_dependencies(path=p_arg)
            self._send_json(json.loads(deps_raw))
            return

        # API: Run test suite
        if path == "/api/tests":
            target = query.get("target", [""])[0]
            tests_raw = self.toolbox.run_tests(test_target=target)
            self._send_json(json.loads(tests_raw))
            return

        # API: Activity audit history
        if path == "/api/history":
            activity = self.toolbox.memory.recent_activity(limit=50)
            self._send_json({"activity": activity})
            return

        # API: AST outline
        if path == "/api/outline":
            target = query.get("path", [""])[0]
            if not target:
                self._send_json({"error": "Path query parameter required"}, status=400)
                return
            out = self.toolbox.view_outline(target)
            self._send_json({"outline": out, "file": target})
            return

        # API: Conversation Dialogue History
        if path == "/api/chat/history":
            history = []
            if self.agent and getattr(self.agent, "history", None):
                history = [
                    {"role": m.get("role"), "content": m.get("content")}
                    for m in self.agent.history
                    if m.get("role") in {"user", "assistant"} and m.get("content")
                ]
            self._send_json({"history": history})
            return

        # Static assets fallback
        if path.startswith("/examples/"):
            rel_file = self.config.root / path.lstrip("/")
            if rel_file.is_file():
                self._send_html(rel_file.read_text(encoding="utf-8", errors="replace"))
                return

        self._send_json({"error": f"Endpoint not found: {path}"}, status=404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            payload = json.loads(raw_body)
        except Exception:
            payload = {}

        # API: Interactive Chat / Prompt
        if path == "/api/chat":
            user_prompt = payload.get("prompt", "").strip()
            if not user_prompt:
                self._send_json({"error": "Prompt cannot be empty"}, status=400)
                return
            if not self.agent:
                self._send_json({"error": "Agent not initialized with valid AI provider keys"}, status=503)
                return
            response = self.agent.run(user_prompt)
            self._send_json({"prompt": user_prompt, "response": response})
            return

        # API: Reset Chat / Conversation Memory
        if path == "/api/chat/reset":
            if self.agent:
                self.agent.reset()
            self._send_json({"status": "ok", "message": "Conversation memory reset"})
            return

        # API: Syntax check
        if path == "/api/syntax":
            target = payload.get("path", "").strip()
            if not target:
                self._send_json({"error": "Path required"}, status=400)
                return
            res = self.toolbox.check_syntax(target)
            self._send_json(json.loads(res))
            return

        # API: Find references
        if path == "/api/refs":
            sym = payload.get("symbol", "").strip()
            p_arg = payload.get("path", "").strip() or None
            if not sym:
                self._send_json({"error": "Symbol required"}, status=400)
                return
            res = self.toolbox.find_references(sym, path=p_arg)
            self._send_json(json.loads(res))
            return

        # API: Rollback file
        if path == "/api/rollback":
            target = payload.get("path", "").strip()
            if not target:
                self._send_json({"error": "Path required"}, status=400)
                return
            res = self.toolbox.rollback_file(target)
            self._send_json({"message": res})
            return

        # API: Undo last change
        if path == "/api/undo":
            res = self.toolbox.undo_last_change()
            self._send_json({"message": res})
            return

        # API: Run tests
        if path == "/api/tests":
            target = payload.get("target", "")
            res = self.toolbox.run_tests(test_target=target)
            self._send_json(json.loads(res))
            return

        self._send_json({"error": f"Unknown POST endpoint: {path}"}, status=404)


def start_web_server(config, toolbox, agent=None, port: int = 8080, open_browser: bool = True):
    """Start local Dev-Mate web dashboard server and listen for requests."""
    DevMateWebHandler.config = config
    DevMateWebHandler.toolbox = toolbox
    DevMateWebHandler.agent = agent

    server_address = ("127.0.0.1", port)
    try:
        httpd = HTTPServer(server_address, DevMateWebHandler)
    except OSError as e:
        if "address already in use" in str(e).lower() or getattr(e, "winerror", None) == 10048:
            port = port + 1
            server_address = ("127.0.0.1", port)
            httpd = HTTPServer(server_address, DevMateWebHandler)
        else:
            raise

    url = f"http://127.0.0.1:{port}"
    banner_text = f"""Server running at: {style(url, Color.BOLD, Color.BRIGHT_CYAN)}
Workspace Root   : {config.root}
Provider         : {config.provider}
Press {style('Ctrl+C', Color.YELLOW)} to stop server and return to terminal.
"""
    print(f"\n{panel('🌐 Dev-Mate Web Dashboard Server', banner_text, border_color=Color.BRIGHT_GREEN)}")

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(f"\n{badge('STOP', 'info')} Web dashboard server stopped.")
    finally:
        httpd.server_close()
