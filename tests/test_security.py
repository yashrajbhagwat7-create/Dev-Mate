"""Security tests verifying protection against path traversal, secret exfiltration,
shell injection, and Windows device name attacks.
"""

import sys
from pathlib import Path
import pytest

from devmate.config import Config
from devmate.tools import ToolBox, safe_path, is_protected_path


@pytest.fixture
def temp_workspace(tmp_path):
    # Setup dummy project files
    (tmp_path / "main.py").write_text("print('hello')", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET_KEY=12345", encoding="utf-8")
    (tmp_path / ".env.example").write_text("SECRET_KEY=", encoding="utf-8")
    
    git_dir = tmp_path / ".git" / "hooks"
    git_dir.mkdir(parents=True)
    (git_dir / "pre-commit").write_text("#!/bin/sh", encoding="utf-8")
    
    cfg = Config(root=tmp_path, allow_delete=True, allow_commands=True)
    box = ToolBox(cfg, approve=lambda q: True)
    return tmp_path, box


def test_path_traversal_blocked(temp_workspace):
    root, box = temp_workspace
    
    # Attempt to escape project root
    with pytest.raises(ValueError, match="escapes the project root"):
        safe_path(root, "../outside_file.txt")

    with pytest.raises(ValueError, match="escapes the project root"):
        safe_path(root, "../../etc/passwd")


def test_windows_device_names_blocked(temp_workspace):
    root, box = temp_workspace
    
    # Attempt to access Windows reserved device names
    for dev in ["CON", "PRN", "AUX", "NUL", "COM1", "LPT1"]:
        with pytest.raises(ValueError, match="invalid Windows device name"):
            safe_path(root, f"{dev}.txt")


def test_env_file_access_blocked(temp_workspace):
    root, box = temp_workspace
    
    # Accessing .env directly must raise PermissionError
    with pytest.raises(PermissionError, match="denied by security policy"):
        box.read_file(".env")

    with pytest.raises(PermissionError, match="denied by security policy"):
        box.write_file(".env", "LEAKED=true")

    with pytest.raises(PermissionError, match="denied by security policy"):
        box.delete_file(".env")


def test_env_example_read_allowed_but_write_protected(temp_workspace):
    root, box = temp_workspace
    
    # Reading .env.example template is allowed
    content = box.read_file(".env.example")
    assert "SECRET_KEY=" in content

    # Writing to .env.example via write_file is guarded by allow_env_example=False
    with pytest.raises(PermissionError, match="denied by security policy"):
        box.write_file(".env.example", "HAX")


def test_git_internals_protected(temp_workspace):
    root, box = temp_workspace
    
    # Overwriting or reading git hooks must be blocked
    with pytest.raises(PermissionError, match="denied by security policy"):
        box.write_file(".git/hooks/pre-commit", "echo malicious")

    with pytest.raises(PermissionError, match="denied by security policy"):
        box.read_file(".git/hooks/pre-commit")

    with pytest.raises(PermissionError, match="denied by security policy"):
        box.delete_file(".git/hooks/pre-commit")


def test_run_python_shell_injection_protection(temp_workspace):
    root, box = temp_workspace
    
    # Attempting to inject shell commands into run_python path must fail safely
    with pytest.raises((FileNotFoundError, ValueError, PermissionError)):
        box.run_python('main.py" & whoami & echo "')


def test_run_python_safe_execution(temp_workspace):
    root, box = temp_workspace
    
    res = box.run_python("main.py")
    assert "hello" in res


def test_list_files_filters_protected(temp_workspace):
    root, box = temp_workspace
    
    file_list = box.list_files(".").splitlines()
    assert "main.py" in file_list
    assert ".env.example" in file_list
    assert ".env" not in file_list
    assert ".git" not in file_list
    assert ".devmate" not in file_list
