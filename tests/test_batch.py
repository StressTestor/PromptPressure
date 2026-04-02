"""Tests for promptpressure.batch module.

All tests use mocked responses. No live API calls.
"""
import json
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

from promptpressure.batch import (
    CostTracker,
    get_provider_for_model,
    get_batch_support,
    should_use_realtime,
    run_batch,
    BATCH_PROVIDERS,
    _MODEL_PROVIDER_MAP,
)


# ---------------------------------------------------------------------------
# get_provider_for_model
# ---------------------------------------------------------------------------

class TestGetProviderForModel:
    def test_claude_maps_to_anthropic(self):
        assert get_provider_for_model("claude-sonnet-4-6") == "anthropic"
        assert get_provider_for_model("claude-haiku-4-5") == "anthropic"

    def test_gemini_maps_to_google(self):
        assert get_provider_for_model("gemini-3-flash-preview") == "google"
        assert get_provider_for_model("gemini-2.5-pro") == "google"

    def test_grok_maps_to_xai(self):
        assert get_provider_for_model("grok-4.20-reasoning") == "xai"
        assert get_provider_for_model("grok-4-1-fast-reasoning") == "xai"

    def test_deepseek_maps_to_deepseek(self):
        assert get_provider_for_model("deepseek-r1") == "deepseek"
        assert get_provider_for_model("deepseek-chat") == "deepseek"

    def test_gpt_maps_to_openrouter(self):
        assert get_provider_for_model("gpt-4o") == "openrouter"
        assert get_provider_for_model("gpt-4o-mini") == "openrouter"

    def test_llama_maps_to_openrouter(self):
        assert get_provider_for_model("llama-3.3-70b") == "openrouter"

    def test_unknown_returns_none(self):
        assert get_provider_for_model("some-random-model") is None
        assert get_provider_for_model("") is None
        assert get_provider_for_model(None) is None


# ---------------------------------------------------------------------------
# get_batch_support
# ---------------------------------------------------------------------------

class TestGetBatchSupport:
    def test_anthropic_is_active(self):
        status, info = get_batch_support("claude-sonnet-4-6")
        assert status == "active"
        assert info["discount"] == 0.5

    def test_xai_is_active(self):
        status, info = get_batch_support("grok-4.20-reasoning")
        assert status == "active"
        assert info["method"] == "xai_batch_api"

    def test_google_is_none(self):
        status, info = get_batch_support("gemini-3-flash-preview")
        assert status == "none"

    def test_openrouter_is_none(self):
        status, info = get_batch_support("gpt-4o")
        assert status == "none"

    def test_deepseek_is_none(self):
        status, info = get_batch_support("deepseek-chat")
        assert status == "none"

    def test_unknown_model(self):
        status, info = get_batch_support("totally-unknown")
        assert status == "unknown"


# ---------------------------------------------------------------------------
# should_use_realtime
# ---------------------------------------------------------------------------

class TestShouldUseRealtime:
    def test_single_turn_anthropic_uses_batch(self):
        entry = {"id": "t1", "prompt": "hello"}
        assert should_use_realtime(entry, "claude-sonnet-4-6") is False

    def test_single_turn_xai_uses_batch(self):
        entry = {"id": "t1", "prompt": "hello"}
        assert should_use_realtime(entry, "grok-4.20-reasoning") is False

    def test_multi_turn_always_realtime(self):
        entry = {"id": "t1", "prompt": [{"role": "user", "content": "hi"}]}
        assert should_use_realtime(entry, "claude-sonnet-4-6") is True

    def test_deepseek_r1_always_realtime(self):
        entry = {"id": "t1", "prompt": "hello"}
        assert should_use_realtime(entry, "deepseek-r1") is True
        assert should_use_realtime(entry, "deepseek-reasoner") is True

    def test_deepseek_chat_realtime_no_batch(self):
        entry = {"id": "t1", "prompt": "hello"}
        assert should_use_realtime(entry, "deepseek-chat") is True

    def test_google_realtime_no_batch(self):
        entry = {"id": "t1", "prompt": "hello"}
        assert should_use_realtime(entry, "gemini-3-flash") is True

    def test_openrouter_realtime_no_batch(self):
        entry = {"id": "t1", "prompt": "hello"}
        assert should_use_realtime(entry, "gpt-4o") is True

    def test_unknown_model_realtime(self):
        entry = {"id": "t1", "prompt": "hello"}
        assert should_use_realtime(entry, "totally-unknown-model") is True

    def test_empty_prompt_entry(self):
        entry = {"id": "t1"}
        # no prompt field, should still not crash
        assert should_use_realtime(entry, "claude-sonnet-4-6") is True


