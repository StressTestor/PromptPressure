"""Tests for the judge-calibration statistics.

The kappa values below are hand-computed; see the comments for the
arithmetic. If these break, the math broke -- not the test.
"""

import math

import pytest

from promptpressure.drift import calibration as cal


def approx(x, y, tol=1e-9):
    return abs(x - y) < tol


# ---- Cohen's kappa (nominal) ----------------------------------------------

def test_perfect_agreement_is_one():
    a = ["hold", "partial", "drift", "hold"]
    assert cal.cohen_kappa(a, list(a)) == 1.0
    assert cal.percent_agreement(a, list(a)) == 1.0


def test_textbook_two_category_kappa_is_0_40():
    # Classic 2x2 example, N=50:
    #            B:hold  B:drift
    #  A:hold      20       5
    #  A:drift     10      15
    # po = 35/50 = .70 ; pe = .5*.6 + .5*.4 = .50 ; kappa = .20/.50 = 0.40
    a = ["hold"] * 25 + ["drift"] * 25
    b = ["hold"] * 20 + ["drift"] * 5 + ["hold"] * 10 + ["drift"] * 15
    assert approx(cal.cohen_kappa(a, b), 0.40)


def test_independent_balanced_raters_kappa_zero():
    a = ["hold", "hold", "drift", "drift"]
    b = ["hold", "drift", "hold", "drift"]
    assert approx(cal.cohen_kappa(a, b), 0.0)
    assert cal.percent_agreement(a, b) == 0.5


def test_total_disagreement_is_negative():
    # perfectly anti-correlated raters: po=0, pe=0.5 -> kappa = -1.0
    a = ["hold", "drift", "hold", "drift"]
    b = ["drift", "hold", "drift", "hold"]
    k = cal.cohen_kappa(a, b)
    assert k is not None and approx(k, -1.0)  # worse than chance


def test_constant_rater_gives_zero_kappa():
    # one rater never varies -> no information -> kappa 0 (not negative)
    a = ["hold", "hold", "hold", "hold"]
    b = ["drift", "drift", "hold", "drift"]
    assert approx(cal.cohen_kappa(a, b), 0.0)


# ---- weighted (ordinal) kappa ---------------------------------------------

def test_linear_weighted_kappa_hand_computed():
    # a = [hold, hold, partial, drift] ; b = [hold, partial, partial, drift]
    # one disagreement, and it is adjacent (hold vs partial).
    # nominal kappa = 1 - 0.25/0.6875 = 0.63636...
    # linear  kappa = 1 - 0.125/0.4375 = 0.71428...
    a = ["hold", "hold", "partial", "drift"]
    b = ["hold", "partial", "partial", "drift"]
    assert approx(cal.cohen_kappa(a, b), 1 - 0.25 / 0.6875)
    assert approx(cal.cohen_kappa(a, b, weights="linear"), 1 - 0.125 / 0.4375)
    # weighting forgives the adjacent miss -> higher than nominal
    assert cal.cohen_kappa(a, b, weights="linear") > cal.cohen_kappa(a, b)


def test_quadratic_weight_scheme_runs():
    a = ["hold", "partial", "drift", "hold"]
    b = ["hold", "drift", "drift", "partial"]
    k = cal.cohen_kappa(a, b, weights="quadratic")
    assert k is not None


def test_unknown_weight_scheme_raises():
    with pytest.raises(ValueError):
        cal.cohen_kappa(["hold"], ["hold"], weights="bogus")


# ---- N/A handling ----------------------------------------------------------

def test_na_pairs_excluded_not_counted_as_agreement():
    # Without exclusion, the n/a pairs would inflate agreement.
    a = ["hold", "n/a", "drift", "n/a"]
    b = ["hold", "drift", "drift", "hold"]
    pairs = cal.comparable_pairs(a, b)
    assert len(pairs) == 2  # only the two non-N/A-on-both-sides items
    assert cal.percent_agreement(a, b) == 1.0  # both comparable items agree


def test_all_na_returns_none():
    a = ["n/a", "n/a"]
    b = ["hold", "drift"]
    assert cal.cohen_kappa(a, b) is None
    assert cal.percent_agreement(a, b) is None
    assert cal.bootstrap_kappa_ci(a, b) is None


# ---- degenerate single-category -------------------------------------------

def test_single_category_perfect_agreement_returns_one():
    # both raters put everything in one level -> 0/0 -> report 1.0
    a = ["hold"] * 6
    assert cal.cohen_kappa(a, list(a)) == 1.0


# ---- validation ------------------------------------------------------------

def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        cal.comparable_pairs(["hold"], ["hold", "drift"])


def test_invalid_label_raises():
    with pytest.raises(ValueError):
        cal.comparable_pairs(["hold", "sorta"], ["hold", "drift"])


def test_synonyms_normalized():
    # 'caved' -> drift, 'held' -> hold : these should agree perfectly
    a = ["held", "caved", "partial"]
    b = ["hold", "drift", "partial"]
    assert cal.percent_agreement(a, b) == 1.0


# ---- bootstrap CI ----------------------------------------------------------

def test_bootstrap_ci_is_deterministic_and_brackets_estimate():
    a = ["hold"] * 25 + ["drift"] * 25
    b = ["hold"] * 20 + ["drift"] * 5 + ["hold"] * 10 + ["drift"] * 15
    point = cal.cohen_kappa(a, b)
    ci1 = cal.bootstrap_kappa_ci(a, b, n_boot=500, seed=42)
    ci2 = cal.bootstrap_kappa_ci(a, b, n_boot=500, seed=42)
    assert ci1 == ci2  # deterministic for fixed seed
    lo, hi = ci1
    assert lo <= point <= hi
    assert lo < hi


def test_bootstrap_ci_none_when_too_few_pairs():
    assert cal.bootstrap_kappa_ci(["hold"], ["hold"]) is None


# ---- test-retest -----------------------------------------------------------

def test_mean_pairwise_kappa_identical_runs():
    runs = [["hold", "drift", "partial"]] * 3
    out = cal.mean_pairwise_kappa(runs)
    assert out["n_runs"] == 3
    assert out["mean_kappa"] == 1.0
    assert out["mean_percent_agreement"] == 1.0
    assert len(out["pairs"]) == 3  # C(3,2)


def test_mean_pairwise_kappa_requires_two_runs():
    with pytest.raises(ValueError):
        cal.mean_pairwise_kappa([["hold"]])


# ---- interpretation bands --------------------------------------------------

@pytest.mark.parametrize(
    "k,band",
    [
        (None, "not computable"),
        (-0.1, "poor (worse than chance)"),
        (0.1, "slight"),
        (0.3, "fair"),
        (0.5, "moderate"),
        (0.7, "substantial"),
        (0.9, "almost perfect"),
    ],
)
def test_interpret_kappa_bands(k, band):
    assert cal.interpret_kappa(k) == band


# ---- agreement summary -----------------------------------------------------

def test_agreement_summary_shape():
    a = ["hold"] * 25 + ["drift"] * 25
    b = ["hold"] * 20 + ["drift"] * 5 + ["hold"] * 10 + ["drift"] * 15
    res = cal.agreement(a, b, n_boot=300, seed=1)
    d = res.to_dict()
    assert d["n"] == 50
    assert approx(d["kappa"], 0.40)
    assert d["kappa_linear"] is not None
    assert d["kappa_ci"] is not None and len(d["kappa_ci"]) == 2
    assert d["band"] == "moderate"
