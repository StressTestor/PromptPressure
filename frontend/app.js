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
    statusPanel: $("status-panel"),
  };

  let providers = [];
  let evalSets = [];
  let currentEventSource = null;

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

  async function fetchJSON(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${url} → ${r.status}`);
    return r.json();
  }

  async function init() {
    try {
      const [provs, sets] = await Promise.all([
        fetchJSON("/providers"),
        fetchJSON("/eval-sets"),
      ]);
      providers = provs;
      evalSets = sets;
    } catch (e) {
      els.loading.textContent = "Failed to load: " + e.message;
      return;
    }

    const available = providers.filter((p) => p.available);
    if (available.length === 0) {
      els.loading.classList.add("hidden");
      els.empty.classList.remove("hidden");
      return;
    }

    populateProviders(available);
    populateEvalSets(evalSets);
    await onProviderChange();

    els.loading.classList.add("hidden");
    els.form.classList.remove("hidden");
    els.provider.addEventListener("change", onProviderChange);
    els.form.addEventListener("submit", onSubmit);
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
    let payload;
    try {
      payload = await fetchJSON(`/models?provider=${encodeURIComponent(provider)}`);
    } catch (e) {
      els.modelNote.textContent = "Failed to load models: " + e.message;
      return;
    }
    if (payload.free_text) {
      els.modelSelect.classList.add("hidden");
      els.model.classList.remove("hidden");
      els.modelDatalist.innerHTML = "";
      for (const m of payload.models || []) {
        const o = document.createElement("option");
        o.value = m;
        els.modelDatalist.appendChild(o);
      }
      els.model.value = "";
    } else {
      els.model.classList.add("hidden");
      els.modelSelect.classList.remove("hidden");
      els.modelSelect.innerHTML = "";
      for (const m of payload.models || []) {
        const o = document.createElement("option");
        o.value = m;
        o.textContent = m;
        els.modelSelect.appendChild(o);
      }
    }
    els.modelNote.textContent = payload.note || "";
  }

  function selectedModel() {
    return els.model.classList.contains("hidden") ? els.modelSelect.value : els.model.value;
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

    els.runBtn.disabled = true;
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
      els.runBtn.disabled = false;
      return;
    }

    appendLine(`run_id=${body.run_id} streaming…`);
    if (currentEventSource) { currentEventSource.close(); }

    currentEventSource = new EventSource(body.stream_url);
    currentEventSource.onmessage = (ev) => {
      let parsed = ev.data;
      try { parsed = JSON.stringify(JSON.parse(ev.data)); } catch (_) {}
      appendLine(parsed);
    };
    currentEventSource.addEventListener("start_prompt", (ev) => {
      let parsed = ev.data;
      try { parsed = "start: " + JSON.stringify(JSON.parse(ev.data)); } catch (_) {}
      appendLine(parsed);
    });
    currentEventSource.addEventListener("end_prompt", (ev) => {
      let parsed = ev.data;
      try { parsed = "end:   " + JSON.stringify(JSON.parse(ev.data)); } catch (_) {}
      appendLine(parsed);
    });
    currentEventSource.addEventListener("complete", (ev) => {
      appendLine("complete: " + ev.data);
      currentEventSource.close();
      els.runBtn.disabled = false;
    });
    currentEventSource.addEventListener("error", (ev) => {
      const data = ev.data || "(connection error)";
      appendLine("error: " + data, { error: true });
      currentEventSource.close();
      els.runBtn.disabled = false;
    });
  }

  init();
})();
