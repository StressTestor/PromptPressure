# todos

## v2 launcher follow-ups

- real `/v1/models` enumeration in OpenAI-compatible adapters (openrouter, openai, groq, lmstudio, litellm-proxy). replaces the free-text + suggestions fallback for those providers. ~20 lines per adapter.
- "load saved config" UI: pre-fill the launcher dropdowns from a chosen `configs/*.yaml` and disable them with a "config-driven" badge. ~30 lines in app.js + 1 endpoint.
- `pp --new` flag to force a new launcher instance even if one is already running on a port in 8000-8019.
- run cancellation UI button. server-side cancellation is trivial via queue close; the UI piece is the work.
- multi-dataset runs: currently `launcher_to_settings_dict` takes only `eval_set_ids[0]`. v2 should concatenate or run sequentially.
- close the port-discovery TOCTOU window: between `find_free_port` releasing the bound socket and uvicorn re-binding, another process could grab it. fix is `subprocess.Popen(..., pass_fds=[fd])` so we hand the bound socket to the subprocess instead. low priority on dev machines but worth doing if the launcher ever sees concurrent multi-user use.
