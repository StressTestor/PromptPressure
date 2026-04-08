"""
PromptPressure OpenRouter Adapter v1.8 (Async)

Handles API calls to OpenRouter for LLM completion.
Captures reasoning tokens when models expose them (e.g. GLM-5.1,
DeepSeek R1). Reasoning is stored in _last_reasoning for the
eval runner to pick up after each call.
"""

import os
import re
import httpx
import asyncio
from promptpressure.rate_limit import AsyncRateLimiter


# module-level storage for per-call reasoning and usage data.
# the eval runner reads these after each generate_response() call.
_last_reasoning = ""
_last_usage = {}


def get_last_reasoning() -> str:
    """Return reasoning tokens from the most recent generate_response call."""
    return _last_reasoning


def get_last_usage() -> dict:
    """Return token usage from the most recent generate_response call."""
    return _last_usage


async def generate_response(prompt, model_name="openai/gpt-oss-20b:free", config=None, messages=None):
    """
    Generate a response from OpenRouter API asynchronously.
    Args:
        prompt (str): User prompt.
        model_name (str): OpenRouter model name.
        config (dict): Optional configuration.
        messages (list): Optional pre-built message history (for multi-turn).
    Returns:
        str: Model-generated response.
    """
    api_key = os.getenv("OPENROUTER_API_KEY") or (config.get("openrouter_api_key") if config else None)
    if not api_key:
        raise ValueError("Missing OPENROUTER_API_KEY in environment or config.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/joebeach420/PromptPressure",  # Optional, for OpenRouter stats
        "X-Title": "PromptPressure"  # Optional, for OpenRouter stats
    }
    data = {
        "model": model_name,
        "messages": messages if messages else [{"role": "user", "content": prompt}],
        "temperature": config.get("temperature", 0.7) if config else 0.7
    }
    endpoint = config.get("openrouter_endpoint", "https://openrouter.ai/api/v1/chat/completions") if config else "https://openrouter.ai/api/v1/chat/completions"
    timeout_s = config.get("timeout", 60) if config else 60

    # Rate limiting
    await AsyncRateLimiter.wait("openrouter", rate=5.0, burst=10.0)

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        response = await client.post(endpoint, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        choices = result.get("choices") or []
        if not choices:
            raise ValueError(f"empty response: no choices returned (model={model_name})")

    choice = choices[0].get("message") or {}
    raw_content = choice.get("content") or ""

    # reasoning token capture.
    # OpenRouter surfaces reasoning in the "reasoning" field for models that
    # support it (GLM-5.1, DeepSeek R1, etc). Also check "reasoning_content"
    # and inline <think> tags as fallbacks.
    reasoning = (
        choice.get("reasoning")
        or choice.get("reasoning_content")
        or ""
    )

    if not reasoning:
        think_match = re.search(r"<think>(.*?)</think>", raw_content, re.DOTALL)
        if think_match:
            reasoning = think_match.group(1).strip()
            raw_content = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()

    global _last_reasoning, _last_usage
    _last_reasoning = reasoning
    _last_usage = result.get("usage", {})

    return raw_content
