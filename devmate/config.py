import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


def as_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass
class Config:
    root: Path
    provider: str = os.getenv("DEV_MATE_PROVIDER", "openrouter")
    mode: str = os.getenv("DEV_MATE_MODE", "ask")
    openrouter_key: Optional[str] = None
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "openrouter/free")
    openrouter_base_url: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:latest")
    google_key: Optional[str] = None
    google_model: str = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")
    max_agent_turns: int = int(os.getenv("MAX_AGENT_TURNS", "30"))
    max_engineering_iterations: int = int(os.getenv("MAX_ENGINEERING_ITERATIONS", "10"))
    max_verification_attempts: int = int(os.getenv("MAX_VERIFICATION_ATTEMPTS", "3"))
    command_timeout: int = int(os.getenv("COMMAND_TIMEOUT", "120"))
    verification_timeout: int = int(os.getenv("VERIFICATION_TIMEOUT", "120"))
    auto_approve_checkpoints: bool = as_bool("AUTO_APPROVE_CHECKPOINTS")
    allow_delete: bool = as_bool("ALLOW_DELETE")
    allow_commands: bool = as_bool("ALLOW_COMMANDS")
    allow_git_push: bool = as_bool("ALLOW_GIT_PUSH")

    # Antigravity-Style Token & Context Optimizations
    max_context_tokens: int = int(os.getenv("MAX_CONTEXT_TOKENS", "16000"))
    compact_context: bool = as_bool("COMPACT_CONTEXT", default=True)
    max_file_read_lines: int = int(os.getenv("MAX_FILE_READ_LINES", "150"))
    max_search_results: int = int(os.getenv("MAX_SEARCH_RESULTS", "25"))

    def __post_init__(self):
        if self.openrouter_key is None:
            self.openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
        if self.google_key is None:
            self.google_key = os.getenv("GOOGLE_API_KEY", "")
        # Adapt default context window budget to provider capacity when not explicitly configured
        if "MAX_CONTEXT_TOKENS" not in os.environ:
            p = (self.provider or "").lower()
            if p in {"google", "gemini"}:
                self.max_context_tokens = 128_000
            elif p == "openrouter":
                self.max_context_tokens = 32_000
            else:
                self.max_context_tokens = 16_000

    @property
    def devmate_dir(self) -> Path:
        return self.root / ".devmate"
