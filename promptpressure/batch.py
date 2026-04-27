"""
Batch processing for PromptPressure eval runs.

All batch functions hit provider APIs directly. No litellm proxy dependency.
Same auth pattern as the real-time litellm adapter: env vars per provider.

Batch is the default path for all single-turn eval prompts. Real-time
is the exception, reserved for:
- Multi-turn sequences (each turn depends on previous model response)
- DeepSeek R1 (reasoning token preservation requires real-time)
- Providers without batch API support
- User override via --no-batch

Provider batch support (direct API, no proxy):
- anthropic: api.anthropic.com/v1/messages/batches, 50% off tokens
- xai/grok: api.x.ai/v1/batches (OpenAI-compatible), 50% off tokens
- google/gemini: batchGenerateContent exists but request format undocumented. real-time only.
- openrouter: no batch API, real-time only
- deepseek: no batch API, real-time only
- groq/ollama/lmstudio: no batch API, real-time only
"""

import asyncio
import io
import json
import logging
import os

import httpx


# litellm is optional. only used for cost calculation, not for API calls.
try:
    import litellm
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False


# provider batch support registry.
BATCH_PROVIDERS = {
    "anthropic": {
        "status": "active",
        "discount": 0.5,
        "method": "anthropic_batch_api",
        "note": "50% off via api.anthropic.com/v1/messages/batches (direct)",
    },
    "google": {
        "status": "none",
        "discount": 1.0,
        "method": None,
        "note": "batchGenerateContent exists but undocumented request format. uses parallel real-time.",
    },
    "xai": {
        "status": "active",
        "discount": 0.5,
        "method": "xai_batch_api",
        "note": "50% off via api.x.ai/v1/batches (direct)",
    },
    "openrouter": {
        "status": "none",
        "discount": 1.0,
        "method": None,
        "note": "no native batch API. real-time only.",
    },
    "deepseek": {
        "status": "none",
        "discount": 1.0,
        "method": None,
        "note": "no native batch API. real-time only.",
    },
}

# model name -> provider mapping for batch routing
_MODEL_PROVIDER_MAP = {
    "claude": "anthropic",
    "anthropic": "anthropic",
    "gemini": "google",
    "grok": "xai",
    "xai": "xai",
    "deepseek": "deepseek",
    "gpt": "openrouter",
    "llama": "openrouter",
    "openrouter": "openrouter",
}


class CostTracker:
    """Tracks per-model cost using litellm's pricing data.

    Concurrent eval coroutines call record_from_usage; mutations are
    guarded by a lock since `dict[k]['total'] += x` is read-modify-write
    and not atomic under the GIL for compound expressions.
    """

    def __init__(self):
        self.costs = {}
        self._lock = asyncio.Lock()
        self._litellm_warned = False

    def _warn_litellm_missing_once(self):
        if not self._litellm_warned:
            logging.warning(
                "litellm not installed; cost tracking disabled. "
                "Install with: pip install litellm"
            )
            self._litellm_warned = True

    def _compute_cost(self, model, prompt_tokens, completion_tokens):
        """Return cost in USD or None on failure. Logs failures, doesn't raise."""
        try:
            input_cost, output_cost = litellm.cost_per_token(
                model=model,
                prompt_tokens=int(prompt_tokens or 0),
                completion_tokens=int(completion_tokens or 0),
            )
            return input_cost + output_cost
        except Exception as exc:
            logging.warning("cost calc failed for model=%s: %s", model, exc)
            return None

    async def record(self, model, response):
        """Record cost from a litellm response object or raw usage dict."""
        if not LITELLM_AVAILABLE:
            self._warn_litellm_missing_once()
            return

        usage = None
        if hasattr(response, "usage"):
            usage = response.usage
        elif isinstance(response, dict) and "usage" in response:
            usage = response["usage"]

        if not usage:
            return

        prompt_tokens = getattr(usage, "prompt_tokens", None) or (
            usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0
        )
        completion_tokens = getattr(usage, "completion_tokens", None) or (
            usage.get("completion_tokens", 0) if isinstance(usage, dict) else 0
        )
        await self.record_from_usage(model, prompt_tokens, completion_tokens)

    async def record_from_usage(self, model, prompt_tokens, completion_tokens):
        """Record cost from raw token counts."""
        if not LITELLM_AVAILABLE:
            self._warn_litellm_missing_once()
            return

        cost = self._compute_cost(model, prompt_tokens, completion_tokens)

        async with self._lock:
            entry = self.costs.setdefault(
                model, {"total": 0.0, "requests": 0, "cost_failures": 0}
            )
            entry["requests"] += 1
            if cost is None:
                entry["cost_failures"] += 1
            else:
                entry["total"] += cost

    def summary(self):
        """Return cost summary dict."""
        total = sum(v["total"] for v in self.costs.values())
        return {
            "per_model": {
                k: {
                    "cost_usd": round(v["total"], 6),
                    "requests": v["requests"],
                    "cost_failures": v.get("cost_failures", 0),
                }
                for k, v in self.costs.items()
            },
            "total_cost_usd": round(total, 6),
        }


