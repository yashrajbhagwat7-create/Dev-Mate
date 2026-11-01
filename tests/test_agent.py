"""Unit tests for Dev-Mate Agent core loop, tool dispatching, and engineering execution."""

from unittest.mock import MagicMock, patch
import json
import pytest
from devmate.config import Config
from devmate.tools import ToolBox
from devmate.agent import Agent, TOOL_SCHEMAS


@pytest.fixture
def agent_workspace(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')", encoding="utf-8")
    cfg = Config(
        root=tmp_path,
        openrouter_key="test-key",
        google_key="test-key",
        allow_delete=True,
        allow_commands=True
    )
    box = ToolBox(cfg, approve=lambda q: True)
    return cfg, box


def test_agent_run_direct_text_response(agent_workspace):
    cfg, box = agent_workspace
    agent = Agent(cfg, box)

    mock_response = {
        "type": "text",
        "message": {"role": "assistant", "content": "Analysis complete."}
    }
    agent.provider.chat = MagicMock(return_value=mock_response)

    res = agent.run("Analyze the codebase")
    assert res == "Analysis complete."
    assert agent.provider.chat.call_count == 1


def test_agent_run_tool_call_and_succeeds(agent_workspace):
    cfg, box = agent_workspace
    agent = Agent(cfg, box)

    # Turn 1: request list_files
    # Turn 2: return final text
    tool_call_response = {
        "type": "tool",
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "list_files", "arguments": '{"path": "."}'}
                }
            ]
        }
    }
    final_response = {
        "type": "text",
        "message": {"role": "assistant", "content": "Found 1 file: main.py"}
    }

    agent.provider.chat = MagicMock(side_effect=[tool_call_response, final_response])

    res = agent.run("List my files")
    assert "Found 1 file" in res
    assert agent.provider.chat.call_count == 2


def test_agent_run_unknown_tool(agent_workspace):
    cfg, box = agent_workspace
    agent = Agent(cfg, box)

    unknown_tool_call = {
        "type": "tool",
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-bad",
                    "type": "function",
                    "function": {"name": "non_existent_tool", "arguments": "{}"}
                }
            ]
        }
    }
    final_response = {
        "type": "text",
        "message": {"role": "assistant", "content": "Handled unknown tool."}
    }
    agent.provider.chat = MagicMock(side_effect=[unknown_tool_call, final_response])

    res = agent.run("Trigger bad tool")
    assert res == "Handled unknown tool."


def test_agent_engineer_autonomous_iteration(agent_workspace):
    cfg, box = agent_workspace
    cfg.max_engineering_iterations = 1
    agent = Agent(cfg, box)

    agent.run = MagicMock(return_value="Iteration 1 complete: improved logging.")
    agent.engineer("Optimize logging", autonomous=True)
    assert agent.run.call_count == 1
