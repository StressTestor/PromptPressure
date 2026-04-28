# todos

## v2 launcher follow-ups

- real `/v1/models` enumeration in OpenAI-compatible adapters (openrouter, openai, groq, lmstudio, litellm-proxy). replaces the free-text + suggestions fallback for those providers. ~20 lines per adapter.
- "load saved config" UI: pre-fill the launcher dropdowns from a chosen `configs/*.yaml` and disable them with a "config-driven" badge. ~30 lines in app.js + 1 endpoint.
- `pp --new` flag to force a new launcher instance even if one is already running on a port in 8000-8019.
- ~~run cancellation UI button. server-side cancellation is trivial via queue close; the UI piece is the work.~~ **Done 2026-04-28** (frontend Cancel shipped in commit `61e6784`; closes `EventSource` client-side. Server-side cancel still TODO if/when needed.)
- multi-dataset runs: currently `launcher_to_settings_dict` takes only `eval_set_ids[0]`. v2 should concatenate or run sequentially.
- close the port-discovery TOCTOU window: between `find_free_port` releasing the bound socket and uvicorn re-binding, another process could grab it. fix is `subprocess.Popen(..., pass_fds=[fd])` so we hand the bound socket to the subprocess instead. low priority on dev machines but worth doing if the launcher ever sees concurrent multi-user use.

## Surfaced + fixed by /qa on 2026-04-28

- ~~**[medium] backend: mock eval crashes silently with `Tier 'quick': 0/45 sequences selected` → `SystemExit: 1`**~~ **Fixed** in commit `0de4920` (`launcher_to_settings_dict` now defaults tier to `"full"` so untagged datasets run). Regression test: `test_launcher_tier_runs_untagged_datasets`.
- ~~**[low] backend: SSE doesn't emit `event:error` on eval crash.**~~ **Fixed** in commit `0b266b3` (`run_eval_background` catches `SystemExit` alongside `Exception`; also JSON-encodes dict/list SSE payloads so frontend `JSON.parse` works instead of silently falling back to Python repr). Regression tests: `test_run_eval_background_publishes_error_on_systemexit`, `test_run_eval_background_json_encodes_dict_payloads`, `test_run_eval_background_passes_string_payloads_through`.
- ~~**[low] tailwind CDN production warning at runtime.**~~ **Fixed** in commit `232a773` (replaced 398KB Play CDN JIT bundle with 4.2KB hand-rolled `frontend/tailwind.css` covering exactly the ~50 utility classes used). No more runtime JS for styling, fully offline, console clean.
