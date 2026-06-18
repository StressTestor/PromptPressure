# roadmap

**direction:** the goal is research credibility - make PromptPressure a citable behavioral-eval *method*, not a wide feature surface. it stays a local CLI. this roadmap reflects that.

## shipped

### v3.3.0 (current) - drift-corpus + judge-calibration v0.1 (the credibility release)
- `corpus/drift-v0.1/`: 9 multi-turn pressure sequences, 3 categories (sycophancy-under-pressure, persona stability, refusal/boundary relaxation), 3 per category. two 8-turn + one 20-turn extension each. 108 labeled assistant turns.
- gold set: per-turn human-reference labels on every assistant turn across 5 ordinal drift dimensions (refusal integrity, boundary relaxation, sycophancy, contradiction, escalation).
- pure-stdlib calibration engine: Cohen's kappa, linearly-weighted kappa, bootstrap CIs, test-retest stability. judge-vs-human + judge-vs-judge.
- `pp run --suite drift-v0.1`, `pp calibrate --suite drift-v0.1`, `reports/drift-v0.1-method.md`. native DeepSeek adapter for the judge.
- first run (deepseek-v4-flash as judge): judge-vs-human pooled kappa **0.41** (moderate, CI [0.31, 0.50]), test-retest **0.78**. honest pilot - gold labels are author reference annotations, not yet a multi-annotator panel.
- the claim narrowed honestly: a citable pilot method for multi-turn behavioral drift, with judge reliability reported on the same corpus. that's the part promptfoo, Inspect, and lm-eval-harness don't publish.

### v3.2.x (on PyPI as `promptpressure-evals`)
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

## next

### v3.4 - real human annotation + corpus expansion (turn the pilot into a benchmark)
v0.1 calibration is judge-vs-author. the honest next step before any strong reliability claim is real inter-human agreement, then more sequences once the method holds.

- **multi-annotator gold**: get 2-3 independent humans labeling the same assistant turns, report inter-human kappa, then judge-vs-(human consensus). this is what upgrades "pilot reference labels" to a defensible ground truth.
- **judge-vs-judge across providers**: run `--judge2-provider` with a second model family (the plumbing already ships) and report cross-model agreement so the labeling isn't one model's quirk.
- **expand the corpus** beyond 9 sequences, category by category, only after the calibration method holds up. quality + calibration over raw count.
- weighted-kappa as the headline for the ordinal dimensions, with the nominal kappa reported alongside.

## maybe later

- reasoning-token alignment-leakage analysis (novel, but premature until the judge is calibrated)
- comparison report generator with calibration confidence bands across models under test
- additional multilingual coverage (Japanese, Korean, Hindi)
- agentic eval sequences (multi-step tool use)

## explicitly deprioritized

- **"dataset expansion to 300+ prompts"** - more *uncalibrated* prompts is more noise, not more credibility. quality + calibration over raw count.
- web dashboard - stays a local CLI.

## not happening

SaaS deployment, multi-tenant architecture, mobile apps, "The Sentient Suite", federated evaluation network. PromptPressure is a local CLI tool for behavioral eval. it runs on your machine.
