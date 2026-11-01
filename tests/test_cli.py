"""Unit tests for Dev-Mate interactive CLI slash commands and main loop."""

from unittest.mock import patch, MagicMock
from pathlib import Path
import pytest
from devmate.cli import print_help, main
from devmate.config import Config
from devmate.tools import ToolBox


def test_print_help(capsys):
    print_help()
    captured = capsys.readouterr()
    assert "/provider" in captured.out
    assert "/team" in captured.out
    assert "/review" in captured.out
    assert "/undo" in captured.out
    assert "/outline" in captured.out
    assert "/report" in captured.out


def test_cli_slash_commands_loop(tmp_path, monkeypatch, capsys):
    # Setup mock workspace and test API key
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("ALLOW_COMMANDS", "true")
    (tmp_path / "hello.py").write_text("print('hello')", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    # Sequence of prompts to simulate user interaction
    prompt_sequence = [
        "/help",
        "/doctor",
        "/tokens",
        "/report",
        "/status",
        "/diff",
        "/grep def",
        "/memory",
        "/history",
        "/mode edit",
        "/outline hello.py",
        "/undo",
        "/exit"
    ]

    with patch("devmate.cli.InputReader.read_prompt", side_effect=prompt_sequence), \
         patch("builtins.input", return_value="1"), \
         patch("sys.argv", ["devmate", "--root", str(tmp_path)]):
        main()

    captured = capsys.readouterr()
    assert "AI Software Engineering Agent" in captured.out
    assert "Operating mode set to: EDIT" in captured.out
    assert "File Structure Outline" in captured.out
    assert "Health Doctor" in captured.out
    assert "Goodbye!" in captured.out


def test_cli_doctor_flag(tmp_path, capsys):
    with patch("sys.argv", ["devmate", "--root", str(tmp_path), "--doctor"]):
        main()
    captured = capsys.readouterr()
    assert "Dev-Mate Environment & Health Doctor" in captured.out
    assert "Python" in captured.out


def test_cli_test_flag(tmp_path, capsys):
    with patch("sys.argv", ["devmate", "--root", str(tmp_path), "--test"]), \
         patch("devmate.tools.ToolBox.run_tests", return_value='{"status": "PASS", "summary": "10 passed", "duration": 0.5, "exit_code": 0}'), \
         pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "10 passed" in captured.out


def test_cli_extended_slash_commands(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    (tmp_path / "app.py").write_text("import os\n\ndef add(a, b):\n    return a + b\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    prompt_sequence = [
        "/syntax app.py",
        "/refs add app.py",
        "/deps app.py",
        "/audit",
        "/test",
        "/clear",
        "/exit"
    ]

    with patch("devmate.cli.InputReader.read_prompt", side_effect=prompt_sequence), \
         patch("devmate.tools.ToolBox.run_tests", return_value='{"status": "PASS", "summary": "All tests passed", "duration": 0.2}'), \
         patch("os.system", return_value=0), \
         patch("sys.argv", ["devmate", "--root", str(tmp_path)]):
        main()

    captured = capsys.readouterr()
    assert "VALID" in captured.out
    assert "Found" in captured.out or "reference" in captured.out
    assert "Dependency Analysis" in captured.out
    assert "AUDIT" in captured.out
    assert "All tests passed" in captured.out
    assert "Goodbye!" in captured.out


def test_cli_one_shot_execution(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    with patch("sys.argv", ["devmate", "--root", str(tmp_path), "-p", "explain this"]), \
         patch("devmate.agent.Agent.run", return_value="One-shot response text"):
        main()

    captured = capsys.readouterr()
    assert "One-shot response text" in captured.out


def test_cli_init_and_web_flags(tmp_path):
    # Test --init calls run_setup_wizard
    with patch("sys.argv", ["devmate", "--root", str(tmp_path), "--init"]), \
         patch("devmate.wizard.run_setup_wizard") as mock_wiz:
        main()
        mock_wiz.assert_called_once()

    # Test --web calls start_web_server
    with patch("sys.argv", ["devmate", "--root", str(tmp_path), "--web", "9090"]), \
         patch("devmate.web.start_web_server") as mock_web:
        main()
        mock_web.assert_called_once()


def test_cli_fuzzy_command_suggestion(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    prompt_sequence = [
        "/doctr",
        "/stts",
        "/exit"
    ]

    with patch("devmate.cli.InputReader.read_prompt", side_effect=prompt_sequence), \
         patch("sys.argv", ["devmate", "--root", str(tmp_path)]):
        main()

    captured = capsys.readouterr()
    assert "Did you mean" in captured.out
    assert "/doctor" in captured.out or "/status" in captured.out

