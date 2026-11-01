"""Toolbox providing file, search, command, and git operations for Dev-Mate.
Equipped with strict path traversal, shell injection, and secret protections,
and optimized for minimal API token consumption on large repositories.
"""

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Union, Optional, Callable, List, Dict, Any

from .memory import Memory
from .context import compress_text
from .ui import (
    prompt_clarification,
    prompt_permission,
    PermissionRequest,
    PermissionDecision,
    RiskLevel,
    classify_risk,
)


TEXT_EXTS = {
    ".py", ".pyw", ".js", ".ts", ".tsx", ".jsx", ".html", ".css",
    ".json", ".yaml", ".yml", ".toml", ".md", ".txt", ".sql",
    ".java", ".cpp", ".c", ".h", ".hpp", ".rs", ".go",
    ".php", ".xml", ".ini", ".cfg", ".sh", ".ps1"
}

BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip",
    ".tar", ".gz", ".exe", ".bin", ".pyc", ".db", ".sqlite",
    ".dll", ".so", ".dylib", ".woff", ".woff2", ".ttf", ".eot"
}

PROTECTED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".idea",
    ".vscode",
    ".devmate"
}

PROTECTED_SECRET_NAMES = {
    "id_rsa",
    "id_ed25519",
    "credentials",
    ".bash_history",
}

WINDOWS_DEVICE_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

DANGEROUS_COMMAND_PATTERNS = [
    r"format\s+[a-zA-Z]:",
    r"del\s+/[fFqsSQ\s]*[cC]:\\",
    r"rm\s+-rf\s+[/~]",
    r":\(\)\s*\{\s*:\|:&\s*\};:",
    r"\bmkfs\b",
    r"\bdd\s+if=",
]


def is_protected_path(rel_path: Path, allow_env_example: bool = True) -> bool:
    """Check if a relative path references a protected directory or secret file."""
    name = rel_path.name.lower()

    if name.startswith(".env"):
        if allow_env_example and name == ".env.example":
            return False
        return True

    if name in PROTECTED_SECRET_NAMES:
        return True

    for part in rel_path.parts:
        if part in PROTECTED_DIRS:
            return True

    return False


def safe_path(root: Path, rel: str, allow_env_example: bool = True) -> Path:
    """
    Resolve and validate a path relative to the project root.
    Guards against path traversal, Windows device names, and access to protected files/dirs.
    """
    if not rel or not isinstance(rel, str):
        raise ValueError("A valid path string is required")

    clean_rel = rel.strip()

    for part in Path(clean_rel).parts:
        stem = Path(part).stem.upper()
        if stem in WINDOWS_DEVICE_NAMES:
            raise ValueError(f"Path references invalid Windows device name: {part}")

    root_resolved = root.resolve()
    target = (root_resolved / clean_rel).resolve()

    try:
        relative = target.relative_to(root_resolved)
    except ValueError:
        raise ValueError(f"Path '{clean_rel}' escapes the project root")

    if is_protected_path(relative, allow_env_example=allow_env_example):
        raise PermissionError(f"Access to protected path '{clean_rel}' is denied by security policy")

    return target


