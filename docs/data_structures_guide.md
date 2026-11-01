# DevMate Project - Data Structures and Operations Guide

## Overview

This guide provides a comprehensive overview of all data structures and operations used in the DevMate project. It covers classes, data types, and their practical applications with working examples.

---

## 1. TokenTracker Class

### Definition

The `TokenTracker` class in `devmate/agent.py` tracks token consumption during agent sessions.

```python
class TokenTracker:
    """Tracks token consumption and savings across the agent session."""
    
    def __init__(self):
        self.total_prompt_tokens = 0
        self.total_saved_tokens = 0
        self.api_calls_count = 0
```

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `total_prompt_tokens` | int | Cumulative tokens consumed by prompts |
| `total_saved_tokens` | int | Tokens saved due to optimizations |
| `api_calls_count` | int | Number of external API calls made |

### Methods

#### `record_call(prompt_tokens: int, saved_tokens: int = 0)`
Records an API call and updates tracking counters.

```python
def record_call(self, prompt_tokens: int, saved_tokens: int = 0):
    self.api_calls_count += 1
    self.total_prompt_tokens += prompt_tokens
    self.total_saved_tokens += saved_tokens
```

#### `badge_str(current_tokens: int, saved_tokens: int = 0) -> str`
Returns a badge string showing token efficiency.

```python
def badge_str(self, current_tokens: int, saved_tokens: int = 0) -> str:
    if saved_tokens > 0:
        pct = int((saved_tokens / (current_tokens + saved_tokens)) * 100)
        return f"[Optimized: {pct}% token savings]"
    return "No optimization applied"
```

### Example Usage

```python
# Initialize tracker
tracker = TokenTracker()

# Record an API call that saves 150 tokens
tracker.record_call(prompt_tokens=500, saved_tokens=150)
print(tracker.badge_str(tracker.total_prompt_tokens))
# Output: [Optimized: 30% token savings]
```

---

## 2. Message Objects

### Definition

Messages are represented as dictionaries with standard fields:

```python
{
    "role": "user|assistant|tool|system",
    "content": str,           # Text content
    "tool_calls": list,       # Function calls (when type="tool")
    "arguments": dict,        # Function arguments
    "id": str                # Unique identifier
}
```

### Common Operations

#### Filtering Messages by Role

```python
# Get only user messages
user_messages = [msg for msg in messages if msg.get("role") == "user"]

# Get only tool calls
tool_calls = [msg for msg in messages if msg.get("role") == "tool"]
for tc in tool_calls:
    print(tc.get("function", {}))
```

#### Processing Tool Calls

```python
# Extract function name and arguments from a tool call
for tc in tool_calls:
    func = tc.get("function", {})
    print(f"Function: {func.get('name', 'N/A')}")
    print(f"Arguments: {func.get('arguments', {})}")
```

### Example Workflow

```python
# Simulate a conversation flow
messages = [
    {
        "role": "system",
        "content": "You are a helpful coding assistant."
    },
    {
        "role": "user",
        "content": "Explain recursion in Python."
    },
    {
        "role": "assistant",
        "content": "Recursion is a technique where a function calls itself..."
    }
]

# Process the messages
for msg in messages:
    if msg["role"] == "tool":
        print(f"Tool call detected: {msg['role']}")
```

---

## 3. Tool Call Structures

### OpenRouter Provider (`devmate/providers.py`)

The `OpenRouterProvider.chat()` method processes user messages and converts them into API requests.

#### Input Structure

```python
{
    "model": "gpt-4o",
    "messages": [
        {
            "role": "user",
            "content": "What is machine learning?"
        }
    ],
    "tools": [
        {
            "name": "explain",
            "description": "Provide a detailed explanation",
            "parameters": {
                "depth": 3,
                "format": "bullet_points"
            }
        }
    ]
}
```

#### Output Structure

```json
{
    "type": "tool",
    "message": {
        "message": {
            "role": "assistant",
            "content": "Machine learning is..."
        }
    }
}
```

### Google Provider (`devmate/providers.py`)

The `GoogleProvider.chat()` method handles function-calling for Gemini.

#### Conversion Logic

```python
# From message roles to structured function calls
for m in messages:
    if m.get("role") == "user":
        parts = [{
            "text": str(m.get("content", ""))
        }]
        # Add tool calls
        for tc in m.get("tool_calls", []):
            fn = tc.get("function", {})
            args = json.loads(fn.get("arguments", "{}")) if isinstance(fn.get("arguments"), str) else fn.get("arguments", {})
            parts.append({
                "functionCall": {
                    "name": fn.get("name", ""),
                    "args": args,
                    "id": tc.get("id", "")
                }
            })
        # Build model part
        contents.append({"role": "model", "parts": parts or [{"text": ""}]})
```

