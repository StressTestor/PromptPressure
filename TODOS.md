# todos

## v2 launcher follow-ups

- real `/v1/models` enumeration in OpenAI-compatible adapters (openrouter, openai, groq, lmstudio, litellm-proxy). replaces the free-text + suggestions fallback for those providers. ~20 lines per adapter.
- "load saved config" UI: pre-fill the launcher dropdowns from a chosen `configs/*.yaml` and disable them with a "config-driven" badge. ~30 lines in app.js + 1 endpoint.
- `pp --new` flag to force a new launcher instance even if one is already running on a port in 8000-8019.
- ~~run cancellation UI button. server-side cancellation is trivial via queue close; the UI piece is the work.~~ **Done 2026-04-28** (frontend Cancel shipped in commit `61e6784`; closes `EventSource` client-side. Server-side cancel still TODO if/when needed.)
- multi-dataset runs: currently `launcher_to_settings_dict` takes only `eval_set_ids[0]`. v2 should concatenate or run sequentially.
- close the port-discovery TOCTOU window: between `find_free_port` releasing the bound socket and uvicorn re-binding, another process could grab it. fix is `subprocess.Popen(..., pass_fds=[fd])` so we hand the bound socket to the subprocess instead. low priority on dev machines but worth doing if the launcher ever sees concurrent multi-user use.

## Surfaced by /qa on 2026-04-28 (deferred, not in scope of frontend-fixes branch)

- **[medium] backend: mock eval crashes silently with `Tier 'quick': 0/45 sequences selected` → `SystemExit: 1`** (`promptpressure/cli.py:62`, `promptpressure/api.py:465`). SSE endpoint stays open but emits no events; frontend hangs on "streaming…" until user clicks Cancel. Likely related to multi-turn drift dataset migration. Repro: run any eval against `evals_tone_sycophancy.json` with the mock provider.
- **[low] backend: SSE doesn't emit `event:error` on eval crash.** `run_eval_background` doesn't catch exceptions and translate them to SSE error frames. Frontend's `instanceof MessageEvent` discriminator works correctly but the backend never sends the frame. Fix: wrap the background task body and publish an error event before closing the bus.
- **[low] tailwind CDN production warning at runtime.** Vendored `/tailwind.js` is the Play CDN bundle which prints a JIT warning on every load. Cosmetic for a localhost dev tool but ages poorly. Future: switch to Tailwind CLI generating precompiled `frontend/tailwind.css`, drop the JIT bundle.
