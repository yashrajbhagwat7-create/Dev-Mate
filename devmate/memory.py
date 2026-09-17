import json
import time
from pathlib import Path


class Memory:
    def __init__(self, config):
        self.root = config.root
        self.devmate_dir = config.devmate_dir

        self.memory_file = self.devmate_dir / "memory.json"
        self.activity_file = self.devmate_dir / "activity.jsonl"

        self.devmate_dir.mkdir(exist_ok=True)
        (self.devmate_dir / "backups").mkdir(exist_ok=True)

        self._ensure_files()

    def _ensure_files(self):
        if not self.memory_file.exists():
            self.memory_file.write_text(
                json.dumps(
                    {
                        "project": {},
                        "decisions": [],
                        "important_files": [],
                        "known_issues": [],
                        "preferences": []
                    },
                    indent=2
                ),
                encoding="utf-8"
            )

        if not self.activity_file.exists():
            self.activity_file.touch()

    # -------------------------
    # PROJECT MEMORY
    # -------------------------

    def load(self):
        try:
            return json.loads(
                self.memory_file.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            return {
                "project": {},
                "decisions": [],
                "important_files": [],
                "known_issues": [],
                "preferences": []
            }

    def save(self, data):
        self.memory_file.write_text(
            json.dumps(data, indent=2),
            encoding="utf-8"
        )

    def remember(self, category, value):
        data = self.load()

        if category not in data:
            data[category] = []

        if isinstance(data[category], list):
            if value not in data[category]:
                data[category].append(value)

        elif isinstance(data[category], dict):
            if isinstance(value, dict):
                data[category].update(value)

        self.save(data)

    def forget(self, category, value=None):
        data = self.load()

        if category not in data:
            return

        if value is None:
            data[category] = [] if isinstance(data[category], list) else {}
        elif isinstance(data[category], list):
            if value in data[category]:
                data[category].remove(value)

        self.save(data)

    def get_context(self):
        """
        Return a compact version of memory suitable
        for sending to the LLM.
        """
        data = self.load()

        return json.dumps(data, indent=2)

    # -------------------------
    # ACTIVITY LOG
    # -------------------------

    def log(self, action, details="", status=None):
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "details": details
        }

        if status is not None:
            entry["status"] = status

        with self.activity_file.open(
            "a",
            encoding="utf-8"
        ) as f:
            f.write(json.dumps(entry) + "\n")

    def recent_activity(self, limit=20):
        if not self.activity_file.exists():
            return []

        lines = self.activity_file.read_text(
            encoding="utf-8"
        ).splitlines()

        results = []

        for line in lines[-limit:]:
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        return results

    def search_activity(self, query):
        query = query.lower()
        results = []

        if not self.activity_file.exists():
            return results

        for line in self.activity_file.read_text(
            encoding="utf-8"
        ).splitlines():

            if query in line.lower():
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

        return results

    def clear_activity(self):
        self.activity_file.write_text("", encoding="utf-8")