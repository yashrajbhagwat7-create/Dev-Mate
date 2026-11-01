"""Interactive Setup & Configuration Wizard for Dev-Mate.
Guides first-time users to set up Google Gemini, OpenRouter, or local Ollama
in under 30 seconds with live connection verification.
"""

import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Tuple, List, Dict, Optional

from .ui import panel, badge, style, Color


def verify_openrouter_key(api_key: str, base_url: str = "https://openrouter.ai/api/v1") -> Tuple[bool, str]:
    """Verify an OpenRouter API key with a fast verification request."""
    if not api_key or not api_key.strip():
        return False, "API key cannot be empty."

    url = f"{base_url.rstrip('/')}/auth/key"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "User-Agent": "Dev-Mate/0.1.0"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                label = data.get("data", {}).get("label") or "Valid Key"
                return True, f"OpenRouter authenticated successfully ({label})"
            return False, f"Unexpected response code: {resp.status}"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "Invalid API key (HTTP 401 Unauthorized)."
        return False, f"HTTP Error {e.code}: {e.reason}"
    except Exception as e:
        # Fallback format check if offline/firewalled
        if api_key.startswith("sk-or-"):
            return True, "Key format recognized (offline/skipped live verification)."
        return False, f"Connection failed: {e}"


def verify_google_key(api_key: str) -> Tuple[bool, str]:
    """Verify a Google Gemini API key via the v1beta models endpoint."""
    if not api_key or not api_key.strip():
        return False, "API key cannot be empty."

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key.strip()}"
    req = urllib.request.Request(url, headers={"User-Agent": "Dev-Mate/0.1.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                models = data.get("models", [])
                count = len(models)
                return True, f"Google Gemini authenticated successfully ({count} models available)"
            return False, f"Unexpected response code: {resp.status}"
    except urllib.error.HTTPError as e:
        if e.code in {400, 403}:
            return False, "Invalid Google Gemini API key or access restricted."
        return False, f"HTTP Error {e.code}: {e.reason}"
    except Exception as e:
        if api_key.startswith("AIza"):
            return True, "Key format recognized (offline/skipped live verification)."
        return False, f"Connection failed: {e}"


def verify_ollama_server(base_url: str = "http://localhost:11434") -> Tuple[bool, str, List[str]]:
    """Test local Ollama server connectivity and retrieve available local models."""
    clean_base = base_url.replace("/v1", "").rstrip("/")
    url = f"{clean_base}/api/tags"
    req = urllib.request.Request(url, headers={"User-Agent": "Dev-Mate/0.1.0"})
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name") for m in data.get("models", []) if m.get("name")]
                return True, f"Ollama is running ({len(models)} local model(s) installed)", models
            return False, f"Unexpected response: {resp.status}", []
    except Exception as e:
        return False, f"Ollama not reachable at {clean_base}: {e}", []


def save_env_settings(root: Path, settings: Dict[str, str]) -> Path:
    """Save key-value configuration into project .env file, preserving other lines."""
    env_file = root / ".env"
    existing_lines = []
    keys_updated = set()

    if env_file.exists():
        existing_lines = env_file.read_text(encoding="utf-8", errors="replace").splitlines()

    new_lines = []
    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, _ = stripped.split("=", 1)
            k = k.strip()
            if k in settings:
                new_lines.append(f"{k}={settings[k]}")
                keys_updated.add(k)
                continue
        new_lines.append(line)

    for k, v in settings.items():
        if k not in keys_updated:
            new_lines.append(f"{k}={v}")

    # Ensure newline at end
    output_text = "\n".join(new_lines).strip() + "\n"
    env_file.write_text(output_text, encoding="utf-8")
    return env_file


def run_setup_wizard(root: Path, interactive_input=input) -> bool:
    """
    Launch interactive onboarding wizard to configure AI providers and environment.
    Returns True if successfully configured, False if cancelled.
    """
    welcome_body = f"""Configure your AI provider in under 30 seconds to begin engineering with Dev-Mate.

{style('[1]', Color.BRIGHT_CYAN)} {style('Google Gemini', Color.BOLD, Color.WHITE)}: Fast, generous free tier via Google AI Studio
{style('[2]', Color.BRIGHT_CYAN)} {style('OpenRouter', Color.BOLD, Color.WHITE)}: Access to DeepSeek, Claude, Llama 3, GPT-4o, etc.
{style('[3]', Color.BRIGHT_CYAN)} {style('Ollama / Local', Color.BOLD, Color.WHITE)}: 100% Free, runs offline, zero API keys needed!
{style('[4]', Color.BRIGHT_CYAN)} {style('Cancel / Exit', Color.DIM)}
"""
    print(f"\n{panel('🪄  Dev-Mate Interactive Setup Wizard', welcome_body, border_color=Color.BRIGHT_CYAN)}")

    try:
        sys.stdout.write(f"\nSelect an option {style('[1-4]', Color.BRIGHT_YELLOW)} (default: 1): ")
        sys.stdout.flush()
        choice = interactive_input().strip() or "1"
    except (KeyboardInterrupt, EOFError):
        print(f"\n{badge('CANCELLED', 'warn')} Setup wizard aborted.")
        return False

    settings: Dict[str, str] = {}

    # Option 1: Google Gemini
    if choice == "1":
        print(f"\n{style('Google Gemini Setup', Color.BOLD, Color.BRIGHT_WHITE)}")
        print(f"Get a free API key at: {style('https://aistudio.google.com/app/apikey', Color.UNDERLINE, Color.BRIGHT_CYAN)}")
        try:
            sys.stdout.write("Paste your Gemini API key: ")
            sys.stdout.flush()
            key = interactive_input().strip()
        except (KeyboardInterrupt, EOFError):
            return False

        if not key:
            print(f"{badge('ERROR', 'fail')} No key provided. Aborting.")
            return False

        print(f"  {badge('TESTING', 'cyan')} Verifying key with Google AI...")
        ok, msg = verify_google_key(key)
        if ok:
            print(f"  {badge('PASS', 'pass')} {msg}")
        else:
            print(f"  {badge('WARN', 'warn')} {msg}")
            sys.stdout.write("Save this key anyway? (y/N): ")
            sys.stdout.flush()
            if interactive_input().strip().lower() not in {"y", "yes"}:
                return False

        settings["GOOGLE_API_KEY"] = key
        settings["DEV_MATE_PROVIDER"] = "google"
        settings["GOOGLE_MODEL"] = "gemini-2.5-flash"

    # Option 2: OpenRouter
    elif choice == "2":
        print(f"\n{style('OpenRouter Setup', Color.BOLD, Color.BRIGHT_WHITE)}")
        print(f"Get an API key at: {style('https://openrouter.ai/keys', Color.UNDERLINE, Color.BRIGHT_CYAN)}")
        try:
            sys.stdout.write("Paste your OpenRouter API key: ")
            sys.stdout.flush()
            key = interactive_input().strip()
        except (KeyboardInterrupt, EOFError):
            return False

        if not key:
            print(f"{badge('ERROR', 'fail')} No key provided. Aborting.")
            return False

        print(f"  {badge('TESTING', 'cyan')} Verifying key with OpenRouter...")
        ok, msg = verify_openrouter_key(key)
        if ok:
            print(f"  {badge('PASS', 'pass')} {msg}")
        else:
            print(f"  {badge('WARN', 'warn')} {msg}")
            sys.stdout.write("Save this key anyway? (y/N): ")
            sys.stdout.flush()
            if interactive_input().strip().lower() not in {"y", "yes"}:
                return False

        settings["OPENROUTER_API_KEY"] = key
        settings["DEV_MATE_PROVIDER"] = "openrouter"
        settings["OPENROUTER_MODEL"] = "openrouter/free"

    # Option 3: Ollama / Local
    elif choice == "3":
        print(f"\n{style('Ollama Local Setup (100% Free & Offline)', Color.BOLD, Color.BRIGHT_WHITE)}")
        default_url = "http://localhost:11434"
        try:
            sys.stdout.write(f"Ollama server URL (default: {default_url}): ")
            sys.stdout.flush()
            raw_url = interactive_input().strip() or default_url
        except (KeyboardInterrupt, EOFError):
            return False

        print(f"  {badge('TESTING', 'cyan')} Checking local Ollama instance...")
        ok, msg, models = verify_ollama_server(raw_url)
        if ok:
            print(f"  {badge('PASS', 'pass')} {msg}")
            model_choice = models[0] if models else "qwen2.5-coder:latest"
            if len(models) > 1:
                print(f"  Available models: {', '.join(models)}")
                sys.stdout.write(f"  Choose model (default: {model_choice}): ")
                sys.stdout.flush()
                chosen_m = interactive_input().strip()
                if chosen_m:
                    model_choice = chosen_m
        else:
            print(f"  {badge('WARN', 'warn')} {msg}")
            print(f"  Make sure Ollama is installed from {style('https://ollama.com', Color.CYAN)} and running ('ollama serve').")
            model_choice = "qwen2.5-coder:latest"

        settings["DEV_MATE_PROVIDER"] = "ollama"
        settings["OLLAMA_BASE_URL"] = f"{raw_url.rstrip('/')}/v1"
        settings["OLLAMA_MODEL"] = model_choice

    else:
        print(f"\n{badge('INFO', 'info')} Setup cancelled.")
        return False

    # Save to .env
    env_path = save_env_settings(root, settings)
    success_msg = f"""Configuration saved to {style(str(env_path.name), Color.BRIGHT_GREEN)}!

Active Provider : {style(settings.get('DEV_MATE_PROVIDER', '').upper(), Color.BOLD, Color.BRIGHT_GREEN)}
Settings Updated: {', '.join(settings.keys())}

You can now start Dev-Mate with:
  {style('devmate', Color.BOLD, Color.BRIGHT_CYAN)}
"""
    print(f"\n{panel('🎉 Setup Completed Successfully', success_msg, border_color=Color.BRIGHT_GREEN)}")
    return True
