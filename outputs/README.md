# outputs/

eval run artifacts. everything here is part of the public reproducibility record.

## directory schema

```
outputs/
├── _archive/              ← old timestamped runs, kept for history
│   ├── 2026-03/           ← Mar 2026 runs (8 dirs, real eval data)
│   ├── 2026-04-01/        ← Apr 1 2026 runs (13 dirs, real eval data)
│   └── 2026-04-08/        ← Apr 8 2026 runs
├── YYYY-MM-DD_descriptive-name/   ← current convention, one dir per published run
└── README.md
```

## naming convention going forward

**`YYYY-MM-DD_descriptive-name/`** — descriptive, not timestamp-only.

example: `2026-04-28_3way-deepseek-laguna/` rather than `2026-04-28_17-04-11/`.

names should let you tell at-a-glance what the run was about. timestamp-only dirs go to `_archive/` once they're no longer the active subject.

## what each run dir contains

| file | what it is |
|------|-----------|
| `eval_<model>.json` | per-prompt results (prompt, response, latency, success, metadata) |
| `eval_<model>.csv` | same data in csv |
| `metrics.json` | aggregated metrics for this run |
| `metrics_report.json` | summary metrics (pass rates, category breakdowns) |
| `run.jsonl` | structured request log (model, latency, cost, retries per request) |
| `cost.json` | token usage and cost tracking |
| `error.log` | errors encountered during the run |
| `report.html`, `report.md` | rendered per-run report |
| `analysis/` | judge-output csvs and json from `pp judge` runs |

not every run produces every file. `run.jsonl` and `cost.json` were added in v3.1.0.

## multi-model + multi-judge runs

dirs that compare several models or apply more than one judge organize internally:

```
2026-04-28_3way-deepseek-laguna/
├── FINAL.md, SCORES.md, RESULTS.md  ← writeups
├── scored-aggregate.json            ← per-rubric % across all models (judge A)
├── scored-aggregate-<judge>.json    ← per-rubric % across all models (judge B…)
├── v4-pro/, v4-flash/, laguna-m1/   ← one subdir per model
│   ├── eval_*.{csv,json}, metrics.json, report.{html,md}, run.jsonl
│   └── analysis/
│       ├── openrouter_scores_*.{csv,json}        ← judge A scores
│       └── <judge>_scores_*.{csv,json}           ← judge B scores
```

## naming rules

- model names in filenames use underscores: `eval_openrouter_haiku.json`
- config names map to filenames: `config_openrouter_haiku.yaml` produces `eval_openrouter_haiku.*`
- timestamps are utc
- judge-output prefixes follow the judge model: `openrouter_scores_*`, `sonnet46_scores_*`, etc.

## what does *not* go here

- root-level aggregated metrics or reports (those used to live here as `outputs/aggregated_metrics.json` etc, but they got overwritten on every run and were misleading — removed 2026-04-30)
- launcher smoke tests (delete or never commit)
- empty / error-only run dirs (delete; they're not data)
