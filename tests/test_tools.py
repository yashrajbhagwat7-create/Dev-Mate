"""Unit tests for ToolBox file and search operations."""

from pathlib import Path
from unittest.mock import patch
import json
import pytest
from devmate.config import Config
from devmate.tools import ToolBox


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "sample.txt").write_text("line 1\nline 2\nline 3\nTargetKeyword\n", encoding="utf-8")
    (tmp_path / "dummy.py").write_text("print('ok')", encoding="utf-8")
    cfg = Config(root=tmp_path, allow_delete=True, allow_commands=True)
    box = ToolBox(cfg, approve=lambda q: True)
    return tmp_path, box


def test_read_file(workspace):
    _, box = workspace
    content = box.read_file("sample.txt", start_line=1, end_line=2)
    assert "1: line 1" in content
    assert "2: line 2" in content
    assert "3: line 3" not in content


def test_write_and_edit_file(workspace):
    tmp_path, box = workspace
    box.write_file("new_file.py", "x = 10\ny = 20\n")
    assert (tmp_path / "new_file.py").exists()

    box.edit_file("new_file.py", "x = 10", "x = 42")
    assert "x = 42" in (tmp_path / "new_file.py").read_text(encoding="utf-8")


def test_search_files(workspace):
    _, box = workspace
    res = box.search_files("TargetKeyword")
    assert "sample.txt" in res
    assert "TargetKeyword" in res


def test_delete_file(workspace):
    tmp_path, box = workspace
    (tmp_path / "to_delete.txt").write_text("temp", encoding="utf-8")
    res = box.delete_file("to_delete.txt")
    assert "Deleted to_delete.txt" in res
    assert not (tmp_path / "to_delete.txt").exists()


def test_project_summary(workspace):
    _, box = workspace
    summary = box.project_summary()
    assert "file_count" in summary
    assert "total_files" in summary
    assert ".txt" in summary


def test_run_command_keyboard_interrupt_handled_gracefully(workspace):
    _, box = workspace
    with patch("subprocess.run", side_effect=KeyboardInterrupt):
        res = box.run_command("dir")
        data = json.loads(res)
        assert "interrupted" in data["error"].lower()


def test_run_python_keyboard_interrupt_handled_gracefully(workspace):
    _, box = workspace
    with patch("subprocess.run", side_effect=KeyboardInterrupt):
        res = box.run_python("dummy.py")
        data = json.loads(res)
        assert "interrupted" in data["error"].lower()
