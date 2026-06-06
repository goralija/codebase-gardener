import json

import httpx
import pytest

from apps.common.llm import LLMError, complete


class _Resp:
    def __init__(self, status_code, payload=None, text=None):
        self.status_code = status_code
        self.text = text if text is not None else json.dumps(payload or {})


def test_complete_builds_request_and_returns_content(monkeypatch, settings):
    settings.OPENROUTER_API_KEY = "sk-test"
    settings.OPENROUTER_MODEL = "deepseek/deepseek-chat"
    settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
    captured = {}

    def fake_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _Resp(200, {"choices": [{"message": {"content": "fixed code"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)

    out = complete("do the thing", system="be careful")

    assert out == "fixed code"
    assert captured["url"].endswith("/chat/completions")
    assert captured["json"]["model"] == "deepseek/deepseek-chat"
    assert captured["json"]["temperature"] == 0.0
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    roles = [m["role"] for m in captured["json"]["messages"]]
    assert roles == ["system", "user"]


def test_complete_tolerates_openrouter_keepalive_prefix(monkeypatch, settings):
    settings.OPENROUTER_API_KEY = "sk-test"
    body = ": OPENROUTER PROCESSING\n\n: OPENROUTER PROCESSING\n\n" + json.dumps(
        {"choices": [{"message": {"content": "fixed"}}]}
    )
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp(200, text=body))
    assert complete("x") == "fixed"


def test_complete_requires_api_key(monkeypatch, settings):
    settings.OPENROUTER_API_KEY = ""
    with pytest.raises(LLMError):
        complete("x")


def test_complete_raises_on_non_200(monkeypatch, settings):
    settings.OPENROUTER_API_KEY = "sk-test"
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp(500))
    with pytest.raises(LLMError):
        complete("x")


def test_complete_raises_on_empty_completion(monkeypatch, settings):
    settings.OPENROUTER_API_KEY = "sk-test"
    monkeypatch.setattr(
        httpx, "post", lambda *a, **k: _Resp(200, {"choices": [{"message": {"content": "  "}}]})
    )
    with pytest.raises(LLMError):
        complete("x")
