"""
LiteLLM adapter for PromptPressure.

Routes requests through either a local litellm proxy (localhost:4000) or
directly to provider APIs via OpenAI-compatible endpoints. The adapter
auto-detects the API key from provider-specific env vars when the
endpoint points at a known provider (xAI, OpenAI, etc).

Reasoning token capture: when the model returns reasoning/thinking
content (deepseek-r1, grok reasoning, claude extended thinking), the
adapter extracts it and stores it in _last_reasoning for the eval runner.

Multi-agent metadata: when the grok multi-agent model returns metadata
about which sub-agent handled the response, it's stored in _last_metadata.
"""

import os
import re
import httpx
from promptpressure.rate_limit import AsyncRateLimiter


# module-level storage for per-call data.
# the eval runner reads these after each generate_response() call.
_last_reasoning = ""
_last_usage = {}
_last_metadata = {}  # multi-agent sub-agent info, system_fingerprint, etc.


def get_last_reasoning() -> str:
    """Return reasoning tokens from the most recent generate_response call."""
    return _last_reasoning


def get_last_usage() -> dict:
    """Return token usage from the most recent generate_response call."""
    return _last_usage


def get_last_metadata() -> dict:
    """Return extra metadata from the most recent generate_response call.

    For grok multi-agent, may include sub-agent routing info.
    """
    return _last_metadata


def _resolve_api_key(endpoint, config):
    """Resolve the API key based on the endpoint URL.

    Checks config first, then provider-specific env vars based on the
    endpoint hostname, then falls back to LITELLM_API_KEY.
    """
    # explicit config key takes priority
    key = config.get("litellm_api_key") if config else None
    if key:
        return key

    endpoint_lower = (endpoint or "").lower()

    # auto-detect provider from endpoint and use the right env var
    if "api.x.ai" in endpoint_lower:
        return os.getenv("XAI_API_KEY", "")
    if "api.anthropic.com" in endpoint_lower:
        return os.getenv("ANTHROPIC_API_KEY", "")
    if "api.deepseek.com" in endpoint_lower:
        return os.getenv("DEEPSEEK_API_KEY", "")
    if "generativelanguage.googleapis.com" in endpoint_lower:
        return os.getenv("GOOGLE_API_KEY", "")
    if "api.openai.com" in endpoint_lower:
        return os.getenv("OPENAI_API_KEY", "")
    if "openrouter.ai" in endpoint_lower:
        return os.getenv("OPENROUTER_API_KEY", "")
    if "api.groq.com" in endpoint_lower:
        return os.getenv("GROQ_API_KEY", "")

    # fallback: generic litellm key (for proxy mode)
    return os.getenv("LITELLM_API_KEY", "")


async def generate_response(prompt, model_name="claude-sonnet-4-6", config=None, messages=None):
    """
    Generate a response via litellm proxy or direct provider API.

    Args:
        prompt: User prompt (ignored if messages provided).
        model_name: Model name / ID for the target API.
        config: Optional configuration dict.
        messages: Optional message history for multi-turn.

    Returns:
        str: Model response text (reasoning stripped if present).
    """
    endpoint = (
        config.get("litellm_endpoint", "http://localhost:4000/v1/chat/completions")
        if config else "http://localhost:4000/v1/chat/completions"
    )

    api_key = _resolve_api_key(endpoint, config)

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

    # rate limit based on endpoint: generous for local proxy, standard for cloud
    if "localhost" in endpoint or "127.0.0.1" in endpoint:
        await AsyncRateLimiter.wait("litellm", rate=50.0, burst=100.0)
    else:
        await AsyncRateLimiter.wait("litellm_cloud", rate=5.0, burst=10.0)

    # detect API format from endpoint
    use_responses_api = "multi-agent" in model_name.lower() or "multi_agent" in model_name.lower()
    use_anthropic_api = "api.anthropic.com" in endpoint

    if use_responses_api:
        return await _call_responses_api(endpoint, headers, model_name, data, timeout_s)

    if use_anthropic_api:
        return await _call_anthropic_api(endpoint, api_key, model_name, data, timeout_s, config)

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
    # grok reasoning: may use "reasoning_content" or inline tags
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

    global _last_reasoning, _last_usage, _last_metadata
    _last_reasoning = reasoning
    _last_usage = result.get("usage", {})

    # capture metadata from response
    metadata = {}
    if result.get("system_fingerprint"):
        metadata["system_fingerprint"] = result["system_fingerprint"]
    if result.get("model") and result["model"] != model_name:
        metadata["resolved_model"] = result["model"]
    for field in ("agent", "agent_name", "agent_info", "routing", "sub_agent"):
        val = choice.get(field) or result.get(field)
        if val:
            metadata[field] = val
    _last_metadata = metadata

    return raw_content


