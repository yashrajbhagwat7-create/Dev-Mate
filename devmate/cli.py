"""Interactive Command Line Interface for Dev-Mate with multi-line paste,
file ingestion, token optimization, and dual-provider swarm collaboration.
"""

import argparse
import json
from pathlib import Path

from .config import Config
from .tools import ToolBox
from .agent import Agent
from .reader import InputReader
from .subagent import MultiAgentSwarm
from .ui import banner, badge, panel, style, Color, colorize_diff, prompt_clarification, prompt_permission


def print_help():
    help_text = f"""
  {style('Interactive Slash Commands:', Color.BOLD, Color.BRIGHT_WHITE)}
    {style('/provider', Color.CYAN):<18} Switch model provider ({style('openrouter', Color.GREEN)} | {style('google', Color.GREEN)})
    {style('/mode', Color.CYAN):<18} Change mode ({style('ask', Color.YELLOW)} | {style('edit', Color.YELLOW)} | {style('engineer', Color.YELLOW)} | {style('autonomous', Color.YELLOW)})
    {style('/team <goal>', Color.CYAN):<18} Run dual-provider swarm ({style('Gemini + OpenRouter side-by-side', Color.BRIGHT_MAGENTA)})
    {style('/review [path]', Color.CYAN):<18} Request independent code review from the peer model
    {style('/file <path>', Color.CYAN):<18} Ingest a large text file directly as your prompt
    {style('/paste', Color.CYAN):<18} Enter multi-line paste mode (paste huge text, type :end to submit)
    {style('/editor', Color.CYAN):<18} Open external editor (Notepad) to write/paste large prompts
    {style('/tokens', Color.CYAN):<18} View session API token usage & compaction savings
    {style('/lint <path>', Color.CYAN):<18} Lint document/report for tables, styles & formatting (--fix)
    {style('/status', Color.CYAN):<18} View current git working tree status
    {style('/diff', Color.CYAN):<18} View current git diff with syntax highlighting
    {style('/memory', Color.CYAN):<18} Display structured project memory
    {style('/history', Color.CYAN):<18} Display recent activity audit log
    {style('/help', Color.CYAN):<18} Show this command reference
    {style('/exit', Color.CYAN):<18} Exit Dev-Mate session

  {style('Input Window Features:', Color.BOLD, Color.BRIGHT_WHITE)}
    • {style('Large Text / Paste', Color.BRIGHT_CYAN)}: Paste multi-line text or code blocks directly into the prompt.
    • {style('Multi-Line Input', Color.BRIGHT_CYAN)}: Wrap prompt in {style('\"\"\"', Color.YELLOW)} or press {style('Alt+Enter', Color.YELLOW)} for newlines.
    • {style('Inline File Context', Color.BRIGHT_CYAN)}: Reference any file with {style('@path/to/file', Color.BRIGHT_MAGENTA)} to auto-inline its contents!
"""
    print(help_text)


