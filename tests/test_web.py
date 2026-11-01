"""Unit tests for Dev-Mate built-in local web dashboard server and API handlers."""

import io
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from devmate.config import Config
from devmate.tools import ToolBox
from devmate.web import DevMateWebHandler, start_web_server


class DummyRequest:
    def __init__(self, command, path, body=b""):
        self.command = command
        self.path = path
        self.body = body

    def makefile(self, *args, **kwargs):
        if "w" in args[0] or "w" in kwargs.get("mode", ""):
            return io.BytesIO()
        return io.BytesIO(self.body)


def create_handler(command, path, body_dict=None, tmp_path=None):
    cfg = Config(root=tmp_path, openrouter_key="test-key", google_key="test-key")
    box = ToolBox(cfg, approve=lambda q: True)
    DevMateWebHandler.config = cfg
    DevMateWebHandler.toolbox = box
    DevMateWebHandler.agent = MagicMock()
    DevMateWebHandler.agent.run.return_value = "Mock agent output"

    raw_body = json.dumps(body_dict).encode("utf-8") if body_dict else b""
    dummy_req = DummyRequest(command, path, raw_body)

    # Instantiate handler with mocks
    with patch.object(DevMateWebHandler, "setup"), \
         patch.object(DevMateWebHandler, "finish"):
        handler = DevMateWebHandler.__new__(DevMateWebHandler)
        handler.command = command
        handler.path = path
        handler.headers = {"Content-Length": str(len(raw_body))}
        handler.rfile = io.BytesIO(raw_body)
        handler.wfile = io.BytesIO()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        return handler


def test_web_get_endpoints(tmp_path):
    # Test /api/doctor
    h_doc = create_handler("GET", "/api/doctor", tmp_path=tmp_path)
    h_doc.do_GET()
    h_doc.send_response.assert_called_with(200)

    # Test /api/status
    h_stat = create_handler("GET", "/api/status", tmp_path=tmp_path)
    h_stat.do_GET()
    h_stat.send_response.assert_called_with(200)

    # Test /api/diff
    h_diff = create_handler("GET", "/api/diff", tmp_path=tmp_path)
    h_diff.do_GET()
    h_diff.send_response.assert_called_with(200)

    # Test /api/deps
    h_deps = create_handler("GET", "/api/deps", tmp_path=tmp_path)
    h_deps.do_GET()
    h_deps.send_response.assert_called_with(200)

    # Test /api/history
    h_hist = create_handler("GET", "/api/history", tmp_path=tmp_path)
    h_hist.do_GET()
    h_hist.send_response.assert_called_with(200)


def test_web_post_chat_and_tools(tmp_path):
    (tmp_path / "sample.py").write_text("x = 10\n", encoding="utf-8")

    # POST /api/chat
    h_chat = create_handler("POST", "/api/chat", {"prompt": "hello"}, tmp_path=tmp_path)
    h_chat.do_POST()
    h_chat.send_response.assert_called_with(200)

    # POST /api/syntax
    h_syn = create_handler("POST", "/api/syntax", {"path": "sample.py"}, tmp_path=tmp_path)
    h_syn.do_POST()
    h_syn.send_response.assert_called_with(200)

    # POST /api/undo
    h_undo = create_handler("POST", "/api/undo", {}, tmp_path=tmp_path)
    h_undo.do_POST()
    h_undo.send_response.assert_called_with(200)
