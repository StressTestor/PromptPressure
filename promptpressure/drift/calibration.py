"""Inter-rater agreement statistics for judge calibration.

Pure standard library -- no numpy, no scipy -- so the calibration math
runs anywhere the package runs and is trivial to audit. Everything here
operates on aligned lists of string labels (the levels in
``dimensions.LEVELS`` plus the ``n/a`` sentinel). N/A entries are excluded
pairwise: if either rater marks an item N/A, that item is dropped from the
comparison rather than scored as agreement or disagreement.

The headline statistic is Cohen's kappa. We implement the general weighted
form, which reduces exactly to Cohen's kappa under nominal (0/1) weights
and gives linearly- or quadratically-weighted kappa for the ordinal case
(hold < partial < drift). Confidence intervals are bootstrap percentile
intervals over the comparable item pairs.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from promptpressure.drift.dimensions import LEVELS, NA, normalize_label, is_valid_label

# A label is comparable iff it is one of the ordinal levels (not N/A).
_LEVEL_INDEX = {lvl: i for i, lvl in enumerate(LEVELS)}
_K = len(LEVELS)


def _weight(i: int, j: int, scheme: str | None) -> float:
    """Disagreement weight between ordinal categories i and j.

    nominal (None): 0 on the diagonal, 1 everywhere else.
    linear: |i-j| / (K-1).
    quadratic: (i-j)^2 / (K-1)^2.
    """
    if scheme is None or scheme == "nominal":
        return 0.0 if i == j else 1.0
    if scheme == "linear":
        return abs(i - j) / (_K - 1)
    if scheme == "quadratic":
        return ((i - j) ** 2) / ((_K - 1) ** 2)
    raise ValueError(f"unknown weight scheme {scheme!r}")


def comparable_pairs(a: list[str], b: list[str]) -> list[tuple[int, int]]:
    """Return aligned (ordinal_a, ordinal_b) pairs, dropping N/A on either side.

    Validates every label, so a malformed gold file or judge response fails
    loudly instead of being silently miscounted.
    """
    if len(a) != len(b):
        raise ValueError(f"label lists differ in length: {len(a)} vs {len(b)}")
    pairs: list[tuple[int, int]] = []
    for la, lb in zip(a, b):
        la_n, lb_n = normalize_label(la), normalize_label(lb)
        for lab in (la_n, lb_n):
            if not is_valid_label(lab):
                raise ValueError(f"invalid label {lab!r}")
        if la_n == NA or lb_n == NA:
            continue
        pairs.append((_LEVEL_INDEX[la_n], _LEVEL_INDEX[lb_n]))
    return pairs


def percent_agreement(a: list[str], b: list[str]) -> float | None:
    """Fraction of comparable items where the two raters give the same level.

    Returns ``None`` when there are no comparable (non-N/A) item pairs.
    """
    pairs = comparable_pairs(a, b)
    if not pairs:
        return None
    return sum(1 for i, j in pairs if i == j) / len(pairs)


def _kappa_from_pairs(pairs: list[tuple[int, int]], scheme: str | None) -> float | None:
    """Weighted kappa from a list of ordinal index pairs."""
    n = len(pairs)
    if n == 0:
        return None

    # observed joint distribution + marginals
    observed = [[0.0] * _K for _ in range(_K)]
    row = [0.0] * _K
    col = [0.0] * _K
    for i, j in pairs:
        observed[i][j] += 1.0 / n
        row[i] += 1.0 / n
        col[j] += 1.0 / n

    numer = 0.0
    denom = 0.0
    for i in range(_K):
        for j in range(_K):
            w = _weight(i, j, scheme)
            numer += w * observed[i][j]
            denom += w * row[i] * col[j]

    if denom == 0.0:
        # No expected disagreement -> both raters concentrated on one level.
        # That can only happen when observed disagreement is also 0, i.e.
        # perfect agreement. Report 1.0 rather than 0/0.
        return 1.0 if numer == 0.0 else 0.0
    return 1.0 - numer / denom


def cohen_kappa(a: list[str], b: list[str], weights: str | None = None) -> float | None:
    """Cohen's kappa between two raters' label lists.

    ``weights``: ``None``/``"nominal"`` for unweighted Cohen's kappa,
    ``"linear"`` or ``"quadratic"`` for ordinal weighting. Returns ``None``
    when there are no comparable item pairs.
    """
    return _kappa_from_pairs(comparable_pairs(a, b), weights)


def bootstrap_kappa_ci(
    a: list[str],
    b: list[str],
    weights: str | None = None,
    n_boot: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> tuple[float, float] | None:
    """Percentile bootstrap confidence interval for kappa.

    Resamples the comparable item pairs with replacement ``n_boot`` times.
    Deterministic for a given ``seed`` so reports are reproducible. Returns
    ``None`` if there are fewer than two comparable pairs (a CI is
    meaningless there).
    """
    pairs = comparable_pairs(a, b)
    if len(pairs) < 2:
        return None
    rng = random.Random(seed)
    n = len(pairs)
    estimates: list[float] = []
    for _ in range(n_boot):
        resample = [pairs[rng.randrange(n)] for _ in range(n)]
        k = _kappa_from_pairs(resample, weights)
        if k is not None:
            estimates.append(k)
    if not estimates:
        return None
    estimates.sort()
    lo_q = (1.0 - confidence) / 2.0
    hi_q = 1.0 - lo_q
    return (_percentile(estimates, lo_q), _percentile(estimates, hi_q))


def _percentile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolation percentile of an already-sorted list."""
    if not sorted_vals:
        raise ValueError("empty list")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def mean_pairwise_kappa(
    runs: list[list[str]], weights: str | None = None
) -> dict:
    """Test-retest stability across >=2 label lists from the *same* rater.

    Computes kappa and percent agreement for every unordered pair of runs
    and averages them. Use this for a judge run N times on the same
    transcripts: high mean kappa == stable judge.

    Returns ``{"mean_kappa", "mean_percent_agreement", "pairs": [...],
    "n_runs"}``. ``mean_kappa`` is ``None`` if no pair was computable.
    """
    if len(runs) < 2:
        raise ValueError("need at least two runs for test-retest")
    pair_stats = []
    kappas: list[float] = []
    agreements: list[float] = []
    for x in range(len(runs)):
        for y in range(x + 1, len(runs)):
            k = cohen_kappa(runs[x], runs[y], weights)
            pa = percent_agreement(runs[x], runs[y])
            pair_stats.append({"a": x, "b": y, "kappa": k, "percent_agreement": pa})
            if k is not None:
                kappas.append(k)
            if pa is not None:
                agreements.append(pa)
    return {
        "n_runs": len(runs),
        "mean_kappa": (sum(kappas) / len(kappas)) if kappas else None,
        "mean_percent_agreement": (sum(agreements) / len(agreements)) if agreements else None,
        "pairs": pair_stats,
    }


