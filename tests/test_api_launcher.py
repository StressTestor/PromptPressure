"""Integration tests for the launcher endpoints and the RunBus-backed /evaluate flow."""
import importlib
import os

import pytest
from fastapi.testclient import TestClient

import promptpressure.api as api_module


@pytest.fixture
def client():
    importlib.reload(api_module)
    with TestClient(api_module.app) as c:
        yield c


def test_module_import_raises_without_auth_or_dev_flag(monkeypatch):
    monkeypatch.delenv("PROMPTPRESSURE_API_SECRET", raising=False)
    monkeypatch.delenv("PROMPTPRESSURE_DEV_NO_AUTH", raising=False)
    with pytest.raises(RuntimeError, match="PROMPTPRESSURE_API_SECRET"):
        importlib.reload(api_module)
    monkeypatch.setenv("PROMPTPRESSURE_DEV_NO_AUTH", "1")
    importlib.reload(api_module)  # restore for downstream tests


def test_evaluate_rejects_neither_config_nor_launcher(client):
    r = client.post("/evaluate", json={})
    assert r.status_code == 422


def test_evaluate_rejects_both_config_and_launcher(client):
    r = client.post("/evaluate", json={
        "config": {"adapter": "mock", "model": "x", "model_name": "x",
                   "dataset": "evals_dataset.json", "output": "x.csv"},
        "launcher_request": {"provider": "mock", "model": "x",
                             "eval_set_ids": ["evals_dataset.json"]},
    })
    assert r.status_code == 422


def test_evaluate_with_launcher_request_returns_run_id(client, monkeypatch):
    # Stub the suite runner so we don't actually call any adapters
    import promptpressure.api
    async def fake_run_evaluation_suite(config_dict, adapter):
        cb = config_dict.get("_callback")
        if cb:
            await cb("progress", "1/1")
    monkeypatch.setattr(promptpressure.api, "run_evaluation_suite", fake_run_evaluation_suite)

    r = client.post("/evaluate", json={
        "launcher_request": {
            "provider": "mock",
            "model": "test-model",
            "eval_set_ids": ["evals_dataset.json"],
        },
    })
    assert r.status_code == 200
    body = r.json()
    assert "run_id" in body
    assert body["status"] == "started"
    assert body["stream_url"] == f"/stream/{body['run_id']}"


def test_evaluate_with_config_dict_returns_run_id(client, monkeypatch):
    """Legacy {config: {...}} path must still validate and dispatch."""
    import promptpressure.api
    async def fake_run_evaluation_suite(config_dict, adapter):
        pass
    monkeypatch.setattr(promptpressure.api, "run_evaluation_suite", fake_run_evaluation_suite)

    r = client.post("/evaluate", json={
        "config": {
            "adapter": "mock",
            "model": "test-model",
            "model_name": "test-model",
            "dataset": "evals_dataset.json",
            "output": "test.csv",
        },
    })
    assert r.status_code == 200
    body = r.json()
    assert "run_id" in body
    assert body["status"] == "started"


def test_stream_unknown_run_id_returns_404(client):
    r = client.get("/stream/does-not-exist")
    assert r.status_code == 404


def test_providers_returns_list(client):
    r = client.get("/providers")
    assert r.status_code == 200
    body = r.json()
    ids = {p["id"] for p in body}
    assert {"ollama", "openrouter", "groq", "mock", "litellm",
            "openai", "deepseek", "claude_code", "opencode", "lmstudio"} >= ids
    assert {"ollama", "mock"} <= ids


def test_providers_mock_always_available(client):
    r = client.get("/providers")
    mock_entry = next(p for p in r.json() if p["id"] == "mock")
    assert mock_entry["available"] is True


