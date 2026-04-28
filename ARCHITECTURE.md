# architecture

PromptPressure is a behavioral eval harness for LLMs -- measures refusal sensitivity, tone consistency, and psychological reasoning across multi-turn conversation sequences.

---

## stack

| layer | technology | version |
|-------|-----------|---------|
| language | Python | >=3.10 |
| api framework | FastAPI | >=0.100,<1.0 |
| server | uvicorn | >=0.20,<1.0 |
| ORM / db | SQLAlchemy (asyncio) + aiosqlite | >=2.0,<3.0 |
| database | SQLite (default) / PostgreSQL (via DATABASE_URL) | - |
| config / validation | pydantic + pydantic-settings | >=2.0,<3.0 |
| http client | httpx | >=0.24,<1.0 |
| SSE | sse-starlette | >=1.6,<4.0 |
| caching | cachetools (TTLCache) | >=5.0,<6.0 |
| templating | jinja2 | >=3.1,<4.0 |
| metrics export | prometheus-client | >=0.17,<1.0 |
| config files | pyyaml | >=6.0,<7.0 |
| frontend | vanilla JS + Tailwind CDN | - |
| test runner | pytest + pytest-asyncio | >=7.0 / >=0.21 |

entry points (from pyproject.toml):
- `promptpressure` -> `promptpressure.cli:main` (config-driven headless runner)
- `pp` -> `promptpressure.launcher:main` (GUI launcher with subprocess + browser open)

---

## directory structure

```
PromptPressure/
├── promptpressure/           # main package
│   ├── api.py                # FastAPI app, all routes, auth gate, RunBus wiring
│   ├── launcher.py           # `pp` CLI: port discovery, subprocess spawn, browser open
│   ├── launcher_translate.py # LauncherRequest pydantic model + Settings dict translation
│   ├── run_bus.py            # per-run SSE event channel with TTL reaping
│   ├── cli.py                # headless runner called by both CLI and api background task
│   ├── config.py             # Settings (pydantic-settings), SettingsWrapper, get_config()
│   ├── database.py           # SQLAlchemy ORM models + init_db / get_db_session
│   ├── batch.py              # batching / concurrency helpers
│   ├── grading.py            # response grading logic
│   ├── metrics.py            # metric collection
│   ├── per_turn_metrics.py   # per-turn metric tracking
│   ├── rate_limit.py         # rate limiter
│   ├── reporting.py          # HTML/markdown report generation
│   ├── resilience.py         # retry / resilience helpers
│   ├── run_log.py            # run logging helpers
│   ├── tier.py               # tier filtering (smoke/quick/full/deep)
│   ├── adapters/             # one file per provider
│   │   ├── __init__.py       # load_adapter() dispatcher
│   │   ├── mock_adapter.py
│   │   ├── ollama_adapter.py
│   │   ├── openrouter_adapter.py
│   │   ├── groq_adapter.py
│   │   ├── openai_adapter.py
│   │   ├── deepseek_r1_adapter.py
│   │   ├── claude_code_adapter.py
│   │   ├── opencode_adapter.py
│   │   ├── litellm_adapter.py
│   │   └── lmstudio_adapter.py
│   ├── monitoring/           # prometheus / health monitoring hooks
│   ├── plugins/              # plugin system (PluginManager, install/list)
│   └── templates/            # jinja2 report templates
├── frontend/                 # static web UI (served by FastAPI StaticFiles)
│   ├── index.html            # single-page launcher form
│   ├── app.js                # provider/model/eval-set fetch + SSE client
│   └── styles.css            # minimal overrides on top of Tailwind
├── tests/                    # pytest suite (191 tests)
│   ├── conftest.py           # sets PROMPTPRESSURE_DEV_NO_AUTH=1 for all tests
│   └── test_*.py             # unit + integration tests per module
├── configs/                  # per-run YAML configs (adapter, model, dataset, tiers)
├── data/                     # SQLite db lives here at runtime (gitignored)
├── outputs/                  # CSV + HTML run outputs (gitignored)
├── evals_dataset.json        # default eval dataset (200 multi-turn sequences)
├── evals_tone_sycophancy.json # sycophancy eval dataset
├── pyproject.toml            # project metadata, deps, entry points
├── .env.example              # env var reference, copy to .env and fill keys
└── TODOS.md                  # v2 launcher follow-up items
```

---

## key patterns

### auth gate

`api.py` raises `RuntimeError` at module import time unless one of these is set:

- `PROMPTPRESSURE_API_SECRET` -- token-based auth enabled
- `PROMPTPRESSURE_DEV_NO_AUTH=1` -- disables auth entirely (local dev / tests)

`tests/conftest.py` sets the dev flag. The `pp` launcher subprocess sets both `PROMPTPRESSURE_DEV_NO_AUTH=1` and `PROMPTPRESSURE_LAUNCHER=1` in the child env via `build_subprocess_env()`.

when `API_SECRET` is set, tokens are `timestamp.HMAC-SHA256(secret, timestamp)` and expire after 24h. all mutating endpoints use `require_auth` as a FastAPI dependency.

### launcher subprocess model

