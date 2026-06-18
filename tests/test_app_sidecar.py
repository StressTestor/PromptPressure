import asyncio
import importlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import promptpressure.api as api_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTPRESSURE_APP_SUPPORT_DIR", str(tmp_path / "Application Support" / "PromptPressure"))
    importlib.reload(api_module)
    with TestClient(api_module.app) as c:
        yield c


def test_health_includes_sidecar_paths(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["sidecar"] is True
    assert body["theme_suffix"] == ".pp-theme.json"
    assert "outputs" in body["data_paths"]
    assert "themes" in body["data_paths"]


def test_app_metadata_includes_provider_path(client):
    r = client.get("/app/metadata")
    assert r.status_code == 200
    body = r.json()
    assert "providers" in body["paths"]
    assert Path(body["paths"]["providers"]).exists()


def test_app_metadata_creates_support_dirs(client):
    r = client.get("/app/metadata")
    assert r.status_code == 200
    body = r.json()
    assert body["theme_schema_version"] == 1
    assert body["locked_drift_colors"] == {
        "hold": "#20B7A8",
        "partial": "#F0B24A",
        "drift": "#F05D7F",
    }
    for path in body["paths"].values():
        assert Path(path).exists()


def test_app_configs_discovers_yaml_configs(client):
    r = client.get("/app/configs")
    assert r.status_code == 200
    configs = r.json()["configs"]
    mock = next(c for c in configs if c["id"] == "config_mock.yaml")
    assert mock["valid"] is True
    assert mock["adapter"] == "mock"
    assert mock["model"]


def test_app_outputs_discovers_reports(client, tmp_path, monkeypatch):
    outputs = tmp_path / "outputs"
    run_dir = outputs / "2026-06-18_12-00-00"
    run_dir.mkdir(parents=True)
    (run_dir / "report.html").write_text("<html></html>", encoding="utf-8")
    (run_dir / "metrics.json").write_text("{}", encoding="utf-8")

    monkeypatch.setenv("PROMPTPRESSURE_OUTPUT_DIR", str(outputs))
    importlib.reload(api_module)
    with TestClient(api_module.app) as c:
        r = c.get("/app/outputs")

    assert r.status_code == 200
    item = next(o for o in r.json()["outputs"] if o["name"] == run_dir.name)
    assert item["report_html"].endswith("report.html")
    assert item["metrics_json"].endswith("metrics.json")


def test_app_themes_loads_valid_and_reports_invalid(client):
    metadata = client.get("/app/metadata").json()
    themes_dir = Path(metadata["paths"]["themes"])

    (themes_dir / "drift-studio.pp-theme.json").write_text(json.dumps({
        "schemaVersion": 1,
        "id": "drift-studio-custom",
        "name": "Drift Studio Custom",
        "base": "dark",
        "accent": "#5269FF",
        "density": "compact",
        "chartIntensity": "high",
        "surfaces": {"panel": "#242733"},
    }), encoding="utf-8")
    (themes_dir / "bad.pp-theme.json").write_text(json.dumps({
        "schemaVersion": 1,
        "id": "bad",
        "name": "Bad",
        "base": "dark",
        "accent": "#5269FF",
        "density": "compact",
        "chartIntensity": "high",
        "surfaces": {"drift": "#000000"},
    }), encoding="utf-8")

    r = client.get("/app/themes")
    assert r.status_code == 200
    body = r.json()
    assert any(t["id"] == "signal-dark" for t in body["built_in"])
    assert any(t["id"] == "drift-studio-custom" for t in body["custom"])
    invalid = next(i for i in body["invalid"] if i["name"] == "bad.pp-theme.json")
    assert "locked drift semantics" in invalid["error"]


def test_app_providers_loads_valid_and_reports_invalid(client):
    metadata = client.get("/app/metadata").json()
    providers_dir = Path(metadata["paths"]["providers"])

    (providers_dir / "acme.pp-provider.json").write_text(json.dumps({
        "schemaVersion": 1,
        "id": "acme",
        "name": "Acme Gateway",
        "apiStyle": "openai_chat",
        "baseURL": "https://api.example.test/v1/chat/completions",
        "apiKeyEnv": "ACME_API_KEY",
        "models": ["acme-fast", "acme-pro"],
    }), encoding="utf-8")
    (providers_dir / "bad.pp-provider.json").write_text(json.dumps({
        "schemaVersion": 1,
        "id": "bad",
        "name": "Bad Provider",
        "apiStyle": "unsupported",
        "baseURL": "https://api.example.test/v1/chat/completions",
        "apiKeyEnv": "BAD_API_KEY",
        "models": ["bad"],
    }), encoding="utf-8")

    r = client.get("/app/providers")
    assert r.status_code == 200
    body = r.json()
    assert any(p["id"] == "mock" for p in body["built_in"])
    custom = next(p for p in body["custom"] if p["id"] == "acme")
    assert custom["api_style"] == "openai_chat"
    invalid = next(i for i in body["invalid"] if i["name"] == "bad.pp-provider.json")
    assert "apiStyle" in invalid["error"]

    providers = client.get("/providers").json()
    acme = next(p for p in providers if p["id"] == "acme")
    assert acme["available"] is False
    assert "ACME_API_KEY" in acme["reason"]

    models = client.get("/models?provider=acme").json()
    assert models["models"] == ["acme-fast", "acme-pro"]
    assert models["free_text"] is True


def test_app_evaluation_job_completes_with_authoritative_status(client, monkeypatch):
    captured = {}

    async def fake_suite(config_dict, adapter):
        captured["config"] = dict(config_dict)
        callback = config_dict["_callback"]
        await callback("start_prompt", {"current": 1, "total": 2, "id": "a"})
        await callback("end_prompt", {"current": 1, "total": 2, "id": "a", "success": True})
        return [], str(Path(config_dict["output_dir"]) / "mock-output")

    monkeypatch.setattr(api_module, "run_evaluation_suite", fake_suite)
    r = client.post("/app/jobs/evaluations", json={
        "provider": "mock",
        "model": "mock-model",
        "eval_set_ids": ["evals_dataset.json", "evals_tone_sycophancy.json"],
    })
    assert r.status_code == 200
    job = r.json()
    assert job["status"] in {"queued", "running", "completed"}

    detail = client.get(f"/app/jobs/{job['id']}").json()
    assert detail["status"] == "completed"
    assert detail["phase"] == "completed"
    assert detail["progress"]["completed"] == 1
    assert detail["progress"]["total"] == 2
    assert detail["summary"]["eval_sets"] == ["evals_dataset.json", "evals_tone_sycophancy.json"]
    assert detail["id"] == captured["config"]["_evaluation_id"]
    assert captured["config"]["eval_set_ids"] == ["evals_dataset.json", "evals_tone_sycophancy.json"]
    assert captured["config"]["dataset"] == "evals_dataset.json"


def test_app_job_terminal_event_replays_after_completion(client, monkeypatch):
    async def fake_suite(config_dict, adapter):
        await config_dict["_callback"]("end_prompt", {"current": 1, "total": 1, "id": "a"})

    monkeypatch.setattr(api_module, "run_evaluation_suite", fake_suite)
    job = client.post("/app/jobs/evaluations", json={
        "provider": "mock",
        "model": "mock-model",
        "eval_set_ids": ["evals_dataset.json"],
    }).json()

    with client.stream("GET", f"/app/jobs/{job['id']}/events") as response:
        body = "".join(response.iter_text())
    assert "event: completed" in body
    assert "Evaluation finished" in body


def test_app_drift_jobs_are_typed_and_complete_without_shelling(client, monkeypatch):
    async def fake_drift_run(job, payload):
        return {
            "suite": payload["suite"],
            "provider": payload["provider"],
            "model": payload["model"],
            "outputs": [{"name": "transcripts.json", "path": "/tmp/transcripts.json", "kind": "file"}],
            "summary": {"sequences": 3, "turns": 9},
        }

    monkeypatch.setattr(api_module, "_execute_drift_run_job", fake_drift_run)
    r = client.post("/app/jobs/drift/run", json={
        "suite": "drift-v0.1",
        "provider": "mock",
        "model": "mock-model",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "drift_run"
    assert body["status"] in {"queued", "running", "completed"}
    detail = client.get(f"/app/jobs/{body['id']}").json()
    assert detail["status"] == "completed"
    assert detail["summary"]["sequences"] == 3


def test_risky_operations_require_confirmation(client):
    r = client.post("/plugins/install", json={"name": "demo"})
    assert r.status_code == 409
    assert "confirmation" in r.json()["detail"].lower()

    r = client.delete("/ollama/models/llama3.2")
    assert r.status_code == 409
    assert "confirmation" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cancelled_background_run_publishes_cancelled(monkeypatch):
    import promptpressure.api as api

    async def slow_suite(config_dict, adapter):
        await asyncio.sleep(60)

    monkeypatch.setattr(api, "run_evaluation_suite", slow_suite)
    api.bus.start("cancel-me")
    task = asyncio.create_task(api.run_eval_background("cancel-me", {"adapter": "mock"}))
    await asyncio.sleep(0.05)

    assert api.bus.cancel("cancel-me") is True
    await asyncio.wait_for(task, timeout=1)

    completion = api.bus._runs["cancel-me"]["completion_event"]
    assert completion == {"event": "cancelled", "data": "Evaluation cancelled"}
