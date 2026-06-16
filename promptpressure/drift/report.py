"""Render a calibration result into the method report markdown.

Output is intentionally plain and honest: tables of kappa with confidence
intervals, what the numbers rest on, and what they do NOT support yet. No
marketing. The credibility comes from publishing the reliability, not from
claiming it.
"""

from __future__ import annotations

from promptpressure.drift.dimensions import DIMENSIONS


def _fmt_k(k: float | None) -> str:
    return "n/a" if k is None else f"{k:.2f}"


def _fmt_ci(ci) -> str:
    if not ci:
        return "-"
    return f"[{ci[0]:.2f}, {ci[1]:.2f}]"


def _dim_title(dim: str) -> str:
    return DIMENSIONS.get(dim, {}).get("title", dim)


def _agreement_table(block: dict) -> str:
    """Render a per-dimension + overall agreement block as a markdown table."""
    lines = [
        "| dimension | n | % agree | kappa | 95% CI | linear kappa | band |",
        "|---|---|---|---|---|---|---|",
    ]
    per_dim = block.get("per_dimension", {})
    for dim, d in per_dim.items():
        pa = "-" if d["percent_agreement"] is None else f"{d['percent_agreement']*100:.0f}%"
        lines.append(
            f"| {_dim_title(dim)} | {d['n']} | {pa} | {_fmt_k(d['kappa'])} | "
            f"{_fmt_ci(d['kappa_ci'])} | {_fmt_k(d['kappa_linear'])} | {d['band']} |"
        )
    overall = block.get("overall")
    if overall:
        pa = "-" if overall["percent_agreement"] is None else f"{overall['percent_agreement']*100:.0f}%"
        lines.append(
            f"| **pooled** | {overall['n']} | {pa} | **{_fmt_k(overall['kappa'])}** | "
            f"{_fmt_ci(overall['kappa_ci'])} | {_fmt_k(overall['kappa_linear'])} | {overall['band']} |"
        )
    return "\n".join(lines)


def _test_retest_table(block: dict) -> str:
    lines = [
        "| dimension | mean pairwise kappa | mean % agree |",
        "|---|---|---|",
    ]
    for dim, d in block.get("per_dimension", {}).items():
        pa = "-" if d.get("mean_percent_agreement") is None else f"{d['mean_percent_agreement']*100:.0f}%"
        lines.append(f"| {_dim_title(dim)} | {_fmt_k(d.get('mean_kappa'))} | {pa} |")
    overall = block.get("overall")
    if overall:
        pa = "-" if overall.get("mean_percent_agreement") is None else f"{overall['mean_percent_agreement']*100:.0f}%"
        lines.append(f"| **pooled** | **{_fmt_k(overall.get('mean_kappa'))}** | {pa} |")
    return "\n".join(lines)


def render_method_report(result: dict, model_under_test: str = "(reference transcript)", generated: str = "") -> str:
    """Render the full method report markdown for a calibration result."""
    cov = result["coverage"]
    jvh = result["judge_vs_human"]
    tr = result.get("test_retest", {})

    cats = cov["categories"]
    cat_lines = "\n".join(
        f"- {c}: {', '.join(ids)} ({len(ids)} sequences)" for c, ids in cats.items()
    )

    parts = [
        f"# {result['suite']} method + judge calibration",
        "",
        "this is a pilot. the point is not a big benchmark, it's a small corpus of "
        "multi-turn pressure sequences plus an honest measurement of how reliably the "
        "model-as-judge labels drift on that same corpus. drift scores are only worth "
        "citing if the judge that produced them is calibrated, and the calibration is "
        "reported here on the exact sequences being scored, never on the single-turn corpus.",
        "",
        "## what's in the corpus",
        "",
        f"- {cov['sequences_total']} multi-turn sequences across 3 categories",
        f"- {cov['sequences_with_gold']} have gold (human-reference) per-turn labels",
        f"- {cov['labeled_assistant_turns']} labeled assistant turns total",
        "",
        cat_lines,
        "",
        "each assistant turn is labeled on its in-scope dimensions using an ordinal "
        "scale: `hold` (0), `partial` (1), `drift` (2). dimensions not in scope for a "
        "sequence are `n/a` and excluded pairwise from every agreement number.",
        "",
        "the five dimensions:",
        "",
    ]
    for key, spec in DIMENSIONS.items():
        parts.append(f"- **{spec['title']}** (`{key}`): {spec['definition']}")
    parts += [
        "",
        f"## judge-vs-human agreement (judge: {result['judge']})",
        "",
        "headline calibration: does the judge agree with the gold labels? kappa is "
        "chance-corrected (Cohen's). the linear-weighted kappa partially forgives "
        "adjacent disagreements (hold-vs-partial), since the levels are ordinal. CIs are "
        "percentile bootstrap over the comparable turn pairs.",
        "",
        _agreement_table(jvh),
        "",
        f"transcripts under test: {model_under_test}.",
        "",
    ]

    if tr and tr.get("n_runs", 0) >= 2:
        temp = result.get("judge_temperature")
        temp_note = f" at temperature {temp}" if temp is not None else ""
        parts += [
            f"## test-retest stability ({tr['n_runs']} judge runs{temp_note})",
            "",
            "same judge, same transcripts, run multiple times. high agreement here means "
            "the judge is stable; low means its labels are a coin flip and the scores "
            "above are noise."
            + (" at temperature 0 a well-behaved judge is near-deterministic, so read this "
               "alongside the temperature." if temp == 0 else ""),
            "",
            _test_retest_table(tr),
            "",
        ]

    if result.get("judge_vs_judge"):
        parts += [
            f"## judge-vs-judge agreement ({result['judge']} vs {result.get('judge_b','judge-B')})",
            "",
            "two different judge models labeling the same transcripts. agreement here "
            "means the labeling isn't an artifact of one model's quirks.",
            "",
            _agreement_table(result["judge_vs_judge"]),
            "",
        ]

    parse_failures = cov.get("judge_parse_failures", 0)
    parts += [
        "## what these numbers do and don't support",
        "",
        "- the gold labels are pilot **reference** annotations by the corpus author, not "
        "a multi-annotator human panel. judge-vs-human here means judge-vs-author. real "
        "inter-human agreement is the next step before any strong reliability claim.",
        f"- N is small: {cov['labeled_assistant_turns']} labeled turns across "
        f"{cov['sequences_with_gold']} sequences. the bootstrap CIs are wide on purpose - "
        "read the interval, not the point estimate.",
        f"- judge parse failures this run: {parse_failures} (turns the judge didn't return "
        "a usable label for; counted as n/a, never as agreement).",
        "- kappa bands (slight/fair/moderate/substantial) are the Landis & Koch convention, "
        "not a law of nature.",
        "",
        "## the honest claim",
        "",
        "drift-v0.1 is a citable **pilot method** for multi-turn behavioral drift, with "
        "judge reliability reported on the same corpus the scores come from. that's the "
        "part promptfoo, Inspect, and lm-eval-harness don't publish. it is not yet a "
        "validated benchmark, and this report says so in numbers.",
    ]
    if generated:
        parts += ["", f"_generated: {generated}_"]
    return "\n".join(parts) + "\n"
