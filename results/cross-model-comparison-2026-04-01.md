# cross-model behavioral eval comparison

date: 2026-03-31 / 2026-04-01
dataset: evals_dataset.json (200 entries, 10 categories)
tool: PromptPressure v3.1.0
mode: real-time via litellm adapter (direct provider APIs)

## models tested

| model | API ID | endpoint | pricing (in/out per 1M) |
|-------|--------|----------|------------------------|
| Grok 4.20 Reasoning | grok-4.20-0309-reasoning | api.x.ai | $2.00/$6.00 |
| Grok 4.20 Multi-Agent | grok-4.20-multi-agent-0309 | api.x.ai (responses API) | $2.00/$6.00 |
| Grok 4.1 Fast | grok-4-1-fast-reasoning | api.x.ai | $0.20/$0.50 |
| Gemini 3 Flash | gemini-3-flash-preview | googleapis.com | free preview |
| Gemini 3 Pro | gemini-3-pro-preview | googleapis.com | free preview |
| Claude Sonnet 4.6 | claude-4-sonnet-20250514 | api.anthropic.com | $3.00/$15.00 |
| Claude Haiku 4.5 | claude-haiku-4-5-20251001 | api.anthropic.com | $0.80/$4.00 |

## results by category

| category | Grok 4.20 Reasoning | Grok 4.20 Multi-Agent | Grok 4.1 Fast | Gemini 3 Flash | Gemini 3 Pro | Claude Sonnet 4.6 | Claude Haiku 4.5 |
|---|---|---|---|---|---|---|---|
| Context Window Stress | 15/15 | 15/15 | 15/15 | 14/15 | 0/15 | 15/15 | 15/15 |
| Instruction Following Under Conflict | 25/25 | 25/25 | 25/25 | 25/25 | 25/25 | 25/25 | 25/25 |
| Model Drift Detection | 20/20 | 20/20 | 20/20 | 20/20 | 19/20 | 20/20 | 20/20 |
| Multi-Turn Behavioral Drift | 9/10 | 0/10 | 10/10 | 10/10 | 0/10 | 4/10 | 0/10 |
| Multilingual Consistency | 30/30 | 0/30 | 30/30 | 30/30 | 0/30 | 30/30 | 4/30 |
| Output Format Compliance | 15/15 | 15/15 | 15/15 | 15/15 | 1/15 | 15/15 | 15/15 |
| Persona Stability | 15/15 | 15/15 | 15/15 | 15/15 | 15/15 | 15/15 | 15/15 |
| Psychological Reasoning | 25/25 | 25/25 | 25/25 | 25/25 | 25/25 | 25/25 | 25/25 |
| Sycophancy Detection | 25/25 | 3/25 | 25/25 | 25/25 | 0/25 | 25/25 | 14/25 |
| Tone Consistency | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |
| **TOTAL** | **199/200 (100%)** | **138/200 (69%)** | **200/200 (100%)** | **199/200 (100%)** | **105/200 (52%)** | **194/200 (97%)** | **153/200 (76%)** |

## multi-turn sequences (35 total)

| model | passed | notes |
|-------|--------|-------|
| Grok 4.20 Reasoning | 34/35 | 1 failures: Turn 14: Client error '429 Too Many Requests' for url 'https://api.x.ai/v1/chat/ |
| Grok 4.20 Multi-Agent | 3/35 | 32 failures: Turn 3: Client error '429 Too Many Requests' for url 'https://api.x.ai/v1/respon |
| Grok 4.1 Fast | 35/35 | clean sweep |
| Gemini 3 Flash | 35/35 | clean sweep |
| Gemini 3 Pro | 0/35 | 35 failures: Turn 1: Client error '429 Too Many Requests' for url 'https://generativelanguage |
| Claude Sonnet 4.6 | 29/35 | 6 failures: Turn 9: Client error '429 Too Many Requests' for url 'https://api.anthropic.com/ |
| Claude Haiku 4.5 | 14/35 | 21 failures: Turn 2: Client error '429 Too Many Requests' for url 'https://api.anthropic.com/ |

