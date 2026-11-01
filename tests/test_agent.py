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


def test_agent_multi_turn_conversation_memory_retention(agent_workspace):
    cfg, box = agent_workspace
    agent = Agent(cfg, box)

    # Turn 1: Propose side income plan
    resp1 = {
        "type": "text",
        "message": {
            "role": "assistant",
            "content": "Here is a 3-step side income plan: 1. freelancing, 2. micro-SaaS, 3. open-source tools."
        }
    }
    # Turn 2: Acknowledge user agreement
    resp2 = {
        "type": "text",
        "message": {
            "role": "assistant",
            "content": "Excellent! Let's start with Step 2 (micro-SaaS)."
        }
    }

    agent.provider.chat = MagicMock(side_effect=[resp1, resp2])

    # Execute Turn 1
    out1 = agent.run("can you suggest a side income plan?")
    assert "3-step side income plan" in out1
    assert len(agent.history) == 2  # [user, assistant]

    # Execute Turn 2
    out2 = agent.run("i agree with the side income plan you suggested, let's start with step 2")
    assert "Step 2" in out2
    assert len(agent.history) == 4  # [user1, asst1, user2, asst2]

    # Verify that in Turn 2, the provider was sent the full conversation history
    call2_messages = agent.provider.chat.call_args_list[1][0][0]
    roles_and_contents = [(m["role"], m.get("content", "")) for m in call2_messages]

    # Check that system prompt is present
    assert roles_and_contents[0][0] == "system"
    # Check that Turn 1 user prompt is present
    assert any(r == "user" and "side income plan" in c for r, c in roles_and_contents)
    # Check that Turn 1 assistant plan is present
    assert any(r == "assistant" and "micro-SaaS" in c for r, c in roles_and_contents)
    # Check that Turn 2 user prompt is present
    assert any(r == "user" and "agree with the side income plan" in c for r, c in roles_and_contents)

    # Verify persistent storage on disk
    convo_file = cfg.devmate_dir / "conversation.json"
    assert convo_file.exists()
    disk_data = json.loads(convo_file.read_text(encoding="utf-8"))
    assert len(disk_data) == 4

    # Verify loaded on new agent instance
    agent_reloaded = Agent(cfg, box)
    assert len(agent_reloaded.history) == 4


def test_agent_reset_clears_memory(agent_workspace):
    cfg, box = agent_workspace
    agent = Agent(cfg, box)
    resp = {"type": "text", "message": {"role": "assistant", "content": "Done."}}
    agent.provider.chat = MagicMock(return_value=resp)

    agent.run("Initial prompt")
    assert len(agent.history) == 2

    # Reset
    agent.reset()
    assert len(agent.history) == 0
    convo_file = cfg.devmate_dir / "conversation.json"
    assert not convo_file.exists()


def test_agent_remember_fact_tool(agent_workspace):
    cfg, box = agent_workspace
    agent = Agent(cfg, box)

    # Tool call: remember_fact
    remember_call = {
        "type": "tool",
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-rem",
                    "type": "function",
                    "function": {
                        "name": "remember_fact",
                        "arguments": json.dumps({
                            "category": "decisions",
                            "fact": "Agreed on micro-SaaS side income plan: API monitoring tool"
                        })
                    }
                }
            ]
        }
    }
    final_resp = {
        "type": "text",
        "message": {"role": "assistant", "content": "Decision saved to project memory."}
    }
    agent.provider.chat = MagicMock(side_effect=[remember_call, final_resp])

    agent.run("Remember this decision")
    mem_data = box.memory.load()
    assert "Agreed on micro-SaaS side income plan: API monitoring tool" in mem_data.get("decisions", [])
