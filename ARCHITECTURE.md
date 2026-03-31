# architecture

multi-turn behavioral drift detection CLI for LLMs. measures how models behave over sustained interaction, not accuracy on known-answer datasets.

## stack

| layer | technology | notes |
|-------|-----------|-------|
| language | Python 3.10+ | tested on 3.10-3.14 via CI |
| CLI framework | argparse | entry point: `promptpressure` via pyproject.toml scripts |
| API server | FastAPI + uvicorn | optional, for programmatic access |
| database | SQLAlchemy async + aiosqlite | SQLite default, Postgres override via DATABASE_URL |
| HTTP client | httpx | async, used by cloud adapters |
| templates | Jinja2 | HTML + markdown report generation |
| metrics | prometheus-client | exposed on port 9090 |
| config | pydantic-settings + YAML | type-validated, tier field is Literal type |
| testing | pytest + pytest-asyncio | 50 tests, ~0.2s |

## directory structure

```
promptpressure/
  __init__.py
  cli.py                    # main eval runner, grading pipelines, multi-turn processor
  config.py                 # pydantic Settings with Literal tier validation
  api.py                    # FastAPI server (optional, binds 127.0.0.1)
  database.py               # SQLAlchemy async models (Evaluation, Result, Metric, etc.)
  metrics.py                # MetricsCollector, aggregation, prometheus integration
  batch.py                  # batch processing (Anthropic batch API, multi-model parallel, cost tracking)
  per_turn_metrics.py       # automated per-turn metrics (response_length_ratio)
  tier.py                   # filter_by_tier() — cumulative smoke/quick/full/deep
  rate_limit.py             # async token bucket rate limiter
  reporting.py              # ReportGenerator — HTML + markdown from Jinja2 templates
  adapters/
    __init__.py             # load_adapter() dispatcher
    openrouter_adapter.py   # OpenRouter API (cloud)
    groq_adapter.py         # Groq API (cloud)
    openai_adapter.py       # OpenAI API (cloud)
    ollama_adapter.py       # Ollama (local inference)
    lmstudio_adapter.py     # LM Studio (local inference)
    claude_code_adapter.py  # claude CLI non-interactive mode (zero-cost)
    opencode_adapter.py     # opencode CLI non-interactive mode (zero-cost)
    deepseek_r1_adapter.py  # DeepSeek R1 with reasoning token capture (via OpenRouter)
    litellm_adapter.py      # LiteLLM local proxy (routes to any provider)
    mock_adapter.py         # synthetic responses for CI
  plugins/
    __init__.py
    core.py                 # ScorerPlugin ABC, PluginInstaller, PluginManager
    demo_scorer.py          # example plugin implementation
  monitoring/
    docker-compose.yml      # prometheus + grafana stack
    prometheus.yml          # scrape config for port 9090
  templates/
    report_default.html     # Jinja2 HTML report template
    report_default.md       # Jinja2 markdown report template

configs/                    # YAML eval configs, one per model/adapter combination
  config_mock.yaml          # CI/test config
  config_litellm_*.yaml     # litellm proxy configs (sonnet, opus, deepseek, gemini)
  config_drift_claude_code.yaml   # drift eval via direct Anthropic API
  config_drift_ollama.yaml        # drift eval via local Ollama
  config_openrouter_*.yaml        # various OpenRouter model configs
  config_claude_code.yaml         # Claude Code adapter configs
  ...

litellm_config.yaml         # litellm proxy config (anthropic, deepseek, google)
scripts/start-litellm.sh    # start litellm proxy on localhost:4000

evals_dataset.json          # 200 behavioral eval entries (190 legacy + 10 multi-turn drift)
schema.json                 # JSON Schema 2020-12 for dataset entry format
archive/adversarial/        # 30 archived refusal sensitivity entries
  refusal_sensitivity.json
  README.md

tests/                      # 50 pytest tests
  test_dataset_validation.py    # schema compliance, field validation
  test_tier_filtering.py        # tier cumulative semantics, edge cases
  test_per_turn_metrics.py      # response_length_ratio computation
  test_cli_tier.py              # CLI --tier flag wiring
  test_config*.py               # pydantic settings validation
  test_adapters.py              # adapter loading
  test_reporting.py             # HTML/markdown report generation
  test_metrics_*.py             # metrics collection
  ...

scripts/
  aggregate_openrouter_scores.py  # post-run score aggregation
  compare.py                      # multi-model comparison
  verification/                   # version verification scripts

outputs/                    # eval run outputs (timestamped dirs)
examples/                   # sample reports and comparison data
results/                    # saved per-model JSON results

pyproject.toml              # build config, deps, entry point
VERSION                     # current version (3.1.0)
registry.json               # plugin registry (official + community)
```

## key patterns

### data flow

