"""AI Studio service — reusable wrapper for Gemini API calls.

Usage:
    from ai_service import ai_analyze, ai_chat

    # One-shot analysis
    result = ai_analyze("Analyze this distribution: ...")

    # Multi-turn chat
    result = ai_chat([
        {"role": "user", "parts": [{"text": "Hello"}]},
    ])
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from config import get_api_key, get_api_base_url


def _headers() -> dict[str, str]:
    return {"Content-Type": "application/json"}


def _url(path: str) -> str:
    base = get_api_base_url().rstrip("/")
    key = get_api_key()
    sep = "&" if "?" in path else "?"
    return f"{base}/{path}{sep}key={key}"


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _post(path: str, body: dict, timeout: float = 60.0) -> dict[str, Any]:
    resp = httpx.post(_url(path), headers=_headers(), json=body, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ai_analyze(prompt: str, *, model: str = "gemini-2.0-flash",
               temperature: float = 0.3, max_tokens: int = 2048) -> str:
    """Send a single prompt and return the model's text response."""
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    data = _post(f"models/{model}:generateContent", body)
    return _extract_text(data)


def ai_chat(messages: list[dict], *, model: str = "gemini-2.0-flash",
            temperature: float = 0.3, max_tokens: int = 2048) -> str:
    """Send a multi-turn conversation and return the model's text response."""
    body = {
        "contents": messages,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    data = _post(f"models/{model}:generateContent", body)
    return _extract_text(data)


def ai_analyze_json(prompt: str, *, model: str = "gemini-2.0-flash",
                    temperature: float = 0.2) -> dict[str, Any]:
    """Send a prompt expecting a JSON response. Returns parsed dict."""
    full_prompt = prompt + "\n\nReturn ONLY valid JSON, no markdown fences."
    body = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
        },
    }
    data = _post(f"models/{model}:generateContent", body)
    text = _extract_text(data)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def _extract_text(data: dict) -> str:
    try:
        candidates = data.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError):
        return ""


# ---------------------------------------------------------------------------
# Quick health check
# ---------------------------------------------------------------------------

def ai_check_connection() -> bool:
    """Verify the API key is valid by sending a minimal request."""
    try:
        text = ai_analyze("Say 'ok'", max_tokens=10)
        return "ok" in text.lower()
    except Exception:
        return False
