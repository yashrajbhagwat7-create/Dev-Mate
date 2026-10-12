"""Project memory and activity logging for Dev-Mate."""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class Memory:
    def __init__(self, config):
        self.root = config.root
        self.devmate_dir = config.devmate_dir

        self.memory_file = self.devmate_dir / "memory.json"
        self.activity_file = self.devmate_dir / "activity.jsonl"
        self.mistakes_file = self.devmate_dir / "mistakes.json"

        self.devmate_dir.mkdir(exist_ok=True)
        (self.devmate_dir / "backups").mkdir(exist_ok=True)

        self._ensure_files()

    def _ensure_files(self):
        if not self.memory_file.exists():
            default_data = {
                "project": {},
                "decisions": [],
                "important_files": [],
                "known_issues": [],
                "preferences": [],
                "mistakes": [],
                "prompt_improvements": []
            }
            try:
                self.memory_file.write_text(
                    json.dumps(default_data, indent=2),
                    encoding="utf-8"
                )
            except OSError:
                pass

        if not self.activity_file.exists():
            try:
                self.activity_file.touch()
            except OSError:
                pass

        if not self.mistakes_file.exists():
            try:
                self.mistakes_file.write_text(
                    json.dumps([], indent=2),
                    encoding="utf-8"
                )
            except OSError:
                pass

    # -------------------------
    # PROJECT MEMORY
    # -------------------------

    def load(self) -> Dict[str, Any]:
        try:
            return json.loads(self.memory_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {
                "project": {},
                "decisions": [],
                "important_files": [],
                "known_issues": [],
                "preferences": []
            }

    def save(self, data: Dict[str, Any]):
        try:
            self.memory_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except OSError:
            pass

    def remember(self, category: str, value: Any):
        data = self.load()
        if category not in data:
            data[category] = {} if isinstance(value, dict) else []

        if isinstance(data[category], dict):
            if isinstance(value, dict):
                data[category].update(value)
            else:
                data[category][str(value)] = True
        elif isinstance(data[category], list):
            if isinstance(value, dict) and len(data[category]) == 0:
                data[category] = value
            elif value not in data[category]:
                data[category].append(value)

        self.save(data)

    def forget(self, category: str, value: Any = None):
        data = self.load()
        if category not in data:
            return

        if value is None:
            data[category] = [] if isinstance(data[category], list) else {}
        elif isinstance(data[category], list) and value in data[category]:
            data[category].remove(value)
        elif isinstance(data[category], dict) and value in data[category]:
            del data[category][value]

        self.save(data)

    def get_context(self) -> str:
        """Return a compact JSON version of memory for inclusion in LLM prompt context."""
        return json.dumps(self.load(), indent=2, ensure_ascii=False)

    # -------------------------
    # MISTAKE TRACKING
    # -------------------------

    def load_mistakes(self) -> List[Dict[str, Any]]:
        """Load recorded mistakes from mistakes.json."""
        try:
            return json.loads(self.mistakes_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def save_mistakes(self, mistakes: List[Dict[str, Any]]):
        """Save mistakes list to mistakes.json."""
        try:
            self.mistakes_file.write_text(
                json.dumps(mistakes, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except OSError:
            pass

    def record_mistake(
        self,
        mistake_type: str,
        description: str,
        context: str = "",
        correction: str = "",
        files_affected: Optional[List[str]] = None
    ):
        """Record a mistake with full context for future reference."""
        mistakes = self.load_mistakes()
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "type": mistake_type,
            "description": description,
            "context": context[:500],
            "correction": correction[:500],
            "files_affected": files_affected or [],
            "occurrences": 1
        }

        # Check if similar mistake already exists
        for existing in mistakes:
            if (existing.get("type") == mistake_type and
                existing.get("description") == description):
                existing["occurrences"] = existing.get("occurrences", 1) + 1
                existing["last_seen"] = entry["timestamp"]
                self.save_mistakes(mistakes)
                return

        mistakes.append(entry)
        self.save_mistakes(mistakes)

    def get_mistakes_context(self, limit: int = 10) -> str:
        """Return recent mistakes as compact JSON for inclusion in prompt context."""
        mistakes = self.load_mistakes()
        if not mistakes:
            return "No recorded mistakes yet."
        recent = mistakes[-limit:]
        return json.dumps(recent, indent=2, ensure_ascii=False)

    # -------------------------
    # PROMPT IMPROVEMENTS
    # -------------------------

    def record_prompt_improvement(
        self,
        original_prompt: str,
        issue: str,
        improved_prompt: str,
        reason: str
    ):
        """Record a prompt refinement with rationale."""
        data = self.load()
        if "prompt_improvements" not in data:
            data["prompt_improvements"] = []

        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "original_prompt": original_prompt[:300],
            "issue": issue[:300],
            "improved_prompt": improved_prompt[:500],
            "reason": reason[:300]
        }
        data["prompt_improvements"].append(entry)
        self.save(data)

    def get_prompt_improvements_context(self, limit: int = 5) -> str:
        """Return recent prompt improvements as compact JSON."""
        data = self.load()
        improvements = data.get("prompt_improvements", [])
        if not improvements:
            return "No prompt improvements recorded yet."
        recent = improvements[-limit:]
        return json.dumps(recent, indent=2, ensure_ascii=False)

    # -------------------------
    # ACTIVITY LOG
    # -------------------------

    def log(self, action: str, details: str = "", status: Optional[str] = None):
        """Append an activity log entry with truncated details to avoid unbounded prompt growth."""
        clean_details = str(details).replace("\r\n", " ").replace("\n", " ").strip()
        if len(clean_details) > 350:
            clean_details = clean_details[:347] + "..."

        entry: Dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "details": clean_details
        }
        if status is not None:
            entry["status"] = status

        try:
            with self.activity_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def recent_activity(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return the most recent activity entries safely."""
        if not self.activity_file.exists():
            return []

        try:
            lines = self.activity_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []

        results = []
        for line in lines[-limit:]:
            line_str = line.strip()
            if not line_str:
                continue
            try:
                results.append(json.loads(line_str))
            except json.JSONDecodeError:
                continue
        return results

    def search_activity(self, query: str) -> List[Dict[str, Any]]:
        query = query.lower()
        results = []
        if not self.activity_file.exists():
            return results

        try:
            lines = self.activity_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            return results

        for line in lines:
            if query in line.lower():
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return results

    def clear_activity(self):
        try:
            self.activity_file.write_text("", encoding="utf-8")
        except OSError:
            pass