def interpret_kappa(kappa: float | None) -> str:
    """Landis & Koch (1977) verbal bands for a kappa value.

    Bands are a convention, not gospel -- the report says so. ``None`` maps
    to ``"not computable"``.
    """
    if kappa is None:
        return "not computable"
    if kappa < 0.0:
        return "poor (worse than chance)"
    if kappa < 0.20:
        return "slight"
    if kappa < 0.40:
        return "fair"
    if kappa < 0.60:
        return "moderate"
    if kappa < 0.80:
        return "substantial"
    return "almost perfect"


@dataclass
class AgreementResult:
    """Agreement between two raters on one dimension."""

    n: int
    percent_agreement: float | None
    kappa: float | None
    kappa_linear: float | None
    kappa_ci: tuple[float, float] | None
    band: str = field(default="")

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "percent_agreement": self.percent_agreement,
            "kappa": self.kappa,
            "kappa_linear": self.kappa_linear,
            "kappa_ci": list(self.kappa_ci) if self.kappa_ci else None,
            "band": self.band,
        }


def agreement(
    a: list[str],
    b: list[str],
    n_boot: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> AgreementResult:
    """Full agreement summary between two raters' label lists.

    Reports both nominal Cohen's kappa and linearly-weighted kappa (the
    levels are ordinal), a bootstrap CI on the nominal kappa, and the
    Landis & Koch band.
    """
    pairs = comparable_pairs(a, b)
    k = _kappa_from_pairs(pairs, None)
    return AgreementResult(
        n=len(pairs),
        percent_agreement=(sum(1 for i, j in pairs if i == j) / len(pairs)) if pairs else None,
        kappa=k,
        kappa_linear=_kappa_from_pairs(pairs, "linear"),
        kappa_ci=bootstrap_kappa_ci(a, b, None, n_boot, confidence, seed),
        band=interpret_kappa(k),
    )
