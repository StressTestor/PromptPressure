"""
Batch processing for PromptPressure eval runs.

Two batch strategies:
1. Anthropic batch API (via litellm passthrough): 50% off input/output tokens.
   Async job submission, poll for results. Single-turn only.
2. Multi-model parallel (via litellm batch_completion_models): same prompt
   fired at all configured models simultaneously. Cuts wall time for
   cross-model comparison runs.

Multi-turn sequences always fall back to real-time because each turn
depends on the previous model response.

DeepSeek R1 falls back to real-time to preserve reasoning token capture.
The batch API response format doesn't reliably surface thinking fields.
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
            # litellm responses have _hidden_params with cost info
            # or we can compute from usage tokens
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
            # cost tracking is best-effort. don't break the eval.
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


def should_use_batch(entry, model_name):
    """Determine if an entry should use batch mode or fall back to real-time.

    Returns False (real-time) for:
    - Multi-turn sequences (each turn depends on previous response)
    - DeepSeek R1 models (reasoning tokens don't survive batch)
    """
    # multi-turn: must be real-time
    prompt = entry.get("prompt") or entry.get("input")
    if isinstance(prompt, list):
        return False

    # deepseek r1: reasoning tokens need real-time
    model_lower = (model_name or "").lower()
    if "deepseek" in model_lower and ("r1" in model_lower or "reasoner" in model_lower):
        return False

    return True


def is_anthropic_model(model_name):
    """Check if a model routes through Anthropic (eligible for batch API discount)."""
    model_lower = (model_name or "").lower()
    return any(x in model_lower for x in ("claude", "anthropic"))


async def run_anthropic_batch(entries, model_name, config, litellm_endpoint=None):
    """Submit single-turn entries to Anthropic batch API via litellm passthrough.

    The litellm proxy exposes /anthropic/v1/messages/batches which passes
    through to Anthropic's batch API. 50% discount on input+output tokens.

    Args:
        entries: list of dataset entries (single-turn only)
        model_name: model name as configured in litellm
        config: eval config dict
        litellm_endpoint: base URL for litellm proxy (default localhost:4000)

    Returns:
        dict mapping entry_id -> {"content": str, "usage": dict}
    """
    base_url = litellm_endpoint or config.get("litellm_endpoint", "http://localhost:4000")
    # strip /v1/chat/completions if present, we need the base
    base_url = base_url.split("/v1/")[0] if "/v1/" in base_url else base_url

    # map litellm model names to anthropic model IDs for the passthrough
    # litellm_config.yaml maps e.g. "claude-sonnet-4-6" -> "anthropic/claude-sonnet-4-6-20250514"
    # the batch API needs the raw anthropic model ID
    anthropic_model_map = {
        "claude-sonnet-4-6": "claude-sonnet-4-6-20250514",
        "claude-opus-4-6": "claude-opus-4-6-20250514",
    }
    anthropic_model = anthropic_model_map.get(model_name, model_name)

    temperature = config.get("temperature", 0.7)
    api_key = os.getenv("ANTHROPIC_API_KEY") or config.get("litellm_api_key", "")

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

    # submit batch via litellm's anthropic passthrough
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        # create batch
        resp = await client.post(
            f"{base_url}/anthropic/v1/messages/batches",
            headers=headers,
            json={"requests": requests},
        )
        resp.raise_for_status()
        batch = resp.json()
        batch_id = batch["id"]

    print(f"  anthropic batch submitted: {batch_id} ({len(requests)} requests)")

    # poll for completion. anthropic batch can take up to 24h but
    # typical small batches complete in minutes.
    results = {}
    max_wait = 3600  # 1 hour max
    poll_interval = 10  # start at 10s
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

            # back off polling interval
            poll_interval = min(poll_interval * 1.5, 60)

            counts = status.get("request_counts", {})
            processing = counts.get("processing", 0)
            succeeded = counts.get("succeeded", 0)
            print(f"  batch {batch_id}: {succeeded}/{len(requests)} done, {processing} processing ({elapsed}s)")
        else:
            print(f"  batch {batch_id} timed out after {max_wait}s")
            return results

        # fetch results
        results_resp = await client.get(
            f"{base_url}/anthropic/v1/messages/batches/{batch_id}/results",
            headers=headers,
        )
        results_resp.raise_for_status()

    # parse JSONL results
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

    # configure litellm to use the local proxy
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
