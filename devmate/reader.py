"""Advanced input reader with multi-line paste support, file ingestion,
inline @file expansion, and external editor integration.
"""

import os
import re
import sys
import tempfile
import subprocess
from pathlib import Path

from .ui import style, badge, panel, Color


class InputReader:
    """Handles multi-line input, bracketed paste, file ingestion, and editor launching."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self._session = None

        # Safely attempt to initialize prompt_toolkit only if standard interactive console exists
        if sys.stdin.isatty() and sys.stdout.isatty():
            try:
                from prompt_toolkit import PromptSession
                from prompt_toolkit.history import InMemoryHistory
                from prompt_toolkit.key_binding import KeyBindings

                kb = KeyBindings()

                @kb.add('enter')
                def _(event):
                    buf = event.current_buffer
                    text = buf.text
                    t_single = text.count("'''")
                    t_double = text.count('"""')
                    if (t_single % 2 == 1) or (t_double % 2 == 1) or text.endswith('\\'):
                        buf.insert_text('\n')
                    else:
                        buf.validate_and_handle()

                @kb.add('escape', 'enter')
                def _(event):
                    event.current_buffer.insert_text('\n')

                self._session = PromptSession(history=InMemoryHistory(), key_bindings=kb, multiline=True)
            except Exception:
                self._session = None

    def read_prompt(self, mode: str) -> str:
        """
        Prompt the user for input with full support for:
        - Multi-line pastes of arbitrary length
        - Triple-quote blocks (''' or \"\"\")
        - Trailing backslash line continuation
        """
        mode_badge = style(f"[{mode}]", Color.BOLD, Color.BRIGHT_YELLOW)
        prompt_str = f"{style('devmate', Color.BOLD, Color.BRIGHT_CYAN)} {mode_badge} {style('❯', Color.BRIGHT_WHITE)} "

        if self._session is not None and sys.stdin.isatty():
            try:
                from prompt_toolkit.formatted_text import ANSI
                text = self._session.prompt(ANSI(prompt_str)).strip()
                if (text.startswith('"""') and text.endswith('"""') and len(text) >= 6) or \
                   (text.startswith("'''") and text.endswith("'''") and len(text) >= 6):
                    text = text[3:-3].strip()
                return self.process_special_syntax(text)
            except KeyboardInterrupt:
                raise
            except EOFError:
                raise
            except Exception:
                # Fallback to standard reader on any terminal exception
                pass

        return self._fallback_multiline_input(prompt_str)

    def _fallback_multiline_input(self, prompt_str: str) -> str:
        """Fallback multi-line reader for terminals without prompt_toolkit."""
        sys.stdout.write(prompt_str)
        sys.stdout.flush()

        first_line = sys.stdin.readline()
        if not first_line:
            raise EOFError

        lines = [first_line.rstrip('\r\n')]
        full_text = lines[0]

        in_triple_double = full_text.startswith('"""') and not (full_text.endswith('"""') and len(full_text) > 3)
        in_triple_single = full_text.startswith("'''") and not (full_text.endswith("'''") and len(full_text) > 3)
        ends_with_backslash = full_text.endswith('\\')

        while in_triple_double or in_triple_single or ends_with_backslash:
            cont_prompt = f" {style('...', Color.DIM)} "
            sys.stdout.write(cont_prompt)
            sys.stdout.flush()

            next_line = sys.stdin.readline()
            if not next_line:
                break
            stripped = next_line.rstrip('\r\n')
            lines.append(stripped)

            if in_triple_double and stripped.endswith('"""'):
                break
            if in_triple_single and stripped.endswith("'''"):
                break
            ends_with_backslash = stripped.endswith('\\')

        result = "\n".join(lines).strip()
        if (result.startswith('"""') and result.endswith('"""') and len(result) >= 6) or \
           (result.startswith("'''") and result.endswith("'''") and len(result) >= 6):
            result = result[3:-3].strip()

        return self.process_special_syntax(result)

    def read_paste_buffer(self) -> str:
        """
        Interactive paste buffer mode for pasting huge documents, logs, or multi-page prompts.
        Submits on ':end', 'EOF', or Ctrl+Z/Ctrl+D.
        """
        print(f"\n{panel('Multi-Line Paste Buffer', 'Paste your text below. Type \':end\' on a new line or press Ctrl+Z / Ctrl+D to submit.', border_color=Color.BRIGHT_MAGENTA)}")
        lines = []
        while True:
            try:
                line = input()
                if line.strip() in {":end", "EOF", ":EOF", ":submit", "```"}:
                    break
                lines.append(line)
            except (EOFError, KeyboardInterrupt):
                print()
                break

        full_paste = "\n".join(lines).strip()
        if not full_paste:
            print(f"{badge('INFO', 'dim')} Paste buffer was empty.")
            return ""

        print(f"{badge('LOADED', 'pass')} Received {len(full_paste):,} characters ({len(lines)} lines).")
        return self.process_special_syntax(full_paste)

    def load_from_file(self, command_line: str) -> str:
        """
        Load a prompt directly from a local file.
        Syntax: /file <path> [optional instructions...]
        """
        parts = command_line.split(None, 2)
        if len(parts) < 2:
            print(f"{badge('WARN', 'warn')} Usage: /file <path> [optional instructions...]")
            return ""

        raw_path = parts[1].strip().strip('"').strip("'")
        extra_instruction = parts[2].strip() if len(parts) > 2 else ""

        target_file = (self.root / raw_path).resolve() if not Path(raw_path).is_absolute() else Path(raw_path)

        if not target_file.exists():
            print(f"{badge('ERROR', 'fail')} File not found: {raw_path}")
            return ""

        if not target_file.is_file():
            print(f"{badge('ERROR', 'fail')} Target is not a file: {raw_path}")
            return ""

        try:
            content = target_file.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"{badge('ERROR', 'fail')} Failed to read file: {e}")
            return ""

        print(f"{badge('FILE', 'pass')} Loaded {target_file.name} ({len(content):,} characters, {len(content.splitlines())} lines)")

        if extra_instruction:
            return f"{extra_instruction}\n\n```\n{content}\n```"
        return content

    def open_external_editor(self) -> str:
        """
        Open the system's text editor (Notepad on Windows, $EDITOR on Unix)
        to compose or paste huge multi-page prompts comfortably.
        """
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w", encoding="utf-8") as f:
            f.write("# Write or paste your prompt here. Save and close this editor when finished.\n\n")
            temp_path = Path(f.name)

        editor = os.getenv("EDITOR")
        if not editor:
            editor = "notepad.exe" if os.name == "nt" else "nano"

        try:
            print(f"{badge('EDITOR', 'info')} Opening external editor ({editor})...")
            subprocess.run([editor, str(temp_path)], check=True)
            text = temp_path.read_text(encoding="utf-8", errors="replace")
            lines = [l for l in text.splitlines() if not l.startswith("# Write or paste your prompt here")]
            result = "\n".join(lines).strip()
            if result:
                print(f"{badge('LOADED', 'pass')} Loaded {len(result):,} characters from editor.")
                return result
            print(f"{badge('INFO', 'dim')} Editor content was empty.")
            return ""
        except Exception as e:
            print(f"{badge('ERROR', 'fail')} Failed to launch editor: {e}")
            return ""
        finally:
            try:
                temp_path.unlink()
            except OSError:
                pass

    def process_special_syntax(self, prompt: str) -> str:
        """
        Expands inline `@filepath` syntax in the user prompt.
        Example: 'Analyze @README.md and fix @devmate/config.py'
        """
        if not prompt or "@" not in prompt:
            return prompt

        matches = re.findall(r"@([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]+)", prompt)
        if not matches:
            return prompt

        expanded_prompt = prompt
        injected_files = []

        for match in set(matches):
            p = (self.root / match).resolve()
            if p.exists() and p.is_file():
                try:
                    content = p.read_text(encoding="utf-8", errors="replace")
                    lines = content.splitlines()
                    if len(lines) > 250:
                        content = "\n".join(lines[:250]) + f"\n... [{len(lines) - 250} more lines omitted]"

                    injected_block = f"\n\n--- [File: {match}] ---\n```\n{content}\n```\n--- [End of {match}] ---\n"
                    injected_files.append((f"@{match}", match, injected_block))
                except Exception:
                    pass

        if injected_files:
            file_names = ", ".join(item[1] for item in injected_files)
            print(f"  {badge('INLINE', 'info')} Inlined file context: {style(file_names, Color.BRIGHT_CYAN)}")
            for token, name, block in injected_files:
                expanded_prompt = expanded_prompt.replace(token, f"`{name}`")
            expanded_prompt = expanded_prompt + "\n" + "".join(item[2] for item in injected_files)

        return expanded_prompt
