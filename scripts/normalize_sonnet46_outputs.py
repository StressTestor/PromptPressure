"""Align Sonnet 4.6 outputs with the existing openrouter_scores schema.

Two fixups:
  1. CSV column set: include rubric fields from errored items (all-None columns)
     so the schema joins cleanly with the gpt-oss-20b output.
  2. Aggregate JSON keys: 'v4_pro' → 'V4 Pro' etc to match scored-aggregate.json.
"""

import csv
import json
import sys
from pathlib import Path

BASE = Path("/Volumes/T7/PromptPressure/outputs/2026-04-28_3way-deepseek-laguna")

CONFIGS = [
    {
        "key": "V4 Pro",
        "key_snake": "v4_pro",
        "dir": "v4-pro",
        "eval_file": "eval_openrouter_deepseek_v4_pro.json",
        "stem": "sonnet46_scores_v4_pro_2026-04-28",
    },
    {
        "key": "V4 Flash",
        "key_snake": "v4_flash",
        "dir": "v4-flash",
        "eval_file": "eval_openrouter_deepseek_v4_flash.json",
        "stem": "sonnet46_scores_v4_flash_2026-04-28",
    },
    {
        "key": "Laguna M.1",
        "key_snake": "laguna",
        "dir": "laguna-m1",
        "eval_file": "eval_openrouter_poolside_laguna_m1.json",
        "stem": "sonnet46_scores_laguna_2026-04-28",
    },
]


def fix_csv_columns(cfg):
    eval_path = BASE / cfg["dir"] / cfg["eval_file"]
    csv_path = BASE / cfg["dir"] / "analysis" / f"{cfg['stem']}.csv"
    json_path = BASE / cfg["dir"] / "analysis" / f"{cfg['stem']}.json"

    # union of rubric fields across ALL items (matches grading.py:121, :136)
    raw_items = json.loads(eval_path.read_text())
    full_rubric = sorted({
        k for it in raw_items for k in (it.get("eval_criteria") or {}).keys()
    })

    # rebuild CSV from JSON with full column set
    scored = json.loads(json_path.read_text())
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "prompt", "response", "model"] + full_rubric)
        for item in scored:
            scores = item.get("scores", {}) or {}
            prompt_out = (
                json.dumps(item["prompt"])
                if isinstance(item["prompt"], list)
                else item["prompt"]
            )
            w.writerow(
                [item.get("id"), prompt_out, item["response"], item["model"]]
                + [scores.get(k) for k in full_rubric]
            )
    return len(full_rubric)


def fix_aggregate_keys():
    src = BASE / "scored-aggregate-sonnet46.json"
    data = json.loads(src.read_text())
    rename = {c["key_snake"]: c["key"] for c in CONFIGS}
    renamed = {rename.get(k, k): v for k, v in data.items()}
    src.write_text(json.dumps(renamed, indent=2))
    return list(renamed.keys())


def main():
    print("=" * 60)
    print("normalizing Sonnet 4.6 outputs for schema parity")
    print("=" * 60)
    for cfg in CONFIGS:
        n_cols = fix_csv_columns(cfg)
        print(f"[{cfg['key_snake']}] CSV rebuilt with {n_cols} rubric columns")
    keys = fix_aggregate_keys()
    print(f"\naggregate keys normalized: {keys}")


if __name__ == "__main__":
    main()
