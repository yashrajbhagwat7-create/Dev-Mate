"""Terminal UI formatting, colors, and visual presentation for Dev-Mate."""

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Union, Callable, Any

# Detect color support
_USE_COLOR = sys.stdout.isatty() and os.getenv("NO_COLOR") is None

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if os.name == "nt":
    # Enable ANSI escape sequences on Windows
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass


class Color:
    RESET = "\033[0m" if _USE_COLOR else ""
    BOLD = "\033[1m" if _USE_COLOR else ""
    DIM = "\033[2m" if _USE_COLOR else ""
    ITALIC = "\033[3m" if _USE_COLOR else ""
    UNDERLINE = "\033[4m" if _USE_COLOR else ""

    # Foreground colors
    BLACK = "\033[30m" if _USE_COLOR else ""
    RED = "\033[31m" if _USE_COLOR else ""
    GREEN = "\033[32m" if _USE_COLOR else ""
    YELLOW = "\033[33m" if _USE_COLOR else ""
    BLUE = "\033[34m" if _USE_COLOR else ""
    MAGENTA = "\033[35m" if _USE_COLOR else ""
    CYAN = "\033[36m" if _USE_COLOR else ""
    WHITE = "\033[37m" if _USE_COLOR else ""

    # Bright foreground
    BRIGHT_BLACK = "\033[90m" if _USE_COLOR else ""
    BRIGHT_RED = "\033[91m" if _USE_COLOR else ""
    BRIGHT_GREEN = "\033[92m" if _USE_COLOR else ""
    BRIGHT_YELLOW = "\033[93m" if _USE_COLOR else ""
    BRIGHT_BLUE = "\033[94m" if _USE_COLOR else ""
    BRIGHT_MAGENTA = "\033[95m" if _USE_COLOR else ""
    BRIGHT_CYAN = "\033[96m" if _USE_COLOR else ""
    BRIGHT_WHITE = "\033[97m" if _USE_COLOR else ""


def style(text: str, *styles: str) -> str:
    """Apply styling to text."""
    if not _USE_COLOR:
        return text
    prefix = "".join(styles)
    return f"{prefix}{text}{Color.RESET}"


def badge(label: str, style_name: str = "cyan") -> str:
    """Format a status badge."""
    colors = {
        "pass": (Color.BOLD, Color.BRIGHT_GREEN),
        "green": (Color.BOLD, Color.BRIGHT_GREEN),
        "fail": (Color.BOLD, Color.BRIGHT_RED),
        "red": (Color.BOLD, Color.BRIGHT_RED),
        "warn": (Color.BOLD, Color.BRIGHT_YELLOW),
        "yellow": (Color.BOLD, Color.BRIGHT_YELLOW),
        "tool": (Color.BOLD, Color.BRIGHT_CYAN),
        "cyan": (Color.BOLD, Color.BRIGHT_CYAN),
        "magenta": (Color.BOLD, Color.BRIGHT_MAGENTA),
        "info": (Color.BOLD, Color.BRIGHT_BLUE),
        "dim": (Color.DIM, Color.WHITE),
    }
    st = colors.get(style_name.lower(), (Color.BOLD, Color.BRIGHT_CYAN))
    return f"{style(f'[{label}]', *st)}"


def agent_badge(provider: str, role: str = "") -> str:
    """Format a styled badge identifying an agent's provider and role."""
    p = provider.lower()
    if "google" in p or "gemini" in p:
        icon = "🤖"
        color = Color.BRIGHT_CYAN
        p_name = "GEMINI"
    elif "openrouter" in p:
        icon = "🧠"
        color = Color.BRIGHT_MAGENTA
        p_name = "OPENROUTER"
    else:
        icon = "⚡"
        color = Color.BRIGHT_YELLOW
        p_name = provider.upper()

    role_str = f":{role.upper()}" if role else ""
    return f"{icon} {style(f'[{p_name}{role_str}]', Color.BOLD, color)}"


