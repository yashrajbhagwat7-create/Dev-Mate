"""Unit tests for Dev-Mate persistent memory and activity logging."""

import pytest
from devmate.config import Config
from devmate.memory import Memory


@pytest.fixture
def memory_fixture(tmp_path):
    cfg = Config(root=tmp_path)
    mem = Memory(cfg)
    return mem


def test_remember_and_load(memory_fixture):
    mem = memory_fixture
    mem.remember("decisions", "Use FastAPI for backend")
    mem.remember("preferences", {"theme": "dark"})

    data = mem.load()
    assert "Use FastAPI for backend" in data["decisions"]
    assert data["preferences"].get("theme") == "dark"


def test_forget(memory_fixture):
    mem = memory_fixture
    mem.remember("decisions", "Use Flask")
    mem.remember("decisions", "Use FastAPI")

    mem.forget("decisions", "Use Flask")
    data = mem.load()
    assert "Use Flask" not in data["decisions"]
    assert "Use FastAPI" in data["decisions"]


def test_activity_logging_and_truncation(memory_fixture):
    mem = memory_fixture
    huge_details = "A" * 1000
    mem.log("HUGE_ACTION", huge_details, "PASS")

    recent = mem.recent_activity(limit=5)
    assert len(recent) == 1
    assert recent[0]["action"] == "HUGE_ACTION"
    # Verify detail was truncated to prevent prompt context explosion
    assert len(recent[0]["details"]) <= 350
    assert recent[0]["details"].endswith("...")
