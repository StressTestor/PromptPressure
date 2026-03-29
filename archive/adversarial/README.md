# archived adversarial eval content

these prompts test refusal sensitivity, how models handle requests that could be
interpreted as requesting harmful content but are actually benign (academic research,
creative writing, historical analysis, etc).

## why archived

hosted API providers may flag or rate-limit accounts that send adversarial-adjacent
prompts at scale. these sequences are preserved for:
- local model testing (ollama, llama.cpp, vLLM)
- testing with explicit provider permission
- red-team exercises with appropriate authorization

## how to run

```bash
promptpressure --dataset archive/adversarial/refusal_sensitivity.json --multi-config config.yaml
```

no special flags needed. the archive is just a dataset file in a different directory.

## contents

30 entries (rs_001 through rs_030). all prompts are completely benign but designed
to test whether models over-refuse legitimate requests.
