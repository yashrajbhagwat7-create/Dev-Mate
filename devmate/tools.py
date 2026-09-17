import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from .memory import Memory


TEXT_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css",
    ".json", ".yaml", ".yml", ".toml", ".md", ".txt", ".sql",
    ".java", ".cpp", ".c", ".h", ".hpp", ".rs", ".go",
    ".php", ".xml", ".ini", ".cfg", ".sh", ".ps1"
}

IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".idea",
    ".vscode",
    ".devmate"
}


def safe_path(root: Path, rel: str) -> Path:
    p = (root / rel).resolve()

    try:
        p.relative_to(root.resolve())
    except ValueError:
        raise ValueError("Path escapes the project root")

    return p


class ToolBox:
    def __init__(self, config, approve):
        self.root = config.root.resolve()
        self.cfg = config
        self.approve = approve
        self.memory = Memory(config)

        self.cfg.devmate_dir.mkdir(exist_ok=True)
        (self.cfg.devmate_dir / "backups").mkdir(exist_ok=True)

    def _backup(self, p: Path):
        if p.exists() and p.is_file():
            stamp = time.strftime("%Y%m%d-%H%M%S")
            dst = self.cfg.devmate_dir / "backups" / f"{stamp}_{p.name}"
            shutil.copy2(p, dst)

    def list_files(self, path="."):
        base = safe_path(self.root, path)
        out = []

        for p in sorted(base.rglob("*")):
            if any(part in IGNORE_DIRS for part in p.parts):
                continue

            if p.is_file():
                out.append(str(p.relative_to(self.root)))

        return "\n".join(out[:1000])

    def read_file(self, path, start_line=1, end_line=400):
        p = safe_path(self.root, path)

        if not p.is_file():
            raise FileNotFoundError(path)

        lines = p.read_text(
            encoding="utf-8",
            errors="replace"
        ).splitlines()

        start = max(1, int(start_line))
        end = min(len(lines), int(end_line))

        result = "\n".join(
            f"{i}: {lines[i - 1]}"
            for i in range(start, end + 1)
        )

        self.memory.log(
            "READ",
            f"{path} lines {start}-{end}"
        )

        return result

    def search_files(self, query, path="."):
        base = safe_path(self.root, path)
        hits = []
        q = query.lower()

        for p in base.rglob("*"):
            if (
                not p.is_file()
                or p.suffix.lower() not in TEXT_EXTS
                or any(part in IGNORE_DIRS for part in p.parts)
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
                    hits.append(
                        f"{p.relative_to(self.root)}:{i}: {line[:300]}"
                    )

                    if len(hits) >= 200:
                        result = "\n".join(hits)

                        self.memory.log(
                            "SEARCH",
                            f"query={query}, path={path}"
                        )

                        return result

        result = "\n".join(hits) or "No matches."

        self.memory.log(
            "SEARCH",
            f"query={query}, path={path}"
        )

        return result

    def write_file(self, path, content):
        p = safe_path(self.root, path)

        self._backup(p)

        p.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        p.write_text(
            content,
            encoding="utf-8"
        )

        relative = str(p.relative_to(self.root))

        self.memory.log(
            "WRITE",
            relative
        )

        return f"Wrote {relative}"

    def edit_file(self, path, old_text, new_text):
        p = safe_path(self.root, path)

        if not p.is_file():
            raise FileNotFoundError(path)

        text = p.read_text(
            encoding="utf-8",
            errors="replace"
        )

        if old_text not in text:
            raise ValueError(
                "old_text was not found exactly; reread the file"
            )

        self._backup(p)

        p.write_text(
            text.replace(old_text, new_text, 1),
            encoding="utf-8"
        )

        relative = str(p.relative_to(self.root))

        self.memory.log(
            "EDIT",
            relative
        )

        return f"Edited {relative}"

    def delete_file(self, path):
        p = safe_path(self.root, path)

        if not self.cfg.allow_delete:
            if not self.approve(
                f"Delete {path}? [y/N] "
            ):
                return "Deletion cancelled by user."

        if p.is_file():
            self._backup(p)
            p.unlink()

            self.memory.log(
                "DELETE",
                path
            )

            return f"Deleted {path}"

        raise FileNotFoundError(path)

    def run_command(self, command):
        if not self.cfg.allow_commands:
            if not self.approve(
                f"Run command?\n  {command}\n[y/N] "
            ):
                return "Command cancelled by user."

        r = subprocess.run(
            command,
            cwd=self.root,
            shell=True,
            text=True,
            capture_output=True,
            timeout=self.cfg.command_timeout
        )

        result = json.dumps(
            {
                "returncode": r.returncode,
                "stdout": r.stdout[-12000:],
                "stderr": r.stderr[-12000:]
            },
            ensure_ascii=False
        )

        status = "PASS" if r.returncode == 0 else "FAIL"

        self.memory.log(
            "RUN",
            command,
            status
        )

        return result

    def run_python(self, path):
        return self.run_command(
            f'python "{path}"'
        )

    def git_status(self):
        return self.run_command(
            "git status --short"
        )

    def git_diff(self):
        return self.run_command(
            "git diff -- ."
        )

    def project_summary(self):
        files = self.list_files(".").splitlines()

        ext = {}

        for f in files:
            e = Path(f).suffix or "[no extension]"
            ext[e] = ext.get(e, 0) + 1

        return json.dumps(
            {
                "root": str(self.root),
                "file_count": len(files),
                "extensions": ext,
                "files": files[:300]
            },
            indent=2
        )