`pp` is a thin parent process that:
1. probes ports 8000-8019 for an existing launcher (`/health` with `launcher: true`)
2. if found: re-opens browser to the existing instance and exits
3. if not found: calls `find_free_port()`, spawns `uvicorn promptpressure.api:app` as a subprocess, waits for `/health` to respond, then opens a browser

the parent process must NOT import `promptpressure.api` -- that would trigger the auth gate RuntimeError. all API logic runs in the child.

### run lifecycle + SSE

```
POST /evaluate
  -> validates LauncherRequest or raw config dict
  -> bus.start(run_id)
  -> background_tasks: run_eval_background(run_id, config_dict)
  <- { run_id, status: "started", stream_url: "/stream/<run_id>" }

GET /stream/<run_id>                       (SSE)
  -> bus.subscribe(run_id) async iterator
  <- SSE events until "complete" or "error"

run_eval_background:
  -> run_evaluation_suite(config_dict)
  -> bus.publish(run_id, {event, data})    (per prompt)
  -> bus.mark_completed(run_id, {event, data})
```

`RunBus` keeps entries alive across subscriber reconnects. a background reaper task (60s interval) evicts completed runs after 5 min idle and any run after 30 min idle.

### SSE event types

| event name | fired by | purpose |
|-----------|---------|---------|
| `start_prompt` | cli.py | per-prompt start (named SSE event) |
| `end_prompt` | cli.py | per-prompt end (named SSE event) |
| `complete` | run_bus | evaluation done |
| `error` | run_bus | evaluation failed |

named events (`start_prompt`, `end_prompt`) are sent as `event: <name>\ndata: ...\n\n`. the browser's `EventSource.onmessage` only fires for unnamed events -- the frontend uses `addEventListener("start_prompt", ...)` etc. for named types.

### provider detection

`/providers` checks each provider's availability at request time (cached 60s):
- `mock` -- always available
- `ollama` -- health check against http://localhost:11434
- API providers (openrouter, groq, openai, etc.) -- env var presence check
- `opencode` / `lmstudio` -- assumed available (no env check)

### model suggestions

`/models?provider=<id>` returns `free_text: true` + a suggestions list for all providers except Ollama. suggestions come from `adapter:` field matches in `configs/*.yaml`. Ollama returns an actual model list via the local API.

### config / tier system

`configs/*.yaml` files drive headless runs. `Settings` (pydantic-settings) validates the full config dict. the `tier` field (`smoke` / `quick` / `full` / `deep`) filters the dataset down to a subset by sequence count -- e.g. `quick` uses 3/200 sequences in CI.

---

## API endpoints

| path | method | auth | purpose |
|------|--------|------|---------|
| `/` | GET | none | serves `frontend/index.html` |
| `/health` | GET | none | status + version; includes `"launcher": true` when spawned by `pp` |
| `/providers` | GET | none | list providers + availability (TTL-cached 60s) |
| `/models` | GET | none | list/suggest models for a provider (TTL-cached 60s) |
| `/eval-sets` | GET | none | list `evals_*.json` files with counts (TTL-cached 60s) |
| `/schema` | GET | none | JSON schema for Settings |
| `/evaluate` | POST | bearer | start eval run; returns `run_id` + `stream_url` |
| `/stream/{run_id}` | GET | none | SSE stream for a run |
| `/evaluations` | GET | bearer | list past evaluations (db) |
| `/evaluations/{id}` | GET | bearer | get evaluation + results (db) |
| `/diagnostics` | GET | bearer | db connectivity + disk space check |
| `/ollama/health` | GET | none | ollama health probe |
| `/ollama/models` | GET | bearer | list installed ollama models |
| `/ollama/models/pull` | POST | bearer | pull a model (background task) |
| `/ollama/models/{name}` | DELETE | bearer | delete a model |
| `/plugins` | GET | bearer | list available plugins |
| `/plugins/install` | POST | bearer | install a plugin |

CORS defaults to `localhost:3000` and `localhost:8000`. override with `PROMPTPRESSURE_CORS_ORIGINS`.

---

## database schema

SQLite at `data/promptpressure.db` (default). override with `DATABASE_URL` for Postgres.

| table | purpose | notes |
|-------|---------|-------|
| `evaluations` | one row per eval run | tracks status (pending/running/completed/failed), config snapshot |
| `results` | one row per prompt response | latency, success, response text, model, adapter |
| `metrics` | float metrics per evaluation | name + value + JSON tags |
| `projects` | group evaluations | optional; foreign key on evaluations |
| `teams` | multi-user grouping | foreign key on projects |
| `users` | user rows | username, role (viewer/...), team FK |
| `comments` | annotations on results | user + content + timestamp |
| `adapter_configs` | stored adapter config | api_key, model_name, base_type |
| `audit_logs` | action log | action, user_id, target_type, target_id |

`init_db()` calls `Base.metadata.create_all` -- schema is auto-created on first run.

relationships:
- `Team` 1->N `Project` 1->N `Evaluation` 1->N `Result` 1->N `Comment`
- `Evaluation` 1->N `Metric`

---

## environment variables

