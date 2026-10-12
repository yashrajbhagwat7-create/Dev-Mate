"""Multi-agent delegation, specialized subagents, and dual-provider collaboration
(Google Gemini and OpenRouter operating side-by-side).
"""

import json
import time
from typing import Any, Dict, List, Optional

from .providers import get_provider, ProviderError
from .ui import agent_badge, badge, panel, style, Color
from .context import optimize_conversation, TokenTracker


ROLE_SYSTEM_PROMPTS = {
    "researcher": """You are the Codebase Researcher subagent in Dev-Mate.
Your goal is to inspect project files, search symbols, and deliver a concise, highly accurate technical summary to the lead engineer.
Rules:
- You have read-only tools. You do NOT make changes.
- Cite exact file names, functions, classes, and line numbers.
- Be dense and factual; avoid fluff.
""",
    "reviewer": """You are the Code Reviewer and Critic subagent in Dev-Mate.
Your goal is to evaluate plans, code changes, git diffs, and security boundaries.
Rules:
- Critique thoroughly: find edge cases, logic flaws, regressions, performance bottlenecks, and security risks.
- If the plan/code is solid, confirm why and suggest optimizations.
- Be constructive, precise, and actionable.
""",
    "debugger": """You are the Debugger subagent in Dev-Mate.
Your goal is to diagnose test failures, stack traces, and unexpected execution behavior.
Rules:
- Pinpoint the exact root cause from output logs and files.
- Propose targeted, minimal fixes rather than large speculative rewrites.
""",
    "general": """You are an autonomous subagent working in Dev-Mate under the lead engineer.
Accomplish the assigned objective with your available tools and return a clear, structured report.
"""
}

# Read-only tool schemas for safe subagent delegation
READONLY_TOOL_NAMES = {"list_files", "read_file", "search_files", "project_summary", "git_status", "git_diff"}


class SubAgent:
    """Specialized subagent running under a designated provider and role."""

    def __init__(
        self,
        config,
        toolbox,
        role: str = "researcher",
        provider_name: Optional[str] = None,
        max_turns: int = 8
    ):
        self.config = config
        self.toolbox = toolbox
        self.role = role.lower()
        self.max_turns = max_turns

        # Determine provider: if "peer", select the opposite provider
        if provider_name == "peer":
            self.provider_name = "openrouter" if config.provider.lower() in {"google", "gemini"} else "google"
        elif provider_name and provider_name != "inherit":
            self.provider_name = provider_name.lower()
        else:
            self.provider_name = config.provider.lower()

        try:
            self.provider = get_provider(config, self.provider_name)
        except Exception:
            # Fallback to configured default provider
            self.provider_name = config.provider.lower()
            self.provider = get_provider(config, self.provider_name)

        # Select tools: default to read-only tools to avoid write collision
        from .agent import TOOL_SCHEMAS
        if self.role in {"researcher", "reviewer"}:
            self.tools = [t for t in TOOL_SCHEMAS if t["function"]["name"] in READONLY_TOOL_NAMES]
        else:
            self.tools = TOOL_SCHEMAS

        self.dispatch = {
            t["function"]["name"]: getattr(toolbox, t["function"]["name"])
            for t in self.tools
        }

    def execute(self, task_prompt: str) -> str:
        """Run the subagent task loop and return a structured report."""
        badge_ui = agent_badge(self.provider_name, self.role)
        print(f"\n{badge_ui} {style(f'Dispatched subagent task:', Color.BOLD)} {task_prompt[:120]}...")

        system_instruction = ROLE_SYSTEM_PROMPTS.get(self.role, ROLE_SYSTEM_PROMPTS["general"])
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": task_prompt}
        ]

        start_time = time.time()

        for turn in range(self.max_turns):
            # Apply token optimization to subagent
            messages, _, _ = optimize_conversation(messages, max_tokens=10000, keep_recent_turns=2)

            try:
                result = self.provider.chat(messages, self.tools)
            except ProviderError as pe:
                return f"[Subagent ({self.provider_name}) Error: {pe}]"

            msg = result.get("message", {})
            messages.append(msg)
            calls = msg.get("tool_calls", [])

            if not calls:
                elapsed = time.time() - start_time
                content = msg.get("content", "").strip()
                print(f"  {badge_ui} {badge('DONE', 'pass')} Finished in {elapsed:.1f}s")
                return f"\n--- [SubAgent Report: {self.role.upper()} ({self.provider_name})] ---\n{content}\n--- [End Report] ---"

            for call in calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                raw_args = fn.get("arguments", "{}")
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    args = {}

                if name in self.dispatch:
                    arg_str = json.dumps(args, ensure_ascii=False)
                    if len(arg_str) > 70:
                        arg_str = arg_str[:67] + "..."
                    print(f"    {badge_ui} {style(name, Color.CYAN)}({style(arg_str, Color.DIM)})")
                    try:
                        out = self.dispatch[name](**args)
                    except Exception as e:
                        out = f"ERROR: {e}"
                else:
                    out = f"Tool '{name}' not available to {self.role} subagent."

                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "name": name,
                    "content": str(out)
                })

        return f"[Subagent ({self.role}) reached maximum turns ({self.max_turns}).]"