```
YAML config → cli.py:main()
  → load dataset (evals_dataset.json)
  → filter_by_tier(prompts, tier)
  → if batch_mode + litellm + anthropic model:
    → split entries: batchable (single-turn, non-R1) vs real-time (multi-turn, R1)
    → submit batchable to Anthropic batch API via litellm passthrough (50% off)
    → poll for results, parse JSONL responses
    → real-time entries process normally (below)
  → for each prompt (real-time):
    single-turn:
      adapter_fn(prompt_text, config) → response string
    multi-turn:
      _process_multi_turn(prompt_array, adapter_fn, config)
        → sequential turn loop: build messages[], call adapter, append response
        → compute_turn_metrics() after each turn (response_length_ratio)
        → per-turn timeout scaling (capped at 5x base)
  → track per-request cost via litellm usage data → cost.json
  → collect metrics, write CSV + JSON + HTML/MD reports to outputs/
  → (optional) post_analyze_groq() or post_analyze_openrouter()
    → LLM-as-judge grades each response against eval_criteria booleans
    → injects per_turn_expectations as <rubric_hints> for drift entries
```

### multi-turn conversation flow

```
prompt array: [{role: "user", content: "..."}]

turn 1: messages = [system, user_1]           → adapter → assistant_1
turn 2: messages = [system, user_1, asst_1, user_2] → adapter → assistant_2
turn N: messages = [full history]              → adapter → assistant_N

each turn: compute_turn_metrics(user_msg, response) → {response_length_ratio}
```

the adapter receives the full conversation history as a `messages` parameter. the runner builds this up turn by turn, injecting each model response before the next user turn.

### grading pipeline

two independent grading functions (groq and openrouter) with identical logic:
1. extract eval_criteria keys as the rubric (all boolean)
2. build grading prompt with XML-tagged conversation + rubric fields
3. if entry has per_turn_expectations, append as `<rubric_hints>` section
4. LLM judge returns JSON with boolean scores per field
5. `IMPORTANT` injection defense tag prevents model responses from influencing grades

### batch mode

batch is the default path. real-time is the exception.

```
entries → should_use_realtime(entry, model_name)
  → True:  multi-turn, R1, unsupported/pending provider → real-time
  → False: everything else → route through provider batch API

provider batch support (BATCH_PROVIDERS registry in batch.py):
  anthropic: active  (50% off, /anthropic/v1/messages/batches passthrough)
  google:    active  (50% off, vertex batch prediction via litellm)
  xai/grok:  active  (50% off, xAI async batch API, direct to api.x.ai)
  openrouter: pending (on hold, red teaming approval)
  deepseek:  none    (no native batch API, parallel real-time)

batch routing:
  1. split entries: should_use_realtime() partitions into batch vs real-time
  2. run_batch() detects provider via get_provider_for_model()
  3. dispatches to _run_anthropic_batch(), _run_google_batch(), or _run_xai_batch()
  4. poll for completion, parse results
  5. merge batch results into result set
  6. real-time entries process normally via adapter_fn()

cost tracking:
  litellm_adapter stores usage in _last_usage after each call
  cli.py reads it and feeds CostTracker.record_from_usage()
  summary written to outputs/<timestamp>/cost.json
```

auto-enabled for litellm adapter + full/deep tier. `--no-batch` forces real-time.
smoke/quick tiers always use real-time (no batch overhead for small runs).

### tier system

```
smoke < quick < full < deep (cumulative)

--tier quick  →  includes smoke + quick entries
--tier full   →  includes smoke + quick + full entries
--tier deep   →  includes everything

entries without a tier field default to "full"
--smoke and --quick are shortcut flags
```

### state management

stateless CLI. no in-memory state persists between runs. database records eval history but the CLI doesn't read from it during runs. all state is in the YAML config + JSON dataset.

### API design

- style: REST (FastAPI)
- base path: `/` (no versioning)
- auth: HMAC-SHA256 bearer token via `PROMPTPRESSURE_API_SECRET` env var. disabled if unset.
- CORS: localhost-only default, overridable via `PROMPTPRESSURE_CORS_ORIGINS`
- binds to 127.0.0.1 (not 0.0.0.0)
- the API is optional. primary interface is the CLI.

## database

SQLite by default (`data/promptpressure.db`), Postgres via `DATABASE_URL` env var.

### tables

| table | purpose |
|-------|---------|
| evaluations | eval run metadata (id, config snapshot, status, timestamp) |
| results | per-prompt results (prompt text, response, model, latency, success) |
| metrics | per-eval aggregated metrics |
| adapter_configs | stored adapter configurations |
| projects | project grouping for eval runs |
| teams | team/org grouping |
| users | user accounts (username, role, team) |
| comments | annotations on individual results |

### key relationships

```
teams 1──N projects 1──N evaluations 1──N results
                                      1──N metrics
users N──1 teams
comments N──1 results
comments N──1 users
```

### migrations

