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
| native app | SwiftUI + SwiftPM | macOS 14+ |
| test runner | pytest + pytest-asyncio | >=7.0 / >=0.21 |

entry points (from pyproject.toml):
- `promptpressure` -> `promptpressure.cli:main` (config-driven headless runner)
- `pp` -> `promptpressure.launcher:main` (GUI launcher with subprocess + browser open; also dispatches `pp run` / `pp calibrate` to the drift CLI)
- `ppdrift` -> `promptpressure.drift.cli:main` (drift suite: run + calibrate)

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
│   │   ├── deepseek_r1_adapter.py   # DeepSeek via OpenRouter (reasoning capture)
│   │   ├── deepseek_adapter.py      # DeepSeek NATIVE api (api.deepseek.com)
│   │   ├── claude_code_adapter.py
│   │   ├── opencode_adapter.py
│   │   ├── litellm_adapter.py
│   │   └── lmstudio_adapter.py
│   ├── drift/                # v3.3 multi-turn drift suite + judge calibration
│   │   ├── dimensions.py     # 5 drift dimensions + ordinal hold/partial/drift labels
│   │   ├── schema.py         # load + validate sequences and gold labels
│   │   ├── runner.py         # replay a sequence through a model -> transcript
│   │   ├── judge.py          # LLM-as-judge labels each assistant turn
│   │   ├── calibration.py    # Cohen/weighted kappa, bootstrap CI, test-retest (pure stdlib)
│   │   ├── pipeline.py       # tie gold + judge labels -> calibration result
│   │   ├── report.py         # render reports/<suite>-method.md
│   │   └── cli.py            # `pp run` / `pp calibrate`
│   ├── monitoring/           # prometheus / health monitoring hooks
│   ├── plugins/              # plugin system (PluginManager, install/list)
│   └── templates/            # jinja2 report templates
├── frontend/                 # static web UI (served by FastAPI StaticFiles)
│   ├── index.html            # single-page launcher form
│   ├── app.js                # provider/model/eval-set fetch + SSE client
│   └── styles.css            # minimal overrides on top of Tailwind
├── tests/                    # pytest suite (302 tests)
│   ├── conftest.py           # sets PROMPTPRESSURE_DEV_NO_AUTH=1 for all tests
│   └── test_*.py             # unit + integration tests per module
├── configs/                  # per-run YAML configs (adapter, model, dataset, tiers)
├── data/                     # SQLite db lives here at runtime (gitignored)
├── outputs/                  # CSV + HTML run outputs (gitignored)
├── corpus/                   # versioned drift suites
│   └── drift-v0.1/           # 9 multi-turn sequences (3 categories) + gold labels
│       ├── schema.json       # sequence + gold JSON schema
│       ├── sequences/        # syc-*/per-*/ref-*.json (pressure conversations)
│       └── gold/             # per-turn human-reference labels + reference transcripts
├── reports/                  # generated method/calibration reports
├── MacApp/                   # SwiftUI macOS workbench
│   ├── Sources/PromptPressureCore/
│   │   ├── Models/           # API/theme/run models
│   │   ├── Services/         # sidecar, API, Keychain, .env, theme/output loaders
│   │   └── Support/          # path and color helpers
│   ├── Sources/PromptPressureApp/
│   │   ├── App/              # @main app + app delegate
│   │   ├── Stores/           # app, credential, and theme state
│   │   └── Views/            # run dashboard, history, themes, settings
│   ├── Resources/            # app icon source PNG + .icns
│   └── Checks/               # no-framework Swift unit check runner
├── script/
│   ├── build_and_run.sh      # SwiftPM build, .app staging, launch
│   └── package_dmg.sh        # DMG staging + optional signing/notarization
├── .github/workflows/
│   ├── ci.yml                # Python test matrix on main/PRs
│   ├── macos-dmg-release.yml # tag/manual macOS DMG release builder
│   └── pr-steward.yml        # comment-triggered Codex steward
├── Package.swift             # SwiftPM package for the native app
├── .codex/environments/      # Codex Run action for the native app
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
native clients can call `POST /evaluations/{run_id}/cancel`; `RunBus` marks the
run cancelled, cancels the registered asyncio task, and emits a final
`event: cancelled` SSE frame.

### SSE event types

| event name | fired by | purpose |
|-----------|---------|---------|
| `start_prompt` | cli.py | per-prompt start (named SSE event) |
| `end_prompt` | cli.py | per-prompt end (named SSE event) |
| `complete` | run_bus | evaluation done |
| `error` | run_bus | evaluation failed |
| `cancelled` | run_bus | evaluation cancelled by a client |

