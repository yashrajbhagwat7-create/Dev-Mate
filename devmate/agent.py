import json
import time
from .providers import make_provider


SYSTEM = """You are Dev-Mate, a careful AI software engineer operating on a real local project.
You have tools to inspect, edit, execute and verify code. The application, not you, executes tools.

Rules:
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
"""


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List project files.",
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
            "description": "Read a text file with line numbers.",
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
            "description": "Run a Python file from the project root.",
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
            "description": "Summarize project structure.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
]


class Agent:
    def __init__(self, config, toolbox):
        self.config = config
        self.toolbox = toolbox
        self.provider = make_provider(config)
        self.history = []

        self.dispatch = {
            n["function"]["name"]: getattr(toolbox, n["function"]["name"])
            for n in TOOL_SCHEMAS
        }

    def _call(self, messages):
        for turn in range(self.config.max_agent_turns):
            result = self.provider.chat(messages, TOOL_SCHEMAS)

            msg = result["message"]
            messages.append(msg)

            calls = msg.get("tool_calls", [])

            if not calls:
                return msg.get("content", "")

            for call in calls:
                name = call["function"]["name"]

                try:
                    args = json.loads(
                        call["function"].get("arguments", "{}")
                    )
                except Exception:
                    args = {}

                if name not in self.dispatch:
                    out = f"Unknown tool: {name}"
                else:
                    try:
                        print(
                            f"\n[tool] {name}("
                            f"{json.dumps(args, ensure_ascii=False)[:500]})"
                        )

                        out = self.dispatch[name](**args)

                    except Exception as e:
                        out = (
                            f"TOOL ERROR: "
                            f"{type(e).__name__}: {e}"
                        )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "name": name,
                        "content": str(out)
                    }
                )

        return "Stopped: maximum agent turns reached."

    def run(self, user_prompt, mode=None):
        mode = mode or self.config.mode

        context = self.toolbox.project_summary()

        memory_context = self.toolbox.memory.get_context()

        recent = self.toolbox.memory.recent_activity(limit=10)

        recent_context = json.dumps(
            recent,
            indent=2,
            ensure_ascii=False
        )

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
            {
                "role": "system",
                "content": system_context
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ]

        result = self._call(messages)

        self.toolbox.memory.log(
            "AGENT",
            user_prompt[:500],
            "PASS"
        )

        return result

    def engineer(self, goal, autonomous=False):
        max_iter = self.config.max_engineering_iterations

        for i in range(1, max_iter + 1):
            print(
                f"\n{'=' * 70}\n"
                f"ENGINEERING ITERATION {i}/{max_iter}\n"
                f"{'=' * 70}"
            )

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

            print("\n" + result)

            if not autonomous or not self.config.auto_approve_checkpoints:
                ans = input(
                    "\nCheckpoint: continue to the next improvement? "
                    "[Y/n/v=show git diff/r=revert manually] "
                ).strip().lower()

                if ans in {"n", "no", "stop", "q"}:
                    break

                if ans == "v":
                    print(self.toolbox.git_diff())

                    ans = input(
                        "Continue? [Y/n] "
                    ).strip().lower()

                    if ans in {"n", "no"}:
                        break

        print("\nEngineering loop stopped.")