# PromptPressure

**Stress-test your LLMs before they stress-test you.**

PromptPressure is an evaluation framework that puts language models through their paces. You give it prompts, it gives you data. No hand-waving about "alignment"—just cold metrics on how models actually behave under pressure.

Built because I got tired of trusting vibes over verification.

---

## The Pitch (30 seconds)

Most people eyeball LLM outputs and call it QA. That's not evaluation—that's hope.

PromptPressure runs structured scenarios across multiple models simultaneously, scores responses with configurable rubrics, and spits out reports you can actually use. You get:

- **Multi-model head-to-head**: Test OpenRouter, Groq, Ollama, LM Studio, whatever. Same prompts, different brains.
- **Automated scoring**: Post-analysis with another LLM grades the responses. No manual review grinding.
- **Desktop app**: Native macOS with bundled Python backend. No server to babysit.
- **Offline mode**: Ollama integration for when you don't want your queries leaving the building.

It's an evaluation suite that respects your time and doesn't require a DevOps team.

---

## Quick Start

```bash
# Clone it
git clone https://github.com/StressTestor/PromptPressure.git
cd PromptPressure

# Install deps
pip install -r requirements.txt

# Set your keys
cp .env.example .env
# Edit .env with your API keys (GROQ_API_KEY, OPENROUTER_API_KEY, etc.)

# Run an eval
python -m promptpressure.cli --multi-config configs/config_openrouter_gpt_oss_20b_free.yaml
```

That's it. Output lands in `outputs/<timestamp>/` with CSVs, metrics, and human-readable reports.

---

## Adapters

Plug in whatever inference source you've got lying around:

| Adapter | Type | Notes |
|---------|------|-------|
| **OpenRouter** | Cloud | 100+ models, one API. Default for broad coverage. |
| **Groq** | Cloud | Fast inference, limited model selection. |
| **Ollama** | Local | Self-hosted. Your data stays on your machine. |
| **LM Studio** | Local | GUI for local models, works if you've got the VRAM. |
| **Mock** | Test | Fake responses for integration testing. |

Switch adapters by changing one line in your YAML. The framework handles the rest.

---

## Desktop App (v2.6)

Because running Python from Terminal is fine until it isn't.

The Tauri-based desktop app bundles everything:
- Next.js dashboard (dark mode, because we live in dark mode)
- Python backend (PyInstaller sidecar, 22MB)
- Local model management (Ollama integration)

**Build it yourself:**
```bash
cd desktop
npm install
npm run tauri build
```

Outputs a `.app` and `.dmg` in `src-tauri/target/release/bundle/`. Self-contained. No brew install, no pip install, no prayers.

---

## Configuration

YAML configs live in `configs/`. Here's the anatomy:

```yaml
adapter: openrouter                    # Which inference source
model: openai/gpt-oss-20b:free         # Model identifier
dataset: evals_dataset.json            # Your test prompts
output_dir: outputs                    # Where results land
temperature: 0.7                       # Creativity dial
max_workers: 5                         # Parallel threads (1-10)
use_timestamp_output_dir: true         # Organize by run time
```

Run multiple configs in one go:
```bash
python -m promptpressure.cli --multi-config configs/config_a.yaml configs/config_b.yaml
```

Results from each config land in the same timestamped folder. Compare at will.

---

## Post-Analysis

After evals run, PromptPressure can score responses automatically:

```bash
python -m promptpressure.cli --multi-config configs/config.yaml --post-analyze openrouter
```

A scoring model reads the responses and grades them against your rubric. You get numbers instead of feelings.

**Override the scorer:**
```yaml
scoring_model_name: anthropic/claude-3-haiku  # Or whatever you trust
```

---

## Metrics

Every run captures:
- Response latency (p50, p90, p99)
- Error rates per model
- Token counts
- Custom metrics you define

```yaml
collect_metrics: true
custom_metrics:
  - "response_length"
  - "word_count"
```

Register your own scorers:
```python
from promptpressure.metrics import get_metrics_analyzer

analyzer = get_metrics_analyzer()
analyzer.register_metric_function("toxicity", your_toxicity_scorer)
```

All metrics dump to `metrics.json` per run. Aggregate across runs for trends.

---

## Reports

Auto-generated after each eval:
- `report.html` — Formatted, shareable
- `report.md` — Grep-friendly

Customize templates by pointing `report_template_dir` to your own.

---

## Security

- API keys live in `.env` (gitignored by default)
- Desktop mode binds to `127.0.0.1` only
- Ollama/local adapters keep everything on-box
- Audit logs track who ran what (v2.4+)

No telemetry. Your evals are your business.

---

## Roadmap

Active development. Current priorities:

- [x] Multi-adapter support (OpenRouter, Groq, Ollama, LM Studio)
- [x] Automated post-analysis scoring
- [x] Desktop app with bundled backend
- [x] Dark mode UI (black/grey theme)
- [ ] Local model manager UI
- [ ] Windows/Linux builds
- [ ] Plugin marketplace

See [roadmap.md](roadmap.md) for the full picture.

---

## Contributing

PRs welcome. Keep these in mind:
1. Tests pass (`pytest tests/`)
2. No new dependencies without a good reason
3. Document what you change

File issues for bugs. Feature requests go in Discussions.

---

## License

MIT. Do what you want. See [LICENSE](LICENSE).

---

*Built by someone who got tired of asking "but does it actually work?" and decided to find out systematically.*
