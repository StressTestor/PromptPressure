"""
Batch processing for PromptPressure eval runs.

Batch is the default path for all single-turn eval prompts. Real-time
is the exception, reserved for:
- Multi-turn sequences (each turn depends on previous model response)
- DeepSeek R1 (reasoning token preservation requires real-time)
- Providers without batch API support
- User override via --no-batch

Provider batch support:
- anthropic: batch API via litellm passthrough, 50% off tokens
- google/gemini: batch prediction API (supported, routed through litellm)
- openrouter: batch-capable but ON HOLD pending red teaming approval
- grok: batch-capable but ON HOLD pending red teaming approval
- deepseek (non-R1): no native batch API, uses parallel real-time
- groq/ollama/lmstudio: no batch API, real-time only

Multi-model parallel via litellm.batch_completion_models fires the same
prompt at all configured models simultaneously for comparison runs.
"""

import os
import json
import time
import asyncio
import httpx

# litellm is optional. batch mode fails gracefully if not installed.
try:
    import litellm
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False


# provider batch support registry.
# status: "active" = wired and working, "pending" = capable but blocked,
# "none" = no batch API available.
# discount: cost multiplier vs real-time (0.5 = 50% off).
BATCH_PROVIDERS = {
    "anthropic": {
        "status": "active",
        "discount": 0.5,
        "method": "anthropic_batch_api",
        "note": "50% off via /anthropic/v1/messages/batches passthrough",
    },
    "google": {
        "status": "active",
        "discount": 0.5,
        "method": "vertex_batch_prediction",
        "note": "50% off via Gemini batch prediction API",
    },
    "openrouter": {
        "status": "pending",
        "discount": 1.0,
        "method": "openai_batch_api",
        "note": "ON HOLD: pending red teaming approval from openrouter safety team",
    },
    "xai": {
        "status": "active",
        "discount": 0.5,
        "method": "xai_batch_api",
        "note": "50% off via xAI async batch API (direct, not through openrouter)",
    },
    "deepseek": {
        "status": "none",
        "discount": 1.0,
        "method": None,
        "note": "no native batch API. uses parallel real-time.",
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
    "openrouter": "openrouter",
}


class CostTracker:
    """Tracks per-model cost using litellm's pricing data."""

    def __init__(self):
        self.costs = {}  # model_name -> {"input_cost": float, "output_cost": float, "total": float, "requests": int}

    def record(self, model, response):
        """Record cost from a litellm response object or raw usage dict."""
        if not LITELLM_AVAILABLE:
            return

        if model not in self.costs:
            self.costs[model] = {"input_cost": 0.0, "output_cost": 0.0, "total": 0.0, "requests": 0}

        try:
            usage = None
            if hasattr(response, "usage"):
                usage = response.usage
            elif isinstance(response, dict) and "usage" in response:
                usage = response["usage"]

            if usage:
                prompt_tokens = getattr(usage, "prompt_tokens", None) or usage.get("prompt_tokens", 0)
                completion_tokens = getattr(usage, "completion_tokens", None) or usage.get("completion_tokens", 0)

                cost = litellm.completion_cost(
                    model=model,
                    prompt=str(prompt_tokens),
                    completion=str(completion_tokens),
                )
                self.costs[model]["total"] += cost
                self.costs[model]["requests"] += 1
        except Exception:
            self.costs[model]["requests"] += 1

    def record_from_usage(self, model, prompt_tokens, completion_tokens):
        """Record cost from raw token counts."""
        if not LITELLM_AVAILABLE:
            return

        if model not in self.costs:
            self.costs[model] = {"input_cost": 0.0, "output_cost": 0.0, "total": 0.0, "requests": 0}

        try:
            cost = litellm.completion_cost(
                model=model,
                prompt=str(prompt_tokens),
                completion=str(completion_tokens),
            )
            self.costs[model]["total"] += cost
            self.costs[model]["requests"] += 1
        except Exception:
            self.costs[model]["requests"] += 1

    def summary(self):
        """Return cost summary dict."""
        total = sum(v["total"] for v in self.costs.values())
        return {
            "per_model": {k: {"cost_usd": round(v["total"], 6), "requests": v["requests"]}
                          for k, v in self.costs.items()},
            "total_cost_usd": round(total, 6),
        }


def get_provider_for_model(model_name):
    """Resolve which provider a model routes through.

    Returns provider key string or None if unknown.
    """
    model_lower = (model_name or "").lower()
    for prefix, provider in _MODEL_PROVIDER_MAP.items():
        if prefix in model_lower:
            return provider
    return None


def get_batch_support(model_name):
    """Get batch support info for a model.

    Returns (status, provider_info) tuple.
    status is one of: "active", "pending", "none", "unknown".
    """
    provider = get_provider_for_model(model_name)
    if provider and provider in BATCH_PROVIDERS:
        info = BATCH_PROVIDERS[provider]
        return info["status"], info
    return "unknown", {"status": "unknown", "discount": 1.0, "method": None, "note": "provider not in registry"}


def should_use_realtime(entry, model_name):
    """Determine if an entry must use real-time instead of batch.

    Real-time is the exception. Returns True (force real-time) for:
    - Multi-turn sequences (each turn depends on previous response)
    - DeepSeek R1 models (reasoning tokens don't survive batch)
    - Providers without active batch support

    Returns False (batch is fine) for everything else.
    """
    # multi-turn: always real-time. turns depend on previous responses.
    prompt = entry.get("prompt") or entry.get("input")
    if isinstance(prompt, list):
        return True

    # deepseek r1: reasoning tokens need real-time
    model_lower = (model_name or "").lower()
    if "deepseek" in model_lower and ("r1" in model_lower or "reasoner" in model_lower):
        return True

    # check provider batch support
    status, _ = get_batch_support(model_name)
    if status != "active":
        return True

    return False


async def run_batch(entries, model_name, config, litellm_endpoint=None):
    """Route a batch of single-turn entries through the appropriate batch API.

    Detects provider from model name and dispatches to the correct
    batch implementation. Falls back to real-time gracefully if the
    provider's batch method isn't implemented yet.

    Args:
        entries: list of dataset entries (single-turn only)
        model_name: model name as configured in litellm_config.yaml
        config: eval config dict
        litellm_endpoint: base URL for litellm proxy

    Returns:
        dict mapping entry_id -> {"content": str, "usage": dict}
    """
    provider = get_provider_for_model(model_name)
    status, info = get_batch_support(model_name)

    if status != "active":
        if status == "pending":
            print(f"  batch: {provider} is batch-capable but on hold ({info['note']})")
        return {}

    method = info.get("method")

    if method == "anthropic_batch_api":
        return await _run_anthropic_batch(entries, model_name, config, litellm_endpoint)
    elif method == "vertex_batch_prediction":
        return await _run_google_batch(entries, model_name, config, litellm_endpoint)
    elif method == "xai_batch_api":
        return await _run_xai_batch(entries, model_name, config, litellm_endpoint)
    elif method == "openai_batch_api":
        # openrouter uses OpenAI-compatible batch. not wired yet (red teaming hold).
        print(f"  batch: {method} not implemented yet for {provider}. falling back to real-time.")
        return {}
    else:
        return {}


async def _run_anthropic_batch(entries, model_name, config, litellm_endpoint=None):
    """Submit single-turn entries to Anthropic batch API via litellm passthrough.

    50% discount on input+output tokens.
    """
    base_url = litellm_endpoint or config.get("litellm_endpoint", "http://localhost:4000")
    base_url = base_url.split("/v1/")[0] if "/v1/" in base_url else base_url

    anthropic_model_map = {
        "claude-sonnet-4-6": "claude-sonnet-4-6-20250514",
        "claude-opus-4-6": "claude-opus-4-6-20250514",
    }
    anthropic_model = anthropic_model_map.get(model_name, model_name)

    temperature = config.get("temperature", 0.7)
    api_key = os.getenv("ANTHROPIC_API_KEY") or config.get("litellm_api_key", "")

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

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{base_url}/anthropic/v1/messages/batches",
            headers=headers,
            json={"requests": requests},
        )
        resp.raise_for_status()
        batch = resp.json()
        batch_id = batch["id"]

    print(f"  anthropic batch submitted: {batch_id} ({len(requests)} requests, 50% off)")

    results = {}
    max_wait = 3600
    poll_interval = 10
    elapsed = 0

    async with httpx.AsyncClient(timeout=60) as client:
        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            status_resp = await client.get(
                f"{base_url}/anthropic/v1/messages/batches/{batch_id}",
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
            processing = counts.get("processing", 0)
            succeeded = counts.get("succeeded", 0)
            print(f"  batch {batch_id}: {succeeded}/{len(requests)} done, {processing} processing ({elapsed}s)")
        else:
            print(f"  batch {batch_id} timed out after {max_wait}s")
            return results

        results_resp = await client.get(
            f"{base_url}/anthropic/v1/messages/batches/{batch_id}/results",
            headers=headers,
        )
        results_resp.raise_for_status()

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
                results[custom_id] = {
                    "content": text,
                    "usage": usage,
                }
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


async def _run_google_batch(entries, model_name, config, litellm_endpoint=None):
    """Submit single-turn entries to Google Gemini batch prediction API.

    Routes through litellm proxy. 50% discount on input+output tokens.
    """
    base_url = litellm_endpoint or config.get("litellm_endpoint", "http://localhost:4000")
    base_url = base_url.split("/v1/")[0] if "/v1/" in base_url else base_url

    api_key = os.getenv("GOOGLE_API_KEY") or config.get("litellm_api_key", "")
    temperature = config.get("temperature", 0.7)

    # google batch prediction uses the same OpenAI-compatible batch format
    # via litellm's batch endpoint
    requests = []
    for entry in entries:
        prompt_text = entry.get("prompt") or entry.get("input", "")
        requests.append({
            "custom_id": entry.get("id", "unknown"),
            "body": {
                "model": model_name,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt_text}],
            }
        })

    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # use litellm's OpenAI-compatible batch endpoint
    # litellm translates this to the provider's native batch format
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            # write requests to a JSONL string for the batch file
            jsonl_content = "\n".join(json.dumps(r) for r in requests)

            # upload the batch file
            import io
            files = {"file": ("batch.jsonl", io.BytesIO(jsonl_content.encode()), "application/jsonl")}
            upload_resp = await client.post(
                f"{base_url}/v1/files",
                headers={"Authorization": headers.get("Authorization", "")},
                files=files,
                data={"purpose": "batch"},
            )
            upload_resp.raise_for_status()
            file_id = upload_resp.json().get("id")

            # create the batch
            batch_resp = await client.post(
                f"{base_url}/v1/batches",
                headers=headers,
                json={
                    "input_file_id": file_id,
                    "endpoint": "/v1/chat/completions",
                    "completion_window": "24h",
                },
            )
            batch_resp.raise_for_status()
            batch = batch_resp.json()
            batch_id = batch.get("id")

        print(f"  google batch submitted: {batch_id} ({len(requests)} requests, 50% off)")

        # poll for completion
        results = {}
        max_wait = 3600
        poll_interval = 10
        elapsed = 0

        async with httpx.AsyncClient(timeout=60) as client:
            while elapsed < max_wait:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

                status_resp = await client.get(
                    f"{base_url}/v1/batches/{batch_id}",
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
                            f"{base_url}/v1/files/{output_file_id}/content",
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
                total = status.get("request_counts", {}).get("total", len(requests))
                print(f"  batch {batch_id}: {completed}/{total} done ({elapsed}s)")
            else:
                print(f"  batch {batch_id} timed out after {max_wait}s")

        return results

    except Exception as e:
        print(f"  google batch failed: {e}. falling back to real-time.")
        return {}


async def _run_xai_batch(entries, model_name, config, litellm_endpoint=None):
    """Submit single-turn entries to xAI's async batch API.

    xAI uses the OpenAI-compatible batch format: upload JSONL, create batch,
    poll, download results. 50% discount on input+output tokens.
    Routes direct to api.x.ai, not through OpenRouter.
    """
    api_key = os.getenv("XAI_API_KEY") or config.get("litellm_api_key", "")
    base_url = "https://api.x.ai/v1"
    temperature = config.get("temperature", 0.7)

    # xAI model name mapping (litellm names -> xAI API model IDs)
    xai_model_map = {
        "grok-4.20-reasoning": "grok-4.20-0309-reasoning",
        "grok-4.20-multi-agent": "grok-4.20-multi-agent-0309",
        "grok-4.20-fast": "grok-4-1-fast-reasoning",
    }
    xai_model = xai_model_map.get(model_name, model_name)

    # build JSONL batch requests in OpenAI format
    jsonl_lines = []
    for entry in entries:
        prompt_text = entry.get("prompt") or entry.get("input", "")
        request = {
            "custom_id": entry.get("id", "unknown"),
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": xai_model,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt_text}],
            }
        }
        jsonl_lines.append(json.dumps(request))

    jsonl_content = "\n".join(jsonl_lines)

    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            # upload batch file
            import io
            files = {"file": ("batch.jsonl", io.BytesIO(jsonl_content.encode()), "application/jsonl")}
            upload_resp = await client.post(
                f"{base_url}/files",
                headers=headers,
                files=files,
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
                },
            )
            batch_resp.raise_for_status()
            batch = batch_resp.json()
            batch_id = batch.get("id")

        print(f"  xai batch submitted: {batch_id} ({len(entries)} requests, 50% off)")

        # poll for completion
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
                total = status.get("request_counts", {}).get("total", len(entries))
                print(f"  batch {batch_id}: {completed}/{total} done ({elapsed}s)")
            else:
                print(f"  batch {batch_id} timed out after {max_wait}s")

        return results

    except Exception as e:
        print(f"  xai batch failed: {e}. falling back to real-time.")
        return {}


async def run_multi_model_parallel(prompt_text, models, config):
    """Fire the same prompt at multiple models in parallel via litellm.

    Uses litellm.batch_completion_models to dispatch simultaneously.
    Returns dict mapping model_name -> response_text.

    Args:
        prompt_text: single prompt string
        models: list of model name strings
        config: eval config dict

    Returns:
        dict: {model_name: {"content": str, "usage": dict, "cost": float}}
    """
    if not LITELLM_AVAILABLE:
        raise RuntimeError("litellm not installed. run: pip install 'litellm[proxy]'")

    endpoint = config.get("litellm_endpoint", "http://localhost:4000")
    base_url = endpoint.split("/v1/")[0] if "/v1/" in endpoint else endpoint
    api_key = config.get("litellm_api_key") or os.getenv("LITELLM_API_KEY", "")

    messages = [{"role": "user", "content": prompt_text}]
    temperature = config.get("temperature", 0.7)

    results = {}
    responses = litellm.batch_completion_models(
        models=models,
        messages=messages,
        temperature=temperature,
        api_base=base_url,
        api_key=api_key if api_key else None,
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
