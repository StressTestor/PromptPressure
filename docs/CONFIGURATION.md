# Configuration Guide

PromptPressure uses a flexible configuration system based on YAML files and environment variables.

## Core Settings

| Setting | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `adapter` | string | Yes | The adapter to use: `groq`, `openrouter`, `lmstudio`, `mock`. |
| `model` | string | Yes | The model identifier used by the provider API. |
| `model_name` | string | Yes | A human-readable display name for the model in reports. |
| `dataset` | string | Yes | Path to the evaluation dataset (JSON). |
| `output` | string | Yes | Filename for the raw CSV output. |
| `output_dir` | string | No | Directory to save outputs (default: `outputs`). |
| `temperature` | float | No | Sampling temperature (0.0 - 2.0, default: 0.7). |
| `is_simulation` | bool | No | Set to `true` to flag simulation runs (default: `false`). |

## Performance Settings

| Setting | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `max_workers` | int | No | Number of concurrent threads for execution (1-10, default: 1). |

## Metrics & Reporting

| Setting | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `collect_metrics` | bool | No | Enable detailed metrics collection (default: `true`). |
| `custom_metrics` | list[str] | No | List of custom metrics to calculate. |
| `report_formats` | list[str] | No | Formats to generate: `html`, `markdown` (default: both). |
| `report_template_dir` | string | No | Directory for custom Jinja2 templates (default: `templates`). |

## API Keys

API keys must be set as environment variables (in `.env`) or explicitly in the config (not recommended for sharing).

- **Groq**: `GROQ_API_KEY`
- **OpenRouter**: `OPENROUTER_API_KEY`

## Example Config

```yaml
adapter: openrouter
model: anthropic/claude-3-opus
model_name: Claude 3 Opus
dataset: evals_dataset.json
output: claude_opus_eval.csv
temperature: 0.7
max_workers: 5
collect_metrics: true
report_formats: 
  - html
  - markdown
```