def banner(root: str, provider: str, mode: str, model: str = "") -> str:
    """Generate a sleek, modern startup banner for Dev-Mate."""
    logo = f"""
  {style('█▀▄ █▀▀ █░█', Color.BOLD, Color.BRIGHT_CYAN)}  {style('█▀▄▀█ ▄▀█ ▀█▀ █▀▀', Color.BOLD, Color.BRIGHT_MAGENTA)}
  {style('█▄▀ ██▄ ▀▄▀', Color.BOLD, Color.BRIGHT_CYAN)}  {style('█░▀░█ █▀█ ░█░ ██▄', Color.BOLD, Color.BRIGHT_MAGENTA)}
  {style('AI Software Engineering Agent', Color.DIM, Color.WHITE)} {style('v0.1.0', Color.BRIGHT_GREEN)}
"""
    divider = style("─" * 60, Color.DIM, Color.BRIGHT_BLACK)
    info_lines = [
        f"  {style('Root', Color.BOLD, Color.WHITE):<12} : {style(str(root), Color.CYAN)}",
        f"  {style('Provider', Color.BOLD, Color.WHITE):<12} : {style(provider, Color.BRIGHT_GREEN)}" + (f" {style(f'({model})', Color.DIM)}" if model else ""),
        f"  {style('Mode', Color.BOLD, Color.WHITE):<12} : {style(mode.upper(), Color.BRIGHT_YELLOW, Color.BOLD)}",
    ]
    return f"{logo}\n{divider}\n" + "\n".join(info_lines) + f"\n{divider}\n"


def panel(title: str, content: str, border_color: str = Color.BRIGHT_CYAN) -> str:
    """Display content inside a rounded border card."""
    lines = content.splitlines() or [""]
    max_len = max(len(title) + 4, max((len(line) for line in lines), default=20))
    width = min(max(max_len, 50), 76)

    top_border = f"╭─ {style(title, Color.BOLD, Color.WHITE)} " + "─" * max(0, width - len(title) - 4) + "╮"
    bot_border = "╰" + "─" * (width - 1) + "╯"

    card = [style(top_border, border_color)]
    for line in lines:
        card.append(f"│ {line}")
    card.append(style(bot_border, border_color))
    return "\n".join(card)


def colorize_diff(diff_text: str) -> str:
    """Syntax highlight git diff output."""
    if not diff_text or not _USE_COLOR:
        return diff_text

    colored_lines = []
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            colored_lines.append(style(line, Color.BOLD, Color.WHITE))
        elif line.startswith("+"):
            colored_lines.append(style(line, Color.BRIGHT_GREEN))
        elif line.startswith("-"):
            colored_lines.append(style(line, Color.BRIGHT_RED))
        elif line.startswith("@@"):
            colored_lines.append(style(line, Color.BRIGHT_CYAN))
        elif line.startswith("diff --git"):
            colored_lines.append(style(line, Color.BOLD, Color.BRIGHT_YELLOW))
        else:
            colored_lines.append(line)
    return "\n".join(colored_lines)


def render_clarification_card(question: str, options: list = None) -> str:
    """Format an interactive clarification modal card."""
    clean_options = [str(o).strip() for o in (options or []) if str(o).strip()]
    lines = [
        f"{style('Question:', Color.BOLD, Color.BRIGHT_WHITE)} {question}",
    ]
    if clean_options:
        lines.append("")
        lines.append(f"{style('Select an option or type a custom answer:', Color.DIM)}")
        for idx, opt in enumerate(clean_options, 1):
            lines.append(f"  {style(f'[{idx}]', Color.BOLD, Color.BRIGHT_CYAN)} {opt}")
        lines.append(f"  {style(f'[{len(clean_options) + 1}]', Color.DIM)} Custom response (type directly)")

    return panel("❓ Clarification Needed", "\n".join(lines), border_color=Color.BRIGHT_YELLOW)


