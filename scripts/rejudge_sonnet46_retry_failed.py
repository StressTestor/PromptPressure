"""Re-grade only items that failed with HTTP errors (transport-layer nulls).

These are items where Sonnet never received the prompt — distinct from judge
content failures. Updates the existing sonnet46_scores_*.{csv,json} in place.

Usage:
  python scripts/rejudge_sonnet46_retry_failed.py
"""

import asyncio
import csv
import json
import os
import sys
import time
from pathlib import Path

import httpx

REPO = Path("/Volumes/T7/PromptPressure")
sys.path.insert(0, str(REPO))

from scripts.rejudge_sonnet46 import (  # noqa: E402
    BASE,
    MODELS,
    INPUT_TPM_LIMIT,
    TokenBucket,
    grade_one,
    write_outputs,
)


def find_failed_ids(scored_json_path: Path) -> set:
    """Items where every rubric field came back None — i.e., all-null scores."""
    data = json.loads(scored_json_path.read_text())
    failed = set()
    for it in data:
        scores = it.get("scores") or {}
        if not scores:
            failed.add(it["id"])
            continue
        if all(v is None for v in scores.values()):
            failed.add(it["id"])
    return failed


async def retry_failed_for_model(model_cfg, api_key, bucket):
    eval_path = model_cfg["dir"] / model_cfg["eval_file"]
    scored_path = model_cfg["dir"] / "analysis" / f"{model_cfg['out_stem']}.json"
    csv_path = model_cfg["dir"] / "analysis" / f"{model_cfg['out_stem']}.csv"

    if not scored_path.exists():
        print(f"[{model_cfg['key']}] no existing scored file, skipping")
        return

    failed_ids = find_failed_ids(scored_path)
    if not failed_ids:
        print(f"[{model_cfg['key']}] zero failed items — nothing to retry")
        return

    print(f"[{model_cfg['key']}] {len(failed_ids)} failed items: {sorted(failed_ids)}")

    items = json.loads(eval_path.read_text())
    targets = [it for it in items if it.get("success") and it["id"] in failed_ids]

    null_log = model_cfg["dir"] / "analysis" / "sonnet46_null_responses.jsonl"
    sem = asyncio.Semaphore(5)
    usage_acc = {"input": 0, "output": 0, "calls": 0}
    counters = {}

    t0 = time.time()
    async with httpx.AsyncClient() as client:
        tasks = [
            grade_one(it, client, api_key, sem, bucket, null_log, usage_acc, counters)
            for it in targets
        ]
        rescored = await asyncio.gather(*tasks)
    elapsed = time.time() - t0

    print(f"[{model_cfg['key']}] retry done in {elapsed:.1f}s; counters={counters}")

    # merge rescored back into existing scored JSON
    existing = json.loads(scored_path.read_text())
    by_id = {it["id"]: it for it in rescored}
    merged = []
    swapped = 0
    for item in existing:
        if item["id"] in by_id:
            merged.append(by_id[item["id"]])
            swapped += 1
        else:
            merged.append(item)
    print(f"[{model_cfg['key']}] swapped {swapped} items into scored JSON")

    # rebuild rubric_fields from existing CSV header so column ordering stays identical
    with open(csv_path, "r", encoding="utf-8") as f:
        header = next(csv.reader(f))
    rubric_fields = header[4:]  # id, prompt, response, model, then rubric

    write_outputs(merged, rubric_fields, csv_path, scored_path)
    print(f"[{model_cfg['key']}] rewrote {csv_path.name} + .json")


async def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(2)
    bucket = TokenBucket(INPUT_TPM_LIMIT)
    for m in MODELS:
        await retry_failed_for_model(m, api_key, bucket)

    # rebuild aggregate
    from scripts.rejudge_sonnet46 import aggregate_scores
    results = []
    for m in MODELS:
        scored_path = m["dir"] / "analysis" / f"{m['out_stem']}.json"
        if scored_path.exists():
            results.append({
                "model": m["key"],
                "scored": json.loads(scored_path.read_text()),
            })
    agg_path = BASE / "scored-aggregate-sonnet46.json"
    agg_path.write_text(json.dumps(aggregate_scores(results), indent=2))
    print(f"\nrewrote {agg_path}")


if __name__ == "__main__":
    asyncio.run(main())
