"""
Optional LLM helper. Works with the Claude API (set ANTHROPIC_API_KEY) or any
OpenAI-compatible endpoint, including a local Ollama server (set LLM_BASE_URL and
LLM_MODEL, plus LLM_API_KEY if the endpoint needs one).

With neither configured, available() is False and every caller falls back to
rules, so the app always runs - and a rate limit can never kill your live demo.
"""
from __future__ import annotations

import json
import os
import re

import httpx

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
BASE_URL = os.getenv("LLM_BASE_URL")        # e.g. http://localhost:11434/v1 for Ollama
MODEL = os.getenv("LLM_MODEL")              # e.g. llama3.1
API_KEY = os.getenv("LLM_API_KEY", "none")
TIMEOUT = float(os.getenv("LLM_TIMEOUT", "12"))


def available() -> bool:
    return bool(ANTHROPIC_KEY or (BASE_URL and MODEL))


def complete(system: str, user: str, max_tokens: int = 300) -> str | None:
    """One-shot completion. Returns None on any failure so callers can fall back."""
    try:
        if ANTHROPIC_KEY:
            r = httpx.post(
                "https://api.anthropic.com/v1/messages", timeout=TIMEOUT,
                headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": ANTHROPIC_MODEL, "max_tokens": max_tokens, "temperature": 0,
                      "system": system, "messages": [{"role": "user", "content": user}]})
            r.raise_for_status()
            return "".join(b.get("text", "") for b in r.json().get("content", []))
        if BASE_URL and MODEL:
            r = httpx.post(
                BASE_URL.rstrip("/") + "/chat/completions", timeout=TIMEOUT,
                headers={"Authorization": f"Bearer {API_KEY}"},
                json={"model": MODEL, "max_tokens": max_tokens, "temperature": 0,
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": user}]})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
    except Exception as exc:  # network error, rate limit, bad key, odd response...
        print(f"[llm] falling back to rules: {exc}")
    return None


def complete_json(system: str, user: str, max_tokens: int = 300) -> dict | None:
    """Like complete(), but parses the first JSON object in the reply."""
    text = complete(system + "\nReply with one JSON object and nothing else.", user, max_tokens)
    match = re.search(r"\{.*\}", text or "", re.S)
    try:
        data = json.loads(match.group(0)) if match else None
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