def prompt_clarification(question: str, options: list = None) -> str:
    """Display clarification card and collect user choice or custom text input."""
    clean_options = [str(o).strip() for o in (options or []) if str(o).strip()]
    card = render_clarification_card(question, clean_options)
    print(f"\n{card}")

    prompt_label = (
        f"  {style('Enter selection [1-' + str(len(clean_options)) + '] or write answer', Color.BOLD, Color.BRIGHT_YELLOW)}: "
        if clean_options else
        f"  {style('Your answer', Color.BOLD, Color.BRIGHT_YELLOW)}: "
    )

    try:
        ans = input(prompt_label).strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return "Clarification interrupted by user."

    if not ans:
        if clean_options:
            return clean_options[0]
        return "No specific clarification provided."

    if clean_options and ans.isdigit():
        idx = int(ans)
        if 1 <= idx <= len(clean_options):
            return clean_options[idx - 1]

    return ans


class RiskLevel:
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class PermissionRequest:
    action: str
    target: str = ""
    risk: str = "MEDIUM"
    details: str = ""
    diff: str = ""

    def __str__(self) -> str:
        target_str = f" on '{self.target}'" if self.target else ""
        return f"{self.action}{target_str} [Risk: {self.risk}]"


class PermissionDecision:
    """Structured decision returned by the permission protocol."""

    def __init__(
        self,
        approved: bool,
        action: str = "proceed",
        feedback: str = "",
        view_diff: bool = False,
    ):
        self.approved = approved
        self.action = action  # "proceed", "diff", "abort", "feedback"
        self.feedback = feedback
        self.view_diff = view_diff

    def __bool__(self) -> bool:
        return self.approved

    def __repr__(self) -> str:
        return (
            f"<PermissionDecision approved={self.approved} "
            f"action='{self.action}' feedback='{self.feedback}'>"
        )


DANGEROUS_COMMAND_PATTERNS = [
    r"format\s+[a-zA-Z]:",
    r"del\s+/[fFqsSQ\s]*[cC]:\\",
    r"rm\s+-rf\s+[/~]",
    r":\(\)\s*\{\s*:\|:&\s*\};:",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\brm\s+-[rf]{1,2}\b",
    r"\brmdir\s+/[sq]\b",
    r"\bdel\s+/[fqs]\b",
    r"\bformat\b",
    r"\bdrop\s+database\b",
    r"\bdrop\s+table\b",
    r"\btruncate\s+table\b",
    r"\bkill\b",
    r"\bshutdown\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\s+-[fdx]{1,3}\b",
]


def classify_risk(action: str, target: str = "") -> str:
    """Classify an action's risk level into LOW, MEDIUM, or HIGH."""
    combined = f"{action} {target}".lower()

    if any(re.search(pat, combined, re.IGNORECASE) for pat in DANGEROUS_COMMAND_PATTERNS):
        return RiskLevel.HIGH
    if any(kw in action.lower() for kw in ["delete", "remove", "destroy", "wipe", "drop"]):
        return RiskLevel.HIGH

    low_keywords = [
        "read", "search", "list", "status", "diff",
        "summary", "checkpoint", "inspect", "clarification"
    ]
    if any(kw in action.lower() for kw in low_keywords) and not any(k in combined for k in ["delete", "drop", "destroy", "format", "rm"]):
        return RiskLevel.LOW

    return RiskLevel.MEDIUM


