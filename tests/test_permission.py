"""Unit tests for interactive permission and approval modals (Day 2)."""

import pytest
from unittest.mock import MagicMock, patch
from devmate.config import Config
from devmate.tools import ToolBox
from devmate.agent import Agent
from devmate.ui import (
    RiskLevel,
    PermissionRequest,
    PermissionDecision,
    classify_risk,
    render_permission_card,
    prompt_permission,
)


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "app.py").write_text("print('hello')", encoding="utf-8")
    (tmp_path / "temp.txt").write_text("temporary file", encoding="utf-8")
    cfg = Config(root=tmp_path, allow_delete=False, allow_commands=False)
    box = ToolBox(cfg, approve=lambda req: True)
    return tmp_path, cfg, box


def test_render_permission_card_low_risk():
    req = PermissionRequest(
        action="Read File",
        target="README.md",
        risk=RiskLevel.LOW,
        details="Safe read operation",
    )
    card = render_permission_card(req)
    assert "Permission Required" in card
    assert "Read File" in card
    assert "README.md" in card
    assert "LOW RISK" in card
    assert "[1]" in card
    assert "[2]" in card
    assert "[3]" in card
    assert "[4]" in card


def test_render_permission_card_medium_risk():
    req = PermissionRequest(
        action="Modify Configuration",
        target="config.py",
        risk=RiskLevel.MEDIUM,
        details="Updating timeout settings",
    )
    card = render_permission_card(req)
    assert "MEDIUM RISK" in card
    assert "Modify Configuration" in card
    assert "Updating timeout settings" in card


def test_render_permission_card_high_risk():
    req = PermissionRequest(
        action="Destructive Shell Command",
        target="rm -rf .",
        risk=RiskLevel.HIGH,
        details="Critical filesystem operation",
    )
    card = render_permission_card(req)
    assert "HIGH RISK" in card
    assert "Destructive Shell Command" in card


def test_render_permission_card_with_diff():
    diff_content = """--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-print('hello')
+print('world')"""
    req = PermissionRequest(
        action="Edit File",
        target="app.py",
        risk=RiskLevel.MEDIUM,
        diff=diff_content,
    )
    card = render_permission_card(req)
    assert "Preview Diff:" in card
    assert "print('world')" in card


def test_prompt_permission_proceed_by_digit():
    req = PermissionRequest(action="Test Action", target="target.py")
    with patch("builtins.input", return_value="1"):
        decision = prompt_permission(req)
        assert decision.approved is True
        assert decision.action == "proceed"
        assert bool(decision) is True


def test_prompt_permission_proceed_by_y():
    req = PermissionRequest(action="Test Action", target="target.py")
    with patch("builtins.input", return_value="yes"):
        decision = prompt_permission(req)
        assert decision.approved is True
        assert decision.action == "proceed"


def test_prompt_permission_default_enter():
    req = PermissionRequest(action="Test Action", target="target.py")
    with patch("builtins.input", return_value=""):
        decision = prompt_permission(req)
        assert decision.approved is True
        assert decision.action == "proceed"


def test_prompt_permission_abort_by_digit():
    req = PermissionRequest(action="Delete File", target="target.py", risk=RiskLevel.HIGH)
    with patch("builtins.input", return_value="3"):
        decision = prompt_permission(req)
        assert decision.approved is False
        assert decision.action == "abort"
        assert bool(decision) is False


def test_prompt_permission_abort_by_n():
    req = PermissionRequest(action="Delete File", target="target.py", risk=RiskLevel.HIGH)
    with patch("builtins.input", return_value="n"):
        decision = prompt_permission(req)
        assert decision.approved is False
        assert decision.action == "abort"


def test_prompt_permission_inspect_diff_then_proceed():
    diff_mock = MagicMock(return_value="--- a\n+++ b\n+new_line")
    req = PermissionRequest(action="Edit File", target="app.py", diff="diff preview")

    # User inputs '2' to inspect diff, then '1' to proceed
    with patch("builtins.input", side_effect=["2", "1"]):
        decision = prompt_permission(req, diff_viewer=diff_mock)
        assert decision.approved is True
        assert decision.action == "proceed"
        assert decision.view_diff is True


def test_prompt_permission_custom_feedback_option_4():
    req = PermissionRequest(action="Run Migration", target="db.py")
    with patch("builtins.input", side_effect=["4", "Use SQLite instead of PostgreSQL"]):
        decision = prompt_permission(req)
        assert decision.approved is False
        assert decision.action == "feedback"
        assert decision.feedback == "Use SQLite instead of PostgreSQL"


def test_prompt_permission_direct_feedback():
    req = PermissionRequest(action="Delete File", target="old.py")
    with patch("builtins.input", return_value="Don't delete, archive to backup folder instead"):
        decision = prompt_permission(req)
        assert decision.approved is False
        assert decision.action == "feedback"
        assert "archive to backup" in decision.feedback


