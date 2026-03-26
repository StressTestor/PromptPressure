# configuration

configs are YAML files in `configs/`. pass one or more to the CLI with `--multi-config`.

## core settings

| setting | type | required | what it does |
|---------|------|----------|--------------|
| `adapter` | string | yes | which adapter to use: `openrouter`, `groq`, `ollama`, `lmstudio`, `mock`, `claude-code`, `opencode-zen`, `deepseek-r1` |
| `model` | string | yes | model identifier for the provider API |
| `model_name` | string | yes | display name for reports |
| `dataset` | string | yes | path to the eval dataset JSON |
| `output` | string | yes | filename for raw CSV output |
| `output_dir` | string | no | directory for outputs (default: `outputs`) |
| `temperature` | float | no | sampling temperature, 0.0-2.0 (default: 0.7) |
| `is_simulation` | bool | no | flag simulation runs (default: false) |

## performance

| setting | type | required | what it does |
|---------|------|----------|--------------|
| `max_workers` | int | no | concurrent eval threads, 1-10 (default: 1) |
| `timeout` | int | no | per-prompt timeout in seconds (default: 120) |

## metrics and reporting

| setting | type | required | what it does |
|---------|------|----------|--------------|
| `collect_metrics` | bool | no | enable metrics collection (default: true) |
| `custom_metrics` | list | no | custom metric names to calculate |
| `report_formats` | list | no | `html`, `markdown`, or both (default: both) |
| `report_template_dir` | string | no | custom Jinja2 template directory |

## api keys

set these in `.env` (gitignored). don't put keys in config files you commit.

- `GROQ_API_KEY`
- `OPENROUTER_API_KEY`
- `OPENAI_API_KEY`

CLI adapters (claude-code, opencode-zen) don't need API keys.

## example

```yaml
adapter: openrouter
model: x-ai/grok-4.20-beta
model_name: Grok 4.20 Beta
dataset: evals_dataset.json
output: results.csv
output_dir: outputs_grok
temperature: 0.7
max_workers: 3
timeout: 180
collect_metrics: true
```
