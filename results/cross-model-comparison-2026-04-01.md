# cross-model behavioral eval comparison

date: 2026-04-01
dataset: evals_dataset.json (200 entries, 10 categories)
tool: PromptPressure v3.1.0
mode: real-time via litellm adapter (direct provider APIs)

## models tested

| model | API ID | endpoint | pricing (in/out per 1M) |
|-------|--------|----------|------------------------|
| Grok 4.20 Reasoning | grok-4.20-0309-reasoning | api.x.ai | $2.00/$6.00 |
| Grok 4.20 Multi-Agent | grok-4.20-multi-agent-0309 | api.x.ai (responses API) | $2.00/$6.00 |
| Grok 4.1 Fast | grok-4-1-fast-reasoning | api.x.ai | $0.20/$0.50 |
| Gemini 3 Flash | gemini-3-flash-preview | generativelanguage.googleapis.com | free preview |
| Gemini 3 Pro | gemini-3-pro-preview | generativelanguage.googleapis.com | free preview |

## results by category

| category | Grok 4.20 Reasoning | Grok 4.20 Multi-Agent | Grok 4.1 Fast | Gemini 3 Flash | Gemini 3 Pro |
|---|---|---|---|---|---|
| Context Window Stress | 15/15 | 15/15 | 15/15 | 14/15 | 0/15 |
| Instruction Following Under Conflict | 25/25 | 25/25 | 25/25 | 25/25 | 25/25 |
| Model Drift Detection | 20/20 | 20/20 | 20/20 | 20/20 | 19/20 |
| Multi-Turn Behavioral Drift | 9/10 | 0/10 | 10/10 | 10/10 | 0/10 |
| Multilingual Consistency | 30/30 | 0/30 | 30/30 | 30/30 | 0/30 |
| Output Format Compliance | 15/15 | 15/15 | 15/15 | 15/15 | 1/15 |
| Persona Stability | 15/15 | 15/15 | 15/15 | 15/15 | 15/15 |
| Psychological Reasoning | 25/25 | 25/25 | 25/25 | 25/25 | 25/25 |
| Sycophancy Detection | 25/25 | 3/25 | 25/25 | 25/25 | 0/25 |
| Tone Consistency | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |
| **TOTAL** | **199/200 (100%)** | **138/200 (69%)** | **200/200 (100%)** | **199/200 (100%)** | **105/200 (52%)** |

## multi-turn sequences (35 total)

| model | passed | notes |
|-------|--------|-------|
| Grok 4.20 Reasoning | 34/35 | 1 failures: Turn 14: Client error '429 Too Many Requests' for url 'https://api.x.ai/v1/chat/ |
| Grok 4.20 Multi-Agent | 3/35 | 32 failures: Turn 3: Client error '429 Too Many Requests' for url 'https://api.x.ai/v1/respon |
| Grok 4.1 Fast | 35/35 | clean sweep |
| Gemini 3 Flash | 35/35 | clean sweep |
| Gemini 3 Pro | 0/35 | 35 failures: Turn 1: Client error '429 Too Many Requests' for url 'https://generativelanguage |

## key findings

- **grok 4.1 fast is the best value.** 200/200 at $0.20/$0.50 per M tokens. the budget model outperformed every flagship variant.
- **gemini 3 flash is nearly perfect.** 199/200, one empty response on context window stress. free during preview. all 35 multi-turn sequences clean.
- **grok 4.20 reasoning: 199/200.** single rate limit error on a 15-turn assumption_creep sequence. functionally equivalent to fast for behavioral eval.
- **grok 4.20 multi-agent: 138/200 (69%).** all failures are 429 rate limits on the /v1/responses endpoint, not model failures. the endpoint has stricter throttling than /v1/chat/completions.
- **gemini 3 pro: 105/200 (52%).** all 95 failures are 503 service unavailable. the preview endpoint is overloaded under sustained load. the model handles what it can reach (persona stability 15/15, psych reasoning 25/25, tone consistency 20/20).
- **multi-turn is the stress test.** grok fast and gemini flash handled all 35 sequences. the other three models failed on multi-turn due to rate limits or capacity, not behavioral issues.
- **no sub-agent routing metadata** surfaced in grok multi-agent API responses. the model returns service_tier and status but no harper/benjamin/lucas routing info.

## error analysis

| model | error type | count | affected categories |
|-------|-----------|-------|---------------------|
| Grok 4.20 Reasoning | 429 rate limit | 1 | Multi-Turn Drift (turn 14) |
| Grok 4.20 Multi-Agent | 429 rate limit | 62 | Sycophancy, Multilingual, Multi-Turn Drift |
| Grok 4.1 Fast | none | 0 | - |
| Gemini 3 Flash | empty response | 1 | Context Window Stress |
| Gemini 3 Pro | 503 service unavailable | 95 | Context Window, Multi-Turn, Multilingual, Sycophancy, Output Format |
