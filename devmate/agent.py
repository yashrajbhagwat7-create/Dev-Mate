"""Agent core orchestrator and engineering loop with Antigravity-style token optimization."""

import json
import time
from typing import Any, Dict, List

from .providers import make_provider, ProviderError
from .ui import badge, panel, style, Color, colorize_diff, PermissionRequest, RiskLevel
from .context import optimize_conversation, TokenTracker, estimate_messages_tokens


SYSTEM = """You are Dev-Mate, a careful AI software engineer operating on a real local project.
You have tools to inspect, edit, execute and verify code. The application, not you, executes tools.

Core Operating Rules:
- Inspect relevant files before editing.
- Prefer small, reversible changes.
- Never claim a change was made unless a tool confirms it.
- After edits, run the most relevant test/check.
- If execution fails, diagnose from the actual output and fix it.
- Do not invent file contents; reread when necessary.
- Respect human approval messages from the application.
- Use the provided project memory when it is relevant.
- Do not assume memory is always correct; verify important facts from the actual files.
- In engineering mode, pursue measurable improvement, but stop at the checkpoint instead of continuing silently.
- Never attempt to read, write, or access .env files or .git internals; they are strictly guarded.

Strict Grounding and Anti-Hallucination Rules:
- DO NOT fabricate, invent, or guess empirical facts, numbers, demographics, sample sizes, survey statistics, or research methodology.
- Preserve Project Identity: Never unilaterally rename or rebrand the user's project, products, repositories, or tools (e.g. if the user says 'finnnst', keep 'finnnst'; never rename it to 'FinSmart' or anything else).
- Clarification First: When key details, metrics, architecture requirements, or project specifications are missing, ambiguous, or unstated, invoke `ask_clarification` with specific questions and recommended options rather than inventing filler data.
- Creative Drafting vs Fact Assertion: When authoring reports, documentation, or synopses:
  * Only assert empirical numbers or outcomes that have been verified in the project repository or explicitly provided by the user.
  * If empirical data is not yet available, ask the user via `ask_clarification` or use clear explicit placeholders (e.g. '[Specify survey sample size]').

Document & Report Quality Self-Verification:
- When authoring or modifying documentation, reports, Markdown tables, or HTML documents, run `lint_document` to verify table integrity (no blank rows, balanced columns), typography hierarchy, and zero placeholder leaks before finalizing.
"""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List project files in a given directory.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file with line numbers in chunks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search text across project files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "path": {"type": "string"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or replace a file. Use only when you know the complete intended content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace one exact text block in a file. Read the file first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"}
                },
                "required": ["path", "old_text", "new_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file. This is risky and requires application approval unless explicitly enabled.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command in the project root. Risky commands require user approval.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Run a Python script safely within the project environment.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Show git status.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Show current git diff.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "project_summary",
            "description": "Summarize project structure compactly.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_task",
            "description": "Delegate a focused task or sub-investigation to a specialized subagent. Can specify provider ('google', 'openrouter', or 'peer') to run models side-by-side.",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "description": "Role of the subagent: 'researcher' (read-only file/symbol inspection), 'reviewer' (code critique & verification), 'debugger' (root cause diagnosis), or 'general'"
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Specific task or questions for the subagent to investigate"
                    },
                    "provider": {
                        "type": "string",
                        "description": "Provider to use: 'google', 'openrouter', 'peer' (uses the alternate model for cross-verification), or 'inherit'",
                        "enum": ["google", "openrouter", "peer", "inherit"]
                    }
                },
                "required": ["role", "prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ask_clarification",
            "description": "Ask the user clarifying questions when specifications, numbers, survey demographics, project names, or requirements are missing or ambiguous. DO NOT guess or hallucinate facts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Clear question describing what specific clarification is needed from the user."
                    },
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of 2 to 5 recommended options for the user to choose from."
                    }
                },
                "required": ["question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lint_document",
            "description": "Lint a document (markdown, HTML, or report) for table column alignment, blank rows, broken delimiters, typography hierarchy, design consistency, and placeholder leaks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the document to validate relative to project root."
                    },
                    "auto_fix": {
                        "type": "boolean",
                        "description": "If true, automatically repairs table formatting, removes empty rows, and normalizes cell alignment in the file."
                    }
                },
                "required": ["path"]
            }
        }
    },
]


