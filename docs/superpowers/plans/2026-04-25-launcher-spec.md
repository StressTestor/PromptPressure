<!-- /autoplan restore point: /Users/joesephgrey/.gstack/projects/StressTestor-PromptPressure/feat-launcher-autoplan-restore-20260425-223426.md -->

# feat/launcher — PromptPressure desktop launcher

Plan reviewed via /autoplan on 2026-04-25. Codex unavailable (binary not installed); reviews ran with Claude subagent only — degradation matrix entry: `[subagent-only]` for all phases.

## Status: NEEDS RESOLUTION before /superpowers:writing-plans

User-flagged stop-and-surface items: **all four confirmed.** Plan as originally drafted contradicts the codebase in concrete, specific ways. Resolutions proposed inline below; final approval gate will pin the choices.

---

## Goal (unchanged)
One page. Three controls. One button.

- Provider dropdown (populated from API)
- Model dropdown (populated from API; filters when provider changes)
- Eval set checkboxes — multi-select (populated from API)
- Run button → POST `/evaluate`, then SSE stream into a status panel
- Status panel: `run_id`, current prompt index/total, current model output (truncated), final summary, errors

## Branch
- `main` → `feat/launcher`. NOT `feat/glm-5.1-integration`.

## Stack (unchanged)
- `frontend/index.html` + `frontend/app.js` + `frontend/styles.css`. Tailwind via CDN OK; no Node, no package.json, no framework.
- FastAPI `StaticFiles`, mounted at `/` (root).
- Native `EventSource` + `fetch`. <400 lines for `app.js` (soft target).

---

## CEO PHASE (P1: completeness, P2: boil lakes, P3: pragmatic)

**Premises challenged:** plan assumes the existing `/evaluate` contract can stay byte-for-byte. **False** — see Eng Finding #1. Premise reframed: "additive launcher endpoints, plus one schema extension to `/evaluate` that is backward-compatible at the data level (existing `{config: {...}}` requests still work) but explicitly not byte-identical at the schema level (the model now accepts an optional second key)."

**Scope discipline:** spec explicitly lists out-of-scope items. Honored. No expansion. The lake here is: "minimum viable launcher that runs an eval end-to-end on real data." Do that completely. Defer history, viz, auth UI, cancellation UI, recharts, etc.

**What already exists (leveraged):**
- `/evaluate` (api.py:106) — extend, don't replace
- `/stream/{run_id}` (api.py:121) — reuse as-is for the launcher's progress panel
- `ollama_adapter.list_models` (ollama_adapter.py:49) — only canonical model-list source in repo
- `configs/*.yaml` (41 files) — adapter+model+dataset triples can be re-used as suggestions
- `evals_dataset.json` (200 entries), `evals_tone_sycophancy.json` (45 entries) — true datasets

**Dream state delta:** v1 ships a single-page launcher. v2 candidates (deferred to TODOS): saved-config loader, run history, cancellation button, real `/v1/models` calls into OpenAI-compatible adapters.

