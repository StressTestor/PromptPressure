# PromptPressure

[![CI](https://github.com/StressTestor/PromptPressure/actions/workflows/ci.yml/badge.svg)](https://github.com/StressTestor/PromptPressure/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)

multi-turn behavioral drift detection for LLMs. the things benchmarks don't test.

most eval frameworks measure accuracy on known-answer datasets. PromptPressure measures how models *behave* over sustained interaction. does the model's tone drift at turn 8? does it cave to sycophancy after 3 rounds of pressure? does persona stability degrade as context fills up?

190 active prompts across 11 behavioral categories, tiered for CI speed. run against any model. get a per-turn behavioral report.

---

## quick start in 60 seconds

```bash
git clone https://github.com/StressTestor/PromptPressure.git
cd PromptPressure
pip install -e .

cp .env.example .env
# add your API keys (see .env.example for which adapters need what)

promptpressure --quick --multi-config configs/config_mock.yaml
```

`--quick` runs 3 sequences (~18 turns) in under 10 minutes. results land in `outputs/<timestamp>/` with CSVs, metrics JSON, and an HTML report.

for a real eval against a cloud model:
```bash
promptpressure --tier full --multi-config configs/config_openrouter_gpt_oss_20b_free.yaml
```

---

## what it evaluates

| category | count | what it tests |
|----------|-------|---------------|
| sycophancy detection | 25 | wrong premises, answer changes when challenged, multi-turn pressure sequences |
| instruction following under conflict | 25 | contradictory instructions, system vs user prompt conflicts |
| tone consistency | 20 | same request in formal/casual/hostile/pleading. does helpfulness change? |
| psychological reasoning | 25 | theory of mind, emotional inference, manipulation detection |
| model drift detection | 20 | calibration questions with known answers, knowledge cutoff awareness |
| persona stability | 15 | system prompt adherence under adversarial messages |
| output format compliance | 15 | JSON output, structured extraction, word count constraints |
| multilingual consistency | 15 | same eval in EN/ES/ZH/AR. does behavior change across languages? |
| context window stress | 15 | long-context faithfulness, needle-in-haystack, buried instructions |

190 active prompts. 30 adversarial refusal sensitivity prompts [archived separately](#archived-adversarial-suite). each prompt has expected behavior, grading criteria, and tier/difficulty tags.

---

## how it compares

| feature | PromptPressure | promptfoo | Inspect | lm-eval-harness |
|---------|---------------|-----------|---------|-----------------|
| refusal sensitivity gradient | yes | no | no | no |
| tone-dependent behavior testing | yes | no | no | no |
| sycophancy detection | yes | no | no | no |
| persona stability testing | yes | no | no | no |
| psychological reasoning evals | yes | no | no | no |
| multilingual behavior consistency | yes | partial | no | partial |
| accuracy benchmarks | no | yes | yes | yes |
| custom eval datasets | yes | yes | yes | yes |
| multi-model comparison | yes | yes | yes | yes |
| built-in grading pipeline | yes | yes | yes | no |

PromptPressure is not trying to replace accuracy benchmarks. it tests the behavioral layer that accuracy benchmarks miss.

---

## run tiers

every eval entry is tagged with a tier. tiers are cumulative: `--tier quick` runs both smoke and quick entries.

| tier | entries | turns | time (fast models) | use case |
|------|---------|-------|--------------------|----------|
| `smoke` | 0* | ~0 | <60s | CI gate (sequences coming in v3.2) |
| `quick` | 3 | ~18 | <10 min | local dev, default |
| `full` | 190 | ~500+ | ~1 hr | pre-release |
| `deep` | 190 | ~500+ | 2+ hrs | quarterly audit (20-turn sequences coming in v3.2) |

*smoke and deep tier sequences are planned for v3.2 when multi-turn content is generated.

```bash
promptpressure --quick --multi-config config.yaml       # 3 sequences, fast
promptpressure --tier full --multi-config config.yaml    # all 190 sequences
promptpressure --smoke --multi-config config.yaml        # CI mode (needs smoke-tagged entries)
```

the default tier is `quick`. entries without a tier field default to `full`.

---

## per-turn metrics

multi-turn sequences automatically compute behavioral metrics after each turn:

- **response_length_ratio**: `len(response) / len(user_message)`. detects terse/verbose drift across turns. a model that starts with detailed responses and shrinks to one-liners is drifting.

metrics are attached to each turn in the JSON output under `turn_responses[].metrics` and aggregated at `result_data.per_turn_metrics`.

---

## archived adversarial suite

30 refusal sensitivity prompts are archived separately at `archive/adversarial/refusal_sensitivity.json`. these test how models handle requests that could be interpreted as harmful but are actually benign (academic research, creative writing, historical analysis).

archived because hosted API providers may flag or rate-limit accounts running adversarial-adjacent prompts at scale.

run them explicitly:
```bash
promptpressure --dataset archive/adversarial/refusal_sensitivity.json --multi-config config.yaml
```

---

## adapters

| adapter | type | what you need |
|---------|------|---------------|
| **Claude Code** | CLI | claude CLI installed (subscription) |
| **OpenCode Zen** | CLI | opencode CLI installed (subscription) |
| OpenRouter | cloud | `OPENROUTER_API_KEY` |
| Groq | cloud | `GROQ_API_KEY` |
| OpenAI | cloud | `OPENAI_API_KEY` |
| Ollama | local | ollama running on localhost |
| LM Studio | local | LM Studio running on localhost |
| Mock | test | nothing. synthetic responses for CI |

switch adapters with one line in your config YAML:
```yaml
adapter: openrouter
model_name: openai/gpt-oss-20b:free
```

### custom adapters

adapters are async functions. add one by creating a file in `promptpressure/adapters/`:

```python
# promptpressure/adapters/your_adapter.py
import httpx

async def generate_response(prompt: str, model_name: str = "your-model", config: dict = None) -> str:
    api_key = config.get("your_api_key") if config else None
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.example.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model_name, "messages": [{"role": "user", "content": prompt}]}
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
```

register it in `promptpressure/adapters/__init__.py`:
```python
from .your_adapter import generate_response as your_generate_response

# in load_adapter():
if name_lower == "your_adapter":
    return lambda text, config: your_generate_response(text, config.get("model_name"), config)
```

### zero-cost adapters

Claude Code and OpenCode run through their respective CLI tools. no API keys, no per-token costs. if you have a subscription, the eval runs are free.

**Claude Code** uses `claude -p` in non-interactive mode. supports `--continue` for multi-turn sycophancy sequences and `--model` for model selection.

```bash
promptpressure --multi-config configs/config_claude_code.yaml
```

```yaml
adapter: claude-code
model: sonnet
```

**OpenCode Zen** uses `opencode run` in non-interactive mode. auto-selects the best model via Zen for each prompt.

```bash
promptpressure --multi-config configs/config_opencode_zen.yaml
```

```yaml
adapter: opencode-zen
```

both adapters check if the CLI tool is installed before running and give a clear error with install instructions if not found.

---

## post-analysis (automated grading)

score responses automatically after evaluation:

```bash
promptpressure --multi-config configs/config.yaml --post-analyze openrouter
```

the grading pipeline uses XML boundary tags to prevent the evaluated model's response from influencing its own score (prompt injection defense).

override the scoring model:
```yaml
scoring_model_name: anthropic/claude-3-haiku
```

---

## CI mode

```bash
promptpressure --multi-config configs/config_mock.yaml --ci
```

outputs a machine-readable JSON summary to stdout. exits 0 if all prompts pass, exits 1 on any failure.

```json
{"total": 200, "passed": 200, "failed": 0, "errors": 0, "success": true}
```

---

## CLI reference

```
$ promptpressure --help
usage: promptpressure [-h] [--multi-config MULTI_CONFIG [MULTI_CONFIG ...]]
                      [--post-analyze {groq,openrouter}] [--schema] [--ci]
                      [--tier {smoke,quick,full,deep}] [--smoke] [--quick]
                      {plugins} ...

options:
  --multi-config    YAML config file(s)
  --tier            run tier: smoke, quick, full, deep (default: quick)
  --smoke           shortcut for --tier smoke
  --quick           shortcut for --tier quick
  --post-analyze    post-eval grading via groq or openrouter
  --schema          dump JSON Schema for configuration
  --ci              machine-readable output + exit codes
  plugins list      list available plugins
  plugins install   install a plugin by name
```

---

## configuration

configs live in `configs/`:

```yaml
adapter: openrouter
model: openai/gpt-oss-20b:free
model_name: GPT-OSS 20B
dataset: evals_dataset.json
output: results.csv
output_dir: outputs
temperature: 0.7
tier: quick                    # smoke | quick | full | deep
max_workers: 5
collect_metrics: true
```

run multiple configs in one pass:
```bash
promptpressure --multi-config configs/a.yaml configs/b.yaml
```

---

## project structure

```
promptpressure/
  adapters/           # model connectors (openrouter, groq, ollama, claude code, etc)
  plugins/            # scorer plugin system
  monitoring/         # prometheus metrics + docker-compose
  templates/          # jinja2 report templates (html, markdown)
  api.py              # fastapi server (optional, for programmatic access)
  cli.py              # main eval runner
  config.py           # pydantic settings
  tier.py             # tier filtering (smoke/quick/full/deep)
  per_turn_metrics.py # automated per-turn behavioral metrics
  database.py         # sqlalchemy models
  metrics.py          # metrics collector
  rate_limit.py       # async token bucket rate limiter
  reporting.py        # report generator
configs/              # yaml eval configs per model
evals_dataset.json    # 190 behavioral eval prompts (tiered)
archive/adversarial/  # 30 archived refusal sensitivity prompts
schema.json           # JSON Schema for dataset entry format
results/              # saved eval results (per-model JSON)
examples/             # sample reports and comparison data
tests/                # pytest suite (50 tests)
```

---

## sample report

see [examples/sample_report.html](examples/sample_report.html) for what the output looks like.

---

## security

- API keys loaded from `.env` (gitignored), never persisted to database
- API server binds to `127.0.0.1` by default
- CORS restricted to localhost (override with `--cors-origins`)
- bearer token auth on all API endpoints (set `PROMPTPRESSURE_API_SECRET`)
- grading pipeline uses XML boundaries to prevent prompt injection
- plugin install requires authentication
- no telemetry

---

## contributing

1. tests pass: `pytest tests/`
2. no unnecessary dependencies
3. document changes

---

## license

MIT. see [LICENSE](LICENSE).