no migration tool. SQLAlchemy `create_all()` on first run. schema changes require manual migration or DB reset.

## environment variables

| variable | scope | purpose |
|----------|-------|---------|
| ANTHROPIC_API_KEY | server | Anthropic API (used by litellm proxy) |
| DEEPSEEK_API_KEY | server | DeepSeek API (used by litellm proxy) |
| GOOGLE_API_KEY | server | Google AI API (used by litellm proxy) |
| XAI_API_KEY | server | xAI/Grok API (used by litellm proxy, direct batch) |
| GROQ_API_KEY | server | Groq adapter auth |
| OPENROUTER_API_KEY | server | OpenRouter adapter auth |
| OPENAI_API_KEY | server | OpenAI adapter auth |
| LITELLM_API_KEY | server | litellm proxy master key (optional, only if proxy has auth) |
| OLLAMA_BASE_URL | server | override Ollama endpoint (default: localhost:11434) |
| LM_STUDIO_BASE_URL | server | override LM Studio endpoint (default: 127.0.0.1:1234) |
| DATABASE_URL | server | database connection (default: SQLite) |
| PROMPTPRESSURE_API_SECRET | server | API bearer token secret (disabled if unset) |
| PROMPTPRESSURE_CORS_ORIGINS | server | comma-separated CORS origins |

## deployment

### hosting

local CLI tool. no hosted deployment. `pip install -e .` from the repo.

### CI/CD

- **trigger:** push to main, PRs to main
- **matrix:** Python 3.10, 3.11, 3.12, 3.13
- **command:** `pytest tests/ -v`
- **platform:** GitHub Actions

## external services

| service | purpose | auth method |
|---------|---------|-------------|
| LiteLLM proxy | local gateway to multiple providers (localhost:4000) | optional master key |
| Anthropic | Claude models (via litellm) | API key |
| DeepSeek | DeepSeek R1/Chat (via litellm) | API key |
| Google AI | Gemini models (via litellm) | API key |
| OpenRouter | cloud model inference (on hold, pending red teaming approval) | API key |
| Groq | cloud model inference | API key |
| OpenAI | cloud model inference | API key |
| Ollama | local model inference | none (localhost) |
| LM Studio | local model inference | none (localhost) |

## gotchas

- **build requires real env vars**: `next build` equivalent (import-time Supabase client creation pattern) doesn't apply here, but `cli.py` imports `database.py` which creates the engine at import time. if `data/` dir doesn't exist, it tries to create it silently.
- **openrouter red teaming hold**: as of 2026-03-31, all OpenRouter-routed models are on hold pending red teaming approval from their safety team. behavioral/adversarial eval prompts cannot run through OpenRouter until approved. use `claude-code` or `ollama` adapters only.
- **multi-turn adapter contract**: adapters must accept `messages=None` kwarg. when `messages` is provided, the adapter sends the full conversation history instead of a single prompt. adapters that don't support this will fail on multi-turn entries.
- **eval_criteria must be boolean-only**: the grading pipeline hardcodes "boolean fields" in its prompt. non-boolean values (strings, ints, nulls) in eval_criteria will cause the LLM judge to produce garbage. dimension metadata goes in `subcategory`, not eval_criteria.
- **pyc tracking**: some `.pyc` files were historically tracked in git. v3.1.0 cleaned them up but if they reappear, `git rm --cached` the `__pycache__/` dirs.
- **prometheus port**: metrics server runs on port 9090 (was 8000 pre-v3.0, which collided with FastAPI).
- **asyncio lock**: MetricsCollector uses `asyncio.Lock`, not `threading.Lock`. don't call metrics methods from sync contexts.

## commands

```bash
# dev
pip install -e ".[dev]"

# start litellm proxy (routes to anthropic, deepseek, google)
scripts/start-litellm.sh

# run eval (CLI)
promptpressure --quick --multi-config configs/config_mock.yaml
promptpressure --tier full --multi-config configs/config_litellm_sonnet.yaml
promptpressure --tier full --multi-config configs/config_drift_claude_code.yaml
promptpressure --tier full --multi-config configs/config_drift_ollama.yaml

# run with post-analysis grading
promptpressure --multi-config configs/config.yaml --post-analyze openrouter

# test
pytest tests/ -v
pytest tests/test_dataset_validation.py -v  # schema validation only

# lint
# (no linter configured in CI — manual)

# API server (optional)
python server.py

# dataset validation
python3 -c "import json; d=json.load(open('evals_dataset.json')); print(f'{len(d)} entries')"
python3 -c "import json, jsonschema; s=json.load(open('schema.json')); d=json.load(open('evals_dataset.json')); [jsonschema.validate(e, s['items']) for e in d]; print('valid')"
```

---

*last updated: 2026-03-31 by claude (litellm proxy integration)*
*this file is maintained per the architecture-doc skill. update on every structural change.*