## rankings

sorted by pass rate, then by pricing (cheapest wins ties):

| rank | model | pass rate | multi-turn | pricing |
|------|-------|-----------|------------|---------|
| 1 | Grok 4.1 Fast | 200/200 (100%) | 35/35 | $0.20/$0.50 |
| 2 | Grok 4.20 Reasoning | 199/200 (100%) | 34/35 | $2.00/$6.00 |
| 3 | Gemini 3 Flash | 199/200 (100%) | 35/35 | free preview |
| 4 | Claude Sonnet 4.6 | 194/200 (97%) | 29/35 | $3.00/$15.00 |
| 5 | Claude Haiku 4.5 | 153/200 (76%) | 14/35 | $0.80/$4.00 |
| 6 | Grok 4.20 Multi-Agent | 138/200 (69%) | 3/35 | $2.00/$6.00 |
| 7 | Gemini 3 Pro | 105/200 (52%) | 0/35 | free preview |

## key findings

- **grok 4.1 fast is the best value.** 200/200 at $0.20/$0.50 per M tokens. the budget model outperformed every flagship across all providers.
- **gemini 3 flash is nearly perfect and free.** 199/200, one empty response on context window stress. all 35 multi-turn sequences clean.
- **grok 4.20 reasoning: 199/200.** single rate limit on a 15-turn assumption_creep sequence. functionally equivalent to fast for behavioral eval.
- **claude sonnet 4.6: 194/200 (97%).** 6 rate limits, all on multi-turn sequences. the best anthropic result. strong multi-turn performance (29/35).
- **claude haiku 4.5: 153/200 (77%).** 47 rate limits. anthropic's rate limits hit harder than other providers on sustained eval runs.
- **grok 4.20 multi-agent: 138/200 (69%).** all failures are 429s on the /v1/responses endpoint. stricter throttling than /v1/chat/completions.
- **gemini 3 pro: 105/200 (52%).** 95 x 503 service unavailable. the preview endpoint can't handle sustained load. every multi-turn sequence failed.
- **multi-turn is the stress test.** only grok fast and gemini flash handled all 35 sequences without errors. rate limits and capacity issues surface on multi-turn first because they fire rapid sequential requests.
- **no sub-agent routing metadata** surfaced in grok multi-agent API responses.

## error analysis

| model | error type | count | affected categories |
|-------|-----------|-------|---------------------|
| Grok 4.20 Reasoning | 429 rate limit | 1 | Multi-Turn Drift (turn 14) |
| Grok 4.20 Multi-Agent | 429 rate limit | 62 | Sycophancy, Multilingual, Multi-Turn Drift |
| Grok 4.1 Fast | none | 0 | - |
| Gemini 3 Flash | empty response | 1 | Context Window Stress |
| Gemini 3 Pro | 503 unavailable | 95 | Context Window, Multi-Turn, Multilingual, Sycophancy, Output Format |
| Claude Sonnet 4.6 | 429 rate limit | 6 | Multi-Turn Drift, Sycophancy |
| Claude Haiku 4.5 | 429 rate limit | 47 | Multi-Turn Drift, Sycophancy, Multilingual, Context Window |

## cost comparison (estimated for 200 entries)

| model | pricing tier | est. cost for full suite |
|-------|-------------|------------------------|
| Grok 4.1 Fast | \/bin/zsh.20/\/bin/zsh.50 | ~\/bin/zsh.15 |
| Claude Haiku 4.5 | \/bin/zsh.80/\.00 | ~\.50 |
| Grok 4.20 Reasoning | \.00/\.00 | ~\.00 |
| Grok 4.20 Multi-Agent | \.00/\.00 | ~\.00 |
| Claude Sonnet 4.6 | \.00/\.00 | ~\.00 |
| Gemini 3 Flash | free preview | \/bin/zsh.00 |
| Gemini 3 Pro | free preview | \/bin/zsh.00 |

batch mode (anthropic, xai) would halve these costs. not used in this run due to rate limit concerns.
