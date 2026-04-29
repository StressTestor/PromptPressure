"""Re-judge the 2026-04-28 PromptPressure 3-way eval with Sonnet 4.6.

Reuses promptpressure.grading._build_grading_prompt() unchanged.
Same parser logic (find first { / last } / json.loads) — copied verbatim.
Same Semaphore(5) concurrency. Same per-item rubric extraction.
Adds: raw-response logging on parse failure, refusal-pattern classification.

Output paths (parallel to existing openrouter_scores_*):
  v4-pro/analysis/sonnet46_scores_v4_pro_2026-04-28.{csv,json}
  v4-flash/analysis/sonnet46_scores_v4_flash_2026-04-28.{csv,json}
  laguna-m1/analysis/sonnet46_scores_laguna_2026-04-28.{csv,json}

Null-response log (per model dir):
  <model_dir>/analysis/sonnet46_null_responses.jsonl

Usage:
  python scripts/rejudge_sonnet46.py --pilot   # 50-item stratified pilot
  python scripts/rejudge_sonnet46.py           # full 593-item run
"""

import argparse
import asyncio
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

REPO = Path("/Volumes/T7/PromptPressure")
sys.path.insert(0, str(REPO))

from promptpressure.grading import _build_grading_prompt  # noqa: E402

BASE = REPO / "outputs/2026-04-28_3way-deepseek-laguna"

MODELS = [
    {
        "key": "v4_pro",
        "dir": BASE / "v4-pro",
        "eval_file": "eval_openrouter_deepseek_v4_pro.json",
        "out_stem": "sonnet46_scores_v4_pro_2026-04-28",
    },
    {
        "key": "v4_flash",
        "dir": BASE / "v4-flash",
        "eval_file": "eval_openrouter_deepseek_v4_flash.json",
        "out_stem": "sonnet46_scores_v4_flash_2026-04-28",
    },
    {
        "key": "laguna",
        "dir": BASE / "laguna-m1",
        "eval_file": "eval_openrouter_poolside_laguna_m1.json",
        "out_stem": "sonnet46_scores_laguna_2026-04-28",
    },
]

JUDGE_MODEL = "claude-sonnet-4-6"
ENDPOINT = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
TEMPERATURE = 0.7  # matches openrouter_adapter default — preserves no-override contract
MAX_TOKENS = 4096  # matches litellm_adapter._call_anthropic_api hardcoded value
HTTP_TIMEOUT = 240.0
MAX_CONCURRENCY = 5

# Transport-layer rate limiting (does NOT alter judge contract — only paces network arrivals).
# Account is on 30K ITPM tier; we cap our estimate at 27K to leave 10% headroom for clock skew
# and Anthropic's tokenizer counting more than our 3.5 chars/token approximation.
INPUT_TPM_LIMIT = 27_000
CHARS_PER_TOKEN_APPROX = 3.5  # conservative for English; Anthropic tokenizer ≈ 3.7-4.0
RETRY_429_MAX = 3
RETRY_429_BASE_WAIT = 10.0  # seconds; doubled per attempt unless retry-after honored


class TokenBucket:
    """Async token bucket for pre-call input-token-per-minute throttling.

    Refills continuously at capacity/60 tokens per second. Coroutines waiting
    on acquire() block until enough capacity refills. Pure pre-call gate —
    never modifies the judge prompt or response.
    """

    def __init__(self, capacity_per_minute: int):
        self.capacity = capacity_per_minute
        self.tokens = float(capacity_per_minute)
        self.last_refill = time.monotonic()
        self.lock = asyncio.Lock()

    async def acquire(self, cost: int):
        cost = min(cost, self.capacity)  # never wait forever for an oversized request
        while True:
            async with self.lock:
                now = time.monotonic()
                elapsed = now - self.last_refill
                self.tokens = min(
                    float(self.capacity),
                    self.tokens + elapsed * (self.capacity / 60.0),
                )
                self.last_refill = now
                if self.tokens >= cost:
                    self.tokens -= cost
                    return
                deficit = cost - self.tokens
                wait_s = deficit / (self.capacity / 60.0)
            await asyncio.sleep(wait_s + 0.05)

