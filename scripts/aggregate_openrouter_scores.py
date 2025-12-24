#!/usr/bin/env python3
"""
Aggregate per-model pass rates for OpenRouter post-analysis scores.

- Finds the latest combined CSV under outputs/analysis/ named like:
  openrouter_scores_all_models_YYYY-MM-DD_HH-MM-SS.csv
- Computes pass rates for boolean scoring columns per model and overall.
- Writes JSON and CSV summaries to outputs/analysis/ with a timestamped name.
- Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import json
import os
import sys
from collections import defaultdict


def _bool_or_none(val: str):
    if val is None:
        return None
    s = str(val).strip().lower()
    if s == "true":
        return True
    if s == "false":
        return False
    return None


def find_latest_combined_csv(analysis_dir: str) -> str | None:
    pattern = os.path.join(analysis_dir, "openrouter_scores_all_models_*.csv")
    files = glob.glob(pattern)
    if not files:
        return None
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files[0]


def compute_pass_rates(csv_path: str):
    # Allow very large CSV cells
    try:
        csv.field_size_limit(sys.maxsize)
    except Exception:
        pass

    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise RuntimeError("CSV has no header: %s" % csv_path)

        header = reader.fieldnames
        # Determine metric columns: everything after 'model' that appears boolean
        if "model" not in header:
            raise RuntimeError("CSV missing required 'model' column")
        # Heuristic: treat columns after 'model' as metrics
        model_index = header.index("model")
        metric_cols = header[model_index + 1 :]

        # Counters: { model: { metric: {passed, total} } }
        counters = defaultdict(lambda: defaultdict(lambda: {"passed": 0, "total": 0}))
        OVERALL = "__overall__"

        rows = list(reader)
        for row in rows:
            model = row.get("model", "__unknown__") or "__unknown__"
            for metric in metric_cols:
                val = _bool_or_none(row.get(metric))
                if val is None:
                    continue  # don't count missing/blank/non-boolean
                counters[model][metric]["total"] += 1
                counters[OVERALL][metric]["total"] += 1
                if val:
                    counters[model][metric]["passed"] += 1
                    counters[OVERALL][metric]["passed"] += 1

        # Compute pass rates
        def finalize(model_name: str):
            out = {}
            for metric, c in counters[model_name].items():
                total = c["total"]
                passed = c["passed"]
                rate = (passed / total) if total > 0 else None
                out[metric] = {"passed": passed, "total": total, "pass_rate": rate}
            return out

        per_model = {m: finalize(m) for m in counters.keys() if m != OVERALL}
        overall = finalize(OVERALL)

        return {
            "input_file": os.path.relpath(csv_path),
            "total_rows": len(rows),
            "metrics": {
                "per_model": per_model,
                "overall": overall,
            },
        }


def write_outputs(result: dict, analysis_dir: str) -> tuple[str, str]:
    ts = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    base = f"openrouter_scores_pass_rates_{ts}"
    json_path = os.path.join(analysis_dir, base + ".json")
    csv_path = os.path.join(analysis_dir, base + ".csv")

    # JSON
    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump(result, jf, indent=2)

    # Flatten to CSV rows
    rows = []
    overall = result["metrics"]["overall"]
    for metric, stats in overall.items():
        rows.append({
            "model": "__overall__",
            "metric": metric,
            "passed": stats["passed"],
            "total": stats["total"],
            "pass_rate": ("" if stats["pass_rate"] is None else f"{stats['pass_rate']:.4f}"),
        })

    for model, metrics in sorted(result["metrics"]["per_model"].items()):
        for metric, stats in metrics.items():
            rows.append({
                "model": model,
                "metric": metric,
                "passed": stats["passed"],
                "total": stats["total"],
                "pass_rate": ("" if stats["pass_rate"] is None else f"{stats['pass_rate']:.4f}"),
            })

    with open(csv_path, "w", encoding="utf-8", newline="") as cf:
        writer = csv.DictWriter(cf, fieldnames=["model", "metric", "passed", "total", "pass_rate"])
        writer.writeheader()
        writer.writerows(rows)

    return json_path, csv_path


auto_desc = (
    "Auto-detect the latest combined CSV under outputs/analysis/ (pattern: openrouter_scores_all_models_*.csv)."
)


def main():
    parser = argparse.ArgumentParser(description="Aggregate OpenRouter pass rates")
    parser.add_argument(
        "--input",
        "-i",
        help=(
            "Path to the combined CSV (default: " + auto_desc + ")"
        ),
    )
    parser.add_argument(
        "--analysis-dir",
        default=os.path.join("outputs", "analysis"),
        help="Directory containing analysis outputs (default: outputs/analysis/)",
    )
    args = parser.parse_args()

    analysis_dir = args.analysis_dir
    os.makedirs(analysis_dir, exist_ok=True)

    csv_path = args.input or find_latest_combined_csv(analysis_dir)
    if not csv_path or not os.path.exists(csv_path):
        print("[ERROR] Combined CSV not found. Provide --input or run post-analysis first.")
        print("        Searched pattern in:", analysis_dir)
        sys.exit(1)

    result = compute_pass_rates(csv_path)
    json_out, csv_out = write_outputs(result, analysis_dir)

    # Brief summary
    overall = result["metrics"]["overall"]
    print("\n[Aggregator] Input:", os.path.relpath(csv_path))
    print("[Aggregator] Total rows:", result["total_rows"])
    print("[Aggregator] Overall pass rates:")
    for metric, stats in sorted(overall.items()):
        rate = stats["pass_rate"]
        rate_str = "n/a" if rate is None else f"{rate:.2%}"
        print(f"  - {metric}: {rate_str} ({stats['passed']}/{stats['total']})")
    print("[Aggregator] Wrote:")
    print("  ", os.path.relpath(json_out))
    print("  ", os.path.relpath(csv_out))


if __name__ == "__main__":
    main()