def test_prompt_permission_interrupt_graceful():
    req = PermissionRequest(action="Run Command", target="pytest")
    with patch("builtins.input", side_effect=KeyboardInterrupt):
        decision = prompt_permission(req)
        assert decision.approved is False
        assert decision.action == "abort"
        assert "cancelled" in decision.feedback.lower()


def test_prompt_permission_eof_error():
    req = PermissionRequest(action="Run Command", target="pytest")
    with patch("builtins.input", side_effect=EOFError):
        decision = prompt_permission(req)
        assert decision.approved is False
        assert decision.action == "abort"


def test_prompt_permission_option_4_interrupt():
    req = PermissionRequest(action="Run Migration", target="db.py")
    with patch("builtins.input", side_effect=["4", KeyboardInterrupt]):
        decision = prompt_permission(req)
        assert decision.approved is False
        assert decision.action == "abort"
        assert "cancelled" in decision.feedback.lower()


def test_prompt_permission_option_2_details_fallback():
    req = PermissionRequest(action="Inspect Config", target="config.py", details="Config details here")
    with patch("builtins.input", side_effect=["2", "3"]):
        decision = prompt_permission(req)
        assert decision.approved is False
        assert decision.action == "abort"
        assert decision.view_diff is True


def test_prompt_permission_string_argument():
    with patch("builtins.input", return_value="1"):
        decision = prompt_permission("Delete file.txt? [y/N]")
        assert decision.approved is True
        assert decision.action == "proceed"


def test_classify_risk():
    assert classify_risk("Delete File", "app.py") == RiskLevel.HIGH
    assert classify_risk("Shell Command", "rm -rf /") == RiskLevel.HIGH
    assert classify_risk("Shell Command", "format C:") == RiskLevel.HIGH
    assert classify_risk("Shell Command", "pytest -v") == RiskLevel.MEDIUM
    assert classify_risk("Run Python Script", "main.py") == RiskLevel.MEDIUM
    assert classify_risk("Read File", "sample.txt") == RiskLevel.LOW
    assert classify_risk("Git Status", "") == RiskLevel.LOW
    assert classify_risk("Inspect Diff", "app.py") == RiskLevel.LOW


def test_permission_decision_bool_eval():
    d_ok = PermissionDecision(approved=True, action="proceed")
    d_no = PermissionDecision(approved=False, action="abort")
    assert bool(d_ok) is True
    assert bool(d_no) is False
    assert "approved=True" in repr(d_ok)


def test_toolbox_ask_permission_backward_compatible_bool(workspace):
    _, cfg, _ = workspace
    box_true = ToolBox(cfg, approve=lambda req: True)
    dec_true = box_true.ask_permission("Test string prompt")
    assert dec_true.approved is True

    box_false = ToolBox(cfg, approve=lambda req: False)
    dec_false = box_false.ask_permission("Test string prompt")
    assert dec_false.approved is False


def test_toolbox_delete_file_interactive_permission(workspace):
    tmp_path, cfg, _ = workspace
    cfg.allow_delete = False

    # Simulate user rejecting delete
    box = ToolBox(cfg, approve=lambda req: PermissionDecision(approved=False, action="abort"))
    res = box.delete_file("temp.txt")
    assert "cancelled by user" in res.lower()
    assert (tmp_path / "temp.txt").exists()

    # Simulate user approving delete
    box_ok = ToolBox(cfg, approve=lambda req: PermissionDecision(approved=True, action="proceed"))
    res_ok = box_ok.delete_file("temp.txt")
    assert "Deleted temp.txt" in res_ok
    assert not (tmp_path / "temp.txt").exists()


def test_toolbox_run_command_high_risk_permission(workspace):
    _, cfg, _ = workspace
    box_denied = ToolBox(cfg, approve=lambda req: PermissionDecision(approved=False, action="abort"))
    res = box_denied.run_command("format C:")
    assert "blocked by security policy" in res.lower()


def test_toolbox_run_python_permission(workspace):
    _, cfg, _ = workspace
    cfg.allow_commands = False
    box_denied = ToolBox(cfg, approve=lambda req: PermissionDecision(approved=False, action="abort"))
    res = box_denied.run_python("app.py")
    assert "cancelled by user" in res.lower()


def test_agent_engineer_checkpoint_with_feedback(workspace):
    _, cfg, box = workspace
    agent = Agent(cfg, box)

    # Mock agent.run to simulate 1 iteration
    agent.run = MagicMock(return_value="Iteration completed successfully.")
    box.git_diff = MagicMock(return_value="+ new code")

    # Mock ask_permission to return feedback on first call, then stop on second
    decisions = [
        PermissionDecision(approved=False, action="feedback", feedback="Add unit tests before proceeding"),
        PermissionDecision(approved=False, action="abort"),
    ]
    box.ask_permission = MagicMock(side_effect=decisions)

    with patch("builtins.print") as mock_print:
        agent.engineer("Build feature X", autonomous=False)

    # Verify guidance was acknowledged
    assert box.ask_permission.call_count >= 1
    first_call_req = box.ask_permission.call_args_list[0][0][0]
    assert isinstance(first_call_req, PermissionRequest)
    assert first_call_req.action == "Engineering Checkpoint"
