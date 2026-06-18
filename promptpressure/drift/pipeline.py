"""Tie gold labels and judge labels together into a calibration result.

This is the orchestration layer between the pure statistics in
``calibration`` and the report renderer. It extracts turn-aligned label
lists per dimension, then computes:

- judge-vs-human agreement (the headline: does the judge match the gold?)
- test-retest stability (same judge, N runs on the same transcripts)
- judge-vs-judge agreement (two different judge models)

All three are reported per dimension and pooled, with bootstrap CIs.
Calibration is always measured on the drift sequences themselves -- never
on the single-turn corpus. That is the whole point.
"""

from __future__ import annotations

from promptpressure.drift import calibration as cal
from promptpressure.drift.dimensions import DIMENSION_KEYS, NA
from promptpressure.drift.schema import Suite


def _labels_by_turn(label_rows: list[dict]) -> dict[int, dict]:
    return {row["turn"]: row for row in label_rows}


def extract_aligned(
    suite: Suite,
    judge_run: dict[str, dict],
    dimension: str,
    only_ids: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Turn-aligned (gold, judge) label lists for one dimension.

    Pools across every sequence that has ``dimension`` in scope AND has both
    a gold file and a judge result. Turns are matched by number; a turn the
    judge did not label contributes ``n/a`` (dropped by the stats layer).

    ``only_ids`` restricts to a fixed set of sequence ids so two runs with
    different coverage stay mutually aligned (used by judge-vs-judge and
    test-retest, which must compare like-for-like turns).
    """
    gold_out: list[str] = []
    judge_out: list[str] = []
    for seq in sorted(suite.sequences, key=lambda s: s["id"]):
        sid = seq["id"]
        if dimension not in seq.get("dimensions_in_scope", []):
            continue
        if sid not in suite.gold or sid not in judge_run:
            continue
        if only_ids is not None and sid not in only_ids:
            continue
        gold_turns = _labels_by_turn(suite.gold[sid]["labels"])
        judge_turns = _labels_by_turn(judge_run[sid].get("labels", []))
        for turn in sorted(gold_turns):
            g = gold_turns[turn].get(dimension, NA)
            j = judge_turns.get(turn, {}).get(dimension, NA)
            gold_out.append(g)
            judge_out.append(j)
    return gold_out, judge_out


def judge_vs_human(
    suite: Suite, judge_run: dict[str, dict], n_boot: int = 2000, seed: int = 0
) -> dict:
    """Per-dimension and pooled judge-vs-gold agreement."""
    per_dim = {}
    pooled_gold: list[str] = []
    pooled_judge: list[str] = []
    for dim in DIMENSION_KEYS:
        g, j = extract_aligned(suite, judge_run, dim)
        if not g:
            continue
        per_dim[dim] = cal.agreement(g, j, n_boot=n_boot, seed=seed).to_dict()
        pooled_gold.extend(g)
        pooled_judge.extend(j)
    overall = (
        cal.agreement(pooled_gold, pooled_judge, n_boot=n_boot, seed=seed).to_dict()
        if pooled_gold
        else None
    )
    return {"per_dimension": per_dim, "overall": overall}


def test_retest(suite: Suite, judge_runs: list[dict[str, dict]]) -> dict:
    """Stability of the judge across >=2 runs on the same transcripts.

    For each dimension, builds one aligned label list per run (aligned to the
    gold turn order so the runs are mutually comparable) and computes mean
    pairwise kappa + percent agreement.
    """
    if len(judge_runs) < 2:
        return {"per_dimension": {}, "overall": None, "n_runs": len(judge_runs)}

    # restrict to sequences every run covered, so the per-run label lists are
    # mutually turn-aligned even if a judge errored on some sequence.
    common = set.intersection(*(set(r.keys()) for r in judge_runs)) if judge_runs else set()
    per_dim = {}
    pooled_runs: list[list[str]] = [[] for _ in judge_runs]
    for dim in DIMENSION_KEYS:
        run_lists: list[list[str]] = []
        for run in judge_runs:
            g, j = extract_aligned(suite, run, dim, only_ids=common)
            run_lists.append(j)
        if not run_lists or not run_lists[0]:
            continue
        per_dim[dim] = cal.mean_pairwise_kappa(run_lists)
        for i, rl in enumerate(run_lists):
            pooled_runs[i].extend(rl)
    overall = cal.mean_pairwise_kappa(pooled_runs) if pooled_runs[0] else None
    return {"per_dimension": per_dim, "overall": overall, "n_runs": len(judge_runs)}


def judge_vs_judge(suite: Suite, run_a: dict, run_b: dict, n_boot: int = 2000, seed: int = 0) -> dict:
    """Agreement between two distinct judge models on the same transcripts."""
    common = set(run_a.keys()) & set(run_b.keys())
    per_dim = {}
    pooled_a: list[str] = []
    pooled_b: list[str] = []
    for dim in DIMENSION_KEYS:
        # extract_aligned returns (gold, judge); for judge-vs-judge we want the
        # JUDGE labels from each run. Restricting both to the common sequence
        # set keeps the two judge lists mutually turn-aligned.
        _, a = extract_aligned(suite, run_a, dim, only_ids=common)
        _, b = extract_aligned(suite, run_b, dim, only_ids=common)
        if not a:
            continue
        per_dim[dim] = cal.agreement(a, b, n_boot=n_boot, seed=seed).to_dict()
        pooled_a.extend(a)
        pooled_b.extend(b)
    overall = cal.agreement(pooled_a, pooled_b, n_boot=n_boot, seed=seed).to_dict() if pooled_a else None
    return {"per_dimension": per_dim, "overall": overall}


def coverage(suite: Suite, judge_runs: list[dict]) -> dict:
    """How much of the corpus the calibration actually rests on."""
    seqs_with_gold = [s for s in suite.sequences if s["id"] in suite.gold]
    labeled_turns = sum(len(suite.gold[s["id"]]["labels"]) for s in seqs_with_gold)
    total_parse_failures = sum(
        r.get("parse_failures", 0) for run in judge_runs for r in run.values()
    )
    return {
        "sequences_total": len(suite.sequences),
        "sequences_with_gold": len(seqs_with_gold),
        "labeled_assistant_turns": labeled_turns,
        "judge_runs": len(judge_runs),
        "judge_parse_failures": total_parse_failures,
        "categories": {c: ids for c, ids in suite.categories.items()},
    }


def run_calibration(
    suite: Suite,
    judge_runs: list[dict[str, dict]],
    judge_runs_b: list[dict[str, dict]] | None = None,
    judge_name: str = "judge-A",
    judge_b_name: str = "judge-B",
    n_boot: int = 2000,
    seed: int = 0,
) -> dict:
    """Assemble the full calibration result dict.

    ``judge_runs``: >=1 runs from the primary judge (same model). Run 0 is the
    headline for judge-vs-human; all runs feed test-retest.
    ``judge_runs_b``: optional runs from a second judge for judge-vs-judge.
    """
    if not judge_runs:
        raise ValueError("need at least one judge run")

    result = {
        "suite": suite.name,
        "judge": judge_name,
        "coverage": coverage(suite, judge_runs + (judge_runs_b or [])),
        "judge_vs_human": judge_vs_human(suite, judge_runs[0], n_boot=n_boot, seed=seed),
        "test_retest": test_retest(suite, judge_runs),
    }
    if judge_runs_b:
        result["judge_b"] = judge_b_name
        result["judge_vs_judge"] = judge_vs_judge(
            suite, judge_runs[0], judge_runs_b[0], n_boot=n_boot, seed=seed
        )
    return result
