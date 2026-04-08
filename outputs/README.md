# outputs/

eval run artifacts. everything here is part of the public reproducibility record.

## directory schema

### top-level files

| file | what it is |
|------|-----------|
| `aggregated_metrics.json` | cross-model aggregated scores from the most recent comparison run |
| `metrics_report.json` | summary metrics (pass rates, category breakdowns) for the latest run |
| `report.html` | rendered HTML report with charts and per-prompt detail |
| `report.md` | markdown version of the same report |

these four files get overwritten on every run. they reflect the last eval executed, not a cumulative history.

### timestamped run directories

format: `YYYY-MM-DD_HH-MM-SS/`

each directory contains the full output of a single eval run:

| file | what it is |
|------|-----------|
| `eval_<model>.json` | per-prompt results (prompt, response, latency, success, metadata) |
| `eval_<model>.csv` | same data in CSV for quick inspection |
| `metrics.json` | aggregated metrics for this specific run |
| `run.jsonl` | structured request log (model, latency, cost, retries, errors per request) |
| `cost.json` | token usage and cost tracking for the run |
| `error.log` | any errors encountered during the run |

not every run produces every file. `run.jsonl` and `cost.json` were added in v3.1.0.

### per-model result directories

directories like `outputs_grok420/` or `outputs_mimo_omni/` follow the same schema but were generated in isolated runs targeting a specific model. the naming convention is `outputs_<model_shortname>/`.

## naming conventions

- model names in filenames use underscores: `eval_openrouter_haiku.json`
- config names map to filenames: `config_openrouter_haiku.yaml` produces `eval_openrouter_haiku.*`
- timestamps are UTC