def get_provider_for_model(model_name):
    """Resolve which provider a model routes through."""
    model_lower = (model_name or "").lower()
    for prefix, provider in _MODEL_PROVIDER_MAP.items():
        if prefix in model_lower:
            return provider
    return None


def get_batch_support(model_name):
    """Get batch support info for a model.

    Returns (status, provider_info) tuple.
    """
    provider = get_provider_for_model(model_name)
    if provider and provider in BATCH_PROVIDERS:
        info = BATCH_PROVIDERS[provider]
        return info["status"], info
    return "unknown", {"status": "unknown", "discount": 1.0, "method": None, "note": "provider not in registry"}


def should_use_realtime(entry, model_name):
    """Determine if an entry must use real-time instead of batch.

    Returns True (force real-time) for:
    - Multi-turn sequences
    - DeepSeek R1 models
    - Providers without active batch support
    """
    prompt = entry.get("prompt") or entry.get("input")
    if not prompt:
        return True
    if isinstance(prompt, list):
        return True

    model_lower = (model_name or "").lower()
    if "deepseek" in model_lower and ("r1" in model_lower or "reasoner" in model_lower):
        return True

    status, _ = get_batch_support(model_name)
    if status != "active":
        return True

    return False


async def run_batch(entries, model_name, config, litellm_endpoint=None):
    """Route a batch of single-turn entries through the appropriate provider batch API.

    All batch calls go direct to the provider. No litellm proxy involved.
    Falls back to real-time (returns empty dict) if batch isn't supported
    or the submission fails.
    """
    provider = get_provider_for_model(model_name)
    status, info = get_batch_support(model_name)

    if status != "active":
        if status == "pending":
            print(f"  batch: {provider} is batch-capable but on hold ({info['note']})")
        return {}

    method = info.get("method")

    if method == "anthropic_batch_api":
        return await _run_anthropic_batch(entries, model_name, config)
    elif method == "xai_batch_api":
        return await _run_xai_batch(entries, model_name, config)
    else:
        print(f"  batch: method '{method}' not implemented for {provider}. falling back to real-time.")
        return {}


# ---------------------------------------------------------------------------
# Anthropic — api.anthropic.com/v1/messages/batches (direct)
# ---------------------------------------------------------------------------

async def _run_anthropic_batch(entries, model_name, config):
    """Submit single-turn entries to Anthropic batch API directly.

    50% discount on input+output tokens.
    Docs: https://docs.anthropic.com/en/docs/build-with-claude/batch-processing
    """
    api_key = os.getenv("ANTHROPIC_API_KEY") or config.get("litellm_api_key", "")
    if not api_key:
        print("  batch: ANTHROPIC_API_KEY not set. falling back to real-time.")
        return {}

    base_url = "https://api.anthropic.com/v1"

    # resolve model ID
    anthropic_model_map = {
        "claude-sonnet-4-6": "claude-4-sonnet-20250514",
        "claude-opus-4-6": "claude-4-opus-20250514",
    }
    anthropic_model = anthropic_model_map.get(model_name, model_name)
    temperature = config.get("temperature", 0.7)

    # build batch requests in Anthropic's format
    requests = []
    for entry in entries:
        prompt_text = entry.get("prompt") or entry.get("input", "")
        requests.append({
            "custom_id": entry.get("id", "unknown"),
            "params": {
                "model": anthropic_model,
                "max_tokens": 4096,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt_text}],
            }
        })

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{base_url}/messages/batches",
                headers=headers,
                json={"requests": requests},
            )
            resp.raise_for_status()
            batch = resp.json()
            batch_id = batch["id"]

        print(f"  anthropic batch submitted: {batch_id} ({len(requests)} requests, 50% off)")
        return await _poll_anthropic_batch(base_url, headers, batch_id, len(requests))

    except Exception as e:
        print(f"  anthropic batch failed: {e}. falling back to real-time.")
        return {}


