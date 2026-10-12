"""Unit tests for multi-agent delegation and dual-provider swarm collaboration."""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from devmate.config import Config
from devmate.tools import ToolBox
from devmate.subagent import SubAgent, MultiAgentSwarm, READONLY_TOOL_NAMES


@pytest.fixture
def agent_workspace(tmp_path):
    (tmp_path / "app.py").write_text("def add(a, b): return a + b\n", encoding="utf-8")
    cfg = Config(
        root=tmp_path,
        provider="google",
        google_key="fake-google-key",
        openrouter_key="fake-openrouter-key"
    )
    box = ToolBox(cfg, approve=lambda q: True)
    return cfg, box


def test_subagent_role_tool_isolation(agent_workspace):
    cfg, box = agent_workspace
    sub_researcher = SubAgent(cfg, box, role="researcher", provider_name="google")

    # Researcher must only have read-only tools
    for tool_decl in sub_researcher.tools:
        name = tool_decl["function"]["name"]
        assert name in READONLY_TOOL_NAMES
        assert name not in {"write_file", "edit_file", "delete_file"}


def test_subagent_peer_provider_selection(agent_workspace):
    cfg, box = agent_workspace
    # When lead provider is google, peer must be openrouter
    sub_peer = SubAgent(cfg, box, role="reviewer", provider_name="peer")
    assert sub_peer.provider_name == "openrouter"

    # When lead provider is openrouter, peer must be google
    cfg.provider = "openrouter"
    sub_peer_2 = SubAgent(cfg, box, role="reviewer", provider_name="peer")
    assert sub_peer_2.provider_name == "google"


def test_subagent_execution(agent_workspace):
    cfg, box = agent_workspace
    sub = SubAgent(cfg, box, role="researcher", provider_name="google")

    # Mock provider chat response
    sub.provider.chat = MagicMock(return_value={
        "type": "text",
        "message": {"role": "assistant", "content": "Found function add(a, b) in app.py:1."}
    })

    report = sub.execute("What functions are defined in app.py?")
    assert "SubAgent Report: RESEARCHER" in report
    assert "Found function add(a, b) in app.py:1." in report


def test_toolbox_delegate_task(agent_workspace):
    cfg, box = agent_workspace

    with patch("devmate.subagent.SubAgent.execute", return_value="--- [SubAgent Report: RESEARCHER (google)] ---\nCode verified\n--- [End Report] ---"):
        report = box.delegate_task(role="researcher", prompt="Inspect app.py", provider="google")
        assert "Code verified" in report


def test_multiagent_swarm_collaborate(agent_workspace):
    cfg, box = agent_workspace
    swarm = MultiAgentSwarm(cfg, box)

    with patch("devmate.subagent.SubAgent.execute", side_effect=[
        "Proposed plan: add multiplication function.",
        "Critique: ensure type hints and docstrings are added.",
        "Final consensus: implementation ready."
    ]):
        result = swarm.collaborate("Add math functions")
        assert "Final consensus" in result