named events (`start_prompt`, `end_prompt`) are sent as `event: <name>\ndata: ...\n\n`. the browser's `EventSource.onmessage` only fires for unnamed events -- the frontend uses `addEventListener("start_prompt", ...)` etc. for named types.

### provider detection

`/providers` checks each provider's availability at request time (cached 60s):
- `mock` -- always available
- `ollama` -- health check against http://localhost:11434
- API providers (openrouter, groq, openai, etc.) -- env var presence check
- `opencode` / `lmstudio` -- assumed available (no env check)

### model suggestions

`/models?provider=<id>` returns `free_text: true` + a suggestions list for all providers except Ollama. suggestions come from `adapter:` field matches in `configs/*.yaml`. Ollama returns an actual model list via the local API.

### drift suite + judge calibration (v3.3)

the `drift/` package is a self-contained vertical slice for multi-turn behavioral
drift. it never touches the single-turn corpus.

- a **suite** is a directory (`corpus/drift-v0.1/`) of `sequences/*.json` (escalating
  user-pressure conversations + per-turn rubric) and `gold/*.json` (a reference
  transcript + per-turn human labels). `schema.load_suite()` validates both strictly.
- every assistant turn is labeled on its in-scope dimensions using an ordinal scale:
  `hold` (0) / `partial` (1) / `drift` (2), plus `n/a` for out-of-scope dimensions
  (excluded pairwise from agreement).
- the 5 dimensions: refusal_integrity, boundary_relaxation, sycophancy, contradiction,
  escalation. each sequence declares `dimensions_in_scope`.
- `pp run` replays each sequence through a model (`runner.py`) -> transcripts.
- `pp calibrate` judges transcripts (`judge.py`, one injection-hardened call per
  sequence) N times, then `calibration.py` computes Cohen's kappa, linearly-weighted
  kappa, bootstrap CIs, and test-retest stability. `pipeline.py` aggregates
  judge-vs-human + test-retest (+ optional judge-vs-judge); `report.py` renders
  `reports/drift-v0.1-method.md`.
- calibration math is **pure stdlib** (no numpy/scipy) so it's auditable and dependency-free.

### macOS native workbench

The native app is a SwiftPM-built SwiftUI app named `PromptPressure`.
It is a Workbench Hub: run dashboard, Drift Studio, providers, models, suites,
reports, plugins, Ollama, diagnostics, jobs, history, settings, and themes.
Native long-running work goes through `/app/jobs/*`; streams are advisory, and
the app reconciles against job detail so a missed final SSE event cannot leave
the UI stuck in `Running`.
The sidecar connection is rendered as `Connected` / `Not Connected`; localhost
addresses stay internal to the IPC layer. The layout uses `NavigationSplitView`
so the history pane can grow into the later analysis-first workbench without
replacing the app shell.

The app launches the existing Python/FastAPI engine as a managed localhost
sidecar rather than rewriting eval execution in Swift. `SidecarProcess` starts:

```bash
python -m uvicorn promptpressure.api:app --host 127.0.0.1 --port <free>
```

The sidecar receives app-specific env vars:

- `PROMPTPRESSURE_APP_SUPPORT_DIR`
- `PROMPTPRESSURE_OUTPUT_DIR`
- `PROMPTPRESSURE_THEMES_DIR`
- `DATABASE_URL`
- provider API keys loaded from macOS Keychain

Dev builds stage `dist/PromptPressure.app` and write
`Contents/Resources/sidecar-dev.json`, pointing the app at the repo checkout and
the active Python executable. Production packaging can replace this with a
bundled engine/runtime under app resources.

macOS app data defaults to:

```
~/Library/Application Support/PromptPressure/
├── data/
├── outputs/
├── providers/
└── themes/
```

Custom themes are injected by placing files ending in `.pp-theme.json` in the
themes folder. The schema is intentionally narrow: `schemaVersion`, `id`, `name`,
`base`, `accent`, `density`, `chartIntensity`, plus optional surface/text tokens.
`hold`, `partial`, and `drift` semantic colors are locked and cannot be
overridden by theme files.

Provider setup is built around Keychain-backed env vars and the `/providers` /
`/models` sidecar endpoints. Built-ins include mock, Ollama, OpenRouter, Groq,
OpenAI, DeepSeek native API (`deepseek_native`, `DEEPSEEK_API_KEY`), DeepSeek R1
via OpenRouter (`deepseek`, `OPENROUTER_API_KEY`), Claude Code, OpenCode, LM
Studio, and LiteLLM. Ollama is discovered live; API providers can return common
suggestions while still allowing typed model ids.