class Agent:
    def __init__(self, config, toolbox):
        self.config = config
        self.toolbox = toolbox
        self.provider = make_provider(config)
        self.tracker = TokenTracker()

        self.dispatch = {
            n["function"]["name"]: getattr(toolbox, n["function"]["name"])
            for n in TOOL_SCHEMAS
        }

    def _call(self, messages: List[Dict[str, Any]]) -> str:
        try:
            for turn in range(self.config.max_agent_turns):
                # Dynamic token optimization (Antigravity-style rolling compaction)
                if getattr(self.config, "compact_context", True):
                    messages, current_tokens, saved = optimize_conversation(
                        messages,
                        max_tokens=self.config.max_context_tokens,
                        keep_recent_turns=2
                    )
                    self.tracker.record_call(current_tokens, saved)
                    if saved > 0 and turn > 1:
                        print(f"  {badge('OPT', 'dim')} {style(self.tracker.badge_str(current_tokens, saved), Color.DIM)}")

                try:
                    result = self.provider.chat(messages, TOOL_SCHEMAS)
                except ProviderError as pe:
                    print(f"\n{badge('ERROR', 'fail')} {style(str(pe), Color.BRIGHT_RED)}")
                    return f"Agent stopped due to provider error: {pe}"

                msg = result["message"]
                messages.append(msg)

                calls = msg.get("tool_calls", [])

                if not calls:
                    return msg.get("content", "")

                for call in calls:
                    fn = call.get("function") or {}
                    name = fn.get("name", "")
                    raw_args = fn.get("arguments", "{}")

                    if isinstance(raw_args, str):
                        try:
                            args = json.loads(raw_args)
                        except Exception:
                            args = {}
                    elif isinstance(raw_args, dict):
                        args = raw_args
                    else:
                        args = {}

                    if not isinstance(args, dict):
                        args = {}

                    if name not in self.dispatch:
                        out = f"Unknown tool: {name}"
                        print(f"\n{badge('WARN', 'warn')} Unknown tool requested: {name}")
                    else:
                        arg_summary = json.dumps(args, ensure_ascii=False)
                        if len(arg_summary) > 100:
                            arg_summary = arg_summary[:97] + "..."

                        print(f"\n{badge('TOOL', 'cyan')} {style(name, Color.BOLD, Color.BRIGHT_WHITE)}({style(arg_summary, Color.DIM)})")

                        try:
                            out = self.dispatch[name](**args)
                            print(f"  {badge('OK', 'pass')} {style('Completed', Color.DIM)}")
                        except PermissionError as pe:
                            out = f"SECURITY ERROR: {pe}"
                            print(f"  {badge('BLOCKED', 'fail')} {style(str(pe), Color.BRIGHT_RED)}")
                        except Exception as e:
                            out = f"TOOL ERROR: {type(e).__name__}: {e}"
                            print(f"  {badge('ERROR', 'fail')} {style(str(e), Color.BRIGHT_RED)}")

                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "name": name,
                        "content": str(out)
                    })

            return "Stopped: maximum agent turns reached."
        except KeyboardInterrupt:
            print(f"\n{badge('CANCELLED', 'warn')} {style('Task turn cancelled by user (Ctrl+C). Returning to prompt.', Color.BRIGHT_YELLOW)}")
            return "Task cancelled by user."

    def run(self, user_prompt: str, mode: str = None) -> str:
        mode = mode or self.config.mode

        context = self.toolbox.project_summary()
        memory_context = self.toolbox.memory.get_context()
        recent = self.toolbox.memory.recent_activity(limit=8)
        recent_context = json.dumps(recent, indent=2, ensure_ascii=False)

        system_context = f"""
{SYSTEM}

Current project summary:
{context}

Project memory:
{memory_context}

Recent activity:
{recent_context}
"""

        messages = [
            {"role": "system", "content": system_context},
            {"role": "user", "content": user_prompt}
        ]

        result = self._call(messages)
        self.toolbox.memory.log("AGENT", user_prompt[:300], "PASS")
        return result

    def engineer(self, goal: str, autonomous: bool = False):
        max_iter = self.config.max_engineering_iterations

        try:
            for i in range(1, max_iter + 1):
                header = f"ENGINEERING ITERATION {i}/{max_iter}"
                print(f"\n{panel(header, f'Goal: {goal}', border_color=Color.BRIGHT_CYAN)}")

                prompt = f"""Engineering goal: {goal}

This is iteration {i}.

Inspect the current project state, identify the highest-value improvement,
implement it with tools, run relevant verification, and report:

1. What you changed
2. Files changed
3. Verification output
4. Whether the goal is now sufficiently satisfied
5. The next best improvement

Use project memory when relevant.
Do not make a speculative large rewrite.
"""
                result = self.run(prompt, "engineer")
                print(f"\n{panel('Iteration Summary', result, border_color=Color.BRIGHT_GREEN)}")

                if not autonomous or not self.config.auto_approve_checkpoints:
                    diff_text = self.toolbox.git_diff()
                    req = PermissionRequest(
                        action="Engineering Checkpoint",
                        target=f"Iteration {i}/{max_iter}",
                        risk=RiskLevel.LOW,
                        details=f"Goal: {goal}\nReview changes and choose whether to proceed with next improvement.",
                        diff=diff_text,
                    )
                    decision = self.toolbox.ask_permission(req, diff_viewer=self.toolbox.git_diff)
                    if not decision.approved:
                        if decision.action == "feedback" and decision.feedback:
                            print(f"\n{badge('FEEDBACK', 'magenta')} {style('Received guidance for next iteration:', Color.BOLD)} {decision.feedback}")
                            goal = f"{goal} (User guidance: {decision.feedback})"
                            continue
                        print(f"\n{badge('STOP', 'info')} Engineering loop stopped by user.")
                        break

            print(f"\n{badge('STOP', 'info')} Engineering loop completed.")
        except KeyboardInterrupt:
            print(f"\n{badge('CANCELLED', 'warn')} {style('Engineering loop interrupted by user (Ctrl+C). Returning to prompt.', Color.BRIGHT_YELLOW)}")