import json
from typing import Any
import requests


class ProviderError(RuntimeError):
    pass


class OpenRouterProvider:
    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise ProviderError("OPENROUTER_API_KEY is not set")
        self.key, self.model = api_key, model

    def chat(self, messages, tools):
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json", "X-Title": "Dev-Mate"},
            json={"model": self.model, "messages": messages, "tools": tools, "tool_choice": "auto"},
            timeout=180,
        )
        if not r.ok:
            raise ProviderError(f"OpenRouter {r.status_code}: {r.text[:2000]}")
        data = r.json()["choices"][0]["message"]
        return {"type": "tool" if data.get("tool_calls") else "text", "message": data}


class GoogleProvider:
    """Gemini generateContent adapter using the public REST API."""
    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise ProviderError("GOOGLE_API_KEY is not set")
        self.key, self.model = api_key, model

    @staticmethod
    def _convert_tools(tools):
        declarations = []
        for t in tools:
            f = t["function"]
            declarations.append({"name": f["name"], "description": f.get("description", ""), "parameters": f["parameters"]})
        return [{"functionDeclarations": declarations}]

    @staticmethod
    def _convert_messages(messages):
        contents = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                continue
            if role == "user":
                contents.append({"role": "user", "parts": [{"text": str(m.get("content", ""))}]})
            elif role == "assistant":
                parts = []
                if m.get("content"):
                    parts.append({"text": m["content"]})
                for tc in m.get("tool_calls", []):
                    fn = tc["function"]
                    try: args = json.loads(fn.get("arguments", "{}"))
                    except json.JSONDecodeError: args = {}
                    parts.append({"functionCall": {"name": fn["name"], "args": args, "id": tc.get("id", "")}})
                contents.append({"role": "model", "parts": parts or [{"text": ""}]})
            elif role == "tool":
                # Gemini accepts function responses as user-role parts.
                contents.append({"role": "user", "parts": [{"functionResponse": {"name": m.get("name", "tool"), "response": {"result": m.get("content", "")}}}]})
        return contents

    def chat(self, messages, tools):
        system = next((m["content"] for m in messages if m.get("role") == "system"), "")
        body = {"contents": self._convert_messages(messages), "tools": self._convert_tools(tools)}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self.key, "Content-Type": "application/json"},
            json=body,
            timeout=180,
        )
        if not r.ok:
            raise ProviderError(f"Google {r.status_code}: {r.text[:2000]}")
        data = r.json()
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts if "text" in p)
        calls = []
        for i, p in enumerate(parts):
            fc = p.get("functionCall")
            if fc:
                calls.append({"id": fc.get("id", f"google-call-{i}"), "type": "function", "function": {"name": fc["name"], "arguments": json.dumps(fc.get("args", {}))}})
        msg = {"role": "assistant", "content": text}
        if calls: msg["tool_calls"] = calls
        return {"type": "tool" if calls else "text", "message": msg}


def make_provider(config):
    if config.provider.lower() in {"google", "gemini"}:
        return GoogleProvider(config.google_key, config.google_model)
    return OpenRouterProvider(config.openrouter_key, config.openrouter_model)
