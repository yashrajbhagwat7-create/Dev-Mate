"""Unit tests for clarification protocol and anti-hallucination guardrails."""

import pytest
from unittest.mock import MagicMock, patch
from devmate.config import Config
from devmate.tools import ToolBox
from devmate.agent import Agent, SYSTEM, TOOL_SCHEMAS
from devmate.ui import render_clarification_card, prompt_clarification


@pytest.fixture
def workspace(tmp_path):
    cfg = Config(root=tmp_path, allow_delete=True, allow_commands=True)
    box = ToolBox(cfg, approve=lambda q: True, clarify=lambda q, opts: "Option A")
    return cfg, box


def test_render_clarification_card():
    card = render_clarification_card(
        "What sample size was surveyed?",
        ["50-100 students", "200-500 students", "No specific numbers"]
    )
    assert "Clarification Needed" in card
    assert "What sample size was surveyed?" in card
    assert "[1]" in card
    assert "50-100 students" in card
    assert "[2]" in card
    assert "200-500 students" in card


def test_prompt_clarification_selection_by_index():
    options = ["Alpha Option", "Beta Option", "Gamma Option"]
    with patch("builtins.input", return_value="2"):
        ans = prompt_clarification("Select option", options)
        assert ans == "Beta Option"


def test_prompt_clarification_custom_text():
    options = ["Alpha Option", "Beta Option"]
    with patch("builtins.input", return_value="My custom survey had 75 students"):
        ans = prompt_clarification("Select option", options)
        assert ans == "My custom survey had 75 students"


def test_prompt_clarification_default_on_empty_input():
    options = ["Default First Option", "Second Option"]
    with patch("builtins.input", return_value=""):
        ans = prompt_clarification("Select option", options)
        assert ans == "Default First Option"


def test_prompt_clarification_interrupt_graceful():
    with patch("builtins.input", side_effect=KeyboardInterrupt):
        ans = prompt_clarification("Select option", ["A", "B"])
        assert "interrupted" in ans.lower()


def test_toolbox_ask_clarification(workspace):
    _, box = workspace
    res = box.ask_clarification(
        "Which database?",
        ["PostgreSQL", "SQLite"]
    )
    assert "User Clarification Response:" in res
    assert "Option A" in res

    # Verify memory log
    logs = box.memory.recent_activity(limit=5)
    assert any(l.get("action") == "CLARIFY" for l in logs)


def test_toolbox_ask_clarification_empty_question(workspace):
    _, box = workspace
    res = box.ask_clarification("")
    assert "Error" in res


def test_agent_tool_schema_and_dispatch(workspace):
    cfg, box = workspace
    agent = Agent(cfg, box)
    assert "ask_clarification" in agent.dispatch

    # Verify tool schema details
    schema = next(s for s in TOOL_SCHEMAS if s["function"]["name"] == "ask_clarification")
    assert "question" in schema["function"]["parameters"]["required"]
    assert "options" in schema["function"]["parameters"]["properties"]


def test_system_prompt_anti_hallucination_directives():
    assert "Strict Grounding and Anti-Hallucination Rules" in SYSTEM
    assert "DO NOT fabricate" in SYSTEM
    assert "Preserve Project Identity" in SYSTEM
    assert "ask_clarification" in SYSTEM
