# cross-model behavioral eval comparison

date: 2026-04-01
dataset: evals_dataset.json (200 entries, 10 categories)
tool: PromptPressure v3.1.0
retry: 3 retries on 429/503, 5s exponential backoff
pacing: 1s request delay, 2s turn delay

grok models via openrouter (retry/pacing, zero infra errors).
gemini/claude via direct provider APIs (pre-retry, some infra noise).

## models tested

| model | API ID | route | pricing (in/out per 1M) |
|-------|--------|-------|------------------------|
| Grok 4.20 Reasoning | x-ai/grok-4.20 | openrouter | $2.00/$6.00 |
| Grok 4.20 Multi-Agent | x-ai/grok-4.20-multi-agent | openrouter | $2.00/$6.00 |
| Grok 4.1 Fast | x-ai/grok-4.1-fast | openrouter | $0.20/$0.50 |
| Gemini 3 Flash | gemini-3-flash-preview | direct (googleapis) | free preview |
| Gemini 3 Pro | gemini-3-pro-preview | direct (googleapis) | free preview |
| Claude Sonnet 4.6 | claude-4-sonnet-20250514 | direct (anthropic) | $3.00/$15.00 |
| Claude Haiku 4.5 | claude-haiku-4-5-20251001 | direct (anthropic) | $0.80/$4.00 |

## results by category

| category | Grok 4.20 Reasoning | Grok 4.20 Multi-Agent | Grok 4.1 Fast | Gemini 3 Flash | Gemini 3 Pro | Claude Sonnet 4.6 | Claude Haiku 4.5 |
|---|---|---|---|---|---|---|---|
| Context Window Stress | 14/15 | 15/15 | 14/15 | 14/15 | 0/15 | 15/15 | 15/15 |
| Instruction Following Under Conflict | 25/25 | 25/25 | 25/25 | 25/25 | 25/25 | 25/25 | 25/25 |
| Model Drift Detection | 20/20 | 18/20 | 20/20 | 20/20 | 19/20 | 20/20 | 20/20 |
| Multi-Turn Behavioral Drift | 10/10 | 4/10 | 6/10 | 10/10 | 0/10 | 4/10 | 0/10 |
| Multilingual Consistency | 30/30 | 30/30 | 29/30 | 30/30 | 0/30 | 30/30 | 4/30 |
| Output Format Compliance | 15/15 | 15/15 | 14/15 | 15/15 | 1/15 | 15/15 | 15/15 |
| Persona Stability | 15/15 | 15/15 | 15/15 | 15/15 | 15/15 | 15/15 | 15/15 |
| Psychological Reasoning | 24/25 | 25/25 | 25/25 | 25/25 | 25/25 | 25/25 | 25/25 |
| Sycophancy Detection | 23/25 | 25/25 | 23/25 | 25/25 | 0/25 | 25/25 | 14/25 |
| Tone Consistency | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |
| **TOTAL** | **196/200 (98%)** | **192/200 (96%)** | **191/200 (96%)** | **199/200 (100%)** | **105/200 (52%)** | **194/200 (97%)** | **153/200 (76%)** |

## multi-turn sequences (35 total)

| model | passed | notes |
|-------|--------|-------|
| Grok 4.20 Reasoning | 33/35 | 2 failures |
| Grok 4.20 Multi-Agent | 29/35 | 6 failures |
| Grok 4.1 Fast | 29/35 | 6 failures |
| Gemini 3 Flash | 35/35 | clean sweep |
| Gemini 3 Pro | 0/35 | 35 failures |
| Claude Sonnet 4.6 | 29/35 | 6 failures |
| Claude Haiku 4.5 | 14/35 | 21 failures |

## error breakdown (infra vs model)

| model | pass | infra errors | model errors | retries used | route |
|-------|------|-------------|-------------|-------------|-------|
| Grok 4.20 Reasoning | 196/200 | 0 | 4 | 0 | openrouter |
| Grok 4.20 Multi-Agent | 192/200 | 0 | 8 | 0 | openrouter |
| Grok 4.1 Fast | 191/200 | 0 | 9 | 0 | openrouter |
| Gemini 3 Flash | 199/200 | 0 | 0 | 0 | direct (googleapis) |
| Gemini 3 Pro | 105/200 | 95 (pre-retry) | 0 | 0 | direct (googleapis) |
| Claude Sonnet 4.6 | 194/200 | 6 (pre-retry) | 0 | 0 | direct (anthropic) |
| Claude Haiku 4.5 | 153/200 | 47 (pre-retry) | 0 | 0 | direct (anthropic) |

## rankings

sorted by pass rate:

| rank | model | pass rate | multi-turn | clean data? |
|------|-------|-----------|------------|-------------|
| 1 | Gemini 3 Flash | 199/200 (100%) | 35/35 | yes (0 infra) |
| 2 | Grok 4.20 Reasoning | 196/200 (98%) | 33/35 | yes (0 infra) |
| 3 | Claude Sonnet 4.6 | 194/200 (97%) | 29/35 | no (6 infra errors) |
| 4 | Grok 4.20 Multi-Agent | 192/200 (96%) | 29/35 | yes (0 infra) |
| 5 | Grok 4.1 Fast | 191/200 (96%) | 29/35 | yes (0 infra) |
| 6 | Claude Haiku 4.5 | 153/200 (76%) | 14/35 | no (47 infra errors) |
| 7 | Gemini 3 Pro | 105/200 (52%) | 0/35 | no (95 infra errors) |

## key findings

- **retry logic eliminated all infra errors for grok models.** the 3 openrouter runs had zero 429/503 errors. every failure is a real model behavioral failure.
- **grok 4.20 multi-agent jumped from 69% to 96%.** routing through openrouter avoids the /v1/responses rate limit. the model was never the problem, the endpoint was.
- **grok 4.20 reasoning leads at 98%.** 4 model errors across 200 entries, 33/35 multi-turn clean.
- **claude sonnet 4.6 at 97%** but with 6 infra errors (pre-retry run). true model performance is likely higher.
- **gemini 3 flash at 100%** (199/200, 1 empty response) but gemini 3 pro at 52% is all infra (503s).
- **claude/gemini results are polluted by infra errors** from pre-retry direct API runs. rerun with retry/pacing would improve their numbers.
- **the budget models compete with flagships.** grok 4.1 fast at 96% costs 10x less than grok 4.20 reasoning at 98%.

## data quality notes

grok results (openrouter): clean. retry logic active, zero infra errors. all failures are model behavioral failures.
gemini/claude results (direct API): noisy. pre-retry runs without pacing. infra errors (429, 503) inflate failure counts. treat these as lower bounds on model capability.
to get clean gemini/claude data: rerun via openrouter with retry/pacing (blocked by 402 out of credits) or rerun direct API with the new retry flags.
