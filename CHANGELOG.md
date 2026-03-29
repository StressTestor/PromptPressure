# changelog

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
