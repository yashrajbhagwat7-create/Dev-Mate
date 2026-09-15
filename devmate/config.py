import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def as_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass
class Config:
    root: Path
    provider: str = os.getenv("DEV_MATE_PROVIDER", "openrouter")
    mode: str = os.getenv("DEV_MATE_MODE", "ask")
    openrouter_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "openrouter/free")
    google_key: str = os.getenv("GOOGLE_API_KEY", "")
    google_model: str = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")
    max_agent_turns: int = int(os.getenv("MAX_AGENT_TURNS", "30"))
    max_engineering_iterations: int = int(os.getenv("MAX_ENGINEERING_ITERATIONS", "10"))
    command_timeout: int = int(os.getenv("COMMAND_TIMEOUT", "120"))
    auto_approve_checkpoints: bool = as_bool("AUTO_APPROVE_CHECKPOINTS")
    allow_delete: bool = as_bool("ALLOW_DELETE")
    allow_commands: bool = as_bool("ALLOW_COMMANDS")
    allow_git_push: bool = as_bool("ALLOW_GIT_PUSH")

    @property
    def devmate_dir(self) -> Path:
        return self.root / ".devmate"
