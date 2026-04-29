"""Re-judge the 2026-04-28 PromptPressure 3-way eval with Kimi K2.6.

Routes through opencode-go's direct OpenAI-compatible endpoint
(https://opencode.ai/zen/go/v1/chat/completions) — NOT the opencode CLI,
which wraps every call in an agent system prompt + tools manifest and
would contaminate the judge contract.

Reuses promptpressure.grading._build_grading_prompt() unchanged.
Same parser logic (find first { / last } / json.loads).
Same Semaphore(5) concurrency. Same per-item rubric extraction.

Output paths (parallel to existing openrouter_scores_* and sonnet46_scores_*):
  v4-pro/analysis/kimi26_scores_v4_pro_2026-04-28.{csv,json}
  v4-flash/analysis/kimi26_scores_v4_flash_2026-04-28.{csv,json}
  laguna-m1/analysis/kimi26_scores_laguna_2026-04-28.{csv,json}

Usage:
  python scripts/rejudge_kimi26.py --smoke   # 1 item per model
  python scripts/rejudge_kimi26.py --pilot   # 51-item stratified pilot
  python scripts/rejudge_kimi26.py           # full 593-item run
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
        "key_human": "V4 Pro",
        "dir": BASE / "v4-pro",
        "eval_file": "eval_openrouter_deepseek_v4_pro.json",
        "out_stem": "kimi26_scores_v4_pro_2026-04-28",
    },
    {
        "key": "v4_flash",
        "key_human": "V4 Flash",
        "dir": BASE / "v4-flash",
        "eval_file": "eval_openrouter_deepseek_v4_flash.json",
        "out_stem": "kimi26_scores_v4_flash_2026-04-28",
    },
    {
        "key": "laguna",
        "key_human": "Laguna M.1",
        "dir": BASE / "laguna-m1",
        "eval_file": "eval_openrouter_poolside_laguna_m1.json",
        "out_stem": "kimi26_scores_laguna_2026-04-28",
    },
]

JUDGE_MODEL = "kimi-k2.6"
ENDPOINT = "https://opencode.ai/zen/go/v1/chat/completions"
TEMPERATURE = 0.7
# Sonnet 4.6 used 4096 (non-reasoning model). K2.6 is reasoning-heavy — budget
# gets consumed by reasoning tokens before content is produced (avg 1.4K reasoning
# per call in pilot, with tail items hitting the cap). 8192 doubles the headroom.
# Judge prompt + parser unchanged; this only affects model working space.
MAX_TOKENS = 8192
HTTP_TIMEOUT = 240.0
MAX_CONCURRENCY = 5

# Start optimistic; opencode-go is BYOK so limits are upstream Moonshot.
# Will dial down via 429-retry if we hit walls during pilot.
INPUT_TPM_LIMIT = 60_000
CHARS_PER_TOKEN_APPROX = 3.5
RETRY_429_MAX = 3
RETRY_429_BASE_WAIT = 10.0

REFUSAL_RE = re.compile(
    r"(i can'?t|i'?m not able|i decline|uncomfortable evaluating|i won'?t|i'?m unable|cannot evaluate|won'?t evaluate|i refuse)",
    re.IGNORECASE,
)


class TokenBucket:
    def __init__(self, capacity_per_minute: int):
        self.capacity = capacity_per_minute
        self.tokens = float(capacity_per_minute)
        self.last_refill = time.monotonic()
        self.lock = asyncio.Lock()

    async def acquire(self, cost: int):
        cost = min(cost, self.capacity)
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


def parse_scores(raw: str, fields_to_grade: list):
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


async def call_kimi(client, api_key, prompt, bucket):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": JUDGE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }

    est_tokens = int(len(prompt) / CHARS_PER_TOKEN_APPROX) + 16
    await bucket.acquire(est_tokens)

    for attempt in range(RETRY_429_MAX + 1):
        try:
            r = await client.post(ENDPOINT, headers=headers, json=body, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            choice = data["choices"][0]["message"]
            text = choice.get("content") or ""
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
            raw, usage = await call_kimi(client, api_key, grading_prompt, bucket)
            usage_acc["input"] += usage.get("prompt_tokens", 0)
            usage_acc["output"] += usage.get("completion_tokens", 0)
            details = usage.get("completion_tokens_details") or {}
            usage_acc["reasoning"] += details.get("reasoning_tokens", 0)
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
    success = [it for it in items if it.get("success")]
    if len(success) <= target_per_model:
        return [it["id"] for it in success]
    stride = max(1, len(success) // target_per_model)
    return [it["id"] for it in success[::stride][:target_per_model]]


async def run_model(model_cfg, api_key, bucket, pilot_ids=None, smoke_only=False):
    eval_path = model_cfg["dir"] / model_cfg["eval_file"]
    items = json.loads(eval_path.read_text())

    if smoke_only:
        items = [next(it for it in items if it.get("success"))]
    elif pilot_ids is not None:
        items = [it for it in items if it.get("id") in pilot_ids]

    successful = [it for it in items if it.get("success")]
    print(f"[{model_cfg['key']}] {len(successful)} success items to grade")

    # union over ALL items (matches grading.py:121, :136 — preserves schema parity)
    all_items = json.loads(eval_path.read_text())
    rubric_fields = sorted({
        k for it in all_items for k in (it.get("eval_criteria") or {}).keys()
    })

    analysis_dir = model_cfg["dir"] / "analysis"
    analysis_dir.mkdir(exist_ok=True)
    null_log = analysis_dir / "kimi26_null_responses.jsonl"

    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    usage_acc = {"input": 0, "output": 0, "reasoning": 0, "calls": 0}
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
        "model_human": model_cfg["key_human"],
        "scored": scored,
        "rubric_fields": rubric_fields,
        "counters": counters,
        "usage": usage_acc,
        "elapsed_s": elapsed,
    }


def aggregate_scores(model_results):
    out = {}
    for r in model_results:
        m = r["model_human"]
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
                per_field[field] = {
                    "true_count": true_count,
                    "scored_count": scored_count,
                    "pct": round(true_count / scored_count * 100, 2),
                }
        out[m] = per_field
    return out


def _tally_scored_file(json_path):
    data = json.loads(json_path.read_text())
    t = f_ = n = total = 0
    for item in data:
        for v in (item.get("scores") or {}).values():
            total += 1
            if v is None: n += 1
            elif v is True: t += 1
            elif v is False: f_ += 1
    return {"true": t, "false": f_, "null": n, "total": total}


def report_calibration(model_results):
    """3-way calibration: gpt-oss-20b vs Sonnet 4.6 vs Kimi K2.6.

    Reads Sonnet/gpt totals from the existing scored JSON files (no hardcoded
    baseline) so the numbers stay correct if upstream files are regenerated.
    """
    gpt_files = {
        "v4_pro":   BASE / "v4-pro/analysis/openrouter_scores_v4_pro_2026-04-28_17-04-11.json",
        "v4_flash": BASE / "v4-flash/analysis/openrouter_scores_v4_flash_2026-04-28_17-06-42.json",
        "laguna":   BASE / "laguna-m1/analysis/openrouter_scores_laguna_2026-04-28_17-09-21.json",
    }
    son_files = {
        "v4_pro":   BASE / "v4-pro/analysis/sonnet46_scores_v4_pro_2026-04-28.json",
        "v4_flash": BASE / "v4-flash/analysis/sonnet46_scores_v4_flash_2026-04-28.json",
        "laguna":   BASE / "laguna-m1/analysis/sonnet46_scores_laguna_2026-04-28.json",
    }
    gpt_baseline = {k: _tally_scored_file(p) for k, p in gpt_files.items()}
    sonnet_baseline = {k: _tally_scored_file(p) for k, p in son_files.items() if p.exists()}
    g_overall = {k: sum(g[k] for g in gpt_baseline.values()) for k in ("true", "false", "null", "total")}
    s_overall = (
        {k: sum(s[k] for s in sonnet_baseline.values()) for k in ("true", "false", "null", "total")}
        if sonnet_baseline else None
    )

    k_per = {}
    for r in model_results:
        m = r["model"]
        t = f_ = n = total = 0
        for item in r["scored"]:
            for v in (item.get("scores") or {}).values():
                total += 1
                if v is None: n += 1
                elif v is True: t += 1
                elif v is False: f_ += 1
        k_per[m] = {"true": t, "false": f_, "null": n, "total": total}
    k_overall = {k: sum(p[k] for p in k_per.values()) for k in ("true", "false", "null", "total")}

    def pct(n, d): return (n/d*100) if d else 0.0

    print("\n" + "=" * 82)
    print("3-WAY JUDGE CALIBRATION — gpt-oss-20b vs Sonnet 4.6 vs Kimi K2.6")
    print("=" * 82)
    if s_overall:
        print(f"\n{'metric':<14} {'gpt-oss':>11} {'Sonnet':>11} {'Kimi':>11} {'son-gpt Δ':>11} {'kimi-gpt Δ':>12} {'kimi-son Δ':>12}")
    else:
        print(f"\n{'metric':<14} {'gpt-oss':>11} {'Kimi':>11} {'kimi-gpt Δ':>12}")
    for label, key in [("True rate", "true"), ("False rate", "false"), ("Null rate", "null")]:
        gv = pct(g_overall[key], g_overall["total"])
        kv = pct(k_overall[key], k_overall["total"])
        if s_overall:
            sv = pct(s_overall[key], s_overall["total"])
            print(f"{label:<14} {gv:>10.2f}% {sv:>10.2f}% {kv:>10.2f}% {sv-gv:>+10.2f}pp {kv-gv:>+11.2f}pp {kv-sv:>+11.2f}pp")
        else:
            print(f"{label:<14} {gv:>10.2f}% {kv:>10.2f}% {kv-gv:>+11.2f}pp")

    delta_kimi_vs_gpt = pct(k_overall["true"], k_overall["total"]) - pct(g_overall["true"], g_overall["total"])
    print()
    if abs(delta_kimi_vs_gpt) > 10:
        print(f"⚠️  Kimi vs gpt-oss true-rate Δ={delta_kimi_vs_gpt:+.2f}pp exceeds ±10pp")
    else:
        print(f"✓ Kimi vs gpt-oss true-rate Δ={delta_kimi_vs_gpt:+.2f}pp within tolerance")
    if s_overall:
        delta_kimi_vs_son = pct(k_overall["true"], k_overall["total"]) - pct(s_overall["true"], s_overall["total"])
        if abs(delta_kimi_vs_son) > 10:
            print(f"⚠️  Kimi vs Sonnet true-rate Δ={delta_kimi_vs_son:+.2f}pp exceeds ±10pp")
        else:
            print(f"✓ Kimi vs Sonnet true-rate Δ={delta_kimi_vs_son:+.2f}pp within tolerance")


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--pilot", action="store_true")
    p.add_argument("--model", choices=["v4_pro", "v4_flash", "laguna"])
    args = p.parse_args()

    api_key = os.environ.get("OPENCODE_API_KEY")
    if not api_key:
        print("ERROR: OPENCODE_API_KEY not set", file=sys.stderr)
        sys.exit(2)

    models = MODELS
    if args.model:
        models = [m for m in MODELS if m["key"] == args.model]

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
        print(f"\n[{r['model']}] {total} calls in {r['elapsed_s']:.1f}s")
        print(f"  ok={ok} no_braces={nb} json_err={je} refusal={ref} exc/http={ex}")
        print(f"  tokens: in={u['input']:,} out={u['output']:,} reasoning={u['reasoning']:,}")
        print(f"  cost: $0.00 (BYOK on opencode-go subscription)")

    if not args.smoke and not args.pilot:
        agg_path = BASE / "scored-aggregate-kimi26.json"
        agg_path.write_text(json.dumps(aggregate_scores(results), indent=2))
        print(f"\nwrote {agg_path}")

    if not args.smoke:
        report_calibration(results)

    if args.pilot:
        print("\n" + "=" * 70)
        print("PILOT GATES")
        print("=" * 70)
        all_fields = sum(
            sum(1 for v in (it.get("scores") or {}).values())
            for r in results for it in r["scored"]
        )
        null_fields = sum(
            sum(1 for v in (it.get("scores") or {}).values() if v is None)
            for r in results for it in r["scored"]
        )
        total_items = sum(c["counters"].get("_total", 0) for c in results)
        total_refusal = sum(c["counters"].get("refusal", 0) for c in results)

        null_rate = null_fields / all_fields * 100 if all_fields else 0
        ref_rate = total_refusal / total_items * 100 if total_items else 0

        print(f"items judged:     {total_items}")
        print(f"null field rate:  {null_rate:.2f}%   (gate: 5.00%)")
        print(f"refusal item rate:{ref_rate:.2f}%   (gate: 1.00%)")

        gates_failed = []
        if null_rate > 5.0: gates_failed.append(f"null {null_rate:.2f}%")
        if ref_rate > 1.0: gates_failed.append(f"refusal {ref_rate:.2f}%")

        if gates_failed:
            print(f"\n⚠️  GATES TRIPPED: {'; '.join(gates_failed)} — STOP, report to user.")
        else:
            print("\n✓ both gates clear, ok to proceed to full run")


if __name__ == "__main__":
    asyncio.run(main())
