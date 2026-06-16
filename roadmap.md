# roadmap

**direction:** the goal is research credibility - make PromptPressure a citable behavioral-eval *method*, not a wide feature surface. it stays a local CLI. this roadmap reflects that.

## shipped

### v3.2.x (current, on PyPI as `promptpressure-evals`)
- `pp` browser launcher: provider/model/eval-set dropdowns, SSE status stream, Cancel button, offline vendored tailwind
- launcher API: `/providers` (availability + remediation hints), `/models`, `/eval-sets`, RunBus per-run channel
- published to PyPI as `promptpressure-evals` (3.2.0), `pp --version` fix (3.2.1)

### v3.1.0
- 4-tier run system (`smoke`/`quick`/`full`/`deep`) with cumulative filtering
- per-turn `response_length_ratio` metric, per-turn timeout scaling (5x cap)
- context-window token estimation + warning
- `schema.json` for the dataset entry format; tier/subcategory/difficulty/per_turn_expectations fields
- 30 refusal-sensitivity entries moved to `archive/adversarial/`

### v3.0.0
- 190 active eval prompts across 11 behavioral categories
- 8 adapters (openrouter, groq, openai, ollama, lm studio, mock, claude code, opencode)
- async eval runner, grading pipeline with prompt-injection defense, html/md reports
- prometheus metrics (port 9090), `--ci` JSON mode, JWT auth, CORS locked to localhost

### v2.x (legacy, pre-overhaul)
- async refactor, db integration, plugin system, fastapi server, sse streaming

## reality check (the gap to close)

the headline pitch is multi-turn behavioral drift ("does it cave at turn 8, drift at turn 20"). right now the corpus is mostly single-turn: smoke + deep tiers have **zero** generated sequences, only ~3 quick sequences exist. and the grading LLM (model-as-judge) has **no published evidence it's calibrated**. credibility blocks on both. the next cycle closes them together.

## next

### v3.3 - drift-corpus + judge-calibration v0.1 (THE credibility release)
the two halves are constitutive: you can't calibrate a drift-judge without drift sequences, and you can't defend drift scores without a calibrated judge. so ship a thin vertical slice of both, and **calibrate on the multi-turn sequences themselves, never on the single-turn corpus.**

- **9 multi-turn sequences**, 3 categories (sycophancy-under-pressure, persona stability, refusal/boundary relaxation), 3 per category. all 8-turn; 3 extended to 20-turn.
- each: stable id, pressure pattern, target behavior, expected drift signature, per-turn rubric.
- **gold set**: human labels on every assistant turn (refusal integrity / boundary relaxation / sycophancy / contradiction / escalation).
- **calibration on exactly that set**: judge-vs-human + judge-vs-judge agreement (Cohen's kappa), 3-run test-retest, confidence intervals.
- ships: `corpus/drift-v0.1/`, `pp run --suite drift-v0.1`, `pp calibrate --suite drift-v0.1`, `reports/drift-v0.1-method.md`.
- the claim narrows honestly: "a citable pilot method for multi-turn behavioral drift, with judge reliability reported on the same corpus."

> rationale: this is the defensible moat. promptfoo, Inspect, and lm-eval-harness don't publish judge-reliability stats. "PromptPressure measures itself, here's the kappa" is what makes results citable. decided via a multi-model debate (codex / deepseek / glm), 2026-06-15.

## maybe later

- expand the drift corpus beyond 9 sequences once the v0.1 calibration method holds up
- reasoning-token alignment-leakage analysis (novel, but premature until the judge is calibrated)
- comparison report generator with calibration confidence bands
- additional multilingual coverage (Japanese, Korean, Hindi)
- agentic eval sequences (multi-step tool use)

## explicitly deprioritized

- **"dataset expansion to 300+ prompts"** - more *uncalibrated* prompts is more noise, not more credibility. quality + calibration over raw count.
- web dashboard - stays a local CLI.

## not happening

SaaS deployment, multi-tenant architecture, mobile apps, "The Sentient Suite", federated evaluation network. PromptPressure is a local CLI tool for behavioral eval. it runs on your machine.
