"""LLM provider adapters for OpenRouter, Google Gemini, and local OpenAI-compatible endpoints."""

import json
import time
from typing import Any, Dict, List
import requests


class ProviderError(RuntimeError):
    pass


def _request_with_retry(post_fn, max_retries: int = 3, initial_delay: float = 1.0):
    """Execute an HTTP request with exponential backoff on rate limits (429) and transient server errors (5xx)."""
    delay = initial_delay
    last_err = None
    for attempt in range(max_retries):
        try:
            r = post_fn()
            if r.status_code in {429, 500, 502, 503, 504} and attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 2.0
                continue
            return r
        except requests.RequestException as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 2.0
            else:
                raise
    if last_err:
        raise last_err


class OpenRouterProvider:
    """OpenRouter and OpenAI-compatible chat-completions adapter."""

    def __init__(self, api_key: str, model: str, base_url: str = "https://openrouter.ai/api/v1"):
        if not api_key:
            raise ProviderError("OPENROUTER_API_KEY is not set. Set it in your .env file or environment.")
        self.key, self.model = api_key, model
        self.base_url = base_url.rstrip("/")

    def chat(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        try:
            r = _request_with_retry(
                lambda: requests.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self.key}",
                        "Content-Type": "application/json",
                        "X-Title": "Dev-Mate"
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "tools": tools,
                        "tool_choice": "auto"
                    },
                    timeout=180,
                )
            )
        except requests.RequestException as e:
            raise ProviderError(f"Connection failed ({self.base_url}): {e}")

        if not r.ok:
            raise ProviderError(f"Provider HTTP {r.status_code}: {r.text[:2000]}")

        try:
            data = r.json()
        except ValueError:
            raise ProviderError("Provider returned invalid JSON response")

        choices = data.get("choices") or []
        if not choices:
            error_msg = data.get("error", "No response choices returned by provider")
            raise ProviderError(f"Provider API error: {error_msg}")

        msg = choices[0].get("message") or {}
        return {
            "type": "tool" if msg.get("tool_calls") else "text",
            "message": msg
        }


class GoogleProvider:
    """Gemini generateContent adapter using the public REST API with function-calling."""

    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise ProviderError("GOOGLE_API_KEY is not set. Set it in your .env file or environment.")
        self.key, self.model = api_key, model

    @staticmethod
    def _convert_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        declarations = []
        for t in tools:
            f = t["function"]
            declarations.append({
                "name": f["name"],
                "description": f.get("description", ""),
                "parameters": f.get("parameters", {})
            })
        return [{"functionDeclarations": declarations}]

    @staticmethod
    def _convert_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        contents = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                continue

            if role == "user":
                contents.append({
                    "role": "user",
                    "parts": [{"text": str(m.get("content", ""))}]
                })

            elif role == "assistant":
                parts = []
                if m.get("content"):
                    parts.append({"text": str(m["content"])})

                for tc in m.get("tool_calls", []):
                    fn = tc.get("function", {})
                    raw_args = fn.get("arguments", "{}")
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except json.JSONDecodeError:
                        args = {}

                    parts.append({
                        "functionCall": {
                            "name": fn.get("name", ""),
                            "args": args if isinstance(args, dict) else {},
                            "id": tc.get("id", "")
                        }
                    })

                contents.append({"role": "model", "parts": parts or [{"text": ""}]})

            elif role == "tool":
                # Gemini accepts function responses as functionResponse parts
                contents.append({
                    "role": "user",
                    "parts": [{
                        "functionResponse": {
                            "name": m.get("name", "tool"),
                            "response": {"result": str(m.get("content", ""))}
                        }
                    }]
                })

        return contents

    def chat(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        system = next((m["content"] for m in messages if m.get("role") == "system"), "")
        body: Dict[str, Any] = {
            "contents": self._convert_messages(messages),
            "tools": self._convert_tools(tools)
        }

        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        try:
            r = _request_with_retry(
                lambda: requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                    headers={"x-goog-api-key": self.key, "Content-Type": "application/json"},
                    json=body,
                    timeout=180,
                )
            )
        except requests.RequestException as e:
            raise ProviderError(f"Google Gemini connection failed: {e}")

        if not r.ok:
            raise ProviderError(f"Google HTTP {r.status_code}: {r.text[:2000]}")

        try:
            data = r.json()
        except ValueError:
            raise ProviderError("Google Gemini returned invalid JSON response")

        candidates = data.get("candidates") or []
        if not candidates:
            feedback = data.get("promptFeedback") or {}
            block_reason = feedback.get("blockReason", "Blocked by safety filter or empty response")
            raise ProviderError(f"Google Gemini returned no candidates ({block_reason})")

        cand = candidates[0]
        finish_reason = cand.get("finishReason")
        if finish_reason in {"SAFETY", "RECITATION", "BLOCKLIST"}:
            raise ProviderError(f"Google Gemini response blocked by policy ({finish_reason})")

        content = cand.get("content") or {}
        parts = content.get("parts") or []
        text = "".join(p.get("text", "") for p in parts if "text" in p)

        calls = []
        for i, p in enumerate(parts):
            fc = p.get("functionCall")
            if fc:
                args = fc.get("args") or {}
                calls.append({
                    "id": fc.get("id", f"google-call-{i}"),
                    "type": "function",
                    "function": {
                        "name": fc.get("name", ""),
                        "arguments": json.dumps(args, ensure_ascii=False)
                    }
                })

        msg: Dict[str, Any] = {"role": "assistant", "content": text}
        if calls:
            msg["tool_calls"] = calls

        return {"type": "tool" if calls else "text", "message": msg}


def make_provider(config):
    p = config.provider.lower()
    if p in {"google", "gemini"}:
        return GoogleProvider(config.google_key, config.google_model)
    elif p in {"ollama", "local"}:
        base_url = getattr(config, "ollama_base_url", "http://localhost:11434/v1")
        model = getattr(config, "ollama_model", "qwen2.5-coder:latest")
        return OpenRouterProvider(api_key="ollama", model=model, base_url=base_url)
    base_url = getattr(config, "openrouter_base_url", "https://openrouter.ai/api/v1")
    return OpenRouterProvider(config.openrouter_key, config.openrouter_model, base_url=base_url)


def get_provider(config, name: str = None):
    """Instantiate a specific provider by name, or fallback to configured provider."""
    chosen = (name or config.provider).lower()
    if chosen in {"google", "gemini"}:
        return GoogleProvider(config.google_key, config.google_model)
    elif chosen in {"ollama", "local"}:
        base_url = getattr(config, "ollama_base_url", "http://localhost:11434/v1")
        model = getattr(config, "ollama_model", "qwen2.5-coder:latest")
        return OpenRouterProvider(api_key="ollama", model=model, base_url=base_url)
    elif chosen in {"openrouter", "openai"}:
        base_url = getattr(config, "openrouter_base_url", "https://openrouter.ai/api/v1")
        return OpenRouterProvider(config.openrouter_key, config.openrouter_model, base_url=base_url)
    return make_provider(config)


