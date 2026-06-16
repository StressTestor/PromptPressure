"""Tests for the native DeepSeek adapter (api.deepseek.com)."""

from unittest.mock import AsyncMock, patch

import pytest

from promptpressure.adapters import deepseek_adapter, load_adapter


def test_native_adapter_registered():
    for name in ("deepseek_native", "deepseek_chat", "deepseek_api"):
        adapter = load_adapter(name)
        assert callable(adapter)


def test_native_distinct_from_openrouter_r1():
    # `deepseek` / `deepseek_r1` still route to the OpenRouter R1 adapter,
    # the native one is a separate provider.
    assert load_adapter("deepseek_native") is not load_adapter("deepseek_r1")


async def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        await deepseek_adapter.generate_response("hi", "deepseek-chat", config={})


async def test_generate_response_parses_content(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    captured = {}

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = lambda: {"choices": [{"message": {"content": "hello from deepseek"}}]}
    mock_response.raise_for_status = lambda: None

    async def fake_post(url, headers=None, json=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return mock_response

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = fake_post
        out = await deepseek_adapter.generate_response(
            "hi", "deepseek-v4-flash",
            config={"temperature": 0.2},
            messages=[{"role": "user", "content": "hi"}],
        )

    assert out == "hello from deepseek"
    assert captured["url"] == deepseek_adapter.DEFAULT_ENDPOINT
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["json"]["model"] == "deepseek-v4-flash"
    assert captured["json"]["temperature"] == 0.2
    assert captured["json"]["messages"] == [{"role": "user", "content": "hi"}]


async def test_empty_choices_raises(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    mock_response = AsyncMock()
    mock_response.json = lambda: {"choices": []}
    mock_response.raise_for_status = lambda: None

    async def fake_post(url, headers=None, json=None):
        return mock_response

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = fake_post
        with pytest.raises(ValueError, match="empty response"):
            await deepseek_adapter.generate_response("hi", "deepseek-chat", config={})