class MultiAgentSwarm:
    """Orchestrates side-by-side collaborative interactions between Google Gemini and OpenRouter."""

    def __init__(self, config, toolbox):
        self.config = config
        self.toolbox = toolbox

    def collaborate(self, goal: str) -> str:
        """
        Collaborative dual-agent pipeline:
        1. Lead Agent (Primary: e.g. Gemini) analyzes the workspace and formulates a proposed plan/change.
        2. Peer Critic (Secondary: OpenRouter) independently reviews the proposal, flagging bugs and flaws.
        3. Lead Agent synthesizes the peer critique and produces the final verified output.
        """
        lead_provider = self.config.provider.lower()
        peer_provider = "openrouter" if lead_provider in {"google", "gemini"} else "google"

        header = f"DUAL-AGENT SWARM: {lead_provider.upper()} & {peer_provider.upper()}"
        print(f"\n{panel(header, f'Goal: {goal}', border_color=Color.BRIGHT_MAGENTA)}")

        # Step 1: Lead Agent drafts solution
        lead_badge = agent_badge(lead_provider, "planner")
        print(f"\n{lead_badge} {style('Phase 1: Formulating technical proposal...', Color.BOLD, Color.WHITE)}")
        lead_agent = SubAgent(self.config, self.toolbox, role="researcher", provider_name=lead_provider, max_turns=6)
        lead_prompt = f"""You are the lead technical planner. Project Goal: {goal}
Inspect the project files and draft a concise, concrete implementation plan detailing:
1. Architectural analysis
2. Exact files to modify or create
3. Potential failure modes and verification steps
"""
        lead_proposal = lead_agent.execute(lead_prompt)
        print(f"\n{panel('Phase 1 Proposal (' + lead_provider.upper() + ')', lead_proposal, border_color=Color.BRIGHT_CYAN)}")

        # Step 2: Peer Review by alternative model (OpenRouter or Gemini)
        peer_badge = agent_badge(peer_provider, "critic")
        print(f"\n{peer_badge} {style('Phase 2: Independent peer review & vulnerability critique...', Color.BOLD, Color.WHITE)}")
        peer_agent = SubAgent(self.config, self.toolbox, role="reviewer", provider_name=peer_provider, max_turns=6)
        critique_prompt = f"""You are the independent technical critic and reviewer from a second AI provider ({peer_provider}).
The lead engineer ({lead_provider}) has proposed this technical plan for the goal: '{goal}'.

PROPOSAL:
{lead_proposal}

Review this proposal critically:
1. Identify any hidden assumptions, edge-case bugs, or security oversights.
2. Verify if the suggested files and logic match the project structure.
3. Suggest concrete refinements or missing test cases.
Be direct, rigorous, and constructive.
"""
        peer_critique = peer_agent.execute(critique_prompt)
        print(f"\n{panel('Phase 2 Peer Critique (' + peer_provider.upper() + ')', peer_critique, border_color=Color.BRIGHT_MAGENTA)}")

        # Step 3: Synthesis
        print(f"\n{lead_badge} {style('Phase 3: Synthesizing consensus & final execution roadmap...', Color.BOLD, Color.WHITE)}")
        synthesis_prompt = f"""Goal: {goal}
Original Proposal ({lead_provider}):
{lead_proposal}

Peer Review Critique ({peer_provider}):
{peer_critique}

Provide the final synthesized action plan incorporating the peer critique's highest-value recommendations.
"""
        synthesizer = SubAgent(self.config, self.toolbox, role="general", provider_name=lead_provider, max_turns=4)
        final_synthesis = synthesizer.execute(synthesis_prompt)

        print(f"\n{panel('Final Dual-Agent Consensus Plan', final_synthesis, border_color=Color.BRIGHT_GREEN)}")
        return final_synthesis

    def peer_review(self, target: str = "") -> str:
        """Have the alternative provider independently review current git changes or a specific file."""
        lead_provider = self.config.provider.lower()
        peer_provider = "openrouter" if lead_provider in {"google", "gemini"} else "google"

        peer_badge = agent_badge(peer_provider, "reviewer")
        print(f"\n{peer_badge} {style('Requesting peer code review from ' + peer_provider.upper() + '...', Color.BOLD)}")

        if not target or target.strip() in {"diff", "git"}:
            context_data = self.toolbox.git_diff()
            context_title = "Git Working Tree Diff"
        else:
            try:
                context_data = self.toolbox.read_file(target.strip())
                context_title = f"File Content: {target.strip()}"
            except Exception as e:
                return f"Could not read review target: {e}"

        prompt = f"""Please perform an independent code review of the following {context_title}:

```
{context_data[:12000]}
```

Provide a structured review covering:
1. Code quality, correctness, and potential bugs
2. Security implications and edge cases
3. Performance or readability improvements
"""
        sub = SubAgent(self.config, self.toolbox, role="reviewer", provider_name=peer_provider, max_turns=4)
        review_result = sub.execute(prompt)
        print(f"\n{panel('Peer Review (' + peer_provider.upper() + ')', review_result, border_color=Color.BRIGHT_MAGENTA)}")
        return review_result
