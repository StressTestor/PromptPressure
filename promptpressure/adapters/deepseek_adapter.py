"""
PromptPressure native DeepSeek adapter.

Talks directly to DeepSeek's own OpenAI-compatible API at api.deepseek.com,
NOT through OpenRouter (that's deepseek_r1_adapter). Key comes from
DEEPSEEK_API_KEY. Models are DeepSeek's native ids (e.g. deepseek-chat,
deepseek-reasoner, deepseek-v4-flash).
"""

import os

import httpx

from promptpressure.rate_limit import AsyncRateLimiter

DEFAULT_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
DEFAULT_MODEL = "deepseek-chat"


async def generate_response(prompt, model_name=DEFAULT_MODEL, config=None, messages=None):
    """Generate a response from the native DeepSeek API.

    Args:
        prompt (str): User prompt (ignored when ``messages`` is provided).
        model_name (str): DeepSeek native model id.
        config (dict): Optional configuration.
        messages (list): Optional pre-built message history (multi-turn).

    Returns:
        str: Model-generated response text.
    """
    api_key = os.getenv("DEEPSEEK_API_KEY") or (config.get("deepseek_native_api_key") if config else None) \
        or (config.get("deepseek_api_key") if config else None)
    if not api_key:
        raise ValueError("Missing DEEPSEEK_API_KEY in environment or config.")

    model = model_name or (config.get("model") if config else None) or DEFAULT_MODEL

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = {
        "model": model,
        "messages": messages if messages else [{"role": "user", "content": prompt}],
        "temperature": config.get("temperature", 0.7) if config else 0.7,
        "stream": False,
    }
    endpoint = (config.get("deepseek_endpoint") if config else None) or DEFAULT_ENDPOINT

    await AsyncRateLimiter.wait("deepseek", rate=5.0, burst=10.0)

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(endpoint, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        choices = result.get("choices") or []
        if not choices:
            raise ValueError(f"empty response: no choices returned (model={model})")
        content = choices[0].get("message", {}).get("content")
        return content if content is not None else ""
