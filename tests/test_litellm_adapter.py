"""Tests for promptpressure.adapters.litellm_adapter module.

All tests use mocked HTTP responses. No live API calls.
"""
import json
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

from promptpressure.adapters.litellm_adapter import (
    _resolve_api_key,
    generate_response,
    get_last_reasoning,
    get_last_usage,
    get_last_metadata,
)


# ---------------------------------------------------------------------------
# _resolve_api_key
# ---------------------------------------------------------------------------

class TestResolveApiKey:
    def test_config_key_takes_priority(self):
        config = {"litellm_api_key": "config-key-123"}
        assert _resolve_api_key("https://api.x.ai/v1", config) == "config-key-123"

    def test_empty_config_key_falls_through(self):
        """Empty string in config should NOT be treated as a valid key."""
        config = {"litellm_api_key": ""}
        # falls through to env var check since empty string is falsy
        with patch.dict("os.environ", {"XAI_API_KEY": "env-key"}, clear=False):
            result = _resolve_api_key("https://api.x.ai/v1", config)
            assert result == "env-key"

    def test_xai_endpoint_resolves_xai_key(self):
        with patch.dict("os.environ", {"XAI_API_KEY": "xai-test"}, clear=False):
            assert _resolve_api_key("https://api.x.ai/v1/chat/completions", None) == "xai-test"

    def test_anthropic_endpoint_resolves_anthropic_key(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=False):
            assert _resolve_api_key("https://api.anthropic.com/v1/messages", None) == "sk-ant-test"

    def test_google_endpoint_resolves_google_key(self):
        with patch.dict("os.environ", {"GOOGLE_API_KEY": "AIza-test"}, clear=False):
            assert _resolve_api_key("https://generativelanguage.googleapis.com/v1beta/openai", None) == "AIza-test"

    def test_openrouter_endpoint_resolves_openrouter_key(self):
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "sk-or-test"}, clear=False):
            assert _resolve_api_key("https://openrouter.ai/api/v1/chat/completions", None) == "sk-or-test"

    def test_deepseek_endpoint_resolves_deepseek_key(self):
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-ds-test"}, clear=False):
            assert _resolve_api_key("https://api.deepseek.com/v1", None) == "sk-ds-test"

    def test_openai_endpoint_resolves_openai_key(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=False):
            assert _resolve_api_key("https://api.openai.com/v1/chat/completions", None) == "sk-test"

    def test_localhost_falls_back_to_litellm_key(self):
        with patch.dict("os.environ", {"LITELLM_API_KEY": "lm-key"}, clear=False):
            assert _resolve_api_key("http://localhost:4000/v1/chat/completions", None) == "lm-key"

    def test_unknown_endpoint_returns_empty(self):
        with patch.dict("os.environ", {}, clear=True):
            assert _resolve_api_key("https://random-api.example.com/v1", None) == ""

    def test_none_config_doesnt_crash(self):
        result = _resolve_api_key("https://api.x.ai/v1", None)
        assert isinstance(result, str)

    def test_case_insensitive_endpoint(self):
        with patch.dict("os.environ", {"XAI_API_KEY": "xai-test"}, clear=False):
            assert _resolve_api_key("https://API.X.AI/v1/chat", None) == "xai-test"


# ---------------------------------------------------------------------------
# generate_response — OpenAI-compatible path (mocked)
# ---------------------------------------------------------------------------

