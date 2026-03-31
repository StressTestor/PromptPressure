"""
LiteLLM proxy adapter for PromptPressure.

Routes requests through a local litellm proxy (localhost:4000) that
handles provider routing, key management, and retries. The proxy
exposes an OpenAI-compatible endpoint so this adapter follows the
same pattern as the openrouter adapter.

Reasoning token capture: when the model returns reasoning/thinking
content (deepseek-r1, claude with extended thinking), the adapter
extracts it and stores it in _last_reasoning for the eval runner.
This mirrors the deepseek_r1_adapter pattern.

The litellm proxy must be running before using this adapter.
Start it with: scripts/start-litellm.sh
"""

import os
import re
import httpx
from promptpressure.rate_limit import AsyncRateLimiter


# module-level storage for reasoning tokens and usage from the last call.
# the eval runner reads these after each generate_response() call.
_last_reasoning = ""
_last_usage = {}  # {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}


def get_last_reasoning() -> str:
    """Return reasoning tokens from the most recent generate_response call."""
    return _last_reasoning


def get_last_usage() -> dict:
    """Return token usage from the most recent generate_response call."""
    return _last_usage


async def generate_response(prompt, model_name="claude-sonnet-4-6", config=None, messages=None):
    """
    Generate a response via the local litellm proxy.

    Args:
        prompt: User prompt (ignored if messages provided).
        model_name: Model name as configured in litellm_config.yaml.
        config: Optional configuration dict.
        messages: Optional message history for multi-turn.

    Returns:
        str: Model response text (reasoning stripped if present).
    """
    endpoint = (
        config.get("litellm_endpoint", "http://localhost:4000/v1/chat/completions")
        if config else "http://localhost:4000/v1/chat/completions"
    )

    # litellm proxy with no master_key needs no auth.
    # if a master_key is set, pass it as bearer token.
    api_key = (
        config.get("litellm_api_key")
        if config else None
    ) or os.getenv("LITELLM_API_KEY", "")

    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    data = {
        "model": model_name,
        "messages": messages if messages else [{"role": "user", "content": prompt}],
        "temperature": config.get("temperature", 0.7) if config else 0.7,
    }

    timeout_s = config.get("timeout", 180) if config else 180

    # local proxy, generous rate limit
    await AsyncRateLimiter.wait("litellm", rate=50.0, burst=100.0)

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        response = await client.post(endpoint, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()

    choice = result["choices"][0]["message"]
    raw_content = choice.get("content") or ""

    # reasoning token capture.
    # litellm preserves provider-specific fields in the response.
    # deepseek-r1: "reasoning_content" field on the message
    # anthropic extended thinking: "thinking" field or content blocks
    # fallback: <think>...</think> tags inline
    reasoning = (
        choice.get("reasoning_content")
        or choice.get("reasoning")
        or choice.get("thinking")
        or ""
    )

    if not reasoning:
        think_match = re.search(r"<think>(.*?)</think>", raw_content, re.DOTALL)
        if think_match:
            reasoning = think_match.group(1).strip()
            raw_content = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()

    global _last_reasoning, _last_usage
    _last_reasoning = reasoning

    # capture token usage for cost tracking
    _last_usage = result.get("usage", {})

    return raw_content