Custom provider injection uses
`~/Library/Application Support/PromptPressure/providers/*.pp-provider.json`.
Keep the schema narrow: `schemaVersion`, `id`, `name`, `apiStyle`, `baseURL`,
`apiKeyEnv`, `models`, optional `modelsEndpoint`, and optional headers.
`apiStyle` supports `openai_chat`, `anthropic_messages`,
`gemini_generate_content`, `openai_responses`, and local OpenAI-compatible chat.
Invalid provider files should be visible in Settings but must not prevent launch.

Risky operations are confirmation-gated: plugin install, Ollama pull/delete,
and other destructive or potentially expensive app actions must pass an explicit
confirmation flag from the native UI.

### config / tier system

`configs/*.yaml` files drive headless runs. `Settings` (pydantic-settings) validates the full config dict. the `tier` field (`smoke` / `quick` / `full` / `deep`) filters the dataset down to a subset by sequence count -- e.g. `quick` uses 3/200 sequences in CI.

---

## API endpoints

| path | method | auth | purpose |
|------|--------|------|---------|
| `/` | GET | none | serves `frontend/index.html` |
| `/health` | GET | none | status + version; includes `"launcher": true` when spawned by `pp` |
| `/providers` | GET | none | list built-in + valid custom providers with availability |
| `/models` | GET | none | list/suggest models for a provider |
| `/eval-sets` | GET | none | list `evals_*.json` files with counts (TTL-cached 60s) |
| `/schema` | GET | none | JSON schema for Settings |
| `/evaluate` | POST | bearer | start eval run; returns `run_id` + `stream_url` |
| `/stream/{run_id}` | GET | none | SSE stream for a run |
| `/evaluations` | GET | bearer | list past evaluations (db) |
| `/evaluations/{id}` | GET | bearer | get evaluation + results (db) |
| `/evaluations/{id}/cancel` | POST | bearer | request server-side run cancellation |
| `/diagnostics` | GET | bearer | db connectivity + disk space check |
| `/app/metadata` | GET | none | native app sidecar metadata, paths, drift colors |
| `/app/configs` | GET | none | list saved YAML configs for native load/prefill |
| `/app/outputs` | GET | none | list generated output dirs/files and report paths |
| `/app/themes` | GET | none | list built-in/custom themes and invalid theme errors |
| `/app/providers` | GET | none | list built-in/custom providers and invalid provider errors |
| `/app/jobs` | GET | none | list sidecar jobs |
| `/app/jobs/{id}` | GET | none | authoritative sidecar job detail |
| `/app/jobs/{id}/events` | GET | none | SSE stream for sidecar job lifecycle/progress |
| `/app/jobs/{id}/cancel` | POST | none | request cancellation for an app job |
| `/app/jobs/evaluations` | POST | none | start native evaluation job with multi-suite selection |
| `/app/jobs/drift/run` | POST | none | run drift suite through a model |
| `/app/jobs/drift/calibrate` | POST | none | run drift judge calibration |
| `/ollama/health` | GET | none | ollama health probe |
| `/ollama/models` | GET | bearer | list installed ollama models |
| `/ollama/models/pull` | POST | bearer | pull a model (confirmation required) |
| `/ollama/models/{name}` | DELETE | bearer | delete a model (confirmation required) |
| `/plugins` | GET | bearer | list available plugins |
| `/plugins/install` | POST | bearer | install a plugin (confirmation required) |

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
| `PROMPTPRESSURE_APP_SUPPORT_DIR` | native sidecar | root app data dir for the macOS app |
| `PROMPTPRESSURE_OUTPUT_DIR` | native sidecar | output dir for app-launched runs |
| `PROMPTPRESSURE_THEMES_DIR` | native sidecar | custom `.pp-theme.json` theme directory |
| `PROMPTPRESSURE_PROVIDERS_DIR` | native sidecar | custom `.pp-provider.json` provider directory |
| `PROMPTPRESSURE_CORS_ORIGINS` | server | comma-separated CORS origins. defaults to localhost:3000/8000 |
| `DATABASE_URL` | server | SQLAlchemy URL. defaults to `sqlite+aiosqlite:///data/promptpressure.db` |
| `GROQ_API_KEY` | server | Groq adapter key |
| `OPENROUTER_API_KEY` | server | OpenRouter adapter key |
| `OPENAI_API_KEY` | server | OpenAI adapter key |
| `ANTHROPIC_API_KEY` | server | Claude / LiteLLM adapter key |
| `DEEPSEEK_API_KEY` | server | DeepSeek native API key (`deepseek_native` adapter, api.deepseek.com); also used by LiteLLM |
| `GOOGLE_API_KEY` | server | Google via LiteLLM key |
| `XAI_API_KEY` | server | xAI via LiteLLM key |
| `OLLAMA_BASE_URL` | server | ollama host (default: http://localhost:11434) |
| `LM_STUDIO_BASE_URL` | server | LM Studio host (default: http://127.0.0.1:1234) |
| `APP_VERSION` | native packaging | optional app bundle short version; CI derives from release tag |
| `APP_BUILD` | native packaging | optional app bundle build number; CI uses GitHub run number |
| `DEVELOPER_ID_APPLICATION` | native packaging / CI secret | optional `codesign` identity for app + DMG signing |
| `NOTARYTOOL_PROFILE` | native packaging / CI secret | optional notarytool keychain profile name |
| `APPLE_DEVELOPER_ID_APPLICATION_P12` | CI secret | base64 `.p12` Developer ID Application certificate |
| `APPLE_CERTIFICATE_PASSWORD` | CI secret | password for the `.p12` certificate |
| `APPLE_KEYCHAIN_PASSWORD` | CI secret | temporary keychain password for GitHub Actions |
| `APPLE_ID` | CI secret | Apple ID used by `notarytool` |
| `APPLE_TEAM_ID` | CI secret | Apple developer team id |
| `APPLE_APP_SPECIFIC_PASSWORD` | CI secret | app-specific password for notarization |

---

## deployment

### launcher (recommended for local use)

```bash
pp
```

finds a free port in 8000-8019, spawns uvicorn as a subprocess, opens a browser. if a launcher is already running, attaches to it instead.

### native macOS app

```bash
./script/build_and_run.sh
./script/build_and_run.sh --bundle
./script/build_and_run.sh --verify
./script/package_dmg.sh
```

`build_and_run.sh` builds the SwiftPM app, stages `dist/PromptPressure.app`, and
launches it as a foreground app bundle. `--bundle` stages the app without
launching, which is the path used by CI. `package_dmg.sh` creates a DMG and uses
`DEVELOPER_ID_APPLICATION` / `NOTARYTOOL_PROFILE` when signing and notarization
credentials are available. `APP_VERSION` and `APP_BUILD` override the generated
Info.plist version and build number.

### GitHub release DMG

`.github/workflows/macos-dmg-release.yml` builds the macOS app on `macos-14`
when a `v*` tag is pushed or the workflow is run manually with a tag. It runs
the Python tests and Swift checks, packages `dist/PromptPressure-<tag>.dmg`,
writes a SHA-256 checksum, uploads both as workflow artifacts, then creates or
updates the matching GitHub Release. Tags with a prerelease suffix, such as
`v3.3.0-macos.1`, are marked as prereleases.

The workflow signs and notarizes automatically only when the Apple signing
secrets listed above are present. Without those secrets, it still publishes an
unsigned DMG and checksum for internal testing.

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
| DeepSeek (native) | LLM inference (api.deepseek.com) | `DEEPSEEK_API_KEY` |
| DeepSeek (via OpenRouter) | reasoning-capture R1 routing | `OPENROUTER_API_KEY` |

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
| native app DMG runs as a dev-sidecar package | the current packaging path writes `sidecar-dev.json` pointing at the checkout/runtime used to build the app | fine for CI artifacts and internal testing; production distribution still needs bundled Python runtime/engine work |
| `next build` (if frontend ever gets a build step) | N/A currently -- frontend is static HTML/JS with Tailwind CDN | no build step needed today |
| `pp --new` not implemented | `find_free_port` reuse logic not yet wired to a flag | tracked in TODOS.md |
| native app launches but sidecar cannot import FastAPI | the selected Python executable lacks PromptPressure dependencies | install Python deps in `.venv`, then rebuild/run so `sidecar-dev.json` points at `.venv/bin/python` |
| custom theme file is ignored | filename does not end in `.pp-theme.json` | rename it and reload themes |
| custom theme shows invalid | schema or color validation failed, or it tried to override `hold`/`partial`/`drift` | fix the file; the app keeps running and reports the error |
| native run appears stuck running | SSE terminal event was missed or stream closed early | app job detail is authoritative; refresh/reconcile `/app/jobs/{id}` and update the UI from terminal job status |

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

# build native macOS app
swift build
swift run PromptPressureChecks
./script/build_and_run.sh --verify
./script/package_dmg.sh
```

---

*last updated: 2026-06-18 -- native workbench hub, app jobs, custom providers, status reconciliation, DMG release CI*