async def _call_anthropic_api(endpoint, api_key, model_name, chat_data, timeout_s, config):
    """Call Anthropic's native Messages API.

    Translates from OpenAI chat format to Anthropic's format and back.
    Handles x-api-key auth, content blocks, and usage metadata.
    """
    # Anthropic uses x-api-key header, not Bearer
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    # translate to Anthropic format
    messages = chat_data.get("messages", [])
    anthropic_data = {
        "model": model_name,
        "max_tokens": 4096,
        "temperature": chat_data.get("temperature", 0.7),
        "messages": messages,
    }

    # ensure endpoint points at /v1/messages
    if not endpoint.endswith("/messages"):
        endpoint = endpoint.rstrip("/")
        if "/v1" in endpoint:
            endpoint = endpoint.split("/v1")[0] + "/v1/messages"
        else:
            endpoint += "/v1/messages"

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        response = await client.post(endpoint, headers=headers, json=anthropic_data)
        response.raise_for_status()
        result = response.json()

    # extract text from Anthropic's content blocks
    content_blocks = result.get("content", [])
    raw_content = ""
    reasoning = ""
    for block in content_blocks:
        if block.get("type") == "text":
            raw_content += block.get("text", "")
        elif block.get("type") == "thinking":
            reasoning += block.get("thinking", "")

    global _last_reasoning, _last_usage, _last_metadata
    _last_reasoning = reasoning

    # normalize usage to OpenAI format
    usage = result.get("usage", {})
    _last_usage = {
        "prompt_tokens": usage.get("input_tokens", 0),
        "completion_tokens": usage.get("output_tokens", 0),
        "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
    }

    _last_metadata = {
        "api_format": "anthropic_messages",
        "model": result.get("model", model_name),
        "stop_reason": result.get("stop_reason", ""),
    }

    return raw_content


async def _call_responses_api(endpoint, headers, model_name, chat_data, timeout_s):
    """Call the OpenAI Responses API format (used by grok multi-agent).

    The Responses API uses /v1/responses with a different request/response shape
    than /v1/chat/completions. This translates between the two formats.
    """
    # swap endpoint: /v1/chat/completions -> /v1/responses
    responses_endpoint = endpoint.replace("/v1/chat/completions", "/v1/responses")
    if responses_endpoint == endpoint:
        # endpoint didn't have the expected path, construct it
        base = endpoint.split("/v1/")[0] if "/v1/" in endpoint else endpoint.rstrip("/")
        responses_endpoint = f"{base}/v1/responses"

    # translate chat format -> responses format
    messages = chat_data.get("messages", [])
    # extract the last user message as input
    user_messages = [m for m in messages if m.get("role") == "user"]
    input_text = user_messages[-1]["content"] if user_messages else ""

    # build previous turns as instructions context if multi-turn
    instructions = None
    if len(messages) > 1:
        context_parts = []
        for m in messages[:-1]:  # all except last
            role = m.get("role", "user")
            context_parts.append(f"[{role}]: {m.get('content', '')}")
        instructions = "Previous conversation:\n" + "\n".join(context_parts)

    responses_data = {
        "model": model_name,
        "input": input_text,
        "temperature": chat_data.get("temperature", 0.7),
    }
    if instructions:
        responses_data["instructions"] = instructions

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        response = await client.post(responses_endpoint, headers=headers, json=responses_data)
        response.raise_for_status()
        result = response.json()

    # extract text from responses format
    raw_content = ""
    output_list = result.get("output", [])
    for output_item in output_list:
        if output_item.get("type") == "message":
            for content_block in output_item.get("content", []):
                if content_block.get("type") == "output_text":
                    raw_content += content_block.get("text", "")

    # reasoning from responses format
    reasoning_data = result.get("reasoning", {})
    reasoning = reasoning_data.get("summary") or "" if isinstance(reasoning_data, dict) else ""

    global _last_reasoning, _last_usage, _last_metadata
    _last_reasoning = reasoning

    # normalize usage to chat completions format
    usage = result.get("usage", {})
    _last_usage = {
        "prompt_tokens": usage.get("input_tokens", 0),
        "completion_tokens": usage.get("output_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "cost_in_usd_ticks": usage.get("cost_in_usd_ticks", 0),
    }

    # capture metadata - multi-agent routing info
    metadata = {
        "api_format": "responses",
        "model": result.get("model", model_name),
        "status": result.get("status", ""),
    }
    if result.get("service_tier"):
        metadata["service_tier"] = result["service_tier"]
    if result.get("metadata"):
        metadata["response_metadata"] = result["metadata"]
    # check for any agent routing data in output items
    for output_item in output_list:
        for field in ("agent", "agent_name", "agent_id", "routing"):
            if output_item.get(field):
                metadata[field] = output_item[field]
    _last_metadata = metadata

    return raw_content