def main():
    parser = argparse.ArgumentParser(prog="devmate", description="Dev-Mate AI Software Engineering Agent")

    parser.add_argument("--root", default=".", help="Project workspace root directory")
    parser.add_argument("--provider", choices=["openrouter", "google"], help="AI Model provider")
    parser.add_argument("--mode", choices=["ask", "edit", "engineer", "autonomous"], help="Operation mode")

    args = parser.parse_args()

    root = Path(args.root).resolve()
    cfg = Config(root=root)

    if args.provider:
        cfg.provider = args.provider

    if args.mode:
        cfg.mode = args.mode

    box = ToolBox(cfg, approve=prompt_permission, clarify=prompt_clarification)
    agent = Agent(cfg, box)
    swarm = MultiAgentSwarm(cfg, box)
    reader = InputReader(root)

    current_model = cfg.google_model if cfg.provider in {"google", "gemini"} else cfg.openrouter_model
    print(banner(str(root), cfg.provider, cfg.mode, current_model))
    print(f"  Type {style('/help', Color.CYAN)} for commands, {style('/team', Color.CYAN)} for Gemini+OpenRouter collaboration.")
    print(f"  {style('Multi-line paste supported directly', Color.DIM)} (or use {style('/file', Color.DIM)}, {style('/paste', Color.DIM)}, {style('/editor', Color.DIM)}).\n")

    while True:
        try:
            prompt = reader.read_prompt(cfg.mode)

        except KeyboardInterrupt:
            print(f"\n{style('^C (type /exit or press Ctrl+D to exit)', Color.DIM)}")
            continue
        except EOFError:
            print(f"\n{badge('EXIT', 'dim')} Goodbye!")
            break

        if not prompt:
            continue

        if prompt in {"/exit", "/quit"}:
            print(f"{badge('EXIT', 'dim')} Goodbye!")
            break

        if prompt == "/help":
            print_help()
            continue

        # Dedicated multi-line paste mode
        if prompt in {"/paste", ":paste"}:
            prompt = reader.read_paste_buffer()
            if not prompt:
                continue

        # External editor command (Notepad / nano)
        if prompt in {"/editor", "/edit"}:
            prompt = reader.open_external_editor()
            if not prompt:
                continue

        # File ingestion command: /file <path> [instruction]
        if prompt.startswith("/file"):
            loaded_prompt = reader.load_from_file(prompt)
            if not loaded_prompt:
                continue
            prompt = loaded_prompt

        # View session token optimization statistics
        if prompt == "/tokens":
            tracker = agent.tracker
            saved = tracker.total_saved_tokens
            total = tracker.total_prompt_tokens
            calls = tracker.api_calls_count
            pct = int((saved / (total + saved) * 100)) if (total + saved) > 0 else 0

            info = [
                f"API Calls Made       : {calls}",
                f"Total Prompt Tokens  : ~{total:,}",
                f"Tokens Saved (Opt)   : ~{saved:,} ({pct}% reduction)",
                f"Active Context Limit : {cfg.max_context_tokens:,} tokens",
                f"Compaction Policy    : Rolling window (Antigravity-style)"
            ]
            print(f"\n{panel('API Token Optimization Stats', '\n'.join(info), border_color=Color.BRIGHT_GREEN)}")
            continue

        # Document & Report Quality Linter
        if prompt.startswith("/lint"):
            parts = prompt.split()
            if len(parts) < 2:
                print(f"{badge('WARN', 'warn')} Usage: /lint <path> [--fix]")
                continue
            doc_path = parts[1]
            do_fix = "--fix" in parts[2:] or "-f" in parts[2:]
            try:
                box.lint_document(doc_path, auto_fix=do_fix)
            except Exception as e:
                print(f"\n{badge('ERROR', 'fail')} {style(str(e), Color.BRIGHT_RED)}")
            continue


        # Dual-Agent Swarm Collaboration (Gemini + OpenRouter side-by-side)
        if prompt.startswith("/team") or prompt.startswith("/swarm"):
            parts = prompt.split(None, 1)
            if len(parts) < 2 or not parts[1].strip():
                print(f"{badge('WARN', 'warn')} Usage: /team <goal>  (runs Gemini & OpenRouter side-by-side)")
                continue
            goal = parts[1].strip()
            try:
                swarm.collaborate(goal)
            except KeyboardInterrupt:
                print(f"\n{badge('CANCELLED', 'warn')} Multi-agent collaboration interrupted.")
            continue

        # Independent Peer Code Review (Alternative Model)
        if prompt.startswith("/review"):
            parts = prompt.split(None, 1)
            target = parts[1].strip() if len(parts) > 1 else ""
            try:
                swarm.peer_review(target)
            except KeyboardInterrupt:
                print(f"\n{badge('CANCELLED', 'warn')} Peer review interrupted.")
            continue

        # Provider switch
        if prompt.startswith("/provider"):
            parts = prompt.split(None, 1)
            if len(parts) < 2 or parts[1].strip() not in {"openrouter", "google"}:
                print(f"{badge('WARN', 'warn')} Usage: /provider openrouter | google")
                continue

            provider = parts[1].strip()
            cfg.provider = provider
            agent = Agent(cfg, box)
            swarm = MultiAgentSwarm(cfg, box)
            current_model = cfg.google_model if cfg.provider in {"google", "gemini"} else cfg.openrouter_model
            print(f"{badge('INFO', 'info')} Active provider switched to: {style(provider, Color.BOLD, Color.BRIGHT_GREEN)} ({current_model})")
            continue

        # Mode switch
        if prompt.startswith("/mode"):
            parts = prompt.split(None, 1)
            valid_modes = {"ask", "edit", "engineer", "autonomous"}
            if len(parts) < 2 or parts[1].strip() not in valid_modes:
                print(f"{badge('WARN', 'warn')} Usage: /mode ask | edit | engineer | autonomous")
                continue

            mode = parts[1].strip()
            cfg.mode = mode
            print(f"{badge('INFO', 'info')} Operating mode set to: {style(mode.upper(), Color.BOLD, Color.BRIGHT_YELLOW)}")
            continue

        # Git status
        if prompt == "/status":
            raw_status = box.git_status()
            try:
                data = json.loads(raw_status)
                status_out = data.get("stdout", "").strip() or "Clean working tree (no changes)."
            except Exception:
                status_out = raw_status
            print(f"\n{panel('Git Working Tree Status', status_out, border_color=Color.BRIGHT_CYAN)}")
            continue

        # Git diff
        if prompt == "/diff":
            raw_diff = box.git_diff()
            try:
                data = json.loads(raw_diff)
                diff_out = data.get("stdout", "").strip() or "No modified files in working tree."
            except Exception:
                diff_out = raw_diff
            print(f"\n{panel('Git Working Tree Diff', colorize_diff(diff_out), border_color=Color.BRIGHT_YELLOW)}")
            continue

        # Show project memory
        if prompt == "/memory":
            memory = box.memory.load()
            formatted = json.dumps(memory, indent=2, ensure_ascii=False)
            print(f"\n{panel('Project Memory State', formatted, border_color=Color.BRIGHT_MAGENTA)}")
            continue

        # Show recent activity
        if prompt == "/history":
            activity = box.memory.recent_activity(limit=25)
            if not activity:
                print(f"{badge('INFO', 'dim')} No activity recorded yet.")
                continue

            lines = []
            for entry in activity:
                ts = entry.get("timestamp", "")
                act = entry.get("action", "")
                details = entry.get("details", "")
                status_val = entry.get("status")

                if status_val == "PASS":
                    st_badge = badge("PASS", "pass")
                elif status_val == "FAIL":
                    st_badge = badge("FAIL", "fail")
                elif status_val:
                    st_badge = badge(status_val, "warn")
                else:
                    st_badge = ""

                lines.append(f"{style(ts, Color.DIM)} │ {style(act, Color.BOLD, Color.WHITE):<10} {st_badge} {details}")

            print(f"\n{panel('Recent Activity Log', '\n'.join(lines), border_color=Color.BRIGHT_BLUE)}")
            continue

        try:
            # Engineering loops
            if cfg.mode in {"engineer", "autonomous"}:
                agent.engineer(prompt, autonomous=(cfg.mode == "autonomous"))

            # Interactive turn execution
            else:
                response = agent.run(prompt, cfg.mode)
                if response:
                    print(f"\n{response}\n")
        except KeyboardInterrupt:
            print(f"\n{badge('CANCELLED', 'warn')} {style('Task cancelled by user (Ctrl+C). Returning to prompt.', Color.BRIGHT_YELLOW)}")


if __name__ == "__main__":
    main()