"""Unit tests for Dev-Mate interactive onboarding setup wizard."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from devmate.wizard import (
    verify_openrouter_key,
    verify_google_key,
    verify_ollama_server,
    save_env_settings,
    run_setup_wizard,
)


def test_verify_openrouter_key():
    # Empty key
    ok, msg = verify_openrouter_key("")
    assert not ok
    assert "empty" in msg

    # Mock success
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"data": {"label": "Active"}}).encode("utf-8")
        mock_url.return_value.__enter__.return_value = mock_resp

        ok, msg = verify_openrouter_key("sk-or-testkey1234567890")
        assert ok
        assert "Active" in msg


def test_verify_google_key():
    # Empty key
    ok, msg = verify_google_key("")
    assert not ok
    assert "empty" in msg

    # Mock success
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"models": [{"name": "gemini-2.5-flash"}]}).encode("utf-8")
        mock_url.return_value.__enter__.return_value = mock_resp

        ok, msg = verify_google_key("AIzaSyDummyTestKey")
        assert ok
        assert "gemini" in msg or "Google" in msg


def test_verify_ollama_server():
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"models": [{"name": "qwen2.5-coder:latest"}]}).encode("utf-8")
        mock_url.return_value.__enter__.return_value = mock_resp

        ok, msg, models = verify_ollama_server("http://localhost:11434")
        assert ok
        assert "qwen2.5-coder:latest" in models


def test_save_env_settings(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("# Existing comment\nEXISTING=true\nGOOGLE_API_KEY=old-key\n", encoding="utf-8")

    save_env_settings(tmp_path, {
        "GOOGLE_API_KEY": "new-gemini-key",
        "DEV_MATE_PROVIDER": "google"
    })

    content = env_file.read_text(encoding="utf-8")
    assert "GOOGLE_API_KEY=new-gemini-key" in content
    assert "DEV_MATE_PROVIDER=google" in content
    assert "EXISTING=true" in content


def test_run_setup_wizard_gemini(tmp_path):
    inputs = iter(["1", "AIzaSyTestKey12345"])
    with patch("devmate.wizard.verify_google_key", return_value=(True, "Key OK")):
        success = run_setup_wizard(tmp_path, interactive_input=lambda: next(inputs))
        assert success
        assert (tmp_path / ".env").exists()
        env_text = (tmp_path / ".env").read_text(encoding="utf-8")
        assert "DEV_MATE_PROVIDER=google" in env_text
        assert "AIzaSyTestKey12345" in env_text


def test_run_setup_wizard_ollama(tmp_path):
    inputs = iter(["3", "http://localhost:11434", "qwen2.5-coder:latest"])
    with patch("devmate.wizard.verify_ollama_server", return_value=(True, "Ollama running", ["qwen2.5-coder:latest"])):
        success = run_setup_wizard(tmp_path, interactive_input=lambda: next(inputs))
        assert success
        env_text = (tmp_path / ".env").read_text(encoding="utf-8")
        assert "DEV_MATE_PROVIDER=ollama" in env_text