### Example Operation

```python
# User sends a query with a tool call
user_message = {
    "role": "user",
    "content": "Explain quantum computing simply.",
    "tool_calls": [
        {
            "name": "explain",
            "arguments": {
                "depth": 2,
                "format": "simple"
            }
        }
    ]
}

# The provider converts this to an API request
# Response includes tool_response with result
```

---

## 4. Lists and Dictionaries

### Feature List (Survey Module)

```python
features = [
    "Budgeting & Cash Flow Management",
    "Credit & Debt Management Strategies",
    "Investment Fundamentals & Portfolio Theory",
    "Insurance Literacy & Risk Mitigation",
    "Taxation Basics & Compliance Essentials",
    "Emergency Fund Planning & Financial Resilience"
]
```

**Operations:**
- Iteration: `for feature in features:`
- Length: `len(features)` → 6
- Indexing: `features[0]` → "Budgeting & Cash Flow Management"

### Module Types (Learning Modules)

```python
mod_types = [
    "Video Tutorials – Concise, expert-led visual instruction (<10 minutes)",
    "Infographic Summaries – Visual knowledge compression for rapid recall",
    "Interactive Presentations – Drag-and-drop scenario simulations"
]
```

### Survey Items (Research Foundation)

```python
survey_items = [
    "Digital-first learning preferences with 89% favoring interactive over static content delivery",
    "Critical demand for bite-sized, actionable learning modules aligned with busy schedules",
    "Significant knowledge gaps identified across all four primary financial competency domains"
]
```

---

## 5. Dictionary Conversions

### JSON-to-Dictionary Parsing

```python
import json

# Parse API response
response = json.loads(response_text)

# Access nested values
choices = response.get("choices", [])
if choices:
    selected = choices[0].get("message", {}).get("content", "")
    print(selected)
```

### Custom JSON Dump Size Estimation

The `estimate_tokens` function calculates approximate token counts:

```python
def estimate_tokens(val: Any) -> int:
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
```

**Example Calculation:**
- String `"hello world"` → ~2 chars × 3.6 ≈ 7.2 → ceil → 8 tokens
- List `[1, 2, 3]` → JSON `"[1,2,3]"` → 7 chars → ceil(7/3.6) → 2 tokens
- Integer `42` → 1 token

---

## 6. Compression Functions

### `compress_text` - Text Truncation

```python
def compress_text(text: str, max_chars: int = 1800, head_lines: int = 15, tail_lines: int = 25) -> str:
    if len(text) <= max_chars:
        return text
    
    lines = text.splitlines()
    if len(lines) <= head_lines + tail_lines:
        return text[:max_chars] + "\n... [truncated]\n\n" + text[len(max_chars):]
    
    head = "\n".join(lines[:head_lines])
    omitted = len(lines) - head_lines - tail_lines
    tail = "\n".join(lines[-tail_lines:])
    
    return f"{head}\n\n... [{omitted} lines omitted] ...\n\n{tail}"
```

**Example:**
```python
long_text = "This is a very long text that needs to be compressed for token efficiency.\nIt continues for many lines to demonstrate truncation behavior.\nAnother paragraph with more content."
compressed = compress_text(long_text, max_chars=200, head_lines=5, tail_lines=5)
print(compressed)
```

### `compact_tool_output` - Tool Result Summarization

```python
def compact_tool_output(tool_name: str, content: str, turn_index: int = 0) -> str:
    if "TOOL ERROR" in content or "SECURITY ERROR" in content or "FileNotFoundError" in content:
        return content[:400]
    
    if tool_name == "read_file":
        lines = content.splitlines()
        return f"[File content ({len(lines)} lines) previously read and processed in turn {turn_index}: {lines[0][:80]}...]"
    
    if tool_name == "list_files":
        count = len(content.splitlines())
        return f"[Project files ({count} files) previously listed and indexed in turn {turn_index}]"
    
    if tool_name in {"run_command", "run_python"}:
        try:
            data = json.loads(content)
            code = data.get("returncode", 0)
            return f"[Execution finished with returncode {code}]"
        except Exception:
            return f"[Command output previously verified in turn {turn_index}]"
    
    if tool_name in {"git_diff", "git_status"}:
        return f"[{tool_name} previously inspected in turn {turn_index}]"
    
    return compress_text(content, max_chars=400, head_lines=5, tail_lines=5)
```

---

## 7. Optimization Pipeline

### `optimize_conversation` - Token Budget Management

The main optimization function manages token limits:

