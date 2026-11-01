"""Unit tests for context window optimization, compression, and token tracking."""

import pytest
from devmate.context import (
    estimate_tokens,
    estimate_messages_tokens,
    compress_text,
    compact_tool_output,
    optimize_conversation,
    TokenTracker
)


def test_estimate_tokens():
    assert estimate_tokens("hello world") >= 1
    assert estimate_tokens(None) == 0
    assert estimate_tokens(["item 1", "item 2"]) > 1


def test_compress_text():
    short_text = "line 1\nline 2"
    assert compress_text(short_text, max_chars=100) == short_text

    long_text = "\n".join(f"line {i}" for i in range(100))
    compressed = compress_text(long_text, max_chars=200, head_lines=5, tail_lines=5)
    assert "omitted to optimize API token usage" in compressed
    assert "line 0" in compressed
    assert "line 99" in compressed


def test_compact_tool_output():
    read_output = "1: import os\n2: import sys\n" + "\n".join(f"{i}: code" for i in range(3, 100))
    compacted = compact_tool_output("read_file", read_output, turn_index=2)
    assert "previously read and processed in turn 2" in compacted
    assert len(compacted) < 150


def test_optimize_conversation_reduces_tokens():
    # Build a simulated conversation where an earlier turn read a huge file
    huge_file_content = "\n".join(f"{i}: def function_{i}(): pass" for i in range(400))
    messages = [
        {"role": "system", "content": "You are Dev-Mate."},
        {"role": "user", "content": "Fix the codebase."},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"big.py"}'}}]},
        {"role": "tool", "name": "read_file", "tool_call_id": "c1", "content": huge_file_content},
        {"role": "assistant", "content": "Now checking tests.", "tool_calls": [{"id": "c2", "type": "function", "function": {"name": "run_command", "arguments": '{"command":"pytest"}'}}]},
        {"role": "tool", "name": "run_command", "tool_call_id": "c2", "content": '{"returncode":0,"stdout":"passed","stderr":""}'},
        {"role": "assistant", "content": "All tests pass."},
    ]

    initial_tokens = estimate_messages_tokens(messages)
    # Optimize with a tight budget
    optimized, final_tokens, saved = optimize_conversation(messages, max_tokens=200, keep_recent_turns=1)

    assert final_tokens < initial_tokens
    assert saved > 0
    # System and user prompt are preserved
    assert optimized[0]["content"] == "You are Dev-Mate."
    assert optimized[1]["content"] == "Fix the codebase."


def test_token_tracker():
    tracker = TokenTracker()
    tracker.record_call(prompt_tokens=1500, saved_tokens=3000)
    assert tracker.api_calls_count == 1
    assert tracker.total_prompt_tokens == 1500
    assert tracker.total_saved_tokens == 3000
    badge_text = tracker.badge_str(1500, 3000)
    assert "saved ~66%" in badge_text


def test_compact_new_tools():
    assert "previously inspected in turn 1" in compact_tool_output("view_outline", "File: calc.py (20 lines)", turn_index=1)
    assert "previously inspected in turn 2" in compact_tool_output("get_definition", "=== Class 'User' ===", turn_index=2)
    assert "mutation applied and verified in turn 3" in compact_tool_output("replace_lines", "Replaced lines", turn_index=3)
    assert "snapshot restored in turn 4" in compact_tool_output("undo_last_change", "Reverted state", turn_index=4)


def test_optimize_conversation_sliding_window_pass3():
    # Construct a multi-turn conversation with 10 user/assistant exchanges
    messages = [
        {"role": "system", "content": "You are Dev-Mate AI engineer."},
        {"role": "user", "content": "Initial project goal: build micro-SaaS."},
    ]
    for i in range(1, 10):
        messages.append({"role": "assistant", "content": f"Turn {i} detailed plan response with code examples and architectural notes." * 5})
        messages.append({"role": "user", "content": f"User follow-up question for turn {i}."})

    messages.append({"role": "assistant", "content": "Latest assistant proposal for current turn."})
    messages.append({"role": "user", "content": "Final user confirmation."})

    initial_tokens = estimate_messages_tokens(messages)
    # Tight max_tokens budget of 250 tokens
    optimized, final_tokens, saved = optimize_conversation(messages, max_tokens=250, keep_recent_turns=2)

    assert final_tokens < initial_tokens
    assert saved > 0
    # System prompt preserved
    assert optimized[0]["content"] == "You are Dev-Mate AI engineer."
    # Original task preserved
    assert optimized[1]["content"] == "Initial project goal: build micro-SaaS."
    # Pass 3 inserted omission notice
    assert any("omitted to maintain context token budget" in m.get("content", "") for m in optimized)
    # Most recent user message preserved
    assert optimized[-1]["content"] == "Final user confirmation."