def test_providers_groq_unavailable_without_key(client, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    # Bust the cache
    from promptpressure.api import _providers_cache
    _providers_cache.clear()
    r = client.get("/providers")
    groq_entry = next(p for p in r.json() if p["id"] == "groq")
    assert groq_entry["available"] is False
    assert "GROQ_API_KEY" in (groq_entry.get("reason") or "")


def test_models_unknown_provider_returns_400(client):
    r = client.get("/models?provider=does-not-exist")
    assert r.status_code == 400


def test_models_provider_query_required(client):
    r = client.get("/models")
    assert r.status_code == 422


def test_models_openrouter_returns_free_text_with_suggestions(client):
    from promptpressure.api import _models_cache
    _models_cache.clear()
    r = client.get("/models?provider=openrouter")
    assert r.status_code == 200
    body = r.json()
    assert body["free_text"] is True
    assert isinstance(body["models"], list)
    # The note should mention typing
    assert "type" in (body.get("note") or "").lower()


def test_models_cache_keyed_by_provider(client):
    from promptpressure.api import _models_cache
    _models_cache.clear()
    r1 = client.get("/models?provider=openrouter")
    r2 = client.get("/models?provider=groq")
    assert r1.json() != r2.json()
    # Both should be cached now under separate keys
    assert len(_models_cache) == 2


def test_models_mock_returns_free_text(client):
    from promptpressure.api import _models_cache
    _models_cache.clear()
    r = client.get("/models?provider=mock")
    assert r.status_code == 200
    body = r.json()
    assert body["free_text"] is True


def test_eval_sets_lists_dataset_files(client):
    from promptpressure.api import _eval_sets_cache
    _eval_sets_cache.clear()
    r = client.get("/eval-sets")
    assert r.status_code == 200
    body = r.json()
    ids = {e["id"] for e in body}
    assert "evals_dataset.json" in ids
    assert "evals_tone_sycophancy.json" in ids


def test_eval_sets_includes_count(client):
    from promptpressure.api import _eval_sets_cache
    _eval_sets_cache.clear()
    r = client.get("/eval-sets")
    body = r.json()
    main = next(e for e in body if e["id"] == "evals_dataset.json")
    assert main["count"] >= 1


def test_eval_sets_no_configs_present(client):
    """Configs MUST NOT appear in /eval-sets (Finding #3 → A)."""
    from promptpressure.api import _eval_sets_cache
    _eval_sets_cache.clear()
    r = client.get("/eval-sets")
    ids = {e["id"] for e in r.json()}
    assert not any(i.endswith(".yaml") for i in ids)
    assert not any("config_" in i for i in ids)


def test_health_no_launcher_field_by_default(client, monkeypatch):
    monkeypatch.delenv("PROMPTPRESSURE_LAUNCHER", raising=False)
    importlib.reload(api_module)
    with TestClient(api_module.app) as c:
        r = c.get("/health")
    body = r.json()
    assert body["status"] == "ok"
    assert "launcher" not in body or body["launcher"] is False


def test_health_launcher_true_when_env_set(monkeypatch):
    monkeypatch.setenv("PROMPTPRESSURE_LAUNCHER", "1")
    importlib.reload(api_module)
    with TestClient(api_module.app) as c:
        r = c.get("/health")
    assert r.json().get("launcher") is True


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


def test_openrouter_remediation_hint_exact(client):
    """Pin the exact spec string for openrouter so edits don't silently break it."""
    r = client.get("/providers")
    openrouter = next(p for p in r.json() if p["id"] == "openrouter")
    assert openrouter["remediation_hint"] == "Set OPENROUTER_API_KEY in your environment."


@pytest.mark.asyncio
async def test_provider_status_fallback_hint():
    """Fallback hint format is correct for unknown provider IDs."""
    from promptpressure.api import _provider_status
    defn = {"id": "unknown_provider", "label": "Unknown"}
    result = await _provider_status(defn)
    assert result["remediation_hint"] == "Configure unknown_provider (see project README)."


def test_static_root_serves_index_html(client, tmp_path, monkeypatch):
    """When frontend/index.html exists, GET / returns the page."""
    import pathlib
    frontend = pathlib.Path("frontend")
    frontend.mkdir(exist_ok=True)
    idx = frontend / "index.html"
    idx_existed = idx.exists()
    if not idx_existed:
        idx.write_text("<html><body>placeholder</body></html>")
    try:
        importlib.reload(api_module)
        with TestClient(api_module.app) as c:
            r = c.get("/")
        assert r.status_code == 200
        assert "html" in r.headers.get("content-type", "").lower()
    finally:
        if not idx_existed:
            idx.unlink()


@pytest.mark.asyncio
async def test_run_eval_background_publishes_error_on_systemexit(monkeypatch):
    """Regression: cli.py's `sys.exit(1)` (e.g., 'Tier matched 0 entries') raises
    SystemExit, which is BaseException — not caught by `except Exception`. The
    background task crashed silently, the SSE stream stayed open with no events,
    and the frontend hung on 'streaming…' until the user clicked Cancel.

    Verify the broadened `except (Exception, SystemExit)` now catches it and
    publishes event:error with a descriptive payload."""
    import promptpressure.api as api

    async def fake_suite(config_dict, adapter):
        import sys
        sys.exit(1)
    monkeypatch.setattr(api, "run_evaluation_suite", fake_suite)

    api.bus.start("test-systemexit")
    await api.run_eval_background("test-systemexit", {"adapter": "mock"})

    entry = api.bus._runs["test-systemexit"]
    assert entry["completed"] is True
    completion = entry["completion_event"]
    assert completion["event"] == "error"
    assert "1" in completion["data"], (
        f"error data should mention exit code; got: {completion['data']!r}"
    )


@pytest.mark.asyncio
async def test_run_eval_background_json_encodes_dict_payloads(monkeypatch):
    """Regression: SSE data was published as Python dict, then sse-starlette
    serialized via str() yielding Python repr {'k': 'v'} (single-quoted) instead
    of valid JSON. Frontend's JSON.parse(ev.data) silently fell back to raw
    string display, showing Python repr in the status panel.

    Verify the log_callback now JSON-encodes dict/list payloads so the SSE
    `data:` field is parseable JSON."""
    import promptpressure.api as api
    import json as _json

    async def fake_suite(config_dict, adapter):
        cb = config_dict["_callback"]
        await cb("start_prompt", {"id": "tc_001", "prompt": "x"})
        await cb("end_prompt", {"id": "tc_001", "success": True, "latency": 0.5})

    monkeypatch.setattr(api, "run_evaluation_suite", fake_suite)

    api.bus.start("test-json-encode")
    await api.run_eval_background("test-json-encode", {"adapter": "mock"})

    entry = api.bus._runs["test-json-encode"]
    events = []
    while not entry["queue"].empty():
        events.append(entry["queue"].get_nowait())

    # Find the start_prompt + end_prompt events
    start_evt = next(e for e in events if e["event"] == "start_prompt")
    end_evt = next(e for e in events if e["event"] == "end_prompt")

    # data must be a JSON string, not a dict
    assert isinstance(start_evt["data"], str), (
        f"start_prompt data must be JSON string; got {type(start_evt['data']).__name__}"
    )
    parsed = _json.loads(start_evt["data"])
    assert parsed["id"] == "tc_001"
    assert parsed["prompt"] == "x"

    parsed_end = _json.loads(end_evt["data"])
    assert parsed_end["success"] is True


@pytest.mark.asyncio
async def test_run_eval_background_passes_string_payloads_through(monkeypatch):
    """JSON-encoding must only fire for dict/list — string payloads (e.g., the
    'progress' callback that emits '1/45') should pass through unchanged so the
    frontend doesn't see double-encoded strings."""
    import promptpressure.api as api

    async def fake_suite(config_dict, adapter):
        cb = config_dict["_callback"]
        await cb("progress", "1/45")

    monkeypatch.setattr(api, "run_evaluation_suite", fake_suite)

    api.bus.start("test-string-passthrough")
    await api.run_eval_background("test-string-passthrough", {"adapter": "mock"})

    entry = api.bus._runs["test-string-passthrough"]
    events = []
    while not entry["queue"].empty():
        events.append(entry["queue"].get_nowait())

    progress_evt = next(e for e in events if e["event"] == "progress")
    assert progress_evt["data"] == "1/45"  # not '"1/45"'