REFUSAL_RE = re.compile(
    r"(i can'?t|i'?m not able|i decline|uncomfortable evaluating|i won'?t|i'?m unable|cannot evaluate|won'?t evaluate|i refuse)",
    re.IGNORECASE,
)


def parse_scores(raw: str, fields_to_grade: list):
    """Mirrors grading.py:79-83 verbatim, then classifies the failure mode.

    Returns (parsed_dict, fail_mode) where fail_mode in:
      'ok'       — clean parse
      'no_braces'— no { or } found in response
      'json_err' — found braces but json.loads failed
      'refusal'  — overrides above when REFUSAL_RE matches the raw text
    """
    refusal = bool(REFUSAL_RE.search(raw or ""))
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end >= 0:
        try:
            parsed = json.loads(raw[start:end + 1])
            return parsed, "ok"
        except Exception:
            return (
                {k: None for k in fields_to_grade},
                "refusal" if refusal else "json_err",
            )
    return (
        {k: None for k in fields_to_grade},
        "refusal" if refusal else "no_braces",
    )


async def call_sonnet(
    client: httpx.AsyncClient,
    api_key: str,
    prompt: str,
    bucket: TokenBucket,
):
    """Single Sonnet judge call with pre-call token-bucket gate + 429-only retry.

    Retry policy: retries are STRICTLY for HTTP 429 (rate limit). Honors
    retry-after header when present, otherwise exponential backoff.
    Other failures (5xx, parse errors, refusals) propagate without retry —
    matches "no retry on null" contract for judge content.
    """
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    body = {
        "model": JUDGE_MODEL,
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "messages": [{"role": "user", "content": prompt}],
    }

    # estimate input tokens for pre-call throttling
    est_tokens = int(len(prompt) / CHARS_PER_TOKEN_APPROX) + 16  # +16 overhead
    await bucket.acquire(est_tokens)

    for attempt in range(RETRY_429_MAX + 1):
        try:
            r = await client.post(ENDPOINT, headers=headers, json=body, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            text = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")
            usage = data.get("usage", {})
            return text, usage
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and attempt < RETRY_429_MAX:
                ra = e.response.headers.get("retry-after")
                try:
                    wait = float(ra) if ra else RETRY_429_BASE_WAIT * (2 ** attempt)
                except ValueError:
                    wait = RETRY_429_BASE_WAIT * (2 ** attempt)
                await asyncio.sleep(min(wait, 90.0))
                continue
            raise


async def grade_one(item, client, api_key, sem, bucket, null_log_path, usage_acc, counters):
    async with sem:
        item_rubric = sorted((item.get("eval_criteria") or {}).keys())
        rubric_list = ", ".join(item_rubric)
        fields_to_grade = item_rubric

        grading_prompt = _build_grading_prompt(item, rubric_list)

        raw = ""
        try:
            raw, usage = await call_sonnet(client, api_key, grading_prompt, bucket)
            usage_acc["input"] += usage.get("input_tokens", 0)
            usage_acc["output"] += usage.get("output_tokens", 0)
            usage_acc["calls"] += 1
            parsed, fail_mode = parse_scores(raw, fields_to_grade)
        except httpx.HTTPStatusError as e:
            raw = f"<HTTPStatusError {e.response.status_code}: {e.response.text[:500]}>"
            parsed = {k: None for k in fields_to_grade}
            fail_mode = "http_err"
        except Exception as e:
            raw = f"<{type(e).__name__}: {e}>"
            parsed = {k: None for k in fields_to_grade}
            fail_mode = "exception"

        counters[fail_mode] = counters.get(fail_mode, 0) + 1
        counters["_total"] = counters.get("_total", 0) + 1

        if fail_mode != "ok":
            with open(null_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "item_id": item.get("id"),
                    "fail_mode": fail_mode,
                    "rubric_fields": fields_to_grade,
                    "raw": (raw or "")[:5000],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }) + "\n")

        return {**item, "scores": parsed}


