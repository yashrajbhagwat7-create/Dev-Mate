"""Terminal UI formatting, colors, and visual presentation for Dev-Mate."""

import os
import sys

# Detect color support
_USE_COLOR = sys.stdout.isatty() and os.getenv("NO_COLOR") is None

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
