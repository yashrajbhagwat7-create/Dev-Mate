"""Context window management, dynamic token budgeting, and intelligent compaction.
Optimizes API consumption on large codebases by preventing token explosion.
"""

import json
import math
from typing import Any, Dict, List, Tuple


def estimate_tokens(val: Any) -> int:
    """Heuristic token estimator (~3.6 characters per token for code/JSON/text)."""
    if val is None:
        return 0
    if isinstance(val, (int, float, bool)):
        return 1
    if isinstance(val, str):
        return max(1, math.ceil(len(val) / 3.6))
    if isinstance(val, (list, dict)):
        try:
            dumped = json.dumps(val, ensure_ascii=False)
            return max(1, math.ceil(len(dumped) / 3.6))
        except Exception:
            return 10
    return max(1, math.ceil(len(str(val)) / 3.6))


def estimate_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    """Calculate the estimated token size of an entire messages list."""
    total = 0
    for m in messages:
        total += 4
        total += estimate_tokens(m.get("content", ""))
        for tc in m.get("tool_calls", []):
            total += 8
            fn = tc.get("function", {})
            total += estimate_tokens(fn.get("name", ""))
            total += estimate_tokens(fn.get("arguments", ""))
    return total


def compress_text(text: str, max_chars: int = 1800, head_lines: int = 15, tail_lines: int = 25) -> str:
    """Compress verbose output by keeping critical head and tail context while omitting middle bulk."""
    if len(text) <= max_chars:
        return text

    lines = text.splitlines()
    if len(lines) <= head_lines + tail_lines:
        return text[:max_chars] + "\n... [truncated]"

    head = "\n".join(lines[:head_lines])
    omitted_count = len(lines) - head_lines - tail_lines
    tail = "\n".join(lines[-tail_lines:])

    return f"{head}\n\n... [{omitted_count} lines omitted to optimize API token usage] ...\n\n{tail}"


def compact_tool_output(tool_name: str, content: str, turn_index: int = 0) -> str:
    """Create a high-density, low-token summary of an older tool output."""
    if "TOOL ERROR" in content or "SECURITY ERROR" in content or "FileNotFoundError" in content:
        return content[:400]

    if tool_name == "read_file":
        lines = content.splitlines()
        first_line = lines[0] if lines else ""
        return f"[File content ({len(lines)} lines) previously read and processed in turn {turn_index}: {first_line[:80]}...]"

    if tool_name == "list_files":
        count = len(content.splitlines())
        return f"[Project files ({count} files) previously listed and indexed in turn {turn_index}]"

    if tool_name == "search_files":
        matches = len([l for l in content.splitlines() if ":" in l])
        return f"[Search results ({matches} matches) previously analyzed in turn {turn_index}]"

    if tool_name in {"run_command", "run_python"}:
        try:
            data = json.loads(content)
            code = data.get("returncode", 0)
            return f"[Execution finished with returncode {code} (output analyzed in turn {turn_index})]"
        except Exception:
            return f"[Command output previously verified in turn {turn_index}]"

    if tool_name in {"git_diff", "git_status"}:
        return f"[{tool_name} previously inspected in turn {turn_index}]"

    return compress_text(content, max_chars=400, head_lines=5, tail_lines=5)


def optimize_conversation(
    messages: List[Dict[str, Any]],
    max_tokens: int = 16000,
    keep_recent_turns: int = 2
) -> Tuple[List[Dict[str, Any]], int, int]:
    """
    Intelligently compacts earlier turns when conversation approaches token limits.
    Guarantees that system prompt, user goal, and the most recent N turns remain intact.
    Returns (optimized_messages, final_tokens, tokens_saved).
    """
    initial_tokens = estimate_messages_tokens(messages)
    if initial_tokens <= max_tokens or len(messages) <= 3:
        return messages, initial_tokens, 0

    optimized = [dict(m) for m in messages]

    # Preserve the last (keep_recent_turns * 2) messages uncompacted
    preserve_count = max(2, keep_recent_turns * 2)
    cutoff_index = max(2, len(optimized) - preserve_count)

    # Pass 1: Compact tool outputs in older turns (from index 2 to cutoff_index)
    for idx in range(2, cutoff_index):
        msg = optimized[idx]
        if msg.get("role") == "tool":
            tool_name = msg.get("name", "tool")
            content = str(msg.get("content", ""))
            if len(content) > 150:
                turn_num = idx // 2
                optimized[idx]["content"] = compact_tool_output(tool_name, content, turn_num)

    current_tokens = estimate_messages_tokens(optimized)

    # Pass 2: If still over budget, compress older assistant messages
    if current_tokens > max_tokens:
        for idx in range(2, cutoff_index):
            msg = optimized[idx]
            content = str(msg.get("content", ""))
            if len(content) > 300:
                optimized[idx]["content"] = compress_text(content, max_chars=300)

    final_tokens = estimate_messages_tokens(optimized)
    saved_tokens = max(0, initial_tokens - final_tokens)

    return optimized, final_tokens, saved_tokens


class TokenTracker:
    """Tracks token consumption and savings across the agent session."""

    def __init__(self):
        self.total_prompt_tokens = 0
        self.total_saved_tokens = 0
        self.api_calls_count = 0

    def record_call(self, prompt_tokens: int, saved_tokens: int = 0):
        self.api_calls_count += 1
        self.total_prompt_tokens += prompt_tokens
        self.total_saved_tokens += saved_tokens

    def badge_str(self, current_tokens: int, saved_tokens: int = 0) -> str:
        if saved_tokens > 0:
            pct = int((saved_tokens / (current_tokens + saved_tokens)) * 100)
            return f"~{current_tokens:,} tokens (saved ~{pct}% via compaction)"
        return f"~{current_tokens:,} tokens"