async def _poll_anthropic_batch(base_url, headers, batch_id, total_requests):
    """Poll Anthropic batch until completion, then fetch results."""
    results = {}
    max_wait = 3600
    poll_interval = 10
    elapsed = 0

    async with httpx.AsyncClient(timeout=60) as client:
        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            status_resp = await client.get(
                f"{base_url}/messages/batches/{batch_id}",
                headers=headers,
            )
            status_resp.raise_for_status()
            status = status_resp.json()

            processing_status = status.get("processing_status", "")
            if processing_status == "ended":
                print(f"  batch {batch_id} completed ({elapsed}s)")
                break

            poll_interval = min(poll_interval * 1.5, 60)
            counts = status.get("request_counts", {})
            succeeded = counts.get("succeeded", 0)
            processing = counts.get("processing", 0)
            print(f"  batch {batch_id}: {succeeded}/{total_requests} done, {processing} processing ({elapsed}s)")
        else:
            print(f"  batch {batch_id} timed out after {max_wait}s")
            return results

        # fetch results
        results_resp = await client.get(
            f"{base_url}/messages/batches/{batch_id}/results",
            headers=headers,
        )
        results_resp.raise_for_status()

    # parse JSONL
    for line in results_resp.text.strip().split("\n"):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            custom_id = item.get("custom_id", "")
            result = item.get("result", {})

            if result.get("type") == "succeeded":
                message = result.get("message", {})
                content_blocks = message.get("content", [])
                text = "".join(
                    block.get("text", "")
                    for block in content_blocks
                    if block.get("type") == "text"
                )
                usage = message.get("usage", {})
                results[custom_id] = {"content": text, "usage": usage}
            else:
                error = result.get("error", {})
                results[custom_id] = {
                    "content": "",
                    "error": error.get("message", "batch request failed"),
                    "usage": {},
                }
        except json.JSONDecodeError:
            continue

    return results


# ---------------------------------------------------------------------------
# xAI/Grok — api.x.ai/v1/batches (OpenAI-compatible, direct)
# ---------------------------------------------------------------------------

async def _run_xai_batch(entries, model_name, config):
    """Submit single-turn entries to xAI batch API directly.

    OpenAI-compatible batch format: upload JSONL, create batch, poll, download.
    50% discount on input+output tokens.
    """
    api_key = os.getenv("XAI_API_KEY") or config.get("litellm_api_key", "")
    if not api_key:
        print("  batch: XAI_API_KEY not set. falling back to real-time.")
        return {}

    base_url = "https://api.x.ai/v1"
    temperature = config.get("temperature", 0.7)

    # resolve model ID
    xai_model_map = {
        "grok-4.20-reasoning": "grok-4.20-0309-reasoning",
        "grok-4.20-multi-agent": "grok-4.20-multi-agent-0309",
        "grok-4.20-fast": "grok-4-1-fast-reasoning",
    }
    xai_model = xai_model_map.get(model_name, model_name)

    # build JSONL
    jsonl_lines = []
    for entry in entries:
        prompt_text = entry.get("prompt") or entry.get("input", "")
        jsonl_lines.append(json.dumps({
            "custom_id": entry.get("id", "unknown"),
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": xai_model,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt_text}],
            }
        }))

    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            # upload batch file
            upload_resp = await client.post(
                f"{base_url}/files",
                headers=headers,
                files={"file": ("batch.jsonl", io.BytesIO("\n".join(jsonl_lines).encode()), "application/jsonl")},
                data={"purpose": "batch"},
            )
            upload_resp.raise_for_status()
            file_id = upload_resp.json().get("id")

            # create batch
            batch_resp = await client.post(
                f"{base_url}/batches",
                headers={**headers, "Content-Type": "application/json"},
                json={
                    "input_file_id": file_id,
                    "endpoint": "/v1/chat/completions",
                    "completion_window": "24h",
                    "name": f"promptpressure-{model_name}",
                },
            )
            batch_resp.raise_for_status()
            batch_id = batch_resp.json().get("id")

        print(f"  xai batch submitted: {batch_id} ({len(entries)} requests, 50% off)")
        return await _poll_openai_compatible_batch(base_url, headers, batch_id, len(entries), "xai")

    except Exception as e:
        print(f"  xai batch failed: {e}. falling back to real-time.")
        return {}