def render_permission_card(request: PermissionRequest) -> str:
    """Format an interactive permission modal card matching Antigravity style."""
    risk = (request.risk or RiskLevel.MEDIUM).upper()
    if risk == RiskLevel.HIGH:
        border_col = Color.BRIGHT_RED
        risk_badge = f"{style('🔴 HIGH RISK', Color.BOLD, Color.BRIGHT_RED)}"
    elif risk == RiskLevel.LOW:
        border_col = Color.BRIGHT_GREEN
        risk_badge = f"{style('🟢 LOW RISK', Color.BOLD, Color.BRIGHT_GREEN)}"
    else:
        border_col = Color.BRIGHT_YELLOW
        risk_badge = f"{style('🟡 MEDIUM RISK', Color.BOLD, Color.BRIGHT_YELLOW)}"

    lines = [
        f"{style('Action:', Color.BOLD, Color.BRIGHT_WHITE)} {request.action}",
    ]
    if request.target:
        lines.append(f"{style('Target:', Color.BOLD, Color.BRIGHT_WHITE)} {request.target}")
    lines.append(f"{style('Risk Level:', Color.BOLD, Color.BRIGHT_WHITE)} {risk_badge}")

    if request.details:
        lines.append("")
        lines.append(f"{style('Details:', Color.BOLD, Color.BRIGHT_WHITE)} {request.details}")

    if request.diff:
        lines.append("")
        lines.append(f"{style('Preview Diff:', Color.BOLD, Color.BRIGHT_WHITE)}")
        diff_lines = request.diff.strip().splitlines()
        for dl in diff_lines[:6]:
            if dl.startswith("+"):
                lines.append(f"  {style(dl[:70], Color.BRIGHT_GREEN)}")
            elif dl.startswith("-"):
                lines.append(f"  {style(dl[:70], Color.BRIGHT_RED)}")
            else:
                lines.append(f"  {dl[:70]}")
        if len(diff_lines) > 6:
            lines.append(f"  {style(f'... [{len(diff_lines) - 6} more lines, select [2] to inspect full diff]', Color.DIM)}")

    lines.append("")
    lines.append(f"{style('Select an option or write custom feedback:', Color.DIM)}")
    lines.append(f"  {style('[1]', Color.BOLD, Color.BRIGHT_GREEN)} Proceed with change")
    lines.append(f"  {style('[2]', Color.BOLD, Color.BRIGHT_CYAN)} Inspect full diff / details")
    lines.append(f"  {style('[3]', Color.BOLD, Color.BRIGHT_RED)} Abort / Skip")
    lines.append(f"  {style('[4]', Color.BOLD, Color.BRIGHT_MAGENTA)} Provide feedback / custom instructions")

    return panel("🛡️ Permission Required", "\n".join(lines), border_color=border_col)


def prompt_permission(
    request: Union[PermissionRequest, str],
    diff_viewer: Optional[Callable[[], str]] = None,
) -> PermissionDecision:
    """Display interactive permission modal and collect user decision."""
    if isinstance(request, str):
        risk = classify_risk("Confirmation", request)
        req = PermissionRequest(
            action="Confirmation Required",
            target=request.strip(),
            risk=risk,
        )
    else:
        req = request

    viewed_diff = False

    while True:
        card = render_permission_card(req)
        print(f"\n{card}")

        prompt_label = (
            f"  {style('Enter selection [1-4] or write feedback', Color.BOLD, Color.BRIGHT_YELLOW)} "
            f"{style('(default: [1] Proceed)', Color.DIM)}: "
        )

        try:
            ans = input(prompt_label).strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return PermissionDecision(approved=False, action="abort", feedback="Cancelled by user (Ctrl+C).", view_diff=viewed_diff)

        # Default or Option 1: Proceed
        if not ans or ans.lower() in {"1", "y", "yes", "proceed"}:
            return PermissionDecision(approved=True, action="proceed", view_diff=viewed_diff)

        # Option 2: Inspect full diff / details
        if ans.lower() in {"2", "v", "view", "diff"}:
            viewed_diff = True
            if req.diff:
                print(f"\n{panel('Full Diff Preview', colorize_diff(req.diff), border_color=Color.BRIGHT_CYAN)}")
            elif diff_viewer:
                try:
                    d = diff_viewer()
                    print(f"\n{panel('Full Diff Preview', colorize_diff(d) if d else 'No diff detected.', border_color=Color.BRIGHT_CYAN)}")
                except Exception as e:
                    print(f"\n{panel('Diff Viewer Error', str(e), border_color=Color.BRIGHT_RED)}")
            else:
                details_text = req.details or "No additional diff or details available."
                print(f"\n{panel('Details', details_text, border_color=Color.BRIGHT_CYAN)}")
            continue

        # Option 3: Abort / Skip
        if ans.lower() in {"3", "n", "no", "abort", "skip", "cancel"}:
            return PermissionDecision(approved=False, action="abort", view_diff=viewed_diff)

        # Option 4: Custom instructions prompt
        if ans == "4":
            try:
                feedback = input(f"  {style('Your instructions / feedback', Color.BOLD, Color.BRIGHT_MAGENTA)}: ").strip()
            except (KeyboardInterrupt, EOFError):
                print()
                return PermissionDecision(approved=False, action="abort", feedback="Feedback entry cancelled.", view_diff=viewed_diff)
            return PermissionDecision(
                approved=False,
                action="feedback",
                feedback=feedback or "User requested alternative approach.",
                view_diff=viewed_diff,
            )

        # Any custom response typed directly
        return PermissionDecision(approved=False, action="feedback", feedback=ans, view_diff=viewed_diff)