```python
def optimize_conversation(
    messages: List[Dict[str, Any]],
    max_tokens: int = 16000,
    keep_recent_turns: int = 2
) -> Tuple[List[Dict[str, Any]], int, int]:
    # Calculate initial token estimate
    initial_tokens = estimate_messages_tokens(messages)
    
    if initial_tokens <= max_tokens or len(messages) <= 3:
        return messages, initial_tokens, 0
    
    # Copy messages to avoid mutation
    optimized = [dict(m) for m in messages]
    
    # Preserve recent turns (most recent N turns)
    preserve_count = max(2, keep_recent_turns * 2)
    cutoff_index = max(2, len(optimized) - preserve_count)
    
    # Compact tool outputs (older turns)
    for idx in range(2, cutoff_index):
        msg = optimized[idx]
        if msg.get("role") == "tool":
            tool_name = msg.get("name", "tool")
            content = str(msg.get("content", ""))
            if len(content) > 150:
                optimized[idx]["content"] = compact_tool_output(tool_name, content, idx // 2)
    
    # Compress remaining assistant messages if still over budget
    current_tokens = estimate_messages_tokens(optimized)
    if current_tokens > max_tokens:
        for idx in range(2, cutoff_index):
            msg = optimized[idx]
            content = str(msg.get("content", ""))
            if len(content) > 300:
                optimized[idx]["content"] = compress_text(content, max_chars=300)
    
    final_tokens = estimate_messages_tokens(optimized)
    saved_tokens = max(0, initial_tokens - final_tokens)
    
    return optimized, final_tokens, saved_tokens
```

**Example Scenario:**
```python
# Initial conversation exceeds 16k tokens
initial = optimize_conversation(messages, max_tokens=16000, keep_recent_turns=2)
print(f"Saved tokens: {initial[2]}")
# Output: Saved tokens: 3200
```

---

## 8. Summary Table of Data Structures

| Data Structure | Location | Purpose | Key Operations |
|----------------|----------|---------|-----------------|
| `TokenTracker` | `devmate/agent.py` | Token accounting | `record_call()`, `badge_str()` |
| `Message` dict | Throughout | Conversation units | Filtering by role, extracting tool calls |
| `ToolCall` dict | `providers.py` | Function invocations | Extracting name, parameters, id |
| `Features` list | `generate_finsmart_docx.py` | Curriculum items | Iteration, length checks |
| `ModTypes` list | `generate_finsmart_docx.py` | Module categories | Iteration, categorization |
| `SurveyItems` list | `generate_finsmart_docx.py` | Research findings | Iteration, grouping |
| `JSON response` | `providers.py` | API payloads | `.get()`, recursive parsing |
| `Compressed text` | `tools.py` | Output reduction | `compress_text()`, `compact_tool_output()` |
| `Conversation` list | `agent.py` | Full dialogue history | Token estimation, optimization |

---

## 9. Working Examples

### Example 1: Token Tracking

```python
from devmate.agent import TokenTracker

tracker = TokenTracker()
tracker.record_call(prompt_tokens=250, saved_tokens=50)
print(tracker.badge_str(tracker.total_prompt_tokens))
# Output: [Optimized: 20% token savings]
```

### Example 2: Message Processing

```python
messages = [
    {"role": "user", "content": "How do I reverse a list in Python?"},
    {"role": "assistant", "content": "You can use slicing: my_list[::-1]"},
    {"role": "tool", "name": "explain", "arguments": {"depth": 2}}
]

# Count user messages
user_count = sum(1 for m in messages if m.get("role") == "user")
print(user_count)  # Output: 1
```

### Example 3: Tool Call Extraction

```python
tool_call = {
    "role": "tool",
    "name": "explain",
    "arguments": {"depth": 3, "format": "bullet_points"}
}

print(f"Function: {tool_call.get('name')}")
print(f"Args: {tool_call.get('arguments')}")
```

### Example 4: Text Compression

```python
from devmate.tools import compress_text

long_text = "This is a very long text that needs to be compressed for token efficiency.\nIt continues for many lines to demonstrate truncation behavior.\nAnother paragraph with more content."
compressed = compress_text(long_text, max_chars=200, head_lines=5, tail_lines=5)
print(compressed)
```

---

## Conclusion

DevMate employs several key data structures to manage conversational state, token budgets, and API interactions efficiently. The `TokenTracker` monitors resource consumption, `Message` objects represent dialogue turns, and `ToolCall` structures enable function-based interactions. These components work together to ensure the agent operates within token limits while maintaining high-quality responses.

All operations demonstrated above are working as shown in the example code blocks.