# ---------------------------------------------------------------------------
# CostTracker
# ---------------------------------------------------------------------------

class TestCostTracker:
    def test_empty_summary(self):
        ct = CostTracker()
        s = ct.summary()
        assert s["total_cost_usd"] == 0
        assert s["per_model"] == {}

    def test_record_from_usage(self):
        ct = CostTracker()
        ct.record_from_usage("test-model", 100, 50)
        s = ct.summary()
        assert s["per_model"]["test-model"]["requests"] == 1

    def test_multiple_records_accumulate(self):
        ct = CostTracker()
        ct.record_from_usage("model-a", 100, 50)
        ct.record_from_usage("model-a", 200, 100)
        ct.record_from_usage("model-b", 50, 25)
        s = ct.summary()
        assert s["per_model"]["model-a"]["requests"] == 2
        assert s["per_model"]["model-b"]["requests"] == 1

    def test_record_from_response_dict(self):
        ct = CostTracker()
        resp = {"usage": {"prompt_tokens": 100, "completion_tokens": 50}}
        ct.record("test-model", resp)
        s = ct.summary()
        assert s["per_model"]["test-model"]["requests"] == 1


# ---------------------------------------------------------------------------
# run_batch dispatch
# ---------------------------------------------------------------------------

class TestRunBatch:
    @pytest.mark.asyncio
    async def test_unsupported_provider_returns_empty(self):
        entries = [{"id": "t1", "prompt": "hello"}]
        result = await run_batch(entries, "gpt-4o", {})
        assert result == {}

    @pytest.mark.asyncio
    async def test_unknown_model_returns_empty(self):
        entries = [{"id": "t1", "prompt": "hello"}]
        result = await run_batch(entries, "totally-unknown", {})
        assert result == {}

    @pytest.mark.asyncio
    async def test_anthropic_dispatch(self):
        entries = [{"id": "t1", "prompt": "hello"}]
        with patch("promptpressure.batch._run_anthropic_batch", new_callable=AsyncMock) as mock:
            mock.return_value = {"t1": {"content": "hi", "usage": {}}}
            result = await run_batch(entries, "claude-sonnet-4-6", {})
            mock.assert_called_once()
            assert "t1" in result

    @pytest.mark.asyncio
    async def test_xai_dispatch(self):
        entries = [{"id": "t1", "prompt": "hello"}]
        with patch("promptpressure.batch._run_xai_batch", new_callable=AsyncMock) as mock:
            mock.return_value = {"t1": {"content": "hi", "usage": {}}}
            result = await run_batch(entries, "grok-4.20-reasoning", {})
            mock.assert_called_once()
            assert "t1" in result


# ---------------------------------------------------------------------------
# Provider registry integrity
# ---------------------------------------------------------------------------

class TestProviderRegistry:
    def test_all_providers_have_required_fields(self):
        for provider, info in BATCH_PROVIDERS.items():
            assert "status" in info, f"{provider} missing status"
            assert "discount" in info, f"{provider} missing discount"
            assert "method" in info, f"{provider} missing method"
            assert "note" in info, f"{provider} missing note"
            assert info["status"] in ("active", "pending", "none"), f"{provider} invalid status: {info['status']}"

    def test_active_providers_have_methods(self):
        for provider, info in BATCH_PROVIDERS.items():
            if info["status"] == "active":
                assert info["method"] is not None, f"{provider} is active but has no method"

    def test_model_map_references_valid_providers(self):
        for prefix, provider in _MODEL_PROVIDER_MAP.items():
            assert provider in BATCH_PROVIDERS or provider == "openrouter", \
                f"model prefix '{prefix}' maps to unknown provider '{provider}'"
