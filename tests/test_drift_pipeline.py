"""Tests for the calibration pipeline + report rendering."""

import pytest

from promptpressure.drift import pipeline, report
from promptpressure.drift.schema import Suite, load_suite


def _mini_suite() -> Suite:
    sequences = [
        {
            "id": "syc-01",
            "category": "sycophancy-under-pressure",
            "dimensions_in_scope": ["sycophancy", "contradiction", "escalation"],
            "turns": [{"turn": t, "role": "user", "content": "x"} for t in (1, 2)],
        },
        {
            "id": "ref-01",
            "category": "refusal-boundary-relaxation",
            "dimensions_in_scope": ["refusal_integrity", "boundary_relaxation", "escalation"],
            "turns": [{"turn": t, "role": "user", "content": "x"} for t in (1, 2)],
        },
    ]
    gold = {
        "syc-01": {"id": "syc-01", "labels": [
            {"turn": 1, "sycophancy": "hold", "contradiction": "hold", "escalation": "hold"},
            {"turn": 2, "sycophancy": "drift", "contradiction": "partial", "escalation": "hold"},
        ]},
        "ref-01": {"id": "ref-01", "labels": [
            {"turn": 1, "refusal_integrity": "hold", "boundary_relaxation": "hold", "escalation": "hold"},
            {"turn": 2, "refusal_integrity": "drift", "boundary_relaxation": "partial", "escalation": "drift"},
        ]},
    }
    return Suite(name="mini", root=None, sequences=sequences, gold=gold)


def _run_from_gold(suite):
    return {sid: {"labels": [dict(r) for r in g["labels"]], "parse_failures": 0}
            for sid, g in suite.gold.items()}


def test_extract_aligned_pools_only_inscope_sequences():
    s = _mini_suite()
    run = _run_from_gold(s)
    # sycophancy only in syc-01 -> 2 turns
    g, j = pipeline.extract_aligned(s, run, "sycophancy")
    assert len(g) == 2 and g == j
    # escalation in BOTH -> 4 turns
    g, j = pipeline.extract_aligned(s, run, "escalation")
    assert len(g) == 4


def test_perfect_judge_kappa_one():
    s = _mini_suite()
    run = _run_from_gold(s)
    res = pipeline.judge_vs_human(s, run, n_boot=100)
    assert res["overall"]["kappa"] == 1.0
    for dim, d in res["per_dimension"].items():
        assert d["kappa"] == 1.0


def test_judge_disagreement_lowers_kappa():
    s = _mini_suite()
    run = _run_from_gold(s)
    # corrupt one escalation label in ref-01 turn 2: drift -> hold
    run["ref-01"]["labels"][1]["escalation"] = "hold"
    res = pipeline.judge_vs_human(s, run, n_boot=100)
    esc = res["per_dimension"]["escalation"]
    assert esc["kappa"] < 1.0
    assert esc["percent_agreement"] < 1.0


def test_na_judge_turn_excluded_from_n():
    s = _mini_suite()
    run = _run_from_gold(s)
    run["syc-01"]["labels"][1]["sycophancy"] = "n/a"  # judge couldn't label
    g, j = pipeline.extract_aligned(s, run, "sycophancy")
    # extract still returns the turn, but agreement drops it
    res = pipeline.judge_vs_human(s, run, n_boot=100)
    assert res["per_dimension"]["sycophancy"]["n"] == 1  # one comparable pair left


def test_test_retest_identical_runs_perfect():
    s = _mini_suite()
    run = _run_from_gold(s)
    tr = pipeline.test_retest(s, [run, _run_from_gold(s), _run_from_gold(s)])
    assert tr["n_runs"] == 3
    assert tr["overall"]["mean_kappa"] == 1.0


def test_judge_vs_judge():
    s = _mini_suite()
    a = _run_from_gold(s)
    b = _run_from_gold(s)
    b["syc-01"]["labels"][1]["contradiction"] = "drift"  # judges differ on one
    jj = pipeline.judge_vs_judge(s, a, b, n_boot=100)
    assert jj["per_dimension"]["contradiction"]["kappa"] < 1.0
    assert jj["per_dimension"]["sycophancy"]["kappa"] == 1.0


def test_coverage_counts():
    s = _mini_suite()
    cov = pipeline.coverage(s, [_run_from_gold(s)])
    assert cov["sequences_total"] == 2
    assert cov["sequences_with_gold"] == 2
    assert cov["labeled_assistant_turns"] == 4


def test_run_calibration_requires_a_run():
    s = _mini_suite()
    with pytest.raises(ValueError):
        pipeline.run_calibration(s, [])


def test_run_calibration_full_shape():
    s = _mini_suite()
    runs = [_run_from_gold(s), _run_from_gold(s)]
    res = pipeline.run_calibration(s, runs, judge_runs_b=[_run_from_gold(s)],
                                   judge_name="J", judge_b_name="K", n_boot=100)
    assert res["judge"] == "J"
    assert "judge_vs_human" in res and "test_retest" in res and "judge_vs_judge" in res
    assert res["coverage"]["labeled_assistant_turns"] == 4


# ---- report rendering -------------------------------------------------------

def test_report_contains_key_sections():
    s = _mini_suite()
    runs = [_run_from_gold(s), _run_from_gold(s)]
    res = pipeline.run_calibration(s, runs, n_boot=100)
    md = report.render_method_report(res, model_under_test="mock", generated="t")
    assert "judge-vs-human agreement" in md
    assert "test-retest stability" in md
    assert "the honest claim" in md
    assert "pilot" in md.lower()
    # the markdown table header is present
    assert "| dimension | n | % agree | kappa |" in md


def test_report_on_real_corpus():
    s = load_suite("drift-v0.1", strict=True)
    run = {sid: {"labels": g["labels"], "parse_failures": 0} for sid, g in s.gold.items()}
    res = pipeline.run_calibration(s, [run, run], n_boot=100)
    assert res["judge_vs_human"]["overall"]["kappa"] == 1.0  # gold vs itself
    assert res["coverage"]["labeled_assistant_turns"] == 108  # 6*8 + 3*20
    md = report.render_method_report(res, generated="t")
    assert "drift-v0.1" in md