# ---------------------------------------------------------------------------
# Shared: OpenAI-compatible batch polling (used by xAI, future OpenRouter)
# ---------------------------------------------------------------------------

async def _poll_openai_compatible_batch(base_url, headers, batch_id, total_requests, provider_name):
    """Poll an OpenAI-compatible batch endpoint until completion."""
    results = {}
    max_wait = 3600
    poll_interval = 10
    elapsed = 0

    async with httpx.AsyncClient(timeout=60) as client:
        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            status_resp = await client.get(
                f"{base_url}/batches/{batch_id}",
                headers=headers,
            )
            status_resp.raise_for_status()
            status = status_resp.json()

            batch_status = status.get("status", "")
            if batch_status == "completed":
                print(f"  batch {batch_id} completed ({elapsed}s)")
                output_file_id = status.get("output_file_id")
                if output_file_id:
                    content_resp = await client.get(
                        f"{base_url}/files/{output_file_id}/content",
                        headers=headers,
                    )
                    content_resp.raise_for_status()

                    for line in content_resp.text.strip().split("\n"):
                        if not line.strip():
                            continue
                        try:
                            item = json.loads(line)
                            custom_id = item.get("custom_id", "")
                            response = item.get("response", {})
                            body = response.get("body", {})
                            choices = body.get("choices", [])
                            if choices:
                                text = choices[0].get("message", {}).get("content", "")
                                usage = body.get("usage", {})
                                results[custom_id] = {"content": text, "usage": usage}
                            else:
                                results[custom_id] = {"content": "", "error": "no choices", "usage": {}}
                        except json.JSONDecodeError:
                            continue
                break
            elif batch_status in ("failed", "cancelled", "expired"):
                print(f"  batch {batch_id} {batch_status} ({elapsed}s)")
                break

            poll_interval = min(poll_interval * 1.5, 60)
            completed = status.get("request_counts", {}).get("completed", 0)
            total = status.get("request_counts", {}).get("total", total_requests)
            print(f"  batch {batch_id}: {completed}/{total} done ({elapsed}s)")
        else:
            print(f"  batch {batch_id} timed out after {max_wait}s")

    return results


# ---------------------------------------------------------------------------
# Multi-model parallel (litellm SDK, no proxy)
# ---------------------------------------------------------------------------

async def run_multi_model_parallel(prompt_text, models, config):
    """Fire the same prompt at multiple models in parallel via litellm SDK.

    Uses litellm.batch_completion_models (Python SDK, not the proxy server).
    """
    if not LITELLM_AVAILABLE:
        raise RuntimeError("litellm not installed. run: pip install 'litellm[proxy]'")

    messages = [{"role": "user", "content": prompt_text}]
    temperature = config.get("temperature", 0.7)

    results = {}
    responses = litellm.batch_completion_models(
        models=models,
        messages=messages,
        temperature=temperature,
    )

    for i, resp in enumerate(responses):
        model = models[i] if i < len(models) else f"model_{i}"
        if hasattr(resp, "choices") and resp.choices:
            content = resp.choices[0].message.content or ""
            usage = {}
            if hasattr(resp, "usage") and resp.usage:
                usage = {
                    "prompt_tokens": resp.usage.prompt_tokens,
                    "completion_tokens": resp.usage.completion_tokens,
                }
            results[model] = {"content": content, "usage": usage}
        elif isinstance(resp, Exception):
            results[model] = {"content": "", "error": str(resp), "usage": {}}
        else:
            results[model] = {"content": str(resp), "usage": {}}

    return results
