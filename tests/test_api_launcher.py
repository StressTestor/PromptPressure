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
