import os
from pathlib import Path

import requests
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("OPENROUTER_API_KEY")

if not API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY is missing from .env")


API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openrouter/free"


def call_llm(messages):

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": MODEL,
        "messages": messages,
    }

    response = requests.post(
        API_URL,
        headers=headers,
        json=payload,
        timeout=60,
    )

    if response.status_code != 200:
        print("\n--- OPENROUTER ERROR ---")
        print("Status:", response.status_code)
        print("OpenRouter response:", response.text)
        print("------------------------\n")

        raise RuntimeError(
            f"OpenRouter request failed with status {response.status_code}"
        )

    data = response.json()

    try:
        return data["choices"][0]["message"]["content"]

    except (KeyError, IndexError, TypeError):
        print("Unexpected API response:")
        print(data)

        raise RuntimeError(
            "Could not extract model response."
        )