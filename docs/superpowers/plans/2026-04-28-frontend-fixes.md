# Launcher Frontend Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Address 17 issues identified in a 3-way LLM debate (codex + sonnet + opus) and a marko taste review of the new launcher frontend on `feat/launcher`.

**Architecture:** Frontend stays vanilla JS IIFE — no bundler, no framework. Backend gets one new field on `/providers` (`remediation_hint`). Tailwind moves from CDN to a vendored static asset for offline robustness. Status panel becomes element-children-only for consistent styling. SSE handler distinguishes transport-level errors from server-emitted `error` events via `ev.data` presence. `onProviderChange` becomes race-safe via `AbortController` and a single `state.freeText` flag.

**Tech Stack:** HTML + vanilla JS IIFE + Tailwind (vendored) + custom CSS · FastAPI + pytest · `/qa` (browser-driven verification)

---

## File Structure

| file | change |
|---|---|
| `promptpressure/api.py` | modify — add `remediation_hint` field to provider response |
| `tests/test_api_launcher.py` | modify — test for `remediation_hint` |
| `frontend/index.html` | modify — a11y attributes, empty-state structure, vendored Tailwind reference |
| `frontend/app.js` | modify — race fix, SSE refactor, helpers, state cleanup, Cancel button wiring |
| `frontend/styles.css` | unchanged |
| `frontend/tailwind.js` | **create** — vendored Tailwind Play standalone (~290 KB) |

---

## Task 1: Backend — `remediation_hint` per provider

**Files:**
- Modify: `promptpressure/api.py` (provider response shape)
- Test: `tests/test_api_launcher.py`

**Why:** Item 9 from spec. Empty-state copy in `index.html:19-21` hardcodes `OPENROUTER_API_KEY` + ollama. Will rot when a 3rd provider exists. Backend is the source of truth for what each provider needs to be reachable.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_api_launcher.py`:

```python
def test_providers_include_remediation_hint(client):
    """Each provider entry must include a remediation_hint string for the UI to render."""
    r = client.get("/providers")
    assert r.status_code == 200
    payload = r.json()
    assert isinstance(payload, list) and len(payload) > 0
    for p in payload:
        assert "remediation_hint" in p, f"missing remediation_hint on {p['id']}"
        assert isinstance(p["remediation_hint"], str)
        assert len(p["remediation_hint"]) > 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Volumes/T7/PromptPressure
pytest tests/test_api_launcher.py::test_providers_include_remediation_hint -v
```

Expected: FAIL with `KeyError: 'remediation_hint'` or `AssertionError: missing remediation_hint`.

If the test relies on a `client` fixture that doesn't yet exist, add a minimal one to `tests/conftest.py` (use `fastapi.testclient.TestClient(app)`) — but check first; existing launcher tests likely already define it.

- [ ] **Step 3: Add the field in `promptpressure/api.py`**

Locate the `/providers` endpoint (search for `@app.get("/providers")` or the function building the provider list). Add `remediation_hint` to each provider dict. Use a small lookup table at module scope:

```python
# Module-scope constant near other launcher config
PROVIDER_REMEDIATION_HINTS: dict[str, str] = {
    "openrouter": "Set OPENROUTER_API_KEY in your environment.",
    "ollama": "Start the ollama daemon: `ollama serve` (or run `ollama run <model>`).",
    "anthropic": "Set ANTHROPIC_API_KEY in your environment.",
    "openai": "Set OPENAI_API_KEY in your environment.",
    "gemini": "Set GEMINI_API_KEY in your environment.",
    # fallback covered by .get()
}
```

Then in the provider response builder, include:

```python
"remediation_hint": PROVIDER_REMEDIATION_HINTS.get(
    provider_id,
    f"Configure {provider_id} (see project README).",
),
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_api_launcher.py::test_providers_include_remediation_hint -v
```

Expected: PASS.

- [ ] **Step 5: Run the full test file to catch regressions**

```bash
pytest tests/test_api_launcher.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add promptpressure/api.py tests/test_api_launcher.py
git commit -m "feat(api): add remediation_hint to /providers response"
```

---

## Task 2: Frontend — `appendLine` helper (replaces `append`/`appendError`)

**Files:**
- Modify: `frontend/app.js` (replace `append` and `appendError` with a single helper)

**Why:** Items 6 + marko #4. Current `append()` does `textContent +=` which flattens any `<span>` children injected by `appendError()`. Result: red error styling vanishes the next time anything else logs. Fix is to make the status panel element-children-only and never use `textContent +=` again.

- [ ] **Step 1: Replace `append` and `appendError` with `appendLine`**

In `frontend/app.js`, delete the existing `append` and `appendError` functions (currently lines 24–35). Replace with:

```javascript
function appendLine(text, opts = {}) {
  const isError = opts.error === true;
  const line = document.createElement(isError ? "span" : "div");
  if (isError) line.className = "text-red-400";
  // Always own newline rendering — pre + whitespace-pre-wrap turns each child's
  // textContent into a visual line. We add an explicit \n inside the element so
  // copy-paste from the panel preserves line breaks.
  line.textContent = (els.statusPanel.children.length ? "\n" : "") + text;
  els.statusPanel.appendChild(line);
  els.statusPanel.scrollTop = els.statusPanel.scrollHeight;
}

