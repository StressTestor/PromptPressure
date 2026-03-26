# roadmap

## shipped

### v3.0 (current)
- 220 eval prompts across 10 behavioral categories
- multi-turn sycophancy sequences (5-turn graduated pressure)
- multilingual consistency testing (EN/ES/ZH/AR/FR)
- 8 adapters: openrouter, groq, openai, ollama, lm studio, mock, claude code, opencode
- deepseek r1 adapter with reasoning token capture
- async eval runner with tqdm progress
- grading pipeline with prompt injection defense
- html/markdown report generation
- prometheus metrics on port 9090
- CI mode with JSON output and exit codes
- JWT auth on API endpoints, CORS locked to localhost

### v2.x (legacy, pre-overhaul)
- async refactor, database integration, rate limiting
- plugin system, fastapi server, sse streaming
- report templates, config validation

## next

### v3.1
- automated grading with per-turn sycophancy scoring
- reasoning token analysis in reports (R1 alignment leakage detection)
- comparison report generator (multi-model behavioral diff)

### v3.2
- ollama adapter for local model benchmarking without API costs
- dataset expansion: 300+ prompts
- additional multilingual coverage (Japanese, Korean, Hindi)

## maybe later

- pypi package publish (`pip install promptpressure`)
- web dashboard for browsing results
- model-as-judge calibration (how consistent is the grading LLM itself)
- agentic eval sequences (multi-step tool use)

## not happening

the v2.x roadmap had plans for SaaS deployment, multi-tenant architecture, mobile apps, "The Sentient Suite", and a federated evaluation network. none of that is in scope. promptpressure is a local CLI tool for behavioral eval. it runs on your machine.
