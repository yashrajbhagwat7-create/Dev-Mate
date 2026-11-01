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


def test_record_mistake(memory_fixture):
    mem = memory_fixture
    mem.record_mistake(
        mistake_type="ImportError",
        description="Missing requests package",
        context="import requests failed",
        correction="Added requests to requirements.txt",
        files_affected=["requirements.txt"]
    )
    mistakes = mem.load_mistakes()
    assert len(mistakes) == 1
    assert mistakes[0]["type"] == "ImportError"
    assert mistakes[0]["correction"] == "Added requests to requirements.txt"

    # Deduplication check
    mem.record_mistake(
        mistake_type="ImportError",
        description="Missing requests package"
    )
    mistakes_after = mem.load_mistakes()
    assert len(mistakes_after) == 1
    assert mistakes_after[0]["occurrences"] == 2


def test_export_summary(memory_fixture):
    mem = memory_fixture
    mem.remember("decisions", "Adopt SQLite for cache")
    mem.remember("important_files", "devmate/agent.py")
    mem.log("EDIT", "Updated devmate/agent.py", "PASS")

    summary = mem.export_summary()
    assert "Dev-Mate Project Memory & Audit Report" in summary
    assert "Adopt SQLite for cache" in summary
    assert "`devmate/agent.py`" in summary
    assert "EDIT" in summary


def test_search_and_clear_activity(memory_fixture):
    mem = memory_fixture
    mem.log("BUILD", "Build success", "PASS")
    mem.log("TEST", "92 passed", "PASS")

    hits = mem.search_activity("build")
    assert len(hits) == 1
    assert hits[0]["action"] == "BUILD"

    mem.clear_activity()
    assert len(mem.recent_activity()) == 0

