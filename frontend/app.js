(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const els = {
    loading: $("loading"),
    empty: $("empty"),
    form: $("run-form"),
    provider: $("provider"),
    model: $("model"),
    modelSelect: $("model-select"),
    modelDatalist: $("model-suggestions"),
    modelNote: $("model-note"),
    evalSets: $("eval-sets"),
    runBtn: $("run-btn"),
    cancelBtn: $("cancel-btn"),
    statusPanel: $("status-panel"),
    emptyHints: $("empty-hints"),
  };

  let providers = [];
  let evalSets = [];
  let currentEventSource = null;

  const state = {
    freeText: false,
    modelsAbort: null,  // AbortController for the currently in-flight /models fetch
  };

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

  function renderEmptyState(allProviders) {
    els.emptyHints.replaceChildren();
    for (const p of allProviders) {
      const li = document.createElement("li");
      li.textContent = `${p.label}: ${p.remediation_hint}`;
      els.emptyHints.appendChild(li);
    }
    els.empty.classList.remove("hidden");
  }

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

  function setRunning(running) {
    // All form inputs go disabled while a run is streaming so the visible config
    // matches the actual running job. Cancel becomes available; Run goes disabled
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

  async function fetchJSON(url, { signal, timeoutMs = 15000 } = {}) {
    const timeoutSignal = AbortSignal.timeout(timeoutMs);
    const composedSignal = signal
      ? AbortSignal.any([signal, timeoutSignal])
      : timeoutSignal;
    const r = await fetch(url, { signal: composedSignal });
    if (!r.ok) throw new Error(`${url} → ${r.status}`);
    return r.json();
  }

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
    els.cancelBtn.addEventListener("click", () => {
      closeStream();
      appendLine("cancelled by user", { error: true });
      setRunning(false);
    });
  }

  function populateProviders(list) {
    els.provider.innerHTML = "";
    for (const p of list) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.label;
      els.provider.appendChild(opt);
    }
  }

  function populateEvalSets(list) {
    els.evalSets.innerHTML = "";
    for (const s of list) {
      const wrap = document.createElement("label");
      wrap.className = "flex items-center gap-2 text-sm";

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.id = `eval-${s.id}`;
      cb.value = s.id;
      cb.className = "accent-emerald-500";

      const labelText = document.createElement("span");
      const main = document.createTextNode(s.label + " ");
      const countWrap = document.createElement("span");
      countWrap.className = "text-slate-500";
      countWrap.textContent = `(${s.count})`;
      labelText.appendChild(main);
      labelText.appendChild(countWrap);

      wrap.appendChild(cb);
      wrap.appendChild(labelText);
      els.evalSets.appendChild(wrap);
    }
  }

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

  function selectedModel() {
    return state.freeText ? els.model.value : els.modelSelect.value;
  }

  function selectedEvalSetIds() {
    return Array.from(els.evalSets.querySelectorAll("input[type=checkbox]:checked")).map((c) => c.value);
  }

  async function onSubmit(e) {
    e.preventDefault();
    const provider = els.provider.value;
    const model = selectedModel().trim();
    const ids = selectedEvalSetIds();
    if (!model) { appendLine("Pick or type a model.", { error: true }); return; }
    if (ids.length === 0) { appendLine("Pick at least one eval set.", { error: true }); return; }

    setRunning(true);
    clearStatusPanel();
    appendLine(`POST /evaluate provider=${provider} model=${model} eval_sets=${ids.join(",")}`);

    let body;
    try {
      const r = await fetch("/evaluate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          launcher_request: { provider, model, eval_set_ids: ids },
        }),
      });
      if (!r.ok) {
        const text = await r.text();
        throw new Error(text || `HTTP ${r.status}`);
      }
      body = await r.json();
    } catch (e) {
      appendLine("evaluate failed: " + e.message, { error: true });
      setRunning(false);
      return;
    }

    appendLine(`run_id=${body.run_id} streaming…`);
    closeStream();

    if (typeof body.stream_url !== "string" || body.stream_url.length === 0) {
      appendLine("evaluate returned no stream_url; aborting", { error: true });
      setRunning(false);
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
      setRunning(false);
    });

    currentEventSource.addEventListener("error", (ev) => {
      // EventSource fires the native `error` event for transport-level failures
      // (network drop, server reset) — in that case ev.data is undefined and the
      // browser will auto-reconnect unless we close. Server-emitted `event:error`
      // frames carry a data payload and should terminate the stream.
      if (ev.data) {
        appendLine("error: " + ev.data, { error: true });
        closeStream();
        setRunning(false);
      } else {
        // Transport hiccup — log once and let EventSource retry.
        appendLine("connection lost, retrying…", { error: true });
      }
    });
  }

  init();
})();
