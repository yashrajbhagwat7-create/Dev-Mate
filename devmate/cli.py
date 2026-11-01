"""Interactive Command Line Interface for Dev-Mate with multi-line paste,
file ingestion, token optimization, and dual-provider swarm collaboration.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from .config import Config
from .tools import ToolBox
from .agent import Agent
from .reader import InputReader
from .subagent import MultiAgentSwarm
from .ui import (
    banner, badge, panel, style, Color, colorize_diff,
    prompt_clarification, prompt_permission,
    render_doctor_card, render_plan_card
)


def print_help():
    help_text = f"""
  {style('Interactive Slash Commands:', Color.BOLD, Color.BRIGHT_WHITE)}
    {style('/provider', Color.CYAN):<18} Switch model provider ({style('openrouter', Color.GREEN)} | {style('google', Color.GREEN)} | {style('ollama', Color.GREEN)})
    {style('/mode', Color.CYAN):<18} Change mode ({style('ask', Color.YELLOW)} | {style('edit', Color.YELLOW)} | {style('engineer', Color.YELLOW)} | {style('autonomous', Color.YELLOW)})
    {style('/team <goal>', Color.CYAN):<18} Run dual-provider swarm ({style('Gemini + OpenRouter side-by-side', Color.BRIGHT_MAGENTA)})
    {style('/plan <goal>', Color.CYAN):<18} Formulate structured implementation plan before editing
    {style('/review [path]', Color.CYAN):<18} Request independent code review from the peer model
    {style('/doctor', Color.CYAN):<18} Run health check on environment, git & AI providers
    {style('/file <path>', Color.CYAN):<18} Ingest a large text file directly as your prompt
    {style('/outline <path>', Color.CYAN):<18} Inspect file structural outline (AST classes & functions)
    {style('/grep <pat>', Color.CYAN):<18} Search workspace text using regular expressions
    {style('/commit <msg>', Color.CYAN):<18} Stage tracked modifications and create a git commit
    {style('/undo', Color.CYAN):<18} Revert the most recent file mutation from backup
    {style('/rollback <path>', Color.CYAN):<18} Restore a specific file from its latest backup
    {style('/paste', Color.CYAN):<18} Enter multi-line paste mode (paste huge text, type :end to submit)
    {style('/editor', Color.CYAN):<18} Open external editor (Notepad) to write/paste large prompts
    {style('/tokens', Color.CYAN):<18} View session API token usage & compaction savings
    {style('/lint <path>', Color.CYAN):<18} Lint document/report for tables, styles & formatting (--fix)
    {style('/report', Color.CYAN):<18} Generate project audit report and structured memory export
    {style('/status', Color.CYAN):<18} View current git working tree status
    {style('/diff', Color.CYAN):<18} View current git diff with syntax highlighting
    {style('/memory', Color.CYAN):<18} Display structured project memory
    {style('/history', Color.CYAN):<18} Display recent activity audit log
    {style('/refs <sym> [p]', Color.CYAN):<18} Locate all AST references and call sites of a symbol
    {style('/syntax <path>', Color.CYAN):<18} Check file syntax (Python, JSON, TOML, MD, HTML) without running
    {style('/deps [path]', Color.CYAN):<18} Analyze package dependencies & detect circular import cycles
    {style('/test [target]', Color.CYAN):<18} Execute test suite and display structured diagnostic results
    {style('/audit [path]', Color.CYAN):<18} Export full session audit & compliance ledger to markdown
    {style('/clear', Color.CYAN):<18} Clear terminal screen buffer
    {style('/help', Color.CYAN):<18} Show this command reference
    {style('/exit', Color.CYAN):<18} Exit Dev-Mate session

  {style('Input Window Features:', Color.BOLD, Color.BRIGHT_WHITE)}
    • {style('Large Text / Paste', Color.BRIGHT_CYAN)}: Paste multi-line text or code blocks directly into the prompt.
    • {style('Multi-Line Input', Color.BRIGHT_CYAN)}: Wrap prompt in {style("'''", Color.YELLOW)} or press {style('Alt+Enter', Color.YELLOW)} for newlines.
    • {style('Inline File Context', Color.BRIGHT_CYAN)}: Reference any file with {style('@path/to/file', Color.BRIGHT_MAGENTA)} to auto-inline its contents!
