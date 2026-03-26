# changelog

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