CEO consensus: SELECTIVE EXPANSION mode. Original scope held. One contract change accepted (#1).

---

## DESIGN PHASE (UI scope: confirmed — page/button/dropdown/panel)

**Information hierarchy:** Provider → Model → Eval sets → Run. Top-down. Status panel below the form. Nothing to debate.

**States that must be designed (not skippable):**
- Loading: while `/providers`, `/models`, `/eval-sets` resolve. Skeleton or spinners.
- Empty: provider list empty (no env keys, no ollama running). User-actionable message: "no providers reachable — set OPENROUTER_API_KEY or start ollama, then refresh."
- Free-text fallback (Eng Finding #2): when `/models` returns `{models: [], note: "..."}`, the dropdown becomes a textbox with a placeholder and the note shown beneath. UI must handle this without a separate code path beyond a conditional render.
- Run-in-progress: button disabled, status panel active, partial output visible.
- Run-complete: button re-enabled, summary shown, panel scroll-locked at end.
- Error: stream drop, eval failure, 4xx/5xx from /evaluate. Panel shows error in red, button re-enabled.

**Accessibility (minimum):** keyboard nav (Tab through controls), label-for on every input, aria-live on status panel for screen readers, contrast on dark background (Tailwind's `slate-100` on `slate-900` ≥ 7:1).

**Out-of-scope confirmed:** charts, recharts, history view, anything visual beyond the text panel. Don't sneak them in.

Design consensus: scope is locked. The only design taste decision is whether the eval-set checkboxes are flat or grouped (see Findings #3 resolution).

---

## ENG PHASE (real findings — these are blockers)

### Finding #1 — CRITICAL — `/evaluate` schema MUST change
**Where:** `api.py:97-98` — `EvalRequest(BaseModel): config: Dict[str, Any]` (required, no alternative).
**Problem:** Sending `{"launcher_request": {...}}` returns HTTP 422 at the Pydantic boundary before any dispatch code runs. The plan's claim "MUST NOT change the existing `/evaluate` contract" is impossible to keep while adding the launcher shape.
**Resolution:**
- Change `EvalRequest` to:
  ```python
  class EvalRequest(BaseModel):
      config: Optional[Dict[str, Any]] = None
      launcher_request: Optional[LauncherRequest] = None

      @model_validator(mode='after')
      def exactly_one(self):
          if (self.config is None) == (self.launcher_request is None):
              raise ValueError("specify config OR launcher_request, not both")
          return self
  ```
- New `LauncherRequest(BaseModel)`: `provider: str`, `model: str`, `eval_set_ids: list[str]`. Validate strictly; do not pass arbitrary keys through.
- Server-side translation builds Settings dict from launcher_request; client cannot inject Settings keys via launcher_request.
- Existing `{config: {...}}` requests are byte-compatible at the data level — they still validate, still dispatch the same way. **The schema is extended, not replaced.** Document this in api.py docstring.
- Plan now owns this change explicitly.

### Finding #2 — HIGH — `/models` is a fiction for 8 of 9 adapters
**Where:** `promptpressure/adapters/*.py` — only `ollama_adapter.py:49-62` has `list_models`.
**Problem:** "Model dropdown" is the v1 goal. 8/9 providers have no canonical list. Spec's "fall back to free text" is a UI-only escape hatch that turns the dropdown into a textbox.
**Resolution — pick one (taste decision, surfaced at gate):**
- **A (honest v1, recommended):** ollama gets a real dropdown. Everyone else gets `<input list="suggested-models">` populated from aggregating `model:` fields across `configs/*.yaml` filtered by adapter. The `note` field tells users they can type any model the provider accepts. Ships now.
- **B (right v1):** add `/v1/models` enumeration to OpenAI-compatible adapters (openrouter, openai, groq, lmstudio, litellm-proxy). ~20 lines per adapter. Adds 2-4 hours. Out of v1 scope per spec's anti-feature-creep rule.
- Recommendation: **A** for v1. File a TODO for B. The user's explicit "ship v1" instruction wins.

### Finding #3 — HIGH — `/eval-sets` mixing configs and datasets creates conflict
**Where:** plan's `kind: dataset|config` discriminator + the launcher's three-control model.
**Problem:** A config like `config_litellm_sonnet.yaml` already pins adapter, model, dataset, temperature, tier. If the user picks `provider=ollama, model=llama3.2, eval_set=config_litellm_sonnet`, who wins? Plan doesn't say.
**Resolution — pick one (taste decision, surfaced at gate):**
- **A (cleanest, recommended):** `/eval-sets` returns datasets only — `evals_dataset.json`, `evals_tone_sycophancy.json`, anything matching `evals_*.json` at repo root. Configs are NOT eval sets. Drop the `kind` discriminator.
- **B:** Same as A, plus add a separate "Load saved config" link in the UI footer that pre-fills all three dropdowns from a chosen YAML and disables them with a "config-driven" badge. ~30 lines extra in app.js, +1 endpoint.
- **C (don't do this):** keep `kind` and silently let one override the other. Worst of both worlds.
- Recommendation: **A** for v1, B as a v2 follow-up TODO.

### Finding #4 — HIGH — tests crash at import without env priming
**Where:** `api.py:48-54` raises `RuntimeError` at module import unless `PROMPTPRESSURE_API_SECRET` or `PROMPTPRESSURE_DEV_NO_AUTH=1` is set. No `tests/conftest.py` exists.
**Resolution:**
- Add `tests/conftest.py`:
  ```python
  import os
  os.environ.setdefault("PROMPTPRESSURE_DEV_NO_AUTH", "1")
  ```
- Tests verifying the prod auth path use `monkeypatch.setenv("PROMPTPRESSURE_API_SECRET", "x")` + `importlib.reload(promptpressure.api)`.
- **`asyncio_mode = "auto"` is NOT a conflict** — pytest-asyncio auto only puts `async def` tests in a loop; sync tests run sync. TestClient is fine.
- Plan's "match existing test style" wording is misleading: api.py has zero tests. This is greenfield.

### Finding #5 — HIGH — subprocess env propagation footgun
**Where:** plan's launcher.py spec, step 3.
**Resolution:**
- `subprocess.Popen([...], env={**os.environ, "PROMPTPRESSURE_DEV_NO_AUTH": "1"})`. Never replace. Required so `PATH`, `OPENROUTER_API_KEY`, `HOME`, etc. survive into the subprocess.
- Parent `pp` process MUST NOT import `promptpressure.api` (would hit the same RuntimeError). Health-check via `httpx.get("http://127.0.0.1:<port>/health")` only. Document this in launcher.py.
- Add a unit test that asserts the env-construction helper preserves a sentinel env var.

### Finding #6 — MEDIUM — `/health` doesn't distinguish launcher
**Where:** `api.py:101-103` — `{"status": "ok", "version": "3.0.0"}` is shared by `python server.py`, `python -m promptpressure.api`, and the launcher's spawned uvicorn.
**Problem:** Plan's "already-running detection" probes `/health`. If the user has a non-launcher PromptPressure server on 8000, `pp` will skip spawning and open a browser to `http://127.0.0.1:8000/` — which 404s because no static files are mounted.
**Resolution:**
- Set `PROMPTPRESSURE_LAUNCHER=1` in the spawned uvicorn env (alongside `PROMPTPRESSURE_DEV_NO_AUTH=1`).
- Modify `/health` to include `"launcher": true` only when that env var is set.
- `pp` already-running detection: probe `/health`, accept only if response includes `"launcher": true`. Otherwise spawn fresh on the next free port.

### Finding #7 — LOW — CORS is fine
**Where:** `api.py:35-40` — `CORSMiddleware` mounted globally.
**Resolution:** static files served same-origin = no CORS preflight = no conflict. One sentence in plan, move on.

### Finding #8 — MEDIUM — cache must key by query params
**Where:** plan's "60s in-process cache" section.
**Resolution:** key on `(endpoint_path, frozenset(query_items.items()))` not just path. Use a small `cachetools.TTLCache(maxsize=64, ttl=60)` or 15 lines of inline dict-with-timestamp. Otherwise `/models?provider=ollama` and `/models?provider=openrouter` collide.

### Finding #9 — MEDIUM — SSE queue lifecycle bug, fixed in v1 (user chose B)
**Where:** `api.py:121-139` and `api.py:282-300`. `EVENT_QUEUES.pop(run_id, None)` runs in the SSE generator's `finally`.
**Problem:**
- (a) If the user reloads after `/evaluate` returns but before the EventSource connects, the eval still runs and writes into a never-drained queue → memory leak (no TTL, no max size).
- (b) Mid-stream EventSource auto-reconnect → the queue was popped on disconnect → reconnect gets 404.
**Resolution (locked):**
- Replace the in-memory `EVENT_QUEUES: Dict[str, asyncio.Queue]` with a small `RunBus` that tracks per-run state: `{run_id: {queue: asyncio.Queue, completed: bool, last_active: float, completion_event: dict|None}}`.
- SSE generator does NOT pop on disconnect; it stops draining but leaves the queue alive.
- New connections to `/stream/{run_id}` for an in-progress run resume from the live queue (replay-from-completion if completed).
- Background asyncio task (`_reap_runs()`) sweeps every 60s: deletes runs where `completed=True` AND `last_active > 5min ago`, OR runs idle >30min regardless.
- Reaper runs are cancelled on app shutdown (clean test teardown).
- ~25 lines net change in api.py. Tested via the new `tests/test_api_launcher.py`: connect-after-completion, mid-stream-disconnect-and-reconnect, reaper-eviction-after-TTL.

### Finding #10 — LOW — frontend size budget
~50 HTML, ~250-340 app.js, ~50-100 CSS. <400 for app.js is plausible-tight. Don't load-bear it.

---

## DX PHASE (pp command)

**TTHW (time to "hello world"):** target <2 minutes from `git pull` to running an eval.
- `pip install -e .` (~30s) + `pp` (~3s spawn + browser open) + form fill (~30s for first time) + click Run = ~1 minute. Plausible.

**`pp --help` requirements:** show usage, the 127.0.0.1-only security note, and how to stop (Ctrl-C). Add `--version` (echoes the package version). No other flags.

**Error messages (must be actionable):**
- Port range exhausted (8000-8019 all taken): `"Could not find a free port in 8000-8019. Stop another launcher or kill whatever is using these ports: lsof -i :8000-8019"`
- Subprocess fails to come up in 10s: `"PromptPressure server didn't respond on http://127.0.0.1:<port>/health within 10 seconds. Check the subprocess output above for the real error. Common causes: missing env vars, port collision, broken venv."`
- Already-running launcher detected: `"Found running launcher at http://127.0.0.1:<port>. Opening browser. (Pass --new to force a new instance — TODO v2)"` — note the TODO.

**README "Launcher" section content:**
- one-line install: `pip install -e .`
- one-line run: `pp`
- security note: "binds 127.0.0.1 only. For remote access, run `uvicorn promptpressure.api:app --host 0.0.0.0` with `PROMPTPRESSURE_API_SECRET` set."
- how to stop: "Ctrl-C in the terminal that started `pp`. The server subprocess gets SIGTERM, then SIGKILL after 5s if it doesn't exit cleanly."
- known v1 limitation: "do not reload the browser mid-run; the SSE stream cannot be re-attached. The eval continues server-side; check `/evaluations/{run_id}` when it completes."

DX consensus: command is well-scoped. Error messages need concrete prompts (above). README section is a non-negotiable acceptance criterion.

---

## Decision Audit Trail

| # | Phase | Decision | Class | Principle | Rationale |
|---|-------|----------|-------|-----------|-----------|
| 1 | CEO | Hold scope (3 controls + 1 button + status panel) | Mechanical | P3 (pragmatic) | Spec already lists out-of-scope; user explicit "ship v1" |
| 2 | Eng | `/evaluate` schema MUST change (XOR config/launcher_request) | Mechanical | P5 (explicit over clever) | Pydantic enforces schema; cannot dispatch around 422. Plan must own change |
| 3 | Eng | `/models` falls back to free-text suggestions from configs (not /v1/models calls) | Taste | P3 + P6 (bias toward action) | A=ship now, B=right thing later. User said "ship v1" |
| 4 | Eng | `/eval-sets` returns datasets only; configs are NOT eval sets | Taste | P5 | Drops `kind` discriminator to avoid silent override conflict |
| 5 | Eng | tests/conftest.py sets DEV_NO_AUTH=1 at import | Mechanical | P5 | Standard pattern; no other way to import api.py in tests |
| 6 | Eng | Subprocess env merges `os.environ`, parent does not import api.py | Mechanical | P1 (completeness) | Anything else breaks PATH and provider keys |
| 7 | Eng | `/health` adds `launcher: true` field gated by PROMPTPRESSURE_LAUNCHER env | Mechanical | P5 | Distinguishes launcher from `python server.py` |
| 8 | Eng | Cache key includes query params | Mechanical | P5 | Otherwise providers collide |
| 9 | Eng | SSE lifecycle: drain-after-completion + 5min TTL + reaper task (user chose B) | Taste-resolved | P1 (completeness) | User locked in correctness over speed. Memory leak + reconnect both fixed. |
| 10 | DX | Concrete error messages for port-exhausted / startup-timeout / already-running | Mechanical | P1 | Acceptance criterion requires actionable failure modes |

---

## Updated acceptance criteria (changes in **bold**)

- `git checkout main && git pull && pip install -e . && pp` opens a browser tab at 127.0.0.1:<port>.
- Provider, Model, Eval set dropdowns populate from real API endpoints. **For non-ollama providers, model field is a free-text input with suggestions from configs.**
- Provider + model + 1+ eval set + Run = an actual eval streaming to completion.
- Failure modes (no providers reachable, eval errors, network drop mid-stream) surface visible errors in the status panel without crashing the page. **Mid-stream drop: EventSource auto-reconnects to the same `/stream/{run_id}` and resumes from the live queue (RunBus keeps state for 5min after completion).**
- All new code has tests. Existing tests still pass. **`tests/conftest.py` sets `PROMPTPRESSURE_DEV_NO_AUTH=1` so api.py can be imported in tests.** No regressions in 80-test batch/litellm/retry suite.
- README has a "Launcher" section: install, run, security note (127.0.0.1 only), how to stop, **mid-run reload limitation**.
- `pp --help` works and is informative. **`pp --version` prints the package version.**
- **`/evaluate` accepts both `{config: {...}}` (existing) and `{launcher_request: {...}}` (new); the model-validator enforces XOR.**
- **`/health` includes `launcher: true` when spawned by `pp`; `pp`'s already-running probe requires that field.**

## Deferred to TODOS.md
- v2: real `/v1/models` enumeration in OpenAI-compatible adapters (openrouter, openai, groq, lmstudio, litellm-proxy)
- v2: "Load saved config" UI affordance that pre-fills dropdowns from a YAML
- v2: `pp --new` flag to force a new launcher instance
- v2: run cancellation UI button (server-side cancellation already trivial via queue close)