"""
    print(help_text)


def main():
    parser = argparse.ArgumentParser(prog="devmate", description="Dev-Mate AI Software Engineering Agent")

    parser.add_argument("--root", default=".", help="Project workspace root directory")
    parser.add_argument("--provider", choices=["openrouter", "google", "ollama"], help="AI Model provider")
    parser.add_argument("--mode", choices=["ask", "edit", "engineer", "autonomous", "plan"], help="Operation mode")
    parser.add_argument("--doctor", action="store_true", help="Run workspace and provider health check and exit")
    parser.add_argument("--test", action="store_true", help="Run project test suite and exit")

    args = parser.parse_args()

    root = Path(args.root).resolve()
    cfg = Config(root=root)

    if args.provider:
        cfg.provider = args.provider

    if args.mode:
        cfg.mode = args.mode

    box = ToolBox(cfg, approve=prompt_permission, clarify=prompt_clarification)

    if args.doctor:
        health = box.run_doctor()
        print(f"\n{render_doctor_card(health)}\n")
        return

    if args.test:
        test_out = box.run_tests()
        try:
            d = json.loads(test_out)
            st = d.get("status")
            col = Color.BRIGHT_GREEN if st == "PASS" else Color.BRIGHT_RED
            bd = badge("PASS", "pass") if st == "PASS" else badge("FAIL", "fail")
            print(f"\n{bd} {style(d.get('summary', ''), Color.BOLD, col)} ({d.get('duration', 0)}s)\n")
            if d.get("failures"):
                for fail_trace in d["failures"]:
                    print(f"\n{panel('Failure Details', fail_trace, border_color=Color.BRIGHT_RED)}")
            sys.exit(d.get("exit_code", 0))
        except Exception:
            print(test_out)
            sys.exit(0)
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
            info_text = "\n".join(info)
            print(f"\n{panel('API Token Optimization Stats', info_text, border_color=Color.BRIGHT_GREEN)}")
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

        # Structural outline command
        if prompt.startswith("/outline"):
            parts = prompt.split(None, 1)
            if len(parts) < 2:
                print(f"{badge('WARN', 'warn')} Usage: /outline <path>")
                continue
            out = box.view_outline(parts[1].strip())
            print(f"\n{panel('File Structure Outline', out, border_color=Color.BRIGHT_CYAN)}")
            continue

        # Undo last file mutation
        if prompt == "/undo":
            res = box.undo_last_change()
            print(f"\n{badge('UNDO', 'warn')} {style(res, Color.BOLD, Color.BRIGHT_YELLOW)}")
            continue

        # Rollback specific file
        if prompt.startswith("/rollback"):
            parts = prompt.split(None, 1)
            if len(parts) < 2:
                print(f"{badge('WARN', 'warn')} Usage: /rollback <path>")
                continue
            res = box.rollback_file(parts[1].strip())
            print(f"\n{badge('ROLLBACK', 'warn')} {style(res, Color.BOLD, Color.BRIGHT_YELLOW)}")
            continue

        # Export session audit report
        if prompt in {"/report", "/export"}:
            rep = box.memory.export_summary()
            print(f"\n{panel('Project Audit & Memory Report', rep, border_color=Color.BRIGHT_GREEN)}")
            continue

        # Environment & provider doctor health check
        if prompt in {"/doctor", ":doctor"}:
            health = box.run_doctor()
            print(f"\n{render_doctor_card(health)}")
            continue

        # Implementation plan mode
        if prompt.startswith("/plan"):
            parts = prompt.split(None, 1)
            if len(parts) < 2 or not parts[1].strip():
                print(f"{badge('WARN', 'warn')} Usage: /plan <goal>")
                continue
            goal = parts[1].strip()
            plan_res = box.plan_task(goal)
            print(f"\n{render_plan_card(goal, plan_res)}")
            continue

        # Regex grep search
        if prompt.startswith("/grep"):
            parts = prompt.split(None, 1)
            if len(parts) < 2 or not parts[1].strip():
                print(f"{badge('WARN', 'warn')} Usage: /grep <regex_pattern>")
                continue
            res = box.grep_search(parts[1].strip())
            print(f"\n{panel('Regex Search Matches', res, border_color=Color.BRIGHT_CYAN)}")
            continue

        # Git commit tracked modifications
        if prompt.startswith("/commit"):
            parts = prompt.split(None, 1)
            if len(parts) < 2 or not parts[1].strip():
                print(f"{badge('WARN', 'warn')} Usage: /commit <message>")
                continue
            res = box.git_commit(parts[1].strip())
            print(f"\n{badge('GIT', 'cyan')} {res}")
            continue

        # Test runner command
        if prompt.startswith("/test"):
            parts = prompt.split(None, 1)
            target = parts[1].strip() if len(parts) > 1 else ""
            print(f"\n{badge('RUNNING', 'cyan')} Running test suite...")
            res = box.run_tests(test_target=target)
            try:
                data = json.loads(res)
                st = data.get("status")
                col = Color.BRIGHT_GREEN if st == "PASS" else Color.BRIGHT_RED
                bd = badge("PASS", "pass") if st == "PASS" else badge("FAIL", "fail")
                print(f"\n{bd} {style(data.get('summary', ''), Color.BOLD, col)} ({data.get('duration', 0)}s)")
                if data.get("failures"):
                    for fail_trace in data["failures"]:
                        print(f"\n{panel('Failure Details', fail_trace, border_color=Color.BRIGHT_RED)}")
            except Exception:
                print(f"\n{res}")
            continue

        # Syntax validator
        if prompt.startswith("/syntax"):
            parts = prompt.split(None, 1)
            if len(parts) < 2:
                print(f"{badge('WARN', 'warn')} Usage: /syntax <path>")
                continue
            res = box.check_syntax(parts[1].strip())
            try:
                data = json.loads(res)
                st = data.get("status")
                if st == "VALID":
                    print(f"\n{badge('VALID', 'pass')} {style(data.get('message', ''), Color.BRIGHT_GREEN)}")
                else:
                    err_txt = f"{data.get('type')}: {data.get('error')}\nLine: {data.get('line', '?')}, Column: {data.get('column', '?')}"
                    if data.get("snippet"):
                        err_txt += f"\n\n{data.get('snippet')}"
                    print(f"\n{panel('Syntax Error Detected', err_txt, border_color=Color.BRIGHT_RED)}")
            except Exception:
                print(f"\n{res}")
            continue

        # Symbol references finder
        if prompt.startswith("/refs"):
            parts = prompt.split(None, 2)
            if len(parts) < 2:
                print(f"{badge('WARN', 'warn')} Usage: /refs <symbol> [optional_path]")
                continue
            sym = parts[1].strip()
            p_filter = parts[2].strip() if len(parts) > 2 else None
            res = box.find_references(sym, path=p_filter)
            try:
                data = json.loads(res)
                tot = data.get("total_matches", 0)
                print(f"\n{badge('REFS', 'cyan')} Found {style(str(tot), Color.BOLD, Color.BRIGHT_WHITE)} reference(s) to '{sym}':")
                ref_lines = []
                for r in data.get("references", []):
                    ref_lines.append(f"{style(r.get('file'), Color.CYAN)}:{style(str(r.get('line')), Color.YELLOW)} [{style(r.get('scope'), Color.DIM)}] {r.get('code')}")
                if ref_lines:
                    print("\n".join(ref_lines[:30]))
            except Exception:
                print(f"\n{res}")
            continue

        # Dependency analyzer
        if prompt.startswith("/deps"):
            parts = prompt.split(None, 1)
            p_filter = parts[1].strip() if len(parts) > 1 else None
            res = box.analyze_dependencies(path=p_filter)
            try:
                data = json.loads(res)
                ext = ", ".join(data.get("third_party_dependencies", [])) or "None"
                std = ", ".join(data.get("standard_library_modules", [])[:10])
                has_cycle = data.get("circular_dependencies_detected")
                cycle_msg = style("YES! (Check cycles below)", Color.BRIGHT_RED) if has_cycle else style("None detected", Color.BRIGHT_GREEN)
                summary = [
                    f"Files Analyzed       : {data.get('total_files_analyzed')}",
                    f"Third-Party Libs     : {ext}",
                    f"Stdlib Modules       : {std}...",
                    f"Circular Imports     : {cycle_msg}"
                ]
                summary_text = "\n".join(summary)
                print(f"\n{panel('Workspace Dependency Analysis', summary_text, border_color=Color.BRIGHT_MAGENTA)}")
            except Exception:
                print(f"\n{res}")
            continue

        # Export audit log markdown
        if prompt.startswith("/audit"):
            parts = prompt.split(None, 1)
            out_p = parts[1].strip() if len(parts) > 1 else None
            res = box.export_audit_log(output_path=out_p)
            print(f"\n{badge('AUDIT', 'pass')} {style(res, Color.BOLD, Color.BRIGHT_GREEN)}")
            continue

        # Clear screen
        if prompt in {"/clear", ":clear", "clear", "cls"}:
            os.system("cls" if os.name == "nt" else "clear")
            continue

        # Provider switch
        if prompt.startswith("/provider"):
            parts = prompt.split(None, 1)
            valid_providers = {"openrouter", "google", "ollama", "local"}
            if len(parts) < 2 or parts[1].strip() not in valid_providers:
                print(f"{badge('WARN', 'warn')} Usage: /provider openrouter | google | ollama")
                continue

            provider = parts[1].strip()
            cfg.provider = provider
            agent = Agent(cfg, box)
            swarm = MultiAgentSwarm(cfg, box)
            if cfg.provider in {"google", "gemini"}:
                current_model = cfg.google_model
            elif cfg.provider in {"ollama", "local"}:
                current_model = cfg.ollama_model
            else:
                current_model = cfg.openrouter_model
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

            history_text = "\n".join(lines)
            print(f"\n{panel('Recent Activity Log', history_text, border_color=Color.BRIGHT_BLUE)}")
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