"""Toolbox providing file, search, command, and git operations for Dev-Mate.
Equipped with strict path traversal, shell injection, and secret protections,
and optimized for minimal API token consumption on large repositories.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Union, Optional, Callable

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
        """Create a timestamped backup before modifying or deleting a file."""
        if p.exists() and p.is_file():
            stamp = time.strftime("%Y%m%d-%H%M%S")
            backup_dir = self.cfg.devmate_dir / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            dst = backup_dir / f"{stamp}_{p.name}"
            try:
                shutil.copy2(p, dst)
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
        """Read a text file with line numbers, guarded against secret exfiltration and token blowup."""
        p = safe_path(self.root, path, allow_env_example=True)

        if not p.is_file():
            raise FileNotFoundError(f"File not found: {path}")

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
        """Replace one exact text block in an existing file."""
        p = safe_path(self.root, path, allow_env_example=False)

        if not p.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        text = p.read_text(encoding="utf-8", errors="replace")

        if old_text not in text:
            raise ValueError("old_text was not found exactly; reread the file")

        self._backup(p)
        p.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")

        relative = str(p.relative_to(self.root))
        self.memory.log("EDIT", relative)
        return f"Edited {relative}"

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