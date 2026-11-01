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
    cfg = Config(root=tmp_path, allow_delete=True, allow_commands=True, openrouter_key="test-key", google_key="test-key")
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


def test_view_outline_python(workspace):
    tmp_path, box = workspace
    code = '''"""Module docstring."""
API_KEY = "test"

class Calculator:
    """A simple calculator."""
    def add(self, a, b):
        """Add two numbers."""
        return a + b

def standalone_func(x):
    """Standalone helper."""
    return x * 2
'''
    (tmp_path / "calc.py").write_text(code, encoding="utf-8")
    outline = box.view_outline("calc.py")
    assert "class Calculator" in outline
    assert "def add(" in outline
    assert "def standalone_func(" in outline
    assert "CONST API_KEY" in outline


def test_view_outline_markdown(workspace):
    tmp_path, box = workspace
    md = "# Project Title\n## Section 1\nSome text\n### Subsection A\n"
    (tmp_path / "doc.md").write_text(md, encoding="utf-8")
    outline = box.view_outline("doc.md")
    assert "Markdown Outline" in outline
    assert "# Project Title" in outline
    assert "## Section 1" in outline
    assert "### Subsection A" in outline


def test_get_definition(workspace):
    tmp_path, box = workspace
    code = '''
class User:
    def __init__(self, name):
        self.name = name

def greet_user(user):
    """Return greeting."""
    return f"Hello, {user.name}!"
'''
    (tmp_path / "user_module.py").write_text(code, encoding="utf-8")
    
    # Class lookup
    res_class = box.get_definition("User")
    assert "Class 'User'" in res_class
    assert "class User:" in res_class

    # Function lookup
    res_func = box.get_definition("greet_user")
    assert "Function/Method 'greet_user'" in res_func
    assert "return f\"Hello, {user.name}!\"" in res_func

    # Missing symbol
    res_none = box.get_definition("NonExistentSymbol")
    assert "not found" in res_none


def test_replace_lines(workspace):
    tmp_path, box = workspace
    orig = "line 1\nline 2\nline 3\nline 4\nline 5\n"
    (tmp_path / "replace_target.txt").write_text(orig, encoding="utf-8")

    res = box.replace_lines("replace_target.txt", start_line=2, end_line=4, new_content="NEW LINE A\nNEW LINE B")
    assert "Replaced lines 2-4" in res

    updated = (tmp_path / "replace_target.txt").read_text(encoding="utf-8")
    assert "line 1" in updated
    assert "NEW LINE A" in updated
    assert "NEW LINE B" in updated
    assert "line 5" in updated
    assert "line 2" not in updated
    assert "line 3" not in updated
    assert "line 4" not in updated


def test_edit_file_newline_normalization(workspace):
    tmp_path, box = workspace
    # Write with CRLF
    (tmp_path / "crlf_target.txt").write_bytes(b"hello\r\nworld\r\n")

    # Edit using LF string
    res = box.edit_file("crlf_target.txt", "hello\nworld", "hello\nearth")
    assert "Edited" in res
    assert "earth" in (tmp_path / "crlf_target.txt").read_text(encoding="utf-8")


def test_read_file_binary_guard(workspace):
    tmp_path, box = workspace
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    content = box.read_file("image.png")
    assert "Binary file" in content
    assert "cannot be displayed as text" in content


def test_rollback_file_and_undo_last_change(workspace):
    tmp_path, box = workspace
    file_p = tmp_path / "state.txt"
    file_p.write_text("initial state\n", encoding="utf-8")

    # First modification
    box.write_file("state.txt", "modified state v1\n")
    assert file_p.read_text(encoding="utf-8") == "modified state v1\n"

    # Second modification
    box.edit_file("state.txt", "v1", "v2")
    assert file_p.read_text(encoding="utf-8") == "modified state v2\n"

    # Undo last change (should revert v2 -> v1)
    undo_res = box.undo_last_change()
    assert "Successfully reverted" in undo_res
    assert file_p.read_text(encoding="utf-8") == "modified state v1\n"

    # Rollback file directly (should revert to initial state)
    rb_res = box.rollback_file("state.txt")
    assert "Successfully restored" in rb_res
    assert file_p.read_text(encoding="utf-8") == "initial state\n"


def test_grep_search(workspace):
    tmp_path, box = workspace
    (tmp_path / "search_target.py").write_text("def find_pattern_123(): pass\n", encoding="utf-8")
    
    hits = box.grep_search(r"find_pattern_\d+")
    assert "search_target.py" in hits
    assert "find_pattern_123" in hits

    # No match
    no_hits = box.grep_search(r"non_existent_\d+")
    assert "No regex matches" in no_hits

    # Invalid regex
    err = box.grep_search(r"[unclosed-bracket")
    assert "Invalid regex" in err


def test_run_doctor(workspace):
    _, box = workspace
    health = box.run_doctor()
    assert "python" in health
    assert "git" in health
    assert "providers" in health
    assert "backups" in health
    assert "test_framework" in health
    assert health["python"]["status"] == "PASS"


def test_git_commit_clean_tree(workspace):
    _, box = workspace
    # Working tree in fresh tmp_path without changes
    with patch.object(box, "run_command", return_value='{"stdout": "", "returncode": 0}'):
        res = box.git_commit("test commit")
        assert "clean" in res.lower()


def test_plan_task(workspace):
    _, box = workspace
    with patch("devmate.subagent.SubAgent.execute", return_value="Plan: 1. Inspect, 2. Test"):
        plan = box.plan_task("Add authentication")
        assert "Plan: 1. Inspect, 2. Test" in plan