function clearStatusPanel() {
  els.statusPanel.replaceChildren();
}
```

- [ ] **Step 2: Update every call site**

Search for `append(` and `appendError(` in `frontend/app.js`. Replace:
- `append(x)` → `appendLine(x)`
- `appendError(x)` → `appendLine(x, { error: true })`
- `els.statusPanel.textContent = ""` → `clearStatusPanel()`

There are call sites at (current line numbers, will shift): 156, 159, 169, 177, 182, 189, 194, 199, 202, 207.

- [ ] **Step 3: Verify in browser**

```bash
cd /Volumes/T7/PromptPressure
pytest tests/ -q  # backend smoke
pp  # launches FastAPI + opens browser
```

In the launcher: pick a provider, click Run, watch status panel render lines. Force an error path (pick a model that doesn't exist) — verify the red error line stays red even after subsequent normal lines append.

- [ ] **Step 4: Commit**

```bash
git add frontend/app.js
git commit -m "refactor(frontend): single appendLine helper, element-children-only status panel"
```

---

## Task 3: Frontend — `fetchJSON` with timeout + signal

**Files:**
- Modify: `frontend/app.js` (`fetchJSON` function)

**Why:** Item 8 (no fetch timeout). Also plumbing for Task 4 (`onProviderChange` AbortController). Wrapping with `AbortSignal.timeout` gives every fetch a default 15s ceiling; the optional `signal` param lets callers compose with their own AbortController.

- [ ] **Step 1: Replace `fetchJSON`**

In `frontend/app.js`, replace the current `fetchJSON` (lines 37–41) with:

```javascript
async function fetchJSON(url, { signal, timeoutMs = 15000 } = {}) {
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  const composedSignal = signal
    ? AbortSignal.any([signal, timeoutSignal])
    : timeoutSignal;
  const r = await fetch(url, { signal: composedSignal });
  if (!r.ok) throw new Error(`${url} → ${r.status}`);
  return r.json();
}
```

(`AbortSignal.any` is supported in all modern browsers as of 2024. If the launcher must support older browsers, fall back to a manual race — but for a localhost dev tool, target current Chromium/Firefox/Safari.)

- [ ] **Step 2: Verify existing call sites still work**

The two call sites in `init()` (`/providers`, `/eval-sets`) pass no options — the new signature is backwards-compatible.

- [ ] **Step 3: Smoke test**

```bash
pp
```

Pick a provider in the UI; verify `/providers`, `/eval-sets`, `/models` all load. Open DevTools Network tab, throttle to "Slow 3G", reload — verify the page surfaces a timeout error in the status panel within ~15s rather than hanging indefinitely.

- [ ] **Step 4: Commit**

```bash
git add frontend/app.js
git commit -m "feat(frontend): fetchJSON timeout + signal composition"
```

---

## Task 4: Frontend — race-safe `onProviderChange`

**Files:**
- Modify: `frontend/app.js` (`onProviderChange`, `selectedModel`, add module state)

**Why:** Items 1 + 10. Rapid provider switching can leave a stale model list visible or submit `provider B` with `provider A`'s model. Replace visibility-as-state with a `state.freeText` flag, abort prior `/models` fetches, and disable Run while a fetch is in flight.

- [ ] **Step 1: Add module-scope state**

Near the top of the IIFE (after the `els` object definition), add:

```javascript
const state = {
  freeText: false,
  modelsAbort: null,  // AbortController for the currently in-flight /models fetch
};
```

- [ ] **Step 2: Replace `onProviderChange`**

Replace the current `onProviderChange` (lines 109–140) with:

```javascript
async function onProviderChange() {
  const provider = els.provider.value;

  // Abort any previous /models fetch so a slow earlier switch can't race with
  // the current one and leave the wrong models on screen.
  if (state.modelsAbort) state.modelsAbort.abort();
  state.modelsAbort = new AbortController();

  // Clear current model UI immediately so the user can't submit a stale value
  // while the new fetch is in flight, and lock Run.
  els.modelSelect.replaceChildren();
  els.modelDatalist.replaceChildren();
  els.model.value = "";
  els.modelNote.textContent = "Loading models…";
  els.runBtn.disabled = true;

  let payload;
  try {
    payload = await fetchJSON(
      `/models?provider=${encodeURIComponent(provider)}`,
      { signal: state.modelsAbort.signal },
    );
  } catch (e) {
    if (e.name === "AbortError") return;  // superseded by a newer call — silent
    els.modelNote.textContent = "Failed to load models: " + e.message;
    return;  // Run stays disabled; user sees the error in modelNote
  }

  state.freeText = payload.free_text === true;
  if (state.freeText) {
    els.modelSelect.classList.add("hidden");
    els.model.classList.remove("hidden");
    for (const m of payload.models || []) {
      const o = document.createElement("option");
      o.value = m;
      els.modelDatalist.appendChild(o);
    }
  } else {
    els.model.classList.add("hidden");
    els.modelSelect.classList.remove("hidden");
    for (const m of payload.models || []) {
      const o = document.createElement("option");
      o.value = m;
      o.textContent = m;
      els.modelSelect.appendChild(o);
    }
  }
  els.modelNote.textContent = payload.note || "";
  els.runBtn.disabled = false;
}
```

- [ ] **Step 3: Replace `selectedModel`**

Replace the current `selectedModel` (lines 142–144):

```javascript
function selectedModel() {
  return state.freeText ? els.model.value : els.modelSelect.value;
}
```

- [ ] **Step 4: Verify**

```bash
pp
```

In the browser DevTools, throttle to "Slow 3G". Switch providers rapidly (3-4 in a row). Verify:
- `Loading models…` shows in `#model-note` while fetching
- Run button is disabled while loading
- The final visible model list matches the LAST-selected provider, not whichever resolved last
- No `(provider B + provider A's model)` mismatch is possible

- [ ] **Step 5: Commit**

```bash
git add frontend/app.js
git commit -m "fix(frontend): race-safe provider switch via AbortController + state.freeText flag"
```

---

## Task 5: Frontend — gate form reveal on init success

**Files:**
- Modify: `frontend/app.js` (`init` function)

**Why:** Item 3. Currently `init()` reveals the form even if `onProviderChange()` fell into its catch and bailed. Form looks ready but Run will fail with `Pick or type a model`. Fix: only reveal after `onProviderChange` confirms a model list is loaded.

- [ ] **Step 1: Add a stub `renderEmptyState`**

This will be replaced by Task 8 with the per-provider hint rendering. The stub keeps Task 5 atomically executable on its own.

Add near the other helpers:

```javascript
function renderEmptyState(_allProviders) {
  els.empty.classList.remove("hidden");
}
```

- [ ] **Step 2: Replace `init`**

Replace the current `init` (lines 43–71):

```javascript
async function init() {
  let provs, sets;
  try {
    [provs, sets] = await Promise.all([
      fetchJSON("/providers"),
      fetchJSON("/eval-sets"),
    ]);
  } catch (e) {
    els.loading.textContent = "Failed to load: " + e.message;
    return;
  }

  const available = provs.filter((p) => p.available);
  if (available.length === 0) {
    els.loading.classList.add("hidden");
    renderEmptyState(provs);  // stub here; Task 8 fills it in
    return;
  }

  populateProviders(available);
  populateEvalSets(sets);
  await onProviderChange();

  // onProviderChange may have failed; only reveal the form if a model list
  // is now visible. Otherwise the user sees the loading message + the
  // modelNote error, and can refresh.
  const hasModels = state.freeText
    ? els.modelDatalist.children.length > 0 || els.model.classList.contains("hidden") === false
    : els.modelSelect.children.length > 0;
  if (!hasModels && els.modelNote.textContent.startsWith("Failed")) {
    els.loading.textContent = "Provider loaded but model list failed: " + els.modelNote.textContent;
    return;
  }

  els.loading.classList.add("hidden");
  els.form.classList.remove("hidden");
  els.provider.addEventListener("change", onProviderChange);
  els.form.addEventListener("submit", onSubmit);
}
```

- [ ] **Step 2: Verify**

```bash
pp
```

To force model-load failure: temporarily edit `promptpressure/api.py` `/models` endpoint to `raise HTTPException(500)` for the first request. Reload the launcher — verify the form does NOT appear and the error is visible. Revert the api.py change.

- [ ] **Step 3: Commit**

```bash
git add frontend/app.js
git commit -m "fix(frontend): gate form reveal on successful model load"
```

---

## Task 6: Frontend — SSE handler refactor

**Files:**
- Modify: `frontend/app.js` (extract helper, fix error handling, validate stream_url, null after close)

**Why:** Items 2, 4, 15, 17. Current `error` listener treats transport-level disconnects and server-emitted `error` events as terminal — kills auto-reconnect, truncates running evals. Three near-identical event handlers do the same JSON-parse-stringify dance. `body.stream_url` is never validated.

- [ ] **Step 1: Add helper near top of file (with other helpers)**

After `appendLine`/`clearStatusPanel`, add:

```javascript
function addJsonEventListener(eventSource, name, prefix) {
  eventSource.addEventListener(name, (ev) => {
    let parsed = ev.data;
    try { parsed = JSON.stringify(JSON.parse(ev.data)); } catch (_) {}
    appendLine(prefix + parsed);
  });
}

function closeStream() {
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }
}
```

- [ ] **Step 2: Replace the SSE block in `onSubmit`**

Replace the current SSE setup (lines 184–211) with:

```javascript
  closeStream();

  if (typeof body.stream_url !== "string" || body.stream_url.length === 0) {
    appendLine("evaluate returned no stream_url; aborting", { error: true });
    els.runBtn.disabled = false;
    return;
  }

  currentEventSource = new EventSource(body.stream_url);

  currentEventSource.onmessage = (ev) => {
    let parsed = ev.data;
    try { parsed = JSON.stringify(JSON.parse(ev.data)); } catch (_) {}
    appendLine(parsed);
  };

  addJsonEventListener(currentEventSource, "start_prompt", "start: ");
  addJsonEventListener(currentEventSource, "end_prompt",   "end:   ");

  currentEventSource.addEventListener("complete", (ev) => {
    appendLine("complete: " + ev.data);
    closeStream();
    els.runBtn.disabled = false;
  });

  currentEventSource.addEventListener("error", (ev) => {
    // EventSource fires the native `error` event for transport-level failures
    // (network drop, server reset) — in that case ev.data is undefined and the
    // browser will auto-reconnect unless we close. Server-emitted `event:error`
    // frames carry a data payload and should terminate the stream.
    if (ev.data) {
      appendLine("error: " + ev.data, { error: true });
      closeStream();
      els.runBtn.disabled = false;
    } else {
      // Transport hiccup — log once and let EventSource retry.
      appendLine("connection lost, retrying…", { error: true });
    }
  });
```

- [ ] **Step 3: Verify error handling distinction**

```bash
pp
```

Smoke test 1 — server error: trigger an eval that the backend rejects (invalid eval_set_id). Verify red `error: ...` line appears and stream closes (Run re-enables).

Smoke test 2 — transport drop: start a long eval. In another terminal: `lsof -i :8000 | grep python | awk '{print $2}' | xargs kill -STOP` to pause the FastAPI process for 5s, then `kill -CONT <pid>`. Verify:
- `connection lost, retrying…` appears in red
- Stream resumes once FastAPI is unpaused
- Run button stays disabled (eval is still running)

- [ ] **Step 4: Commit**

```bash
git add frontend/app.js
git commit -m "fix(frontend): SSE handler distinguishes transport vs server errors"
```

---

## Task 7: Frontend — disable form during streaming + Cancel button

**Files:**
- Modify: `frontend/index.html` (add Cancel button), `frontend/app.js` (form state machine)

**Why:** Item 5. Provider/model/eval-set controls remain editable while a run is streaming, so the UI can show config that no longer matches the running job. Also no cancel affordance for long evals.

- [ ] **Step 1: Add Cancel button to the form**

In `frontend/index.html`, replace the current `<button id="run-btn">…</button>` block with:

```html
      <div class="flex gap-2">
        <button id="run-btn" type="submit"
                class="bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-700 px-4 py-2 rounded font-medium">
          Run
        </button>
        <button id="cancel-btn" type="button"
                class="bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-500 px-4 py-2 rounded font-medium hidden">
          Cancel
        </button>
      </div>
```

- [ ] **Step 2: Add a `setRunning` helper and wire Cancel in `app.js`**

Add to the `els` object:

```javascript
    cancelBtn: $("cancel-btn"),
```

After the `closeStream` helper from Task 6, add:

```javascript
function setRunning(running) {
  // All form inputs go disabled while a run is streaming so the visible config
  // matches the actual running job. Cancel becomes available; Run goes hidden
  // (the user can't submit again until cancel or complete).
  els.provider.disabled = running;
  els.model.disabled = running;
  els.modelSelect.disabled = running;
  for (const cb of els.evalSets.querySelectorAll("input[type=checkbox]")) {
    cb.disabled = running;
  }
  els.runBtn.disabled = running;
  els.runBtn.setAttribute("aria-busy", running ? "true" : "false");
  els.cancelBtn.classList.toggle("hidden", !running);
}
```

- [ ] **Step 3: Use `setRunning` in `onSubmit`**

In `onSubmit`:
- Replace `els.runBtn.disabled = true;` (early in the function) with `setRunning(true);`
- Replace every `els.runBtn.disabled = false;` (in error and complete paths) with `setRunning(false);`

- [ ] **Step 4: Wire the Cancel button in `init`**

At the bottom of `init`, after the existing `addEventListener` calls:

```javascript
  els.cancelBtn.addEventListener("click", () => {
    closeStream();
    appendLine("cancelled by user", { error: true });
    setRunning(false);
  });
```

- [ ] **Step 5: Verify**

```bash
pp
```

Start a long eval. Verify:
- All form controls are disabled while running (try clicking provider — no change)
- Cancel button is visible
- Click Cancel → stream closes, "cancelled by user" appears in red, form re-enables
- Run an eval to completion — Run button comes back, Cancel hides

- [ ] **Step 6: Commit**

```bash
git add frontend/index.html frontend/app.js
git commit -m "feat(frontend): lock form during run + Cancel button"
```

---

## Task 8: Frontend — render `remediation_hint` from /providers

**Files:**
- Modify: `frontend/index.html` (replace hardcoded copy with empty container), `frontend/app.js` (add `renderEmptyState`)

**Why:** Item 9. The empty-state copy hardcodes `OPENROUTER_API_KEY` + ollama. Backend `/providers` now returns `remediation_hint` per provider (Task 1). Render those instead.

- [ ] **Step 1: Replace the hardcoded `#empty` content**

In `frontend/index.html`, change the `<section id="empty">` block to:

```html
    <section id="empty" class="hidden text-amber-400 space-y-2" role="alert" aria-live="assertive">
      <p class="font-medium">No providers reachable.</p>
      <ul id="empty-hints" class="list-disc list-inside text-sm space-y-1"></ul>
      <p class="text-sm text-slate-400">Fix one of the above, then refresh.</p>
    </section>
```

(The `role="alert"` + `aria-live="assertive"` covers item 11 too — included here so the a11y pass in Task 9 doesn't duplicate.)

- [ ] **Step 2: Add `renderEmptyState` to `app.js`**

Add to the `els` object: `emptyHints: $("empty-hints"),`. Then add:

```javascript
function renderEmptyState(allProviders) {
  els.emptyHints.replaceChildren();
  for (const p of allProviders) {
    const li = document.createElement("li");
    li.textContent = `${p.label}: ${p.remediation_hint}`;
    els.emptyHints.appendChild(li);
  }
  els.empty.classList.remove("hidden");
}
```

- [ ] **Step 3: Wire it into `init` (already referenced in Task 5)**

If Task 5 was applied, `renderEmptyState(provs)` is already called when `available.length === 0`. Pass the full provider list (not the filtered `available`) so the user sees hints for every provider that's currently unreachable.

- [ ] **Step 4: Verify**

```bash
unset OPENROUTER_API_KEY
ollama stop 2>/dev/null  # or skip if ollama isn't installed
pp
```

Verify the launcher shows `No providers reachable.` followed by a bulleted list of every provider with its `remediation_hint`. Refresh after exporting one — verify list shrinks, eventually the form appears.

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html frontend/app.js
git commit -m "feat(frontend): render per-provider remediation_hint instead of hardcoded copy"
```

---

## Task 9: Frontend — accessibility pass

**Files:**
- Modify: `frontend/index.html`

**Why:** Items 12, 13, 14. Status panel `aria-live="polite"` floods screen readers on streaming runs. `#model-select` has no associated label. Run button has no `aria-busy` (Task 7 added it programmatically — codify in HTML).

- [ ] **Step 1: Status panel — switch to `role="log"`**

Change the `<pre id="status-panel">` opening tag from:

```html
<pre id="status-panel"
     class="bg-slate-800 border border-slate-700 rounded p-3 text-xs whitespace-pre-wrap min-h-32 max-h-96 overflow-auto"
     aria-live="polite"></pre>
```

to:

```html
<pre id="status-panel"
     class="bg-slate-800 border border-slate-700 rounded p-3 text-xs whitespace-pre-wrap min-h-32 max-h-96 overflow-auto"
     role="log"
     aria-live="off"
     aria-relevant="additions"
     aria-label="Run status log"></pre>
```

`role="log"` implies the panel is an append-only log; `aria-live="off"` suppresses per-line announcements for streaming runs (the user can navigate to the log to read it). The `complete:` / `error:` lines fire the form's own announcement via Cancel/Run state changes.

- [ ] **Step 2: Label both model controls**

Wrap both model controls in a single labelled group. Change the `<div>` containing `#model` and `#model-select` to:

```html
      <div role="group" aria-labelledby="model-label">
        <span id="model-label" class="block text-sm font-medium mb-1">Model</span>
        <input id="model" list="model-suggestions"
               aria-labelledby="model-label"
               class="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 hidden" />
        <select id="model-select"
                aria-labelledby="model-label"
                class="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 hidden"></select>
        <datalist id="model-suggestions"></datalist>
        <p id="model-note" class="text-xs text-slate-500 mt-1" aria-live="polite"></p>
      </div>
```

(Removes the `<label for="model">` since `aria-labelledby="model-label"` now associates whichever control is visible. The `model-note` gets `aria-live="polite"` so model-load failures and "Loading models…" are announced.)

- [ ] **Step 3: Pre-set `aria-busy` on Run button**

In the Run button, add `aria-busy="false"`:

```html
        <button id="run-btn" type="submit"
                aria-busy="false"
                class="bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-700 px-4 py-2 rounded font-medium">
          Run
        </button>
```

(`setRunning` from Task 7 already toggles this attribute.)

- [ ] **Step 4: Verify with a screen reader**

If VoiceOver is available (macOS Cmd+F5):
- Tab through the form — every control announces its label
- Trigger empty-state — `No providers reachable` is announced immediately (assertive)
- Start a run — `Run, busy` announces; status log does NOT torrent every event
- Use VO+U to navigate to the status log when curious

If no screen reader handy: open Chrome DevTools → Accessibility tab, inspect each control, verify `name` is non-empty and roles are correct.

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html
git commit -m "feat(frontend): a11y — role=log on status panel, label association on model controls"
```

---

## Task 10: Frontend — vendor Tailwind for offline robustness

**Files:**
- Create: `frontend/tailwind.js` (vendored standalone)
- Modify: `frontend/index.html` (script src)

**Why:** Item 7. `https://cdn.tailwindcss.com` is a third-party network dep. Launcher breaks on planes, spotty wifi, captive portals. Vendor it once.

- [ ] **Step 1: Download the standalone Tailwind script**

```bash
cd /Volumes/T7/PromptPressure
curl -L --fail -o frontend/tailwind.js https://cdn.tailwindcss.com
ls -lh frontend/tailwind.js  # expect ~290KB
```

If the curl fails, try `https://cdn.tailwindcss.com/3.4.0` or whichever is the current pinned version. Pin the version in the filename comment if so:

```bash
head -1 frontend/tailwind.js  # confirm it's a JS file, not an HTML error page
```

- [ ] **Step 2: Update `index.html` script reference**

Change:

```html
<script src="https://cdn.tailwindcss.com"></script>
```

to:

```html
<script src="/tailwind.js"></script>
```

(FastAPI's `StaticFiles` mount on `frontend/` already serves this path. Confirm by visiting `http://localhost:<port>/tailwind.js` after starting the launcher.)

- [ ] **Step 3: Verify offline behavior**

Disable wifi (or run `sudo route add -host cdn.tailwindcss.com 127.0.0.1` to blackhole the CDN). Run `pp`. The launcher should render with full Tailwind styling.

- [ ] **Step 4: Commit**

```bash
git add frontend/tailwind.js frontend/index.html
git commit -m "build(frontend): vendor Tailwind for offline launcher"
```

---

## Task 11: Cleanup — drop dead module-scope state

**Files:**
- Modify: `frontend/app.js`

**Why:** marko gripe #7. `let providers = [];` and `let evalSets = [];` are populated in `init()` then never read again. YAGNI.

- [ ] **Step 1: Drop the unused module-scope vars**

In `frontend/app.js`, near the top (currently lines 20–22):

```javascript
let providers = [];
let evalSets = [];
let currentEventSource = null;
```

Becomes:

```javascript
let currentEventSource = null;
```

In `init()`, change:

```javascript
providers = provs;
evalSets = sets;
```

to (just drop those two lines — `provs` and `sets` are local and used directly via `populateProviders(available)` / `populateEvalSets(sets)`):

```javascript
// (removed)
```

- [ ] **Step 2: Search for any other reference**

```bash
grep -n 'providers\|evalSets' frontend/app.js | grep -v 'els\.providers\|els\.evalSets\|const provs\|const sets'
```

Expected: no output (other than function param names). If anything remains, decide keep or drop based on whether it's actually read.

- [ ] **Step 3: Verify**

```bash
pp
```

Smoke test the full happy path — load → pick provider → pick eval set → Run → complete. No regressions.

- [ ] **Step 4: Commit**

```bash
git add frontend/app.js
git commit -m "refactor(frontend): drop unused module-scope providers/evalSets vars"
```

---

## Task 12: Verification — `/qa` + marko re-check

**Files:** none (verification only)

**Why:** Frontend has no JS test runner. Verification happens via real browser exercise (`/qa`) + a marko taste re-check now that the code is clean.

- [ ] **Step 1: Run `/qa` against the launcher**

The launcher is a localhost web app served by FastAPI. `/qa` drives a real browser through it.

```bash
cd /Volumes/T7/PromptPressure
pp &
PP_PID=$!
sleep 2
# /qa requires the URL — capture from `pp` output or hit /health
PP_URL=$(curl -s http://localhost:$(lsof -i -P -n | grep python.*LISTEN | grep -v 127 | head -1 | awk -F: '{print $2}' | awk '{print $1}')/health | jq -r .launcher_url 2>/dev/null)
```

Or just open the launcher manually with `pp`, copy the URL from the browser, and pass to `/qa`. Run the QA skill against that URL.

Acceptance criteria for `/qa`:
- Happy path: pick provider → pick eval set → Run → status panel streams events → completes cleanly
- Error path: submit with no model selected → red error in status panel, no crash
- Race path: rapidly switch providers → final model list matches last selection
- Cancel path: start a run, click Cancel → stream closes, "cancelled by user" red line, form re-enables
- Empty state: stop ollama, unset OPENROUTER_API_KEY, refresh → bulleted hints rendered

- [ ] **Step 2: Marko re-check**

After `/qa` passes, run marko on the diff:

```bash
git -C /Volumes/T7/PromptPressure diff main...HEAD -- frontend/ promptpressure/api.py
```

Marko's verdict on the post-fix diff should be at minimum **mediocre**, ideally **ok**. If marko returns **bad** again, the gripes raised are in scope for follow-up before `/ship`.

- [ ] **Step 3: Manual SSE drop test**

This isn't easy to script reliably — do it once by hand:

```bash
pp  # in one terminal
# In browser, start a long eval (e.g., 50-prompt eval set)
# In another terminal:
PP_PID=$(pgrep -f "uvicorn.*promptpressure")
kill -STOP $PP_PID
sleep 5
kill -CONT $PP_PID
```

Verify the status panel showed `connection lost, retrying…` (red) and then resumed streaming. Run does NOT re-enable until the actual eval completes.

- [ ] **Step 4: Commit nothing**

This task is verification only — no code commits expected. If `/qa` or marko surfaced a real bug, fix it as a NEW task and append to this plan.

- [ ] **Step 5: Hand off to `/ship`**

Once verification passes, the branch is ready for `/ship`. Pre-ship: marko auto-pulls per the trigger rules (>50-line diff on a launcher feature), so expect one more taste verdict before the PR is created.

```bash
# Joe runs:
/ship
```

---

## Notes

- **Branch:** all work lands on `feat/launcher`. No worktree needed.
- **No new dependencies:** Tailwind is vendored as a static file; no package manager touched.
- **Commit cadence:** 11 commits expected (12 tasks, Task 12 is verification only).
- **Order:** Recommended order: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12. Dependencies:
  - Task 4 introduces `state.freeText`, used by Task 5
  - Task 5 includes a stub `renderEmptyState` that Task 8 replaces with the per-provider hint render
  - Task 8 needs Task 1's backend field on `/providers`
  - Tasks 2 (`appendLine`), 3 (`fetchJSON` w/ signal), 6 (`closeStream`), 7 (`setRunning`) are referenced by later tasks — implement helpers before consumers
- **Rollback:** each commit is atomic; `git revert <sha>` rolls back any single task without affecting others.
