"""
DeepSeek R1 adapter for PromptPressure.

Routes through OpenRouter's OpenAI-compatible endpoint. Captures
reasoning tokens (chain-of-thought) separately from the final
response. The thinking is where alignment leakage shows up even
when the final output refuses properly.

No prompt logging headers sent (no X-Title, no HTTP-Referer).
"""

import os
import re
import httpx
import asyncio
from promptpressure.rate_limit import AsyncRateLimiter


async def generate_response(prompt, model_name="deepseek/deepseek-r1", config=None, messages=None):
    """
    Generate a response from DeepSeek R1 via OpenRouter.

    Returns the final response text. Reasoning tokens are attached
    to the response metadata via a side channel (stored in
    _last_reasoning module-level variable for the eval runner to pick up).

    Args:
        prompt: User prompt.
        model_name: OpenRouter model ID.
        config: Optional configuration dict.
        messages: Optional message history for multi-turn.

    Returns:
        str: Final response text (reasoning stripped).
    """
    api_key = os.getenv("OPENROUTER_API_KEY") or (config.get("openrouter_api_key") if config else None)
    if not api_key:
        raise ValueError("Missing OPENROUTER_API_KEY in environment or config.")

    # no tracking headers. no X-Title, no HTTP-Referer
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    data = {
        "model": model_name,
        "messages": messages if messages else [{"role": "user", "content": prompt}],
        "temperature": config.get("temperature", 0.7) if config else 0.7,
    }

    endpoint = config.get("openrouter_endpoint", "https://openrouter.ai/api/v1/chat/completions") if config else "https://openrouter.ai/api/v1/chat/completions"
    timeout_s = config.get("timeout", 180) if config else 180

    await AsyncRateLimiter.wait("openrouter", rate=5.0, burst=10.0)

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        response = await client.post(endpoint, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()

    choice = result["choices"][0]["message"]
    raw_content = choice.get("content") or ""

    # Extract reasoning tokens. R1 returns them either in:
    # 1. A separate "reasoning" or "reasoning_content" field
    # 2. Inline <think>...</think> tags in the content
    reasoning = choice.get("reasoning") or choice.get("reasoning_content") or ""

    if not reasoning:
        # Try extracting from <think> tags
        think_match = re.search(r"<think>(.*?)</think>", raw_content, re.DOTALL)
        if think_match:
            reasoning = think_match.group(1).strip()
            # Strip the think block from the final response
            final_content = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()
        else:
            final_content = raw_content
    else:
        final_content = raw_content

    # Store reasoning for the eval runner to pick up
    global _last_reasoning
    _last_reasoning = reasoning

    return final_content


# Module-level storage for reasoning tokens from the last call.
# The eval runner reads this after each generate_response() call.
_last_reasoning = ""


def get_last_reasoning() -> str:
    """Return reasoning tokens from the most recent generate_response call."""
    return _last_reasoning
