"""Multi-turn behavioral drift suite + judge calibration (v3.3).

This package is the home of the `drift-v0.1` work: a small, hand-labeled
corpus of multi-turn pressure sequences plus the machinery to measure how
reliably an LLM-as-judge labels behavioral drift on that same corpus.

The credibility claim is narrow and honest: drift scores are only worth
citing if the judge that produced them is calibrated, and calibration is
reported on the exact sequences being scored -- never on the single-turn
corpus. See `corpus/drift-v0.1/README.md` and `reports/drift-v0.1-method.md`.

Layout:
- dimensions.py  -- the five drift dimensions + ordinal label space
- schema.py      -- load + validate sequences and gold labels
- runner.py      -- replay a sequence through a model -> per-turn transcript
- judge.py       -- LLM-as-judge labels each assistant turn
- calibration.py -- Cohen's kappa, weighted kappa, bootstrap CI, test-retest
- report.py      -- render the method report markdown
- cli.py         -- `pp run --suite` / `pp calibrate --suite`
"""

SUITE_VERSION = "drift-v0.1"

__all__ = ["SUITE_VERSION"]
