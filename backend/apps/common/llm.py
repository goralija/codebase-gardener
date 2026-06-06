"""Minimal OpenRouter chat-completion client for the AI code-fix author.

Deterministic (temperature 0) single-turn completions. Never logs the API key
or full prompts/responses.
"""

from __future__ import annotations

import httpx
from django.conf import settings


class LLMError(RuntimeError):
    """Raised when the LLM request fails or returns an unusable response."""


def complete(prompt: str, *, system: str | None = None, temperature: float = 0.0) -> str:
    """Return the assistant message text for a single prompt.

    Raises LLMError on missing config, transport failure, non-200, or empty body.
    """
    api_key = settings.OPENROUTER_API_KEY
    if not api_key:
        raise LLMError("OPENROUTER_API_KEY is not configured.")

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    url = f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"
    try:
        response = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.OPENROUTER_MODEL,
                "messages": messages,
                "temperature": temperature,
            },
            timeout=settings.OPENROUTER_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise LLMError("LLM request failed.") from exc

    if response.status_code != 200:
        raise LLMError(f"LLM returned status {response.status_code}.")

    try:
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMError("LLM response was malformed.") from exc

    if not isinstance(content, str) or not content.strip():
        raise LLMError("LLM returned an empty completion.")
    return content