def write_outputs(scored, rubric_fields, csv_path, json_path):
    """Match grading._write_grading_output schema exactly."""
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "prompt", "response", "model"] + rubric_fields)
        for item in scored:
            scores = item.get("scores", {}) or {}
            prompt_out = (
                json.dumps(item["prompt"])
                if isinstance(item["prompt"], list)
                else item["prompt"]
            )
            w.writerow(
                [item.get("id"), prompt_out, item["response"], item["model"]]
                + [scores.get(k) for k in rubric_fields]
            )
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(scored, f, indent=2, default=str)


def stratified_pilot_ids(items, target_per_model=17):
    """Stride-sample success items to span all category prefixes.

    Returns a list of item IDs.
    """
    success = [it for it in items if it.get("success")]
    if len(success) <= target_per_model:
        return [it["id"] for it in success]
    stride = max(1, len(success) // target_per_model)
    sampled = success[::stride][:target_per_model]
    return [it["id"] for it in sampled]


async def run_model(model_cfg, api_key, bucket, pilot_ids=None, smoke_only=False):
    eval_path = model_cfg["dir"] / model_cfg["eval_file"]
    items = json.loads(eval_path.read_text())

    if smoke_only:
        items = [next(it for it in items if it.get("success"))]
    elif pilot_ids is not None:
        items = [it for it in items if it.get("id") in pilot_ids]

    successful = [it for it in items if it.get("success")]
    print(f"[{model_cfg['key']}] {len(successful)} success items to grade")

    rubric_fields = sorted({
        k for it in successful for k in (it.get("eval_criteria") or {}).keys()
    })

    analysis_dir = model_cfg["dir"] / "analysis"
    analysis_dir.mkdir(exist_ok=True)
    null_log = analysis_dir / "sonnet46_null_responses.jsonl"

    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    usage_acc = {"input": 0, "output": 0, "calls": 0}
    counters = {}

    t0 = time.time()
    async with httpx.AsyncClient() as client:
        tasks = [
            grade_one(it, client, api_key, sem, bucket, null_log, usage_acc, counters)
            for it in successful
        ]
        scored = await asyncio.gather(*tasks)
    elapsed = time.time() - t0

    if not smoke_only and pilot_ids is None:
        csv_path = analysis_dir / f"{model_cfg['out_stem']}.csv"
        json_path = analysis_dir / f"{model_cfg['out_stem']}.json"
        write_outputs(scored, rubric_fields, csv_path, json_path)
        print(f"[{model_cfg['key']}] wrote {csv_path.name} + .json")

    return {
        "model": model_cfg["key"],
        "scored": scored,
        "rubric_fields": rubric_fields,
        "counters": counters,
        "usage": usage_acc,
        "elapsed_s": elapsed,
    }


def aggregate_scores(model_results):
    """Build scored-aggregate-sonnet46.json matching original schema.

    Per-model, per-rubric-field: true_count / scored_count (pct).
    Null fields excluded from scored_count.
    """
    out = {}
    for r in model_results:
        m = r["model"]
        scored = r["scored"]
        per_field = {}
        all_fields = set()
        for item in scored:
            for k in (item.get("scores") or {}).keys():
                all_fields.add(k)
            for k in (item.get("eval_criteria") or {}).keys():
                all_fields.add(k)
        for field in sorted(all_fields):
            true_count = 0
            scored_count = 0
            for item in scored:
                if field not in (item.get("eval_criteria") or {}):
                    continue
                v = (item.get("scores") or {}).get(field)
                if v is None:
                    continue
                scored_count += 1
                if v is True:
                    true_count += 1
            if scored_count > 0:
                pct = true_count / scored_count * 100
                per_field[field] = {
                    "true_count": true_count,
                    "scored_count": scored_count,
                    "pct": round(pct, 2),
                }
        out[m] = per_field
    return out


def report_calibration(model_results):
    """Report per-model true/false/null + calibration delta vs gpt-oss-20b."""
    # gpt-oss-20b baseline (computed earlier in this session)
    gpt_baseline = {
        "v4_pro":   {"true": 572, "false": 141, "null": 18, "total": 756},
        "v4_flash": {"true": 550, "false": 152, "null": 18, "total": 736},
        "laguna":   {"true": 554, "false": 181, "null": 12, "total": 769},
    }
    gpt_overall = {
        "true": sum(g["true"] for g in gpt_baseline.values()),
        "false": sum(g["false"] for g in gpt_baseline.values()),
        "null": sum(g["null"] for g in gpt_baseline.values()),
        "total": sum(g["total"] for g in gpt_baseline.values()),
    }

    print("\n" + "=" * 70)
    print("CALIBRATION DELTA — gpt-oss-20b vs Sonnet 4.6")
    print("=" * 70)

    son_overall = {"true": 0, "false": 0, "null": 0, "total": 0}
    son_per = {}
    for r in model_results:
        m = r["model"]
        t = f_ = n = total = 0
        for item in r["scored"]:
            for k, v in (item.get("scores") or {}).items():
                total += 1
                if v is None:
                    n += 1
                elif v is True:
                    t += 1
                elif v is False:
                    f_ += 1
        son_per[m] = {"true": t, "false": f_, "null": n, "total": total}
        son_overall["true"] += t
        son_overall["false"] += f_
        son_overall["null"] += n
        son_overall["total"] += total

    def pct(n, d):
        return (n / d * 100) if d else 0.0

    g = gpt_overall
    s = son_overall
    print(f"\nOverall (all 3 models, all rubric fields):")
    print(f"{'metric':<14} {'gpt-oss-20b':>14} {'Sonnet 4.6':>14} {'Δ':>10}")
    print(f"{'True rate':<14} {pct(g['true'], g['total']):>13.2f}% {pct(s['true'], s['total']):>13.2f}% {pct(s['true'], s['total']) - pct(g['true'], g['total']):>+9.2f}pp")
    print(f"{'False rate':<14} {pct(g['false'], g['total']):>13.2f}% {pct(s['false'], s['total']):>13.2f}% {pct(s['false'], s['total']) - pct(g['false'], g['total']):>+9.2f}pp")
    print(f"{'Null rate':<14} {pct(g['null'], g['total']):>13.2f}% {pct(s['null'], s['total']):>13.2f}% {pct(s['null'], s['total']) - pct(g['null'], g['total']):>+9.2f}pp")

    print(f"\nPer-model null rate:")
    for m in ("v4_pro", "v4_flash", "laguna"):
        if m not in son_per:
            continue
        gn = pct(gpt_baseline[m]["null"], gpt_baseline[m]["total"])
        sn = pct(son_per[m]["null"], son_per[m]["total"])
        print(f"  {m:<12} {gn:>5.2f}%  →  {sn:>5.2f}%  Δ {sn - gn:+.2f}pp")

    delta_true = pct(s["true"], s["total"]) - pct(g["true"], g["total"])
    if abs(delta_true) > 10:
        print(f"\n⚠️  TRUE-RATE DELTA = {delta_true:+.2f}pp — exceeds ±10pp threshold")
        print("    Judges aren't measuring the same thing; per-field κ will be misleading.")
    else:
        print(f"\n✓ True-rate delta {delta_true:+.2f}pp within ±10pp tolerance.")

    return son_overall, son_per


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--smoke", action="store_true", help="smoke-test 1 item per model")
    p.add_argument("--pilot", action="store_true", help="50-item stratified pilot")
    p.add_argument("--model", choices=["v4_pro", "v4_flash", "laguna"], help="single model")
    args = p.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(2)

    models = MODELS
    if args.model:
        models = [m for m in MODELS if m["key"] == args.model]

    # per-model pilot IDs (was a global set before — collapsed dupes across models)
    per_model_pilot_ids = {}
    if args.pilot:
        for m in models:
            items = json.loads((m["dir"] / m["eval_file"]).read_text())
            ids = stratified_pilot_ids(items, target_per_model=17)
            per_model_pilot_ids[m["key"]] = set(ids)
            print(f"[{m['key']}] pilot IDs ({len(ids)}): {ids}")
        total = sum(len(s) for s in per_model_pilot_ids.values())
        print(f"\ntotal pilot grading calls: {total}\n")

    bucket = TokenBucket(INPUT_TPM_LIMIT)

    results = []
    for m in models:
        ids_for_model = per_model_pilot_ids.get(m["key"]) if args.pilot else None
        r = await run_model(m, api_key, bucket, pilot_ids=ids_for_model, smoke_only=args.smoke)
        results.append(r)

    print("\n" + "=" * 70)
    print("PER-MODEL SUMMARY")
    print("=" * 70)
    for r in results:
        c = r["counters"]
        u = r["usage"]
        total = c.get("_total", 0)
        ok = c.get("ok", 0)
        nb = c.get("no_braces", 0)
        je = c.get("json_err", 0)
        ref = c.get("refusal", 0)
        ex = c.get("exception", 0) + c.get("http_err", 0)
        # estimated cost: $3/M in, $15/M out for sonnet 4.6
        cost = u["input"] / 1_000_000 * 3.0 + u["output"] / 1_000_000 * 15.0
        print(f"\n[{r['model']}] {total} calls in {r['elapsed_s']:.1f}s")
        print(f"  ok={ok} no_braces={nb} json_err={je} refusal={ref} exc/http={ex}")
        print(f"  tokens: in={u['input']:,} out={u['output']:,}  est cost ${cost:.2f}")

    if not args.smoke and not args.pilot:
        agg_path = BASE / "scored-aggregate-sonnet46.json"
        agg_path.write_text(json.dumps(aggregate_scores(results), indent=2))
        print(f"\nwrote {agg_path}")

    if not args.smoke:
        report_calibration(results)

    if args.pilot:
        print("\n" + "=" * 70)
        print("PILOT GATES")
        print("=" * 70)
        total_items = sum(c["counters"].get("_total", 0) for c in results)
        total_null = sum(
            c["counters"].get("no_braces", 0)
            + c["counters"].get("json_err", 0)
            + c["counters"].get("refusal", 0)
            + c["counters"].get("exception", 0)
            + c["counters"].get("http_err", 0)
            for c in results
        )
        total_refusal = sum(c["counters"].get("refusal", 0) for c in results)
        # null rate gate is field-level, not item-level — recompute on rubric fields
        all_fields = sum(
            sum(1 for v in (it.get("scores") or {}).values())
            for r in results for it in r["scored"]
        )
        null_fields = sum(
            sum(1 for v in (it.get("scores") or {}).values() if v is None)
            for r in results for it in r["scored"]
        )
        null_field_rate = null_fields / all_fields * 100 if all_fields else 0
        refusal_item_rate = total_refusal / total_items * 100 if total_items else 0

        print(f"items judged:     {total_items}")
        print(f"null field rate:  {null_field_rate:.2f}%   (gate: 5.00%)")
        print(f"refusal item rate:{refusal_item_rate:.2f}%   (gate: 1.00%)")

        gates_failed = []
        if null_field_rate > 5.0:
            gates_failed.append(f"null rate {null_field_rate:.2f}% > 5.00%")
        if refusal_item_rate > 1.0:
            gates_failed.append(f"refusal rate {refusal_item_rate:.2f}% > 1.00%")

        if gates_failed:
            print(f"\n⚠️  GATES TRIPPED: {'; '.join(gates_failed)}")
            print("   STOP — report to user before proceeding to full run.")
        else:
            print("\n✓ both gates clear, ok to proceed to full run")


if __name__ == "__main__":
    asyncio.run(main())
