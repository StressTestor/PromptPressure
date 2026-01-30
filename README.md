# PromptPressure

**Stress-test your LLMs before they stress-test you.**

An evaluation framework that puts language models through structured scenarios and gives you data on how they actually behave. Prompts in, metrics out.

---

## What It Does

- **Multi-model evaluation**: Run the same prompts against OpenRouter, Groq, Ollama, LM Studio simultaneously
- **Automated scoring**: Post-analysis with configurable rubrics grades responses without manual review
- **Desktop app**: Native macOS with bundled Python backend (no server management)
- **Offline mode**: Ollama integration for air-gapped or privacy-conscious environments
- **Reports**: Auto-generated HTML and Markdown after each run

---

## Quick Start

```bash
git clone https://github.com/StressTestor/PromptPressure.git
cd PromptPressure
pip install -r requirements.txt

cp .env.example .env
# Add your API keys: GROQ_API_KEY, OPENROUTER_API_KEY

python -m promptpressure.cli --multi-config configs/config_openrouter_gpt_oss_20b_free.yaml
```

Results land in `outputs/<timestamp>/` with CSVs, metrics, and reports.

---

## Adapters

| Adapter | Type | Description |
|---------|------|-------------|
| **OpenRouter** | Cloud | 100+ models via single API |
| **Groq** | Cloud | Fast inference |
| **Ollama** | Local | Self-hosted, data stays on-machine |
| **LM Studio** | Local | GUI-based local inference |
| **Mock** | Test | Synthetic responses for CI |

Switch adapters with one line in your config YAML.

### Custom Adapters

Add support for any LLM API by creating an adapter class:

```python
# promptpressure/adapters/your_adapter.py
class YourAdapter:
    def __init__(self, config: dict):
        self.endpoint = config.get("your_endpoint", "https://api.example.com/v1/chat")
        self.api_key = os.getenv("YOUR_API_KEY")
    
    def generate(self, prompt: str, system_prompt: str = None) -> str:
        # Make API call, return response text
        response = httpx.post(self.endpoint, json={...}, headers={...})
        return response.json()["choices"][0]["message"]["content"]
```

Register it in `promptpressure/adapters/__init__.py`:
```python
from .your_adapter import YourAdapter
ADAPTERS["youradapter"] = YourAdapter
```

Use in config:
```yaml
adapter: youradapter
model: your-model-id
your_endpoint: https://api.example.com/v1/chat
```

The config dict passes through to `__init__`, so define any custom keys you need.

---

## Desktop App (v2.6)

Tauri-based native app bundles everything:
- Next.js dashboard with dark theme
- Python backend (PyInstaller sidecar, 22MB)
- Local model management via Ollama

```bash
cd desktop
npm install
npm run tauri build
```

Self-contained `.app` and `.dmg` output. No external dependencies.

---

## Configuration

Configs live in `configs/`:

```yaml
adapter: openrouter
model: openai/gpt-oss-20b:free
dataset: evals_dataset.json
output_dir: outputs
temperature: 0.7
max_workers: 5
use_timestamp_output_dir: true
```

Run multiple configs:
```bash
python -m promptpressure.cli --multi-config configs/a.yaml configs/b.yaml
```

---

## Post-Analysis

Score responses automatically after evaluation:

```bash
python -m promptpressure.cli --multi-config configs/config.yaml --post-analyze openrouter
```

Override the scoring model:
```yaml
scoring_model_name: anthropic/claude-3-haiku
```

---

## Metrics

Captured per run:
- Response latency (p50, p90, p99)
- Error rates per model
- Token counts
- Custom metrics

```yaml
collect_metrics: true
custom_metrics:
  - "response_length"
  - "word_count"
```

Register custom scorers:
```python
from promptpressure.metrics import get_metrics_analyzer
analyzer = get_metrics_analyzer()
analyzer.register_metric_function("toxicity", your_scorer)
```

---

## Security

- API keys in `.env` (gitignored)
- Desktop mode binds to `127.0.0.1` only
- Ollama keeps everything local
- Audit logs (v2.4+)
- No telemetry

---

## Roadmap

- [x] Multi-adapter support
- [x] Automated post-analysis
- [x] Desktop app with bundled backend
- [x] Dark mode UI
- [ ] Local model manager UI
- [ ] Windows/Linux builds
- [ ] Plugin marketplace

Full roadmap: [roadmap.md](roadmap.md)

---

## Contributing

1. Tests pass: `pytest tests/`
2. No unnecessary dependencies
3. Document changes

Bugs → Issues. Features → Discussions.

---

## License

MIT. See [LICENSE](LICENSE).