def render_lint_report(report: Any) -> str:
    """Format a styled document quality report card with scores and highlighted issues."""
    if hasattr(report, "score"):
        score = report.score
        file_path = report.file_path
        summary = report.summary
        crit = report.critical_count
        warn = report.warning_count
        info = report.info_count
        issues = report.issues
    elif isinstance(report, dict):
        score = report.get("score", 0)
        file_path = report.get("file_path", "")
        summary = report.get("summary", "")
        crit = report.get("critical_count", 0)
        warn = report.get("warning_count", 0)
        info = report.get("info_count", 0)
        issues = report.get("issues", [])
    else:
        return str(report)

    if score >= 90:
        score_style = (Color.BOLD, Color.BRIGHT_GREEN)
        score_badge = badge(f"SCORE {score}/100", "pass")
    elif score >= 70:
        score_style = (Color.BOLD, Color.BRIGHT_YELLOW)
        score_badge = badge(f"SCORE {score}/100", "warn")
    else:
        score_style = (Color.BOLD, Color.BRIGHT_RED)
        score_badge = badge(f"SCORE {score}/100", "fail")

    lines = [
        f"{style('Target:', Color.BOLD, Color.WHITE)} {style(file_path, Color.CYAN)}",
        f"{style('Rating:', Color.BOLD, Color.WHITE)} {score_badge} - {style(summary, *score_style)}",
        f"{style('Issues:', Color.BOLD, Color.WHITE)} {badge(str(crit), 'fail')} Critical  {badge(str(warn), 'warn')} Warnings  {badge(str(info), 'info')} Notices",
    ]

    if not issues:
        lines.append("")
        lines.append(f"  {style('[OK] All design, typography, and table integrity checks passed.', Color.BRIGHT_GREEN)}")
    else:
        lines.append("")
        lines.append(style("Findings & Recommendations:", Color.BOLD, Color.UNDERLINE))
        for iss in issues[:15]:
            sev = getattr(iss, "severity", None)
            sev_str = sev.value if hasattr(sev, "value") else str(iss.get("severity", ""))
            line_no = getattr(iss, "line", 0) or (iss.get("line") if isinstance(iss, dict) else 0)
            cat = getattr(iss, "category", "") or (iss.get("category", "") if isinstance(iss, dict) else "")
            msg = getattr(iss, "message", "") or (iss.get("message", "") if isinstance(iss, dict) else "")
            sug = getattr(iss, "suggestion", "") or (iss.get("suggestion", "") if isinstance(iss, dict) else "")

            sev_badge = badge(sev_str, "fail" if sev_str == "CRITICAL" else ("warn" if sev_str == "WARNING" else "info"))
            loc = f"Line {line_no}: " if line_no > 0 else ""
            lines.append(f"  {sev_badge} {style(loc, Color.DIM)}{style(cat, Color.BOLD)}: {msg}")
            if sug:
                lines.append(f"    {style('-> Fix:', Color.DIM, Color.BRIGHT_CYAN)} {style(sug, Color.DIM)}")

        if len(issues) > 15:
            lines.append(f"  ... [and {len(issues) - 15} more issues]")

    display_name = Path(file_path).name if file_path else "Report"
    return panel(f"Document Quality Linter: {display_name}", "\n".join(lines), border_color=Color.BRIGHT_MAGENTA)


