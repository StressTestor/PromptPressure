# PromptPressure

behavioral eval for LLM refusal sensitivity, tone consistency, and psychological reasoning. the things benchmarks don't test.

most eval frameworks measure accuracy on known-answer datasets. PromptPressure measures how models *behave* — where they draw the refusal line, whether they change helpfulness based on tone, whether they cave to sycophancy, whether their persona breaks under pressure.

200+ prompts across 10 behavioral categories. run against any model. get a report.

---

## quick start in 60 seconds

```bash
git clone https://github.com/StressTestor/PromptPressure.git
cd PromptPressure
pip install -e .

cp .env.example .env
# add your API keys (see .env.example for which adapters need what)

promptpressure --multi-config configs/config_mock.yaml
```

results land in `outputs/<timestamp>/` with CSVs, metrics JSON, and an HTML report.

for a real eval against a cloud model:
```bash
promptpressure --multi-config configs/config_openrouter_gpt_oss_20b_free.yaml
```

---

## what it evaluates

| category | count | what it tests |
|----------|-------|---------------|
| refusal sensitivity | 30+ | graduated harm levels from clearly safe to borderline. where does the model draw the line? |
| tone consistency | 20+ | same request in formal/casual/hostile/pleading. does helpfulness change based on how you ask? |
| psychological reasoning | 25+ | theory of mind, emotional inference, manipulation detection |
| instruction following under conflict | 25+ | contradictory instructions, system vs user prompt conflicts |
| model drift detection | 20+ | calibration questions with known answers, knowledge cutoff awareness |
| sycophancy detection | 20+ | wrong premises ("2+2=5, right?"), answer changes when challenged |
| persona stability | 15+ | system prompt adherence under adversarial messages, jailbreak resistance |
| output format compliance | 15+ | JSON output, structured extraction, word count constraints |
| multilingual consistency | 15+ | same eval in EN/ES/ZH/AR. does behavior change across languages? |
| context window stress | 15+ | long-context faithfulness, needle-in-haystack, buried instructions |

total: 200+ prompts. each with expected behavior and grading criteria.

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

## adapters

| adapter | type | what you need |
|---------|------|---------------|
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
                      {plugins} ...

options:
  --multi-config    YAML config file(s)
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
max_workers: 5
collect_metrics: true
```

run multiple configs in one pass:
```bash
promptpressure --multi-config configs/a.yaml configs/b.yaml
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
