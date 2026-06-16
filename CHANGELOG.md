# changelog

## 3.3.0 - 2026-06-16

the credibility release: a multi-turn drift corpus plus a judge that reports its own reliability. drift scores are only worth citing if the judge is calibrated, and the calibration is measured on the exact sequences being scored - never on the single-turn corpus.

### added
- `corpus/drift-v0.1/`: 9 multi-turn pressure sequences across 3 categories (sycophancy-under-pressure, persona-stability, refusal-boundary-relaxation), 3 per category, each with a per-turn rubric. two 8-turn sequences + one 20-turn extension per category. 108 labeled assistant turns.
- gold set: per-turn human-reference labels on every assistant turn across 5 ordinal drift dimensions (refusal_integrity, boundary_relaxation, sycophancy, contradiction, escalation) with `hold`/`partial`/`drift` levels + `n/a` exclusion.
- `promptpressure/drift/` package: dimensions, strict schema loader/validator, suite runner, injection-hardened per-turn LLM-as-judge, and a pure-stdlib calibration engine (Cohen's kappa, linearly-weighted kappa, bootstrap CIs, test-retest stability) with no numpy/scipy dependency.
- `pp run --suite drift-v0.1` (replay sequences through a model -> transcripts) and `pp calibrate --suite drift-v0.1` (judge transcripts N times, compute judge-vs-human + test-retest [+ optional judge-vs-judge], write `reports/drift-v0.1-method.md`). also exposed as `ppdrift`.
- native DeepSeek adapter (`deepseek_native` / `deepseek_chat` / `deepseek_api`) hitting api.deepseek.com directly, separate from the OpenRouter-routed `deepseek-r1` adapter.
- first calibration run (deepseek-v4-flash as judge, 3 runs): judge-vs-human pooled kappa 0.41 (moderate, 95% CI [0.31, 0.50], n=324), test-retest pooled kappa 0.78, 0 parse failures. reported honestly as a pilot - gold labels are author reference annotations, not a multi-annotator panel.

### tests
- 87 new tests covering the dimension vocabulary, calibration math (hand-verified against textbook kappa values), schema validation, judge parsing, runner, pipeline aggregation, CLI, and the native DeepSeek adapter. full suite: 286 passing.

## 3.2.1 - 2026-04-28

### fixed
- `pp --version` reads `__version__` from the package instead of dist metadata, so it reports correctly from a source checkout

## 3.2.0 - 2026-04-28

packaging + launcher release. distributed on PyPI as `promptpressure-evals` (the `promptpressure` name is held by an unrelated red-team scanner). import name and CLI entry points unchanged.

### added
- `pp` browser launcher: starts the API on the first free port in 8000-8019, opens a browser, three dropdowns (provider / model / eval set) + Run
- launcher API surface: `/providers` (with availability detection + per-provider `remediation_hint`), `/models` (ollama dropdown + free-text fallback), `/eval-sets`, RunBus per-run event channel with reconnect + TTL reaper, XOR `launcher_request` schema on `/evaluate`
- frontend: SSE status streaming, form lock during run + Cancel button, race-safe provider switch (AbortController), a11y (`role=log`, label association), `fetchJSON` timeout + signal composition

### changed
- vendored a 4.2KB hand-rolled `frontend/tailwind.css`, dropped the 398KB Tailwind Play CDN JIT bundle (offline, no runtime JS for styling)

### fixed
- launcher defaults tier to `full` so untagged datasets actually run (was exiting `0/N sequences selected`)
- API publishes an error frame on `SystemExit` and JSON-encodes SSE data payloads
- SSE handler distinguishes transport vs server errors; form reveal gated on successful model load

## 3.1.0 - 2026-03-29

multi-turn behavioral drift infrastructure. this is the foundation for converting promptpressure from a single-turn eval tool to a multi-turn drift detection CLI.

### added
- 4-tier run system: `--tier smoke|quick|full|deep` with `--smoke` and `--quick` shortcuts
- tier filtering with cumulative semantics (smoke < quick < full < deep)
- per-turn `response_length_ratio` metric computed automatically during multi-turn evals
- per-turn timeout scaling with 5x cap (prevents indefinite hangs on deep sequences)
- context window token estimation with warning when approaching model limits
- `tier` field in pydantic Settings with `Literal` type validation
- `schema.json` documenting the full entry format (JSON Schema 2020-12)
- `archive/adversarial/` directory for refusal sensitivity entries
- `subcategory`, `tier`, `difficulty`, `per_turn_expectations` fields to dataset schema

### changed
- default run tier is `quick` (was: run everything)
- dataset validation now accepts and validates 4 new optional fields
- all 190 dataset entries tagged with tier/subcategory/difficulty
- exits non-zero when tier filter produces 0 matching entries

### removed
- 30 refusal sensitivity entries moved from default dataset to `archive/adversarial/refusal_sensitivity.json` (still accessible via `--dataset`)

## 3.0.0 - 2026-03-25

breaking overhaul. if you're upgrading from 2.x, start fresh.

### changed
- eval IDs now use uuid4 instead of timestamp (no more collisions on fast runs)
- prometheus metrics moved to port 9090 (was 8000, collided with FastAPI)
- API server binds to 127.0.0.1 by default (was 0.0.0.0)
- CORS restricted to localhost by default (was wildcard)
- `threading.Lock` replaced with `asyncio.Lock` in MetricsCollector
- all test imports fixed to use `promptpressure.` prefix
- dependencies cleaned up (removed unused pandas, requests)
- tqdm wired up as progress bar during eval runs
- all dependency versions pinned

### added
- `promptpressure` CLI entry point via `pip install -e .`
- `.env.example` with inline docs for all adapter keys
- terminal summary after eval runs (prompt count, pass/fail/error, avg latency)
- `--ci` flag for machine-readable JSON summary + exit codes (0 = pass, 1 = fail)
- CI pipeline (.github/workflows/ci.yml), pytest on push/PR, Python 3.10+
- JWT auth on all API endpoints
- grading prompt injection defense (XML boundary tags + structured output)
- API key stripping from config snapshots before DB persistence
- `--cors-origins` flag for explicit CORS override
- VERSION file
- 200+ eval prompts across 10 behavioral categories
- sample report at examples/sample_report.html

### removed
- desktop/ directory (Tauri + PyInstaller, premature scope)
- enterprise features from default surface (teams, projects, SSO, audit logs)
- unused pandas, requests dependencies

### security
- grading LLM now uses XML-delimited model responses to prevent score manipulation
- API keys stripped from config_snapshot before persisting to DB
- plugin install endpoint now requires JWT auth (was unauthenticated RCE)
- CORS locked down to localhost
- API server defaults to loopback binding
