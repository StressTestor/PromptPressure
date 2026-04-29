# PromptPressure 3-way comparison — 2026-04-28

**Eval set:** `evals_dataset.json` · **Tier:** full · **Total sequences:** 200 (35 multi-turn = 245 turns) per model · **Provider:** OpenRouter

| metric | V4 Pro | V4 Flash | Laguna M.1 (free) |
|---|---:|---:|---:|
| model id | `deepseek/deepseek-v4-pro` | `deepseek/deepseek-v4-flash` | `poolside/laguna-m.1:free` |
| pricing | $0.435/M prompt + $0.87/M completion | $0.14/M + $0.28/M | free |
| **success rate** | 99.00% (198/200) | 97.50% (195/200) | **100.00% (200/200)** |
| errors | 2 | 5 | 0 |
| **avg latency / prompt** | 87.07s | 45.57s | **28.25s** |
| **wallclock** | 107.0 min | 54.3 min | **47.1 min** |
| concurrency (max_workers) | 3 | 3 | 2 |
| cumulative response time | 4.79 h | 2.47 h | 1.57 h |
| **response chars (mean)** | 7,763 | 5,078 | 4,649 |
| response chars (max) | 206,020 | 43,992 | 141,060 |
| response chars (total) | 1,552,612 | 1,015,639 | 929,751 |
| words/response (mean) | 1,146 | 797 | 639 |
| total words generated | 229,104 | 159,419 | 127,801 |

## Headline findings

1. **Laguna M.1 (free) won across every reliability + speed metric.** 100% success, fastest wallclock (47min), fastest per-prompt latency (28s). It also generated the *fewest* words per response, which could be a virtue (less filler) or a vice (less thorough) depending on what you're optimizing for. The eval can't tell you which without scoring.
2. **V4 Pro is ~3× slower than Laguna and ~1.5× more verbose.** That's expected for a reasoning model — it spends tokens thinking. The 206K-char outlier response is worth eyeballing — that's roughly a small novel and probably indicates a reasoning loop the model didn't escape cleanly.
3. **V4 Flash had the most errors (5) and longest tail.** All 5 errors were timeouts — Turn 1 (90s), Turn 2 (120s), one Turn 6 (240s). That last one is a genuine multi-turn breakdown at deep context. Flash hit the deepest stalls.
4. **Errors are timeout-only across all three** — none were rate-limit, auth, or content-policy refusals. That's clean OpenRouter behavior; the timeouts come from the eval harness's per-turn cutoff hitting models that just generate slowly on certain prompts.

## Cost estimate (rough)

Token counts aren't in the metrics; using char-counts as a proxy (≈4 chars/token for English):

| | input tokens (est) | output tokens (est) | est cost |
|---|---:|---:|---:|
| V4 Pro | ~390K | ~390K | ~$0.51 |
| V4 Flash | ~390K | ~254K | ~$0.13 |
| Laguna | — | — | $0.00 |

Real cost is whatever OpenRouter's billing dashboard says — these are back-of-envelope.

## Per-error detail

**V4 Pro (2 errors):**
- `Turn 2 timed out after 120s` — prompt about blood being blue inside veins (factual correction prompt, Turn 1 likely answered, Turn 2 followup stalled)
- `Turn 1 timed out after 90s` — prompt about Q3 marketing budget (TikTok ads for B2B SaaS) — model possibly trying to give a long structured answer

**V4 Flash (5 errors):**
- Turn 1 × 90s (×2)
- Turn 2 × 120s (×2)
- Turn 6 × 240s (×1) — multi-turn breakdown deep in context

**Laguna M.1 (0 errors):** all 200 prompts × 245 turns completed within timeout.

## Output dirs

| model | dir |
|---|---|
| V4 Pro | `outputs/2026-04-28_3way-deepseek-laguna/v4-pro/` |
| V4 Flash | `outputs/2026-04-28_3way-deepseek-laguna/v4-flash/` |
| Laguna M.1 | `outputs/2026-04-28_3way-deepseek-laguna/laguna-m1/` |

Each contains: `metrics.json` (run-level), `metrics_report.json` (custom-metrics), `report.html` (long-form), `report.md` (long-form), `eval_*.csv` (full results), `eval_*.json` (full results), `run.jsonl` (per-event log), `error.log` (errors).

## What's NOT in this comparison

The PromptPressure README promises behavioral signals (sycophancy detection, tone consistency, persona stability). Those metrics live in custom plugins and didn't run because no `--post-analyze` flag was passed. The `custom_metrics_results` block here only has `response_length` and `word_count` — the verbosity proxies, not the behavioral signals.

To get the behavioral analysis, re-run with `--post-analyze openrouter` (or another configured analyzer). That would score each response for sycophancy, refusal, tone-drift, etc., using a judge model. Worth doing as a follow-up since the raw responses are already in the CSVs — no need to re-evaluate, just re-score.

## Verdict

For pure throughput on this dataset, **Laguna M.1 is the surprise winner** — fastest, most reliable, free. Whether its shorter responses are better or worse depends on whether you want depth (Pro) or efficiency (Laguna) for your eval workload.

If you wanted reasoning quality, Pro's 87s/prompt and verbose answers suggest it's doing actual thinking work. The 206K-char outlier is the most interesting datum — drop into the CSV to see what prompt triggered it.
