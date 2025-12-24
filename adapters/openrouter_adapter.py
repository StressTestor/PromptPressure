"""
PromptPressure OpenRouter Adapter v1.7 (Async)

Handles API calls to OpenRouter for LLM completion.
"""

import os
import httpx
import asyncio
from rate_limit import AsyncRateLimiter


async def generate_response(prompt, model_name="openai/gpt-oss-20b:free", config=None):
    """
    Generate a response from OpenRouter API asynchronously.
    Args:
        prompt (str): User prompt.
        model_name (str): OpenRouter model name.
        config (dict): Optional configuration.
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
        "messages": [{"role": "user", "content": prompt}],
        "temperature": config.get("temperature", 0.7) if config else 0.7
    }
    endpoint = config.get("openrouter_endpoint", "https://openrouter.ai/api/v1/chat/completions") if config else "https://openrouter.ai/api/v1/chat/completions"
    
    # Rate limiting
    await AsyncRateLimiter.wait("openrouter", rate=5.0, burst=10.0)
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(endpoint, headers=headers, json=data)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
