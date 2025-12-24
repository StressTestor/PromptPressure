# PromptPressure

PromptPressure is an evaluation suite for Large Language Models (LLMs) designed to test their responses under various pressure scenarios. The framework allows you to evaluate different models using customizable prompts and adapters for various API providers.

## Features

- Multi-model evaluation support
- Adapters for OpenRouter, Groq, LM Studio (optional), and mock providers
- Configurable evaluation scenarios
- Post-analysis scoring with customizable rubrics
- Secure handling of API keys via environment variables
- Comprehensive error logging and reporting
- **New in v1.6**: Automated HTML/Markdown reports
- **New in v1.6**: Concurrent prompt execution
- **New in v2.3**: Team Collaboration & Data Export
- **New in v2.4**: Enterprise Audit Logs & SSO Support
- **New in v2.5**: System Diagnostics & Onboarding Tour

## Installation

1. Clone the repository
1. Install the required dependencies:

```bash
pip install -r requirements.txt
```

## Setup

1. Copy the `.env.example` file to `.env`:

```bash
cp .env.example .env
```

1. Edit the `.env` file and add your API keys:

```env
# GroqCloud
GROQ_API_KEY=your_groq_api_key_here

# OpenRouter
OPENROUTER_API_KEY=your_openrouter_api_key_here
```

## Usage

Run evaluations with one or more configuration files (cloud-first quickstart):

```bash
python run_eval.py --multi-config config_openrouter_gpt_oss_20b_free.yaml config.yaml
```

Or use the one-click batch script for cloud runs (OpenRouter evals + OpenRouter post-analysis + metrics):

```powershell
./run_promptpressure_cloud.bat
```

Notes:

- `config_openrouter_gpt_oss_20b_free.yaml` uses OpenRouter (broad model access).
- `config.yaml` uses Groq (e.g., llama3-70b-8192).
- You can mix and match any cloud configs; LM Studio is fully supported but optional (see below).

For detailed configuration options, see the [Configuration Guide](docs/CONFIGURATION.md).

### Configuration Files

Create YAML configuration files for each model you want to evaluate.

Cloud example (OpenRouter):

```yaml
adapter: openrouter
model: openai/gpt-oss-20b:free
model_name: openai/gpt-oss-20b:free
dataset: evals_dataset.json
output: eval_scores_output_openrouter_gpt_oss_20b_free.csv
output_dir: outputs
openrouter_endpoint: https://openrouter.ai/api/v1/chat/completions
temperature: 0.7
use_timestamp_output_dir: true
# Performance
max_workers: 5
```

Optional: Local models (LM Studio)

```yaml
adapter: lmstudio
model: qwen/qwen3-8b
model_name: qwen/qwen3-8b
is_simulation: false
dataset: evals_dataset.json
output: eval_scores_output_qwen3_8b.csv
output_dir: outputs
lmstudio_endpoint: http://127.0.0.1:1234/v1/chat/completions
temperature: 0.7
use_timestamp_output_dir: true
```

## Security

API keys are securely managed through environment variables and are never hardcoded in configuration files. The `.env` file is automatically excluded from version control via `.gitignore`.

## Adapters

The framework supports multiple adapters:

- **OpenRouter**: Cloud; access to 100+ models (recommended quickstart)
- **Groq**: Cloud
- **LM Studio (optional)**: Local models
- **Mock**: For testing purposes

## Post-Analysis

After running evaluations, the framework can perform post-analysis using OpenRouter (default) or Groq to score responses:

- Default when running multiple configs: OpenRouter scoring (model: `openai/gpt-oss-20b:free`).
- Override with CLI flags:
  - `--post-analyze openrouter` for OpenRouter scoring
  - `--post-analyze groq` for Groq scoring
  
You can also override the scoring model by setting `scoring_model_name` in the last config passed to `--multi-config`.

## Automated Reports

PromptPressure now generates human-readable reports (HTML and Markdown) automatically after each run.

- **HTML Report**: `outputs/<timestamp>/report.html`
- **Markdown Report**: `outputs/<timestamp>/report.md`

You can customize the templates by pointing `report_template_dir` in your config to a directory containing `report_default.html` and `report_default.md`.

## Performance

To speed up evaluations, you can enable concurrent execution by setting `max_workers` in your configuration:

```yaml
max_workers: 5  # Recommended: 1-10
```

This uses a thread pool to process prompts in parallel.

## Metrics Collection

PromptPressure now includes an enhanced metrics collection system that automatically tracks:

- Response times
- Error rates
- Custom metrics (response length, word count, etc.)
- Aggregated performance statistics

Metrics are automatically collected during evaluation runs and saved to `metrics.json` in each output directory. When running multiple configurations, an aggregated metrics report is also generated.

### Configuration

To enable metrics collection, add the following to your configuration file:

```yaml
# Enable/disable metrics collection (default: true)
collect_metrics: true

# Custom metrics to collect (default: empty)
custom_metrics:
  - "response_length"
  - "word_count"
```

### Custom Metrics

You can register custom metrics functions in your evaluation code:

```python
from metrics import get_metrics_analyzer

# Register a custom metric function
analyzer = get_metrics_analyzer()
analyzer.register_metric_function("sentiment_score", your_sentiment_function)
```

Custom metrics are automatically calculated and included in the metrics report.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
