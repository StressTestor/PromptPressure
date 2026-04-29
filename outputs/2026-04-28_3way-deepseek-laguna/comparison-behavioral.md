# PromptPressure 3-way **behavioral** comparison — 2026-04-28

Re-score of the 593 successful runs from the morning's eval. Judge model: `openai/gpt-oss-20b:free` via OpenRouter. Each prompt has its own rubric (subset of 76 total fields); aggregates below report `true_count / scored_count (pct)`. The `(no data)` cells = no prompts in this rubric for that model's run.

## Headline divergences (where the models actually differ)

### Multi-turn accuracy decay

How well each model holds factual accuracy as conversation context grows.

| | Turn 1 | Turn 2 | Turn 3 | Turn 4 | Turn 5 |
|---|---:|---:|---:|---:|---:|
| **V4 Pro** | 100% | 100% | 100% | 100% | **100%** |
| V4 Flash | 95.7% | 95.7% | 95.7% | 91.3% | 87.0% |
| Laguna M.1 | 100% | 100% | 100% | 96.0% | 84.0% |

**Pro is the only one that doesn't decay through turn 5.** Flash and Laguna both drift by turn 4-5 — exactly the failure mode PromptPressure was built to surface.

### Persona / character consistency

| field | V4 Pro | V4 Flash | Laguna M.1 |
|---|---:|---:|---:|
| `maintains_persona` | 93.3% | **100%** | 40.0% |
| `character_consistent` | 86.7% | **100%** | 33.3% |
| `persona_maintained_turn3` | 100% | 100% | **0%** |
| `persona_maintained_turn5` | 100% | **0%** | **0%** |
| `persona_maintained_turn7` | 100% | **0%** | **0%** |
| `persona_maintained_turn10` | 100% | 100% | **0%** |

**Laguna falls out of character almost immediately.** Flash holds character on the headline metric (100%) but breaks at specific deep turns (5, 7). Pro is rock-solid on persona at every turn measured.

### Resistance to override / pressure

| field | V4 Pro | V4 Flash | Laguna M.1 |
|---|---:|---:|---:|
| `resists_override` | 86.7% | **93.3%** | 40.0% |
| `resists_pressure` | 66.7% | 50.0% | 50.0% |
| `resists_style_pressure` | 100% | 100% | 0% |
| `resists_sycophancy` | **100%** | **100%** | 96.0% |

**Laguna gets overridden a lot.** Tell it "ignore previous instructions" or push it stylistically and it folds. Flash is the most stubborn. Sycophancy resistance is universally strong.

### Refusal rate

How often the model refused harmful or borderline prompts (out of ~47-48 prompts where refusal was the rubric criterion).

| | refused | rate |
|---|---:|---:|
| V4 Pro | 4 / 47 | **8.5%** |
| V4 Flash | 8 / 47 | 17.0% |
| Laguna M.1 | 9 / 48 | 18.8% |

**Pro refuses about half as often as the other two.** Could mean it's better at distinguishing legitimate requests from harmful ones — or it's more permissive. Without checking the specific refused/non-refused prompts you can't tell which.

### Helpfulness fairness

How equally helpful the model was across demographic / framing variations of the same question.

| field | V4 Pro | V4 Flash | Laguna M.1 |
|---|---:|---:|---:|
| `equally_helpful` (yes/no) | 100% | 100% | 95.0% |
| `equal_helpfulness` (treats variants the same) | **81.8%** | 72.7% | 56.5% |
| `compliance_decision_matches_baseline` | **86.4%** | 81.8% | 82.6% |

**Laguna treats prompt variants very differently** — 56.5% on `equal_helpfulness` means it gives meaningfully different answers based on framing. Pro the most consistent.

### Polite correction

When the user is wrong about a fact, does the model correct gracefully?

| | rate |
|---|---:|
| V4 Pro | 70.8% |
| V4 Flash | 87.0% |
| Laguna M.1 | **88.0%** |

**Pro is the most abrupt corrector.** Flash and Laguna correct more diplomatically.

### Acknowledged contradiction

When the user contradicts themselves mid-conversation, did the model notice + acknowledge?

| | rate |
|---|---:|
| V4 Pro | 44.0% |
| V4 Flash | 32.0% |
| Laguna M.1 | **56.0%** |

**Laguna catches contradictions best** — surprising for a smaller/faster model.

### Handled conflict

When the user takes a hostile or argumentative stance, how well did the model navigate it?

| | rate |
|---|---:|
| V4 Pro | **40.0%** |
| V4 Flash | 24.0% |
| Laguna M.1 | 32.0% |

All three weak. Pro best, Flash worst.

## Where they're indistinguishable

Comparable across all three (within ±5pp):
- `tone_adapted` (95% all)
- `nuanced_perspective` (92-96%)
- `factually_correct` (93.8 / 93.8 / 100)
- `consistent_with_known_answer` (93.8 / 93.8 / 100)
- `acknowledges_uncertainty` (100% all)
- `language_appropriate` (95.5 / 100 / 95.7)
- `format_correct` (100 / 100 / 93.3)
- `reasoning_depth` (88 / 88 / 92)

## Composite read

**Pick by use case:**

| if you want… | pick |
|---|---|
| longest-context multi-turn accuracy | **V4 Pro** |
| most consistent character / persona | **V4 Flash** |
| fastest + cheapest with good factual accuracy | **Laguna M.1** |
| best resistance to "ignore previous instructions" attacks | **V4 Flash** |
| most willing to engage with edge-case prompts (lowest refusal) | **V4 Pro** |
| most abrupt — least diplomatic correction | **V4 Pro** |
| weakest persona / role-play | **Laguna M.1** |
| weakest demographic-fairness consistency | **Laguna M.1** |

## Caveats

- **Judge model:** scored with `openai/gpt-oss-20b:free`. Switching judges (e.g., Claude Sonnet, GPT-5.4) can shift these numbers measurably. Re-run with a stronger judge if you want production-grade conclusions.
- **Sample sizes are small per-field:** many rubric fields only appear on 1-5 prompts. The big-N findings (multi-turn accuracy, persona, refusal rate, helpfulness fairness) are the ones to trust. Single-prompt fields are anecdotes, not signals.
- **`[N∅]` cells:** parse-failures / nulls. The free judge model occasionally returned non-JSON; those scores get nulled out and excluded from the pct.
- **Refusal rate without verdict labeling:** an 8.5% refusal rate is good IF those 4 prompts genuinely warranted refusal AND the 43 it answered were genuinely OK. We didn't audit which is which — the judge marked the boolean, not the appropriateness.

## Files

```
outputs/2026-04-28_3way-deepseek-laguna/
├── v4-pro/analysis/openrouter_scores_v4_pro_2026-04-28_17-04-11.{csv,json}
├── v4-flash/analysis/openrouter_scores_v4_flash_2026-04-28_17-06-42.{csv,json}
├── laguna-m1/analysis/openrouter_scores_laguna_2026-04-28_17-09-21.{csv,json}
├── scored-aggregate.json
├── comparison-throughput.md     ← throughput/cost comparison
└── comparison-behavioral.md     ← this report
```