class TestGenerateResponseOpenAI:
    """Tests for the standard OpenAI chat completions path."""

    @pytest.mark.asyncio
    async def test_single_turn_returns_content(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello there"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        with patch("promptpressure.adapters.litellm_adapter.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            config = {"litellm_endpoint": "https://openrouter.ai/api/v1/chat/completions", "temperature": 0.5}
            with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}, clear=False):
                result = await generate_response("Say hello", "gpt-4o", config)

            assert result == "Hello there"
            assert get_last_usage() == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}

    @pytest.mark.asyncio
    async def test_reasoning_extraction_from_field(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {
                "content": "The answer is 4",
                "reasoning_content": "2+2=4, simple arithmetic",
            }}],
            "usage": {},
        }

        with patch("promptpressure.adapters.litellm_adapter.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            config = {"litellm_endpoint": "https://api.x.ai/v1/chat/completions"}
            with patch.dict("os.environ", {"XAI_API_KEY": "test"}, clear=False):
                result = await generate_response("What is 2+2", "grok-4.20", config)

            assert result == "The answer is 4"
            assert get_last_reasoning() == "2+2=4, simple arithmetic"

    @pytest.mark.asyncio
    async def test_reasoning_extraction_from_think_tags(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {
                "content": "<think>Let me think about this</think>The answer is 42",
            }}],
            "usage": {},
        }

        with patch("promptpressure.adapters.litellm_adapter.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            config = {"litellm_endpoint": "https://api.x.ai/v1/chat/completions"}
            with patch.dict("os.environ", {"XAI_API_KEY": "test"}, clear=False):
                result = await generate_response("Deep question", "some-model", config)

            assert result == "The answer is 42"
            assert get_last_reasoning() == "Let me think about this"

    @pytest.mark.asyncio
    async def test_metadata_capture(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "hi"}}],
            "usage": {},
            "system_fingerprint": "fp_abc123",
            "model": "resolved-model-name",
        }

        with patch("promptpressure.adapters.litellm_adapter.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            config = {"litellm_endpoint": "https://api.x.ai/v1/chat/completions"}
            with patch.dict("os.environ", {"XAI_API_KEY": "test"}, clear=False):
                await generate_response("hi", "grok-fast", config)

            meta = get_last_metadata()
            assert meta["system_fingerprint"] == "fp_abc123"
            assert meta["resolved_model"] == "resolved-model-name"

    @pytest.mark.asyncio
    async def test_multi_turn_passes_messages(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "response"}}],
            "usage": {},
        }

        with patch("promptpressure.adapters.litellm_adapter.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            messages = [
                {"role": "user", "content": "turn 1"},
                {"role": "assistant", "content": "reply 1"},
                {"role": "user", "content": "turn 2"},
            ]
            config = {"litellm_endpoint": "https://api.x.ai/v1/chat/completions"}
            with patch.dict("os.environ", {"XAI_API_KEY": "test"}, clear=False):
                await generate_response("ignored", "grok-fast", config, messages=messages)

            # verify messages were passed in the request body
            call_args = mock_client.post.call_args
            body = call_args.kwargs.get("json", call_args[1].get("json", {}))
            assert body["messages"] == messages


# ---------------------------------------------------------------------------
# generate_response — Anthropic native path (mocked)
# ---------------------------------------------------------------------------

class TestGenerateResponseAnthropic:
    @pytest.mark.asyncio
    async def test_anthropic_endpoint_uses_native_api(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "Hello from Claude"}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "model": "claude-haiku-4-5-20251001",
            "stop_reason": "end_turn",
        }

        with patch("promptpressure.adapters.litellm_adapter.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            config = {"litellm_endpoint": "https://api.anthropic.com/v1/messages"}
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=False):
                result = await generate_response("Say hello", "claude-haiku-4-5-20251001", config)

            assert result == "Hello from Claude"
            usage = get_last_usage()
            assert usage["prompt_tokens"] == 10
            assert usage["completion_tokens"] == 5
            meta = get_last_metadata()
            assert meta["api_format"] == "anthropic_messages"

    @pytest.mark.asyncio
    async def test_anthropic_uses_x_api_key_header(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "hi"}],
            "usage": {"input_tokens": 5, "output_tokens": 2},
            "model": "test",
            "stop_reason": "end_turn",
        }

        with patch("promptpressure.adapters.litellm_adapter.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            config = {"litellm_endpoint": "https://api.anthropic.com/v1/messages"}
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-secret"}, clear=False):
                await generate_response("hi", "claude-test", config)

            call_args = mock_client.post.call_args
            headers = call_args.kwargs.get("headers", call_args[1].get("headers", {}))
            assert headers.get("x-api-key") == "sk-ant-secret"
            assert "Authorization" not in headers


# ---------------------------------------------------------------------------
# generate_response — Responses API path for multi-agent (mocked)
# ---------------------------------------------------------------------------

class TestGenerateResponseMultiAgent:
    @pytest.mark.asyncio
    async def test_multi_agent_uses_responses_api(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "Agent response"}],
                    "status": "completed",
                }
            ],
            "reasoning": {"summary": None},
            "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
            "model": "grok-4.20-multi-agent-0309",
            "status": "completed",
            "service_tier": "default",
            "metadata": {},
        }

        with patch("promptpressure.adapters.litellm_adapter.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            config = {"litellm_endpoint": "https://api.x.ai/v1/chat/completions"}
            with patch.dict("os.environ", {"XAI_API_KEY": "test"}, clear=False):
                result = await generate_response("test", "grok-4.20-multi-agent-0309", config)

            assert result == "Agent response"
            meta = get_last_metadata()
            assert meta["api_format"] == "responses"

            # verify the endpoint was rewritten to /v1/responses
            call_args = mock_client.post.call_args
            url = call_args[0][0] if call_args[0] else call_args.kwargs.get("url", "")
            assert "/v1/responses" in str(url)
