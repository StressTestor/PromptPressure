# PromptPressure

PromptPressure is an evaluation suite for Large Language Models (LLMs) designed to test their responses under various pressure scenarios. The framework allows you to evaluate different models using customizable prompts and adapters for various API providers.

## Features

- Multi-model evaluation support
- Adapters for Groq, OpenAI, LM Studio, and mock providers
- Configurable evaluation scenarios
- Post-analysis scoring with customizable rubrics
- Secure handling of API keys via environment variables
- Comprehensive error logging and reporting

## Installation

1. Clone the repository
2. Install the required dependencies:

```bash
pip install -r requirements.txt
```

## Setup

1. Copy the `.env.example` file to `.env`:

```bash
cp .env.example .env
```

2. Edit the `.env` file and add your API keys:

```env
# GroqCloud
GROQ_API_KEY=your_groq_api_key_here

# OpenAI
OPENAI_API_KEY=your_openai_api_key_here

# OpenRouter
OPENROUTER_API_KEY=your_openrouter_api_key_here
```

## Usage

Run evaluations with one or more configuration files:

```bash
python run_eval.py --multi-config config_lmstudio.yaml config_openchat.yaml
```

### Configuration Files

Create YAML configuration files for each model you want to evaluate. Example:

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

- **LM Studio**: For locally hosted models
- **OpenAI**: For OpenAI API models
- **Groq**: For Groq API models
- **OpenRouter**: For OpenRouter API models (provides access to 100+ models from multiple providers)
- **Mock**: For testing purposes

## Post-Analysis

After running evaluations, the framework can perform post-analysis using either Groq or OpenAI APIs to score the responses based on predefined criteria.

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