class ToolBox:
    def __init__(self, config, approve=None, clarify=None):
        self.root = config.root.resolve()
        self.cfg = config
        self.approve = approve or prompt_permission
        self.clarify = clarify or prompt_clarification
        self.memory = Memory(config)

        self.cfg.devmate_dir.mkdir(exist_ok=True)
        (self.cfg.devmate_dir / "backups").mkdir(exist_ok=True)

    def ask_permission(
        self,
        req: Union[PermissionRequest, str],
        diff_viewer: Optional[Callable] = None,
    ) -> PermissionDecision:
        """Request permission using either the configured callback or prompt_permission."""
        if not self.approve:
            return PermissionDecision(approved=True, action="proceed")

        try:
            res = self.approve(req)
        except TypeError:
            res = self.approve(str(req))

        if isinstance(res, PermissionDecision):
            return res
        if isinstance(res, bool):
            return PermissionDecision(approved=res, action="proceed" if res else "abort")
        return PermissionDecision(approved=bool(res), action="proceed" if res else "abort")

    def _backup(self, p: Path):
        """Create a timestamped backup before modifying or deleting a file and record in manifest."""
        if p.exists() and p.is_file():
            stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{time.perf_counter_ns() % 1_000_000_000:09d}"
            backup_dir = self.cfg.devmate_dir / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            dst = backup_dir / f"{stamp}_{p.name}"
            try:
                shutil.copy2(p, dst)
                # Maintain structured rollback manifest
                manifest_file = backup_dir / "manifest.json"
                manifest = []
                if manifest_file.exists():
                    try:
                        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                    except Exception:
                        manifest = []
                try:
                    rel_str = str(p.resolve().relative_to(self.root))
                except ValueError:
                    rel_str = p.name
                manifest.append({
                    "timestamp": stamp,
                    "target": rel_str,
                    "backup": str(dst.relative_to(self.cfg.devmate_dir))
                })
                manifest = manifest[-50:]
                manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            except OSError:
                pass

    def list_files(self, path="."):
        """List project files while filtering out protected directories and capping output for token efficiency."""
        base = safe_path(self.root, path)
        out = []

        for p in sorted(base.rglob("*")):
            try:
                rel = p.relative_to(self.root)
            except ValueError:
                continue

            if is_protected_path(rel):
                continue

            if p.is_file():
                out.append(str(rel))

        total_count = len(out)
        limit = 100
        results = out[:limit]
        if total_count > limit:
            results.append(f"... [{total_count - limit} more files in '{path}'. Specify subpath to inspect specific folders]")

        return "\n".join(results)

    def read_file(self, path, start_line=1, end_line=None):
        """Read a text file with line numbers, guarded against secret exfiltration, binary corruption, and token blowup."""
        p = safe_path(self.root, path, allow_env_example=True)

        if not p.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        if p.suffix.lower() in BINARY_EXTS:
            size_kb = round(p.stat().st_size / 1024, 1)
            return f"[Binary file '{path}' ({size_kb} KB) cannot be displayed as text. Use inspect_artifact or dedicated tools.]"

        lines = p.read_text(
            encoding="utf-8",
            errors="replace"
        ).splitlines()

        total_lines = len(lines)
        start = max(1, int(start_line))

        if end_line is None:
            end = min(total_lines, start + self.cfg.max_file_read_lines - 1)
        else:
            end = min(total_lines, int(end_line))

        # Cap single read chunk to 200 lines to prevent context flooding
        if (end - start + 1) > 200:
            end = start + 199
            truncated_note = f"\n... [Chunk capped at 200 lines to save tokens. Use start_line={end + 1} to read remaining {total_lines - end} lines]"
        else:
            truncated_note = ""

        formatted_lines = [
            f"{i}: {lines[i - 1]}"
            for i in range(start, end + 1)
        ]

        result = "\n".join(formatted_lines) + truncated_note
        self.memory.log("READ", f"{path} lines {start}-{end}")
        return result

    def search_files(self, query, path="."):
        """Search text across project files, capped at top relevant hits to save tokens."""
        base = safe_path(self.root, path)
        hits = []
        q = query.lower()
        max_hits = getattr(self.cfg, "max_search_results", 25)

        for p in base.rglob("*"):
            try:
                rel = p.relative_to(self.root)
            except ValueError:
                continue

            if (
                not p.is_file()
                or p.suffix.lower() not in TEXT_EXTS
                or is_protected_path(rel)
            ):
                continue

            try:
                lines = p.read_text(
                    encoding="utf-8",
                    errors="ignore"
                ).splitlines()
            except Exception:
                continue

            for i, line in enumerate(lines, 1):
                if q in line.lower():
                    hits.append(f"{rel}:{i}: {line.strip()[:240]}")

                    if len(hits) >= max_hits:
                        self.memory.log("SEARCH", f"query={query}, path={path} (hits={len(hits)})")
                        return "\n".join(hits) + f"\n... [Showing top {max_hits} matches. Use a more specific query or subpath if needed]"

        result = "\n".join(hits) or "No matches."
        self.memory.log("SEARCH", f"query={query}, path={path} (hits={len(hits)})")
        return result

    def write_file(self, path, content):
        """Create or replace a file, guarded against overwriting protected project files."""
        p = safe_path(self.root, path, allow_env_example=False)

        self._backup(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

        relative = str(p.relative_to(self.root))
        self.memory.log("WRITE", relative)
        return f"Wrote {relative}"

    def edit_file(self, path, old_text, new_text):
        """Replace one exact text block in an existing file with newline normalization support."""
        p = safe_path(self.root, path, allow_env_example=False)

        if not p.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        text = p.read_text(encoding="utf-8", errors="replace")

        if old_text in text:
            target_text = text
            target_old = old_text
            target_new = new_text
        elif old_text.replace("\r\n", "\n") in text.replace("\r\n", "\n"):
            target_text = text.replace("\r\n", "\n")
            target_old = old_text.replace("\r\n", "\n")
            target_new = new_text.replace("\r\n", "\n")
        else:
            raise ValueError("old_text was not found exactly; reread the file")

        self._backup(p)
        p.write_text(target_text.replace(target_old, target_new, 1), encoding="utf-8")

        relative = str(p.relative_to(self.root))
        self.memory.log("EDIT", relative)
        return f"Edited {relative}"

    def replace_lines(self, path: str, start_line: int, end_line: int, new_content: str) -> str:
        """Replace an exact line range [start_line, end_line] in a file with new content."""
        p = safe_path(self.root, path, allow_env_example=False)
        if not p.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        total = len(lines)
        s = max(1, int(start_line))
        e = min(total, int(end_line))
        if s > e or s > total:
            raise ValueError(f"Invalid line range {s}-{e} for file with {total} lines")

        self._backup(p)
        new_lines_list = new_content.splitlines()
        updated_lines = lines[:s - 1] + new_lines_list + lines[e:]

        p.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
        relative = str(p.relative_to(self.root))
        self.memory.log("REPLACE_LINES", f"{relative} lines {s}-{e}")
        return f"Replaced lines {s}-{e} in {relative} ({len(new_lines_list)} lines inserted)."

    def delete_file(self, path):
        """Delete a file with human approval and backup."""
        p = safe_path(self.root, path, allow_env_example=False)

        if not self.cfg.allow_delete:
            req = PermissionRequest(
                action="Delete File",
                target=path,
                risk=RiskLevel.HIGH,
                details=f"Permanently remove file '{path}'. A backup will be stored in .devmate/backups/.",
            )
            decision = self.ask_permission(req)
            if not decision:
                return "Deletion cancelled by user."

        if p.is_file():
            self._backup(p)
            p.unlink()
            self.memory.log("DELETE", path)
            return f"Deleted {path}"

        raise FileNotFoundError(f"File not found: {path}")

    def run_command(self, command):
        """Execute a shell command with encoding safety, timeout, and compressed token output."""
        is_high_risk = any(re.search(pat, command, re.IGNORECASE) for pat in DANGEROUS_COMMAND_PATTERNS)

        if is_high_risk:
            req = PermissionRequest(
                action="Destructive Shell Command",
                target=command,
                risk=RiskLevel.HIGH,
                details="Potentially destructive command pattern detected.",
            )
            decision = self.ask_permission(req)
            if not decision:
                return "Command execution blocked by security policy."
        elif not self.cfg.allow_commands:
            req = PermissionRequest(
                action="Execute Shell Command",
                target=command,
                risk=RiskLevel.MEDIUM,
                details="Shell command execution in workspace.",
            )
            decision = self.ask_permission(req)
            if not decision:
                return "Command cancelled by user."

        try:
            r = subprocess.run(
                command,
                cwd=self.root,
                shell=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=self.cfg.command_timeout
            )
            # Compress long output to save tokens while keeping key diagnostics
            clean_stdout = compress_text(r.stdout, max_chars=2000, head_lines=15, tail_lines=25)
            clean_stderr = compress_text(r.stderr, max_chars=2000, head_lines=15, tail_lines=25)

            result = json.dumps(
                {
                    "returncode": r.returncode,
                    "stdout": clean_stdout,
                    "stderr": clean_stderr
                },
                ensure_ascii=False
            )
            status = "PASS" if r.returncode == 0 else "FAIL"
            self.memory.log("RUN", command[:200], status)
            return result

        except KeyboardInterrupt:
            self.memory.log("RUN", command[:200], "INTERRUPTED")
            return json.dumps({"error": "Command execution interrupted by user (Ctrl+C)"})
        except subprocess.TimeoutExpired:
            msg = f"Command timed out after {self.cfg.command_timeout}s"
            self.memory.log("RUN", command[:200], "TIMEOUT")
            return json.dumps({"error": msg})
        except Exception as e:
            msg = f"Command failed: {type(e).__name__}: {e}"
            self.memory.log("RUN", command[:200], "ERROR")
            return json.dumps({"error": msg})

    def run_python(self, path):
        """
        Safely execute a Python file inside the project.
        Uses sys.executable and direct argument execution (shell=False) to eliminate shell injection.
        """
        p = safe_path(self.root, path, allow_env_example=False)

        if not p.is_file():
            raise FileNotFoundError(f"Python script not found: {path}")

        if p.suffix.lower() not in {".py", ".pyw"}:
            raise ValueError(f"File is not a Python script: {path}")

        rel_str = str(p.relative_to(self.root))

        if not self.cfg.allow_commands:
            req = PermissionRequest(
                action="Run Python Script",
                target=rel_str,
                risk=RiskLevel.MEDIUM,
                details=f"Executing Python script via sys.executable ({Path(sys.executable).name}).",
            )
            decision = self.ask_permission(req)
            if not decision:
                return "Execution cancelled by user."

        try:
            r = subprocess.run(
                [sys.executable, str(p)],
                cwd=self.root,
                shell=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=self.cfg.command_timeout
            )
            clean_stdout = compress_text(r.stdout, max_chars=2000, head_lines=15, tail_lines=25)
            clean_stderr = compress_text(r.stderr, max_chars=2000, head_lines=15, tail_lines=25)

            result = json.dumps(
                {
                    "returncode": r.returncode,
                    "stdout": clean_stdout,
                    "stderr": clean_stderr
                },
                ensure_ascii=False
            )
            status = "PASS" if r.returncode == 0 else "FAIL"
            self.memory.log("RUN_PYTHON", rel_str, status)
            return result

        except KeyboardInterrupt:
            self.memory.log("RUN_PYTHON", rel_str, "INTERRUPTED")
            return json.dumps({"error": "Python script execution interrupted by user (Ctrl+C)"})
        except subprocess.TimeoutExpired:
            msg = f"Script execution timed out after {self.cfg.command_timeout}s"
            self.memory.log("RUN_PYTHON", rel_str, "TIMEOUT")
            return json.dumps({"error": msg})
        except Exception as e:
            msg = f"Script execution failed: {type(e).__name__}: {e}"
            self.memory.log("RUN_PYTHON", rel_str, "ERROR")
            return json.dumps({"error": msg})

    def git_status(self):
        """Run git status with short summary."""
        return self.run_command("git status --short")

    def git_diff(self):
        """Run git diff against current directory."""
        return self.run_command("git diff -- .")

    def git_commit(self, message: str) -> str:
        """Stage tracked modifications and create a git commit with human approval."""
        if not message or not str(message).strip():
            return "Error: A commit message is required."

        clean_msg = str(message).strip()
        status_raw = self.run_command("git status --short")
        try:
            status_data = json.loads(status_raw)
            status_text = status_data.get("stdout", "").strip()
        except Exception:
            status_text = str(status_raw).strip()

        if not status_text:
            return "Working tree is clean. Nothing to commit."

        req = PermissionRequest(
            action="Git Commit",
            target=clean_msg[:80],
            risk=RiskLevel.MEDIUM,
            details=f"Create git commit with message: '{clean_msg}'. Staging tracked modifications (git add -u).",
            diff=status_text,
        )
        decision = self.ask_permission(req)
        if not decision:
            return "Git commit cancelled by user."

        # Stage only tracked modifications (guards against committing untracked secrets)
        self.run_command("git add -u")
        # Commit with escaped quotes
        safe_msg = clean_msg.replace('"', '\\"')
        commit_res = self.run_command(f'git commit -m "{safe_msg}"')

        self.memory.log("GIT_COMMIT", clean_msg, "PASS")
        return commit_res

    def grep_search(self, pattern: str, path: str = ".", case_sensitive: bool = False, max_matches: int = 25) -> str:
        """Search project files using regular expressions. Powerful for structural and pattern matching."""
        base = safe_path(self.root, path)
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            regex = re.compile(pattern, flags)
        except re.error as e:
            return f"Invalid regex pattern '{pattern}': {e}"

        hits = []
        for p in base.rglob("*"):
            try:
                rel = p.relative_to(self.root)
            except ValueError:
                continue

            if (
                not p.is_file()
                or p.suffix.lower() not in TEXT_EXTS
                or is_protected_path(rel)
            ):
                continue

            try:
                lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue

            for i, line in enumerate(lines, 1):
                if regex.search(line):
                    hits.append(f"{rel}:{i}: {line.strip()[:240]}")
                    if len(hits) >= max_matches:
                        self.memory.log("GREP", f"pattern={pattern}, hits={len(hits)}")
                        return "\n".join(hits) + f"\n... [Showing top {max_matches} regex matches]"

        result = "\n".join(hits) or "No regex matches found."
        self.memory.log("GREP", f"pattern={pattern}, hits={len(hits)}")
        return result

    def project_summary(self):
        """Provide a compact, token-efficient architectural overview without dumping raw file lists."""
        all_files = []
        top_dirs = {}
        manifests = []
        key_manifest_names = {
            "pyproject.toml", "requirements.txt", "package.json",
            "Cargo.toml", "go.mod", "pom.xml", "build.gradle",
            "Makefile", "Dockerfile", "README.md"
        }

        for p in sorted(self.root.rglob("*")):
            try:
                rel = p.relative_to(self.root)
            except ValueError:
                continue
            if is_protected_path(rel):
                continue
            if p.is_file():
                all_files.append(rel)
                top_part = rel.parts[0] if len(rel.parts) > 1 else "."
                top_dirs[top_part] = top_dirs.get(top_part, 0) + 1
                if p.name in key_manifest_names:
                    manifests.append(str(rel))

        ext = {}
        for f in all_files:
            e = f.suffix.lower() or "[no extension]"
            ext[e] = ext.get(e, 0) + 1

        sorted_ext = dict(sorted(ext.items(), key=lambda item: item[1], reverse=True)[:10])

        return json.dumps(
            {
                "root": str(self.root),
                "file_count": len(all_files),
                "total_files": len(all_files),
                "directories": top_dirs,
                "key_manifests": manifests[:10],
                "extensions": sorted_ext,
                "hint": "Use list_files(path) to inspect specific directories on demand."
            },
            indent=2
        )

    def delegate_task(self, role: str, prompt: str, provider: str = "inherit") -> str:
        """Delegate a subtask to a specialized subagent (e.g. researcher, reviewer, debugger)."""
        from .subagent import SubAgent
        sub = SubAgent(
            config=self.cfg,
            toolbox=self,
            role=role,
            provider_name=provider,
            max_turns=6
        )
        report = sub.execute(prompt)
        self.memory.log("DELEGATE", f"role={role}, provider={provider}, prompt={prompt[:100]}", "PASS")
        return report

    def ask_clarification(self, question: str, options: list = None) -> str:
        """Ask the user clarifying questions when project details, facts, or specifications are ambiguous or missing."""
        if not question or not str(question).strip():
            return "Error: A clear clarification question is required."

        opts = options if isinstance(options, list) else []
        ans = self.clarify(str(question).strip(), opts)
        self.memory.log("CLARIFY", f"Q: {question[:80]} | A: {str(ans)[:80]}", "PASS")
        return f"User Clarification Response:\n{ans}"

    def lint_document(self, path: str, auto_fix: bool = False) -> str:
        """Lint a document (markdown, HTML, or report) for table integrity, column alignment, empty rows, design consistency, and placeholder leaks."""
        from .design import DocumentLinter
        from .ui import render_lint_report

        p = safe_path(self.root, path, allow_env_example=False)
        if not p.is_file():
            raise FileNotFoundError(f"Document not found: {path}")

        linter = DocumentLinter()
        raw_text = p.read_text(encoding="utf-8", errors="replace")

        if auto_fix:
            self._backup(p)
            repaired_text = linter.auto_fix_content(raw_text)
            p.write_text(repaired_text, encoding="utf-8")
            report = linter.lint_text(repaired_text, file_path=str(p.relative_to(self.root)))
            fix_msg = f"Auto-fix applied and saved to {p.relative_to(self.root)}. "
        else:
            report = linter.lint_text(raw_text, file_path=str(p.relative_to(self.root)))
            fix_msg = ""

        # Format visual card
        card = render_lint_report(report)
        print(f"\n{card}")

        status = "PASS" if report.is_valid else "FAIL"
        rel_str = str(p.relative_to(self.root))
        self.memory.log("LINT", f"{rel_str} (Score: {report.score}/100, Issues: {len(report.issues)})", status)

        return json.dumps(
            {
                "status": status,
                "file": rel_str,
                "score": report.score,
                "auto_fix": auto_fix,
                "message": fix_msg + report.summary,
                "critical": report.critical_count,
                "warnings": report.warning_count,
                "notices": report.info_count,
                "issues": [
                    {
                        "severity": iss.severity.value,
                        "category": iss.category,
                        "message": iss.message,
                        "line": iss.line,
                        "suggestion": iss.suggestion,
                    }
                    for iss in report.issues
                ]
            },
            ensure_ascii=False,
            indent=2
        )

    def view_outline(self, path: str) -> str:
        """
        Extract a structured architectural outline of a source file (classes, methods, functions, docstrings).
        Extremely token-efficient way to inspect file structure without loading full source code.
        """
        p = safe_path(self.root, path, allow_env_example=False)
        if not p.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        try:
            source = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"Error reading file: {e}"

        rel_str = str(p.relative_to(self.root))
        lines = source.splitlines()

        if p.suffix.lower() in {".py", ".pyw"}:
            try:
                tree = ast.parse(source, filename=str(p))
            except SyntaxError as e:
                return f"Syntax error in {rel_str} at line {e.lineno}: {e.msg}"

            outline = [f"File: {rel_str} ({len(lines)} lines)"]
            doc = ast.get_docstring(tree)
            if doc:
                outline.append(f"  \"\"\"{doc.splitlines()[0]}\"\"\"")

            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    bases = [ast.unparse(b) for b in node.bases] if hasattr(ast, "unparse") else [getattr(b, "id", "") for b in node.bases]
                    base_str = f"({', '.join(b for b in bases if b)})" if bases else ""
                    c_doc = ast.get_docstring(node)
                    c_doc_str = f" - \"{c_doc.splitlines()[0][:60]}\"" if c_doc else ""
                    outline.append(f"  class {node.name}{base_str} [L{node.lineno}-L{getattr(node, 'end_lineno', node.lineno)}]{c_doc_str}")
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            prefix = "async def " if isinstance(item, ast.AsyncFunctionDef) else "def "
                            args = [a.arg for a in item.args.args]
                            ret = f" -> {ast.unparse(item.returns)}" if hasattr(ast, "unparse") and item.returns else ""
                            m_doc = ast.get_docstring(item)
                            m_doc_str = f" - \"{m_doc.splitlines()[0][:50]}\"" if m_doc else ""
                            outline.append(f"    {prefix}{item.name}({', '.join(args[:5])}){ret} [L{item.lineno}]{m_doc_str}")

                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
                    args = [a.arg for a in node.args.args]
                    ret = f" -> {ast.unparse(node.returns)}" if hasattr(ast, "unparse") and node.returns else ""
                    f_doc = ast.get_docstring(node)
                    f_doc_str = f" - \"{f_doc.splitlines()[0][:60]}\"" if f_doc else ""
                    outline.append(f"  {prefix}{node.name}({', '.join(args[:5])}){ret} [L{node.lineno}-L{getattr(node, 'end_lineno', node.lineno)}]{f_doc_str}")

                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id.isupper():
                            outline.append(f"  CONST {target.id} [L{node.lineno}]")

            self.memory.log("OUTLINE", rel_str)
            return "\n".join(outline)

        elif p.suffix.lower() in {".md", ".markdown"}:
            outline = [f"Markdown Outline: {rel_str} ({len(lines)} lines)"]
            for i, line in enumerate(lines, 1):
                if line.startswith("#"):
                    outline.append(f"  L{i}: {line[:80]}")
            self.memory.log("OUTLINE", rel_str)
            return "\n".join(outline)

        else:
            outline = [f"File: {rel_str} ({len(lines)} lines)"]
            patterns = [
                (r"^\s*(export\s+)?(class|interface|type)\s+([A-Za-z0-9_]+)", "type/class"),
                (r"^\s*(export\s+)?(async\s+)?function\s+([A-Za-z0-9_]+)", "function"),
                (r"^\s*(pub\s+)?(fn|struct|enum)\s+([A-Za-z0-9_]+)", "rust"),
                (r"^\s*func\s+([A-Za-z0-9_]+)", "go"),
            ]
            for i, line in enumerate(lines, 1):
                for pat, _ in patterns:
                    m = re.search(pat, line)
                    if m:
                        outline.append(f"  L{i}: {line.strip()[:80]}")
                        break
            self.memory.log("OUTLINE", rel_str)
            return "\n".join(outline)

    def get_definition(self, symbol: str, path: Optional[str] = None) -> str:
        """
        Locate and extract the full source code and metadata of a class, function, or method by name.
        Uses AST analysis to return exact symbol definitions without guessing line numbers.
        """
        if not symbol or not str(symbol).strip():
            return "Error: A symbol name is required."

        target_symbol = symbol.strip()
        files_to_check = []

        if path:
            p = safe_path(self.root, path, allow_env_example=False)
            if not p.is_file():
                return f"File not found: {path}"
            files_to_check = [p]
        else:
            for p in self.root.rglob("*.py"):
                try:
                    rel = p.relative_to(self.root)
                    if not is_protected_path(rel):
                        files_to_check.append(p)
                except ValueError:
                    continue

        results = []

        for p in files_to_check:
            try:
                source = p.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=str(p))
            except Exception:
                continue

            lines = source.splitlines()
            rel_str = str(p.relative_to(self.root))

            for node in ast.walk(tree):
                matched = False
                node_type = ""
                if isinstance(node, ast.ClassDef) and node.name == target_symbol:
                    matched = True
                    node_type = "Class"
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == target_symbol:
                    matched = True
                    node_type = "Function/Method"

                if matched:
                    start_l = node.lineno
                    end_l = getattr(node, "end_lineno", start_l + 20)
                    definition_lines = lines[start_l - 1:end_l]
                    if len(definition_lines) > 120:
                        code_preview = "\n".join(definition_lines[:120]) + f"\n... [{len(definition_lines) - 120} more lines omitted]"
                    else:
                        code_preview = "\n".join(definition_lines)

                    results.append(
                        f"=== {node_type} '{target_symbol}' in {rel_str} (Lines {start_l}-{end_l}) ===\n"
                        f"{code_preview}"
                    )
                    if len(results) >= 5:
                        break

            if len(results) >= 5:
                break

        if not results:
            return f"Symbol '{target_symbol}' not found in {'specified file' if path else 'project Python files'}."

        self.memory.log("GET_DEF", f"symbol={target_symbol}, found={len(results)}")
        return "\n\n".join(results)

    def rollback_file(self, path: str) -> str:
        """Rollback a file to its most recent backup snapshot."""
        p = safe_path(self.root, path, allow_env_example=False)
        rel_str = str(p.resolve().relative_to(self.root))
        backup_dir = self.cfg.devmate_dir / "backups"
        manifest_file = backup_dir / "manifest.json"

        target_backup = None
        if manifest_file.exists():
            try:
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                for entry in reversed(manifest):
                    if entry.get("target") == rel_str:
                        candidate = self.cfg.devmate_dir / entry["backup"]
                        if candidate.is_file():
                            target_backup = candidate
                            break
            except Exception:
                pass

        if not target_backup:
            backups = sorted(backup_dir.glob(f"*_{p.name}"), reverse=True)
            if backups:
                target_backup = backups[0]

        if not target_backup or not target_backup.is_file():
            return f"No backup found for '{path}'."

        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target_backup, p)
        self.memory.log("ROLLBACK", f"{rel_str} restored from {target_backup.name}", "PASS")
        return f"Successfully restored '{rel_str}' from backup ({target_backup.name})."

    def undo_last_change(self) -> str:
        """Revert the most recent file mutation made in the project."""
        backup_dir = self.cfg.devmate_dir / "backups"
        manifest_file = backup_dir / "manifest.json"
        if not manifest_file.exists():
            return "No recorded changes available to undo."

        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except Exception:
            return "Could not read backup manifest."

        if not manifest:
            return "No recorded changes available to undo."

        last_entry = manifest.pop()
        target_rel = last_entry.get("target")
        backup_rel = last_entry.get("backup")

        backup_file = self.cfg.devmate_dir / backup_rel
        if not backup_file.is_file():
            return f"Backup file {backup_rel} not found."

        dest_file = self.root / target_rel
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_file, dest_file)
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        self.memory.log("UNDO", f"Reverted {target_rel} from {backup_file.name}", "PASS")
        return f"Successfully reverted '{target_rel}' to snapshot before last modification ({backup_file.name})."

    def run_doctor(self) -> Dict[str, Any]:
        """Perform a comprehensive environment, git, provider, and storage diagnostic health check."""
        results = {}

        # 1. Python Environment
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        py_ok = sys.version_info >= (3, 11)
        results["python"] = {
            "status": "PASS" if py_ok else "FAIL",
            "version": py_ver,
            "executable": sys.executable,
            "details": f"Python {py_ver} (>= 3.11 required)"
        }

        # 2. Git Status
        try:
            git_check = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=self.root, capture_output=True, text=True, shell=False
            )
            is_git = git_check.returncode == 0
        except Exception:
            is_git = False

        branch_name = "unknown"
        if is_git:
            try:
                b_check = subprocess.run(
                    ["git", "branch", "--show-current"],
                    cwd=self.root, capture_output=True, text=True, shell=False
                )
                branch_name = b_check.stdout.strip() or "detached"
            except Exception:
                pass

        results["git"] = {
            "status": "PASS" if is_git else "WARN",
            "branch": branch_name,
            "details": f"Git repository on branch '{branch_name}'" if is_git else "Not a git repository"
        }

        # 3. Provider Configurations
        has_openrouter = bool(self.cfg.openrouter_key)
        has_google = bool(self.cfg.google_key)
        is_ollama = self.cfg.provider.lower() in {"ollama", "local"}
        active_provider = self.cfg.provider

        prov_ok = has_openrouter or has_google or is_ollama
        results["providers"] = {
            "status": "PASS" if prov_ok else "WARN",
            "active": active_provider,
            "openrouter_configured": has_openrouter,
            "google_configured": has_google,
            "ollama_active": is_ollama,
            "details": f"Active: {active_provider} | OpenRouter: {'Configured' if has_openrouter else 'Unset'} | Gemini: {'Configured' if has_google else 'Unset'}"
        }

        # 4. Storage & Backups
        backup_dir = self.cfg.devmate_dir / "backups"
        backup_ok = backup_dir.exists() and os.access(backup_dir, os.W_OK)
        manifest_p = backup_dir / "manifest.json"
        manifest_count = 0
        if manifest_p.exists():
            try:
                manifest_count = len(json.loads(manifest_p.read_text(encoding="utf-8")))
            except Exception:
                pass

        results["backups"] = {
            "status": "PASS" if backup_ok else "FAIL",
            "directory": str(backup_dir),
            "manifest_entries": manifest_count,
            "details": f"Writable backup directory ({manifest_count} snapshots indexed)"
        }

        # 5. Test Framework
        try:
            import pytest
            test_framework = f"pytest {pytest.__version__}"
            test_ok = True
        except ImportError:
            test_framework = "pytest not installed"
            test_ok = False

        results["test_framework"] = {
            "status": "PASS" if test_ok else "WARN",
            "details": test_framework
        }

        self.memory.log("DOCTOR", f"Py={py_ver}, Prov={active_provider}, Tests={test_ok}", "PASS")
        return results

    def plan_task(self, goal: str) -> str:
        """
        Formulate a structured, non-destructive implementation plan before modifying any files.
        Enables human-in-the-loop review and architectural sign-off before code edits begin.
        """
        from .subagent import SubAgent
        sub = SubAgent(
            config=self.cfg,
            toolbox=self,
            role="researcher",
            max_turns=4
        )
        plan_prompt = f"""You are the principal architect in Dev-Mate.
Create a structured, step-by-step implementation plan for this goal: '{goal}'.

Output requirements:
1. Architectural Impact & Assumptions
2. Exact Files to Read, Create, or Modify
3. Step-by-Step Implementation Sequence
4. Verification & Testing Strategy
5. Potential Failure Modes & Rollback Plan

Do NOT write code or modify files. Focus on precision, minimal footprint, and clarity.
"""
        plan_text = sub.execute(plan_prompt)
        self.memory.log("PLAN", f"Goal: {goal[:100]}", "PASS")
        return plan_text

    def remember_fact(self, fact: str, category: str = "decisions") -> str:
        """
        Record a key fact, user agreement, strategic plan, or architecture decision
        into persistent project memory (.devmate/memory.json).
        """
        valid_categories = {
            "decisions", "project", "preferences", "important_files", "known_issues"
        }
        clean_cat = category.strip().lower() if category and category.strip().lower() in valid_categories else "decisions"
        clean_fact = str(fact).strip()
        if not clean_fact:
            return "Cannot remember an empty fact."

        self.memory.remember(clean_cat, clean_fact)
        self.memory.log("REMEMBER", f"[{clean_cat}] {clean_fact[:100]}", "PASS")
        return f"Recorded into project memory under '{clean_cat}': {clean_fact}"

    def check_syntax(self, path: str) -> str:
        """
        Validate source code syntax for Python, JSON, TOML, Markdown, and HTML without running code.
        Catches syntax errors and returns detailed line, column, and context diagnostics.
        """
        p = safe_path(self.root, path, allow_env_example=False)
        if not p.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        ext = p.suffix.lower()
        rel_str = str(p.relative_to(self.root))
        raw_text = p.read_text(encoding="utf-8", errors="replace")

        try:
            if ext == ".py":
                ast.parse(raw_text, filename=str(p))
            elif ext == ".json":
                json.loads(raw_text)
            elif ext == ".toml":
                import tomllib
                tomllib.loads(raw_text)
            elif ext in {".md", ".html"}:
                from .design import DocumentLinter
                linter = DocumentLinter()
                rep = linter.lint_text(raw_text, file_path=rel_str)
                if not rep.is_valid:
                    crit = [f"Line {i.line}: {i.message}" for i in rep.issues if i.severity.value == "critical"]
                    return json.dumps({
                        "status": "INVALID",
                        "file": rel_str,
                        "type": "DocumentLintError",
                        "error": "; ".join(crit[:5]) if crit else "Document linting failed",
                        "critical_issues": len(crit),
                        "score": rep.score
                    }, indent=2)
            else:
                p.read_text(encoding="utf-8")
        except SyntaxError as se:
            lines = raw_text.splitlines()
            err_line = se.lineno or 1
            start = max(0, err_line - 2)
            end = min(len(lines), err_line + 2)
            snippet = "\n".join(f"{idx+1:>4}: {lines[idx]}" for idx in range(start, end))
            return json.dumps({
                "status": "INVALID",
                "file": rel_str,
                "type": "SyntaxError",
                "error": str(se.msg),
                "line": se.lineno,
                "column": se.offset,
                "snippet": snippet
            }, indent=2)
        except json.JSONDecodeError as jde:
            return json.dumps({
                "status": "INVALID",
                "file": rel_str,
                "type": "JSONDecodeError",
                "error": str(jde.msg),
                "line": jde.lineno,
                "column": jde.colno
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "status": "INVALID",
                "file": rel_str,
                "type": type(e).__name__,
                "error": str(e)
            }, indent=2)

        self.memory.log("SYNTAX", f"{rel_str} syntax OK", "PASS")
        return json.dumps({
            "status": "VALID",
            "file": rel_str,
            "message": "Syntax validation passed cleanly."
        }, indent=2)

    def find_references(self, symbol: str, path: Optional[str] = None) -> str:
        """
        Locate all AST references, usages, and call sites of a symbol across project Python files.
        Extracts file, line number, enclosing scope (class/function), and code snippet.
        """
        if not symbol or not symbol.strip():
            return "Please provide a valid symbol name."

        symbol = symbol.strip()
        search_paths = []
        if path:
            target = safe_path(self.root, path, allow_env_example=False)
            if target.is_file() and target.suffix == ".py":
                search_paths.append(target)
            elif target.is_dir():
                search_paths.extend(p for p in target.rglob("*.py") if ".git" not in p.parts and ".devmate" not in p.parts and "__pycache__" not in p.parts)
        else:
            search_paths.extend(p for p in self.root.rglob("*.py") if ".git" not in p.parts and ".devmate" not in p.parts and "__pycache__" not in p.parts)

        references = []
        root_dir = self.root

        for file_p in sorted(search_paths):
            try:
                content = file_p.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(content, filename=str(file_p))
            except Exception:
                continue

            lines = content.splitlines()

            class ReferenceVisitor(ast.NodeVisitor):
                def __init__(self):
                    self.scope_stack = []

                def visit_ClassDef(self, node):
                    if node.name == symbol:
                        line_idx = node.lineno - 1
                        code_snip = lines[line_idx].strip() if 0 <= line_idx < len(lines) else ""
                        scope = " -> ".join(self.scope_stack) if self.scope_stack else "module"
                        references.append({
                            "file": str(file_p.relative_to(root_dir)),
                            "line": node.lineno,
                            "scope": scope,
                            "code": code_snip,
                            "context": "definition"
                        })
                    self.scope_stack.append(f"class {node.name}")
                    self.generic_visit(node)
                    self.scope_stack.pop()

                def visit_FunctionDef(self, node):
                    if node.name == symbol:
                        line_idx = node.lineno - 1
                        code_snip = lines[line_idx].strip() if 0 <= line_idx < len(lines) else ""
                        scope = " -> ".join(self.scope_stack) if self.scope_stack else "module"
                        references.append({
                            "file": str(file_p.relative_to(root_dir)),
                            "line": node.lineno,
                            "scope": scope,
                            "code": code_snip,
                            "context": "definition"
                        })
                    self.scope_stack.append(f"def {node.name}")
                    self.generic_visit(node)
                    self.scope_stack.pop()

                def visit_AsyncFunctionDef(self, node):
                    if node.name == symbol:
                        line_idx = node.lineno - 1
                        code_snip = lines[line_idx].strip() if 0 <= line_idx < len(lines) else ""
                        scope = " -> ".join(self.scope_stack) if self.scope_stack else "module"
                        references.append({
                            "file": str(file_p.relative_to(root_dir)),
                            "line": node.lineno,
                            "scope": scope,
                            "code": code_snip,
                            "context": "definition"
                        })
                    self.scope_stack.append(f"async def {node.name}")
                    self.generic_visit(node)
                    self.scope_stack.pop()

                def visit_Name(self, node):
                    if node.id == symbol:
                        line_idx = node.lineno - 1
                        code_snip = lines[line_idx].strip() if 0 <= line_idx < len(lines) else ""
                        scope = " -> ".join(self.scope_stack) if self.scope_stack else "module"
                        references.append({
                            "file": str(file_p.relative_to(root_dir)),
                            "line": node.lineno,
                            "scope": scope,
                            "code": code_snip,
                            "context": "usage"
                        })
                    self.generic_visit(node)

                def visit_Attribute(self, node):
                    if node.attr == symbol:
                        line_idx = node.lineno - 1
                        code_snip = lines[line_idx].strip() if 0 <= line_idx < len(lines) else ""
                        scope = " -> ".join(self.scope_stack) if self.scope_stack else "module"
                        references.append({
                            "file": str(file_p.relative_to(root_dir)),
                            "line": node.lineno,
                            "scope": scope,
                            "code": code_snip,
                            "context": "attribute"
                        })
                    self.generic_visit(node)

            visitor = ReferenceVisitor()
            visitor.visit(tree)

        self.memory.log("REFS", f"Found {len(references)} references to '{symbol}'", "PASS")
        return json.dumps({
            "symbol": symbol,
            "total_matches": len(references),
            "references": references[:100]
        }, indent=2)

    def run_tests(self, test_target: str = "", marker: str = "", timeout: int = 60) -> str:
        """
        Execute pytest or unittest test suite inside the workspace and return a structured diagnostic summary.
        Extracts passed/failed counts, duration, and details of failed test cases.
        """
        cmd = [sys.executable, "-m", "pytest", "-q", "--tb=short"]
        if marker:
            cmd.extend(["-m", marker])
        if test_target:
            t_path = safe_path(self.root, test_target, allow_env_example=False)
            cmd.append(str(t_path))

        start_time = time.time()
        try:
            res = subprocess.run(
                cmd,
                cwd=self.root,
                capture_output=True,
                text=True,
                shell=False,
                timeout=timeout
            )
            duration = round(time.time() - start_time, 2)
            stdout = res.stdout
            stderr = res.stderr
            code = res.returncode
        except subprocess.TimeoutExpired:
            return json.dumps({
                "status": "TIMEOUT",
                "error": f"Test run timed out after {timeout} seconds.",
                "duration": timeout
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "status": "ERROR",
                "error": f"Failed to execute test runner: {e}"
            }, indent=2)

        summary_line = ""
        for line in reversed(stdout.splitlines()):
            if "passed" in line or "failed" in line or "error" in line:
                summary_line = line.strip(" =")
                break

        failures = []
        if code != 0 and "FAILURES" in stdout:
            parts = stdout.split("FAILURES")
            if len(parts) > 1:
                fail_section = parts[1].split("short test summary info")[0]
                failures.append(fail_section[:3000].strip())

        status = "PASS" if code == 0 else "FAIL"
        self.memory.log("TEST", f"Code {code}: {summary_line or 'Executed'}", status)

        return json.dumps({
            "status": status,
            "exit_code": code,
            "duration": duration,
            "summary": summary_line or ("Tests passed" if code == 0 else "Tests failed"),
            "failures": failures,
            "output_snippet": stdout[-2000:] if len(stdout) > 2000 else stdout
        }, indent=2)

    def analyze_dependencies(self, path: Optional[str] = None) -> str:
        """
        Perform static dependency analysis of Python imports in the workspace or a specific module.
        Classifies imports into standard library, third-party packages, and internal project modules,
        and detects potential circular import cycles.
        """
        stdlib_names = getattr(sys, "stdlib_module_names", set())

        search_paths = []
        if path:
            target = safe_path(self.root, path, allow_env_example=False)
            if target.is_file() and target.suffix == ".py":
                search_paths.append(target)
            elif target.is_dir():
                search_paths.extend(p for p in target.rglob("*.py") if ".git" not in p.parts and ".devmate" not in p.parts and "__pycache__" not in p.parts)
        else:
            search_paths.extend(p for p in self.root.rglob("*.py") if ".git" not in p.parts and ".devmate" not in p.parts and "__pycache__" not in p.parts)

        # Collect internal module names
        project_modules = set()
        for p in search_paths:
            rel = p.relative_to(self.root)
            parts = list(rel.with_suffix("").parts)
            if parts and parts[-1] == "__init__":
                parts.pop()
            mod_name = ".".join(parts)
            if mod_name:
                project_modules.add(mod_name)
                if parts:
                    project_modules.add(parts[0])

        internal_deps = {}
        third_party_deps = set()
        stdlib_deps = set()

        for p in search_paths:
            rel_str = str(p.relative_to(self.root))
            internal_deps[rel_str] = set()
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"), filename=str(p))
            except Exception:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        if top in project_modules:
                            internal_deps[rel_str].add(alias.name)
                        elif top in stdlib_names:
                            stdlib_deps.add(top)
                        else:
                            third_party_deps.add(top)
                elif isinstance(node, ast.ImportFrom):
                    if node.level and node.level > 0:
                        internal_deps[rel_str].add(f".{node.module or ''}")
                    elif node.module:
                        top = node.module.split(".")[0]
                        if top in project_modules:
                            internal_deps[rel_str].add(node.module)
                        elif top in stdlib_names:
                            stdlib_deps.add(top)
                        else:
                            third_party_deps.add(top)

        cycles = []
        visited = {}
        rec_stack = set()

        def dfs(node, path_stack):
            visited[node] = True
            rec_stack.add(node)
            for neighbor in internal_deps.get(node, []):
                matching_file = next((f for f in internal_deps if neighbor in f or f.replace("\\", "/").endswith(neighbor.replace(".", "/") + ".py")), None)
                if matching_file:
                    if matching_file in rec_stack:
                        cycles.append(path_stack + [matching_file])
                    elif matching_file not in visited:
                        dfs(matching_file, path_stack + [matching_file])
            rec_stack.remove(node)

        for file_node in list(internal_deps.keys()):
            if file_node not in visited:
                dfs(file_node, [file_node])

        clean_internal = {k: sorted(list(v)) for k, v in internal_deps.items() if v}
        self.memory.log("DEPS", f"Analyzed {len(search_paths)} files, {len(third_party_deps)} external deps", "PASS")

        return json.dumps({
            "total_files_analyzed": len(search_paths),
            "third_party_dependencies": sorted(list(third_party_deps)),
            "standard_library_modules": sorted(list(stdlib_deps)),
            "internal_import_graph": clean_internal,
            "circular_dependencies_detected": len(cycles) > 0,
            "cycles": cycles[:10]
        }, indent=2)

    def export_audit_log(self, output_path: Optional[str] = None) -> str:
        """
        Generate a comprehensive markdown compliance & activity audit report of all agent actions,
        file modifications, backups, and security checkpoints.
        """
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        ts_slug = time.strftime("%Y%m%d-%H%M%S")

        if output_path:
            out_file = safe_path(self.root, output_path, allow_env_example=False)
        else:
            audit_dir = self.cfg.devmate_dir / "audit"
            audit_dir.mkdir(parents=True, exist_ok=True)
            out_file = audit_dir / f"audit_{ts_slug}.md"

        activity = self.memory.recent_activity(limit=100)
        manifest_p = self.cfg.devmate_dir / "backups" / "manifest.json"
        backups = []
        if manifest_p.exists():
            try:
                backups = json.loads(manifest_p.read_text(encoding="utf-8"))
            except Exception:
                pass

        doc = [
            "# Dev-Mate System Audit & Compliance Log",
            f"**Generated:** {now} | **Workspace Root:** `{self.root}`\n",
            "## 1. Executive Summary",
            f"- **Total Recorded Operations:** {len(activity)}",
            f"- **Total Automatic File Backups:** {len(backups)}",
            f"- **Active Provider:** `{self.cfg.provider}`",
            f"- **Execution Mode:** `{self.cfg.mode}`\n",
            "## 2. Activity Ledger",
            "| Timestamp | Action | Status | Details |",
            "| :--- | :--- | :---: | :--- |"
        ]

        for item in activity:
            ts = item.get("timestamp", "-")
            act = item.get("action", "-")
            status = item.get("status", "INFO")
            details = str(item.get("details", "")).replace("|", "\\|")
            doc.append(f"| {ts} | `{act}` | **{status}** | {details} |")

        if backups:
            doc.extend([
                "\n## 3. Atomic Backup Snapshots",
                "| Timestamp | Target File | Snapshot File |",
                "| :--- | :--- | :--- |"
            ])
            for b in backups[-20:]:
                doc.append(f"| {b.get('timestamp', '-')} | `{b.get('target', '-')}` | `{b.get('backup_file', '-')}` |")

        doc.append("\n---\n*Generated by Dev-Mate Autonomous Engineering Platform.*")
        report_content = "\n".join(doc)

        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(report_content, encoding="utf-8")
        rel_str = str(out_file.relative_to(self.root))
        self.memory.log("AUDIT", f"Exported audit log to {rel_str}", "PASS")
        return f"Audit report successfully exported to '{rel_str}' ({len(activity)} activities indexed)."