def test_check_syntax_python_and_json(workspace):
    tmp_path, box = workspace
    # Valid Python
    good_py = tmp_path / "valid.py"
    good_py.write_text("def hello():\n    return 42\n", encoding="utf-8")
    res_good = json.loads(box.check_syntax("valid.py"))
    assert res_good["status"] == "VALID"

    # Syntax Error Python
    bad_py = tmp_path / "broken.py"
    bad_py.write_text("def broken(\n", encoding="utf-8")
    res_bad = json.loads(box.check_syntax("broken.py"))
    assert res_bad["status"] == "INVALID"
    assert res_bad["type"] == "SyntaxError"
    assert "snippet" in res_bad

    # Valid JSON
    good_json = tmp_path / "data.json"
    good_json.write_text('{"name": "devmate", "valid": true}', encoding="utf-8")
    res_json_ok = json.loads(box.check_syntax("data.json"))
    assert res_json_ok["status"] == "VALID"

    # Invalid JSON
    bad_json = tmp_path / "bad.json"
    bad_json.write_text('{"name": "devmate", broken}', encoding="utf-8")
    res_json_bad = json.loads(box.check_syntax("bad.json"))
    assert res_json_bad["status"] == "INVALID"
    assert res_json_bad["type"] == "JSONDecodeError"


def test_check_syntax_toml_and_markdown(workspace):
    tmp_path, box = workspace
    # Valid TOML
    toml_f = tmp_path / "test.toml"
    toml_f.write_text('[tool.devmate]\nversion = "1.0"\n', encoding="utf-8")
    res_toml = json.loads(box.check_syntax("test.toml"))
    assert res_toml["status"] == "VALID"

    # Markdown lint check
    md_f = tmp_path / "report.md"
    md_f.write_text("# Title\n\n| Col1 | Col2 |\n| --- | --- |\n| Val1 | Val2 |\n", encoding="utf-8")
    res_md = json.loads(box.check_syntax("report.md"))
    assert res_md["status"] == "VALID"


def test_find_references(workspace):
    tmp_path, box = workspace
    py_code = """
class Calculator:
    def add(self, a, b):
        return a + b

def run():
    c = Calculator()
    return c.add(1, 2)
"""
    (tmp_path / "calc.py").write_text(py_code, encoding="utf-8")

    # Find usages of Calculator
    res_raw = box.find_references("Calculator")
    res = json.loads(res_raw)
    assert res["total_matches"] >= 1
    files = [r["file"] for r in res["references"]]
    assert "calc.py" in files

    # Find usages of add
    res_add = json.loads(box.find_references("add"))
    assert res_add["total_matches"] >= 2  # def add and c.add
    scopes = [r["scope"] for r in res_add["references"]]
    assert any("Calculator" in s for s in scopes)


def test_run_tests_success_and_failure(workspace):
    _, box = workspace
    # Mock passing test suite
    with patch("subprocess.run") as mock_sub:
        mock_sub.return_value.returncode = 0
        mock_sub.return_value.stdout = "10 passed in 0.45s"
        mock_sub.return_value.stderr = ""
        res_pass = json.loads(box.run_tests())
        assert res_pass["status"] == "PASS"
        assert res_pass["exit_code"] == 0

    # Mock failing test suite
    with patch("subprocess.run") as mock_sub:
        mock_sub.return_value.returncode = 1
        mock_sub.return_value.stdout = "FAILURES\n____ test_foo ____\nassert False\nshort test summary info\nFAILED test_foo"
        mock_sub.return_value.stderr = ""
        res_fail = json.loads(box.run_tests(test_target="tests/test_dummy.py"))
        assert res_fail["status"] == "FAIL"
        assert res_fail["exit_code"] == 1
        assert len(res_fail["failures"]) > 0


def test_analyze_dependencies_and_cycles(workspace):
    tmp_path, box = workspace
    pkg_dir = tmp_path / "mypackage"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    (pkg_dir / "mod_a.py").write_text("import os\nimport requests\nfrom . import mod_b\n", encoding="utf-8")
    (pkg_dir / "mod_b.py").write_text("import sys\nimport pytest\n", encoding="utf-8")

    res_raw = box.analyze_dependencies()
    res = json.loads(res_raw)
    assert "requests" in res["third_party_dependencies"]
    assert "pytest" in res["third_party_dependencies"]
    assert "os" in res["standard_library_modules"]
    assert "sys" in res["standard_library_modules"]
    assert res["circular_dependencies_detected"] is False


def test_export_audit_log(workspace):
    tmp_path, box = workspace
    box.memory.log("TEST_ACTION", "Testing audit export", "PASS")
    res = box.export_audit_log()
    assert "Audit report successfully exported" in res

    # Verify custom path export
    custom_audit = "docs/audit_report.md"
    res_custom = box.export_audit_log(output_path=custom_audit)
    assert "docs" in res_custom
    assert (tmp_path / "docs" / "audit_report.md").exists()
    content = (tmp_path / "docs" / "audit_report.md").read_text(encoding="utf-8")
    assert "Dev-Mate System Audit & Compliance Log" in content
    assert "TEST_ACTION" in content


def test_remember_fact(workspace):
    tmp_path, box = workspace
    res = box.remember_fact("Agreed to start with micro-SaaS side income plan", category="decisions")
    assert "Recorded into project memory under 'decisions'" in res

    data = box.memory.load()
    assert "Agreed to start with micro-SaaS side income plan" in data["decisions"]

    # Test empty fact guard
    res_empty = box.remember_fact("", category="decisions")
    assert "Cannot remember an empty fact" in res_empty