| var | scope | purpose |
|-----|-------|---------|
| `PROMPTPRESSURE_API_SECRET` | server | enables bearer auth. required in prod (or set DEV_NO_AUTH) |
| `PROMPTPRESSURE_DEV_NO_AUTH` | server | set to `1` to skip auth entirely. local dev + tests only |
| `PROMPTPRESSURE_LAUNCHER` | server | set to `1` by `pp` subprocess. flags the `/health` response |
| `PROMPTPRESSURE_CORS_ORIGINS` | server | comma-separated CORS origins. defaults to localhost:3000/8000 |
| `DATABASE_URL` | server | SQLAlchemy URL. defaults to `sqlite+aiosqlite:///data/promptpressure.db` |
| `GROQ_API_KEY` | server | Groq adapter key |
| `OPENROUTER_API_KEY` | server | OpenRouter adapter key |
| `OPENAI_API_KEY` | server | OpenAI adapter key |
| `ANTHROPIC_API_KEY` | server | Claude / LiteLLM adapter key |
| `DEEPSEEK_API_KEY` | server | DeepSeek via LiteLLM key |
| `GOOGLE_API_KEY` | server | Google via LiteLLM key |
| `XAI_API_KEY` | server | xAI via LiteLLM key |
| `OLLAMA_BASE_URL` | server | ollama host (default: http://localhost:11434) |
| `LM_STUDIO_BASE_URL` | server | LM Studio host (default: http://127.0.0.1:1234) |

---

## deployment

### launcher (recommended for local use)

```bash
pp
```

finds a free port in 8000-8019, spawns uvicorn as a subprocess, opens a browser. if a launcher is already running, attaches to it instead.

### headless / production

```bash
PROMPTPRESSURE_API_SECRET=<secret> uvicorn promptpressure.api:app --host 127.0.0.1 --port 8000
```

or via `python -m promptpressure.api` with the same env vars.

### config-driven CLI

```bash
promptpressure --config configs/config_ollama.yaml
```

runs a headless eval from a YAML config file, writes CSV + HTML to `outputs/`.

---

## external integrations

| service | purpose | auth method |
|---------|---------|------------|
| Groq | LLM inference | `GROQ_API_KEY` |
| OpenRouter | LLM routing / inference | `OPENROUTER_API_KEY` |
| OpenAI | LLM inference | `OPENAI_API_KEY` |
| Anthropic (Claude Code) | Claude via CLI subprocess | `ANTHROPIC_API_KEY` |
| OpenCode | LLM via CLI | none (CLI must be in PATH) |
| LiteLLM proxy | multi-provider routing | optional `LITELLM_API_KEY` |
| Ollama | local inference | none (HTTP on localhost) |
| LM Studio | local inference | none (HTTP on localhost) |
| DeepSeek | via OpenRouter | `OPENROUTER_API_KEY` |

---

## gotchas

| problem | cause | fix |
|---------|-------|-----|
| `RuntimeError: PROMPTPRESSURE_API_SECRET is required` at import | `api.py` raises at module-import time if neither auth env var is set | set `PROMPTPRESSURE_DEV_NO_AUTH=1` for local dev, or `PROMPTPRESSURE_API_SECRET` for prod |
| tests fail with the same RuntimeError | test file imports `api.py` before `conftest.py` sets the env var | `conftest.py` uses `os.environ.setdefault` at module level -- works as long as the test is in the `tests/` tree |
| launcher parent process crashes with RuntimeError | parent imported `promptpressure.api` | `launcher.py` must never import `api.py`. it spawns uvicorn as a subprocess instead |
| `frontend/` was previously an orphaned git submodule | old repo history | now a normal tracked directory. if git shows it as a submodule, run `git rm --cached frontend && git add frontend` |
| port-discovery TOCTOU window | `find_free_port` releases the socket before uvicorn re-binds it; another process could grab the port in that window | low priority on dev machines. fix is `subprocess.Popen(..., pass_fds=[fd])` to hand the bound socket to the subprocess. tracked in TODOS.md |
| `EventSource.onmessage` doesn't fire for named events | the SSE spec: `onmessage` only fires for events with no `event:` field | use `addEventListener("start_prompt", ...)` etc. for named events. `onmessage` catches only unnamed data frames |
| multi-dataset runs only use the first dataset | `launcher_to_settings_dict` reads `eval_set_ids[0]` only | v2 follow-up. tracked in TODOS.md |
| `next build` (if frontend ever gets a build step) | N/A currently -- frontend is static HTML/JS with Tailwind CDN | no build step needed today |
| `pp --new` not implemented | `find_free_port` reuse logic not yet wired to a flag | tracked in TODOS.md |

---

## commands

```bash
# dev server (no auth, launcher mode)
pp

# run full pytest suite
.venv/bin/pytest

# run a single test file
.venv/bin/pytest tests/test_api_launcher.py -v

# headless eval from config
.venv/bin/promptpressure --config configs/config_ollama.yaml

# install deps
pip install -e ".[dev]"

# install with litellm proxy support
pip install -e ".[dev,litellm]"
```

---

*last updated: 2026-04-28 -- launcher v3.1.0 implementation*
