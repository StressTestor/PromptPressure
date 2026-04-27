# PromptPressure Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a one-page web launcher (provider/model/eval-set + Run + SSE status) and a `pp` CLI command that spawns the API + opens the browser.

**Architecture:** Additive endpoints (`/providers`, `/models`, `/eval-sets`) on the existing FastAPI app, plus one backward-compatible schema change to `/evaluate` (accepts existing `{config: {...}}` OR new `{launcher_request: {...}}` via XOR validator). The flaky in-memory `EVENT_QUEUES` is replaced with a `RunBus` that survives SSE reconnects and gets reaped on a TTL. Frontend is vanilla HTML+JS+CSS served by `StaticFiles`. The `pp` command is a thin Python CLI: free-port discovery → subprocess uvicorn → `webbrowser.open`.

**Tech Stack:** FastAPI, pydantic v2, sse-starlette, httpx, cachetools, uvicorn, pytest + pytest-asyncio (auto), vanilla HTML/JS, Tailwind via CDN.

**Spec source:** [`docs/superpowers/plans/2026-04-25-launcher-spec.md`](./2026-04-25-launcher-spec.md). All 10 findings from that spec are addressed in this plan.

**Locked taste decisions (from autoplan, do not re-litigate):**
- Free-text + suggestions for non-ollama models (Finding #2 → A)
- Datasets only for `/eval-sets`, no configs (Finding #3 → A)
- SSE: drain-after-completion + 5min TTL + reaper (Finding #9 → B)

---

## File Structure

**New files:**
- `tests/conftest.py` — sets `PROMPTPRESSURE_DEV_NO_AUTH=1` at import (Finding #4)
- `promptpressure/run_bus.py` — `RunBus` class: per-run queue + completion state + reaper (Finding #9)
- `promptpressure/launcher_translate.py` — pure function `launcher_to_settings(req) -> dict` (Finding #1)
- `promptpressure/launcher.py` — `pp` CLI: port discovery, subprocess, browser (Findings #5, #6)
- `frontend/index.html` — page shell with provider/model/eval-set form + status panel
- `frontend/app.js` — fetch endpoints, render dropdowns, POST /evaluate, EventSource consume
- `frontend/styles.css` — minimal CSS (Tailwind via CDN handles most)
- `tests/test_run_bus.py` — RunBus unit tests (reconnect, TTL, reaper)
- `tests/test_launcher_translate.py` — translate function unit tests
- `tests/test_api_launcher.py` — integration tests for new endpoints + XOR validator
- `tests/test_launcher_cli.py` — port discovery + env helper unit tests
- `TODOS.md` — v2 deferred items

**Modified files:**
- `promptpressure/api.py` — `EvalRequest` XOR schema, `LauncherRequest` model, `RunBus` wiring, new `/providers` `/models` `/eval-sets` endpoints, `/health` launcher field, StaticFiles mount, dispatch helper, on-shutdown reaper cancellation
- `pyproject.toml` — add `pp = "promptpressure.launcher:main"` entry point, add `cachetools` dependency
- `README.md` — Launcher section
- `.gitignore` — `frontend/__pycache__` if any (only if needed)

---

## Task 1: Test infrastructure (conftest)

**Files:**
- Create: `tests/conftest.py`

**Why first:** every other test in this plan imports `promptpressure.api`, which raises `RuntimeError` at module import unless either `PROMPTPRESSURE_API_SECRET` or `PROMPTPRESSURE_DEV_NO_AUTH=1` is set (api.py:31, with the gate added in Task 3 — for now this just needs to exist for clean test runs going forward).

- [ ] **Step 1: Write the failing test**

Create `tests/test_conftest_smoke.py`:

```python
def test_conftest_sets_dev_no_auth():
    import os
    assert os.environ.get("PROMPTPRESSURE_DEV_NO_AUTH") == "1"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_conftest_smoke.py -v
```

Expected: FAIL — `PROMPTPRESSURE_DEV_NO_AUTH` is not in `os.environ`.

- [ ] **Step 3: Write conftest.py**

Create `tests/conftest.py`:

```python
"""
Test environment priming.

api.py raises RuntimeError at module import unless either PROMPTPRESSURE_API_SECRET
or PROMPTPRESSURE_DEV_NO_AUTH=1 is set. This conftest sets the dev flag so import works.

Tests verifying the prod auth path should set PROMPTPRESSURE_API_SECRET via
monkeypatch.setenv() and importlib.reload(promptpressure.api) inside the test.
"""
import os

os.environ.setdefault("PROMPTPRESSURE_DEV_NO_AUTH", "1")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_conftest_smoke.py -v
```

Expected: PASS.

- [ ] **Step 5: Run the full existing test suite to confirm no regression**

```bash
pytest -x --tb=short 2>&1 | tail -20
```

Expected: same pass/fail count as before this branch (the conftest only adds an env var; nothing should break).

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py tests/test_conftest_smoke.py
git commit -m "test(conftest): prime PROMPTPRESSURE_DEV_NO_AUTH for api import"
```

---

## Task 2: RunBus core (replaces EVENT_QUEUES)

**Files:**
- Create: `promptpressure/run_bus.py`
- Create: `tests/test_run_bus.py`

**What it does:** Per-run state machine. `start(run_id)` creates a queue. `publish(run_id, event)` pushes to the queue and bumps `last_active`. `mark_completed(run_id, summary)` flips `completed=True` and stores the final summary so late connections can replay it. `subscribe(run_id)` returns an async generator that drains the queue but does NOT pop the entry on disconnect (key bug fix). A separate `reap()` coroutine sweeps idle/old runs every 60s.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_run_bus.py`:

```python
import asyncio
import time
import pytest

from promptpressure.run_bus import RunBus


@pytest.mark.asyncio
async def test_publish_and_subscribe_basic():
    bus = RunBus()
    bus.start("run1")
    await bus.publish("run1", {"event": "progress", "data": "1/10"})
    await bus.publish("run1", {"event": "progress", "data": "2/10"})

    received = []
    async def consumer():
        async for item in bus.subscribe("run1"):
            received.append(item)
            if item.get("event") == "complete":
                break

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0.05)
    await bus.mark_completed("run1", {"event": "complete", "data": "done"})
    await asyncio.wait_for(task, timeout=1.0)

    assert [r["data"] for r in received] == ["1/10", "2/10", "done"]


@pytest.mark.asyncio
async def test_subscribe_after_completion_replays_summary():
    bus = RunBus()
    bus.start("run2")
    await bus.publish("run2", {"event": "progress", "data": "1/1"})
    await bus.mark_completed("run2", {"event": "complete", "data": "summary"})

    received = []
    async def consumer():
        async for item in bus.subscribe("run2"):
            received.append(item)
            if item.get("event") == "complete":
                break
    await asyncio.wait_for(consumer(), timeout=1.0)

    assert any(r.get("event") == "complete" and r.get("data") == "summary" for r in received)


@pytest.mark.asyncio
async def test_disconnect_does_not_pop_entry():
    bus = RunBus()
    bus.start("run3")
    await bus.publish("run3", {"event": "progress", "data": "x"})

    async def early_disconnect():
        async for item in bus.subscribe("run3"):
            return  # Drop after first item
    await early_disconnect()

    # Entry must still exist, queue still alive for reconnect
    assert "run3" in bus._runs


@pytest.mark.asyncio
async def test_reap_evicts_completed_after_ttl():
    bus = RunBus(completed_ttl=0.05, idle_ttl=10.0, reap_interval=0.02)
    bus.start("run4")
    await bus.mark_completed("run4", {"event": "complete", "data": "done"})

    bus._runs["run4"]["last_active"] = time.monotonic() - 1.0  # Force expiration

    await bus.reap_once()
    assert "run4" not in bus._runs


@pytest.mark.asyncio
async def test_reap_evicts_idle_runs():
    bus = RunBus(completed_ttl=300.0, idle_ttl=0.05, reap_interval=0.02)
    bus.start("run5")
    bus._runs["run5"]["last_active"] = time.monotonic() - 1.0  # Force idle expiration

    await bus.reap_once()
    assert "run5" not in bus._runs


@pytest.mark.asyncio
async def test_subscribe_unknown_run_raises():
    bus = RunBus()
    with pytest.raises(KeyError):
        async for _ in bus.subscribe("nope"):
            break


@pytest.mark.asyncio
async def test_reaper_lifecycle():
    bus = RunBus(reap_interval=0.02)
    await bus.start_reaper()
    assert bus._reaper_task is not None
    await bus.stop_reaper()
    assert bus._reaper_task is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_run_bus.py -v
```

Expected: ImportError (`promptpressure.run_bus` doesn't exist).

- [ ] **Step 3: Write run_bus.py**

Create `promptpressure/run_bus.py`:

```python
"""
RunBus: per-run event channel with completion replay and TTL reaping.

Replaces the original EVENT_QUEUES dict whose entries were popped on SSE
disconnect, breaking auto-reconnect and creating a memory leak when
EventSource never connected at all.

Lifecycle:
- start(run_id):                creates an entry, queue, last_active=now
- publish(run_id, event):       pushes event to queue, bumps last_active
- mark_completed(run_id, evt):  pushes the final event, flips completed=True
- subscribe(run_id):            async-iterates queue items; if completed at
                                subscribe-time, replays final event and exits
- reap_once() / reaper task:    deletes entries where (completed and idle > TTL)
                                or (any state and idle > idle_ttl)
"""
import asyncio
import logging
import time
from typing import Any, AsyncIterator, Dict, Optional


class RunBus:
    def __init__(
        self,
        completed_ttl: float = 300.0,   # 5 minutes
        idle_ttl: float = 1800.0,       # 30 minutes
        reap_interval: float = 60.0,
    ) -> None:
        self._runs: Dict[str, Dict[str, Any]] = {}
        self._completed_ttl = completed_ttl
        self._idle_ttl = idle_ttl
        self._reap_interval = reap_interval
        self._reaper_task: Optional[asyncio.Task] = None

    def start(self, run_id: str) -> None:
        self._runs[run_id] = {
            "queue": asyncio.Queue(),
            "completed": False,
            "completion_event": None,
            "last_active": time.monotonic(),
        }

    def has(self, run_id: str) -> bool:
        return run_id in self._runs

    async def publish(self, run_id: str, event: Dict[str, Any]) -> None:
        entry = self._runs.get(run_id)
        if entry is None:
            return
        entry["last_active"] = time.monotonic()
        await entry["queue"].put(event)

    async def mark_completed(self, run_id: str, completion_event: Dict[str, Any]) -> None:
        entry = self._runs.get(run_id)
        if entry is None:
            return
        entry["completed"] = True
        entry["completion_event"] = completion_event
        entry["last_active"] = time.monotonic()
        await entry["queue"].put(completion_event)

    async def subscribe(self, run_id: str) -> AsyncIterator[Dict[str, Any]]:
        entry = self._runs.get(run_id)
        if entry is None:
            raise KeyError(run_id)

        # If already completed, replay the completion event and exit.
        # (Queue may have been drained by a previous subscriber.)
        if entry["completed"] and entry["queue"].empty():
            yield entry["completion_event"]
            return

        try:
            while True:
                item = await entry["queue"].get()
                entry["last_active"] = time.monotonic()
                if item is None:
                    return
                yield item
                if entry["completed"] and entry["queue"].empty():
                    return
        except asyncio.CancelledError:
            # Subscriber went away — DO NOT pop the entry. The reaper handles eviction.
            raise

    async def reap_once(self) -> None:
        now = time.monotonic()
        to_delete = []
        for run_id, entry in self._runs.items():
            idle = now - entry["last_active"]
            if entry["completed"] and idle > self._completed_ttl:
                to_delete.append(run_id)
            elif idle > self._idle_ttl:
                to_delete.append(run_id)
        for rid in to_delete:
            logging.info("RunBus reaped run %s", rid)
            self._runs.pop(rid, None)

    async def _reaper_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._reap_interval)
                await self.reap_once()
        except asyncio.CancelledError:
            return

    async def start_reaper(self) -> None:
        if self._reaper_task is None:
            self._reaper_task = asyncio.create_task(self._reaper_loop())

    async def stop_reaper(self) -> None:
        if self._reaper_task is not None:
            self._reaper_task.cancel()
            try:
                await self._reaper_task
            except asyncio.CancelledError:
                pass
            self._reaper_task = None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_run_bus.py -v
```

Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add promptpressure/run_bus.py tests/test_run_bus.py
git commit -m "feat(run_bus): per-run event channel with reconnect + TTL reaper"
```

---

## Task 3: launcher_translate — pure mapper from LauncherRequest to Settings dict

**Files:**
- Create: `promptpressure/launcher_translate.py`
- Create: `tests/test_launcher_translate.py`

**What it does:** Pure function that takes a validated `LauncherRequest` (provider + model + eval_set_ids) and returns a dict suitable for `Settings(**dict)`. Datasets are concatenated when multiple eval_set_ids are given; output filenames are derived deterministically from `run_id`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_launcher_translate.py`:

```python
import pytest

from promptpressure.launcher_translate import (
    launcher_to_settings_dict,
    LauncherRequest,
)


def test_single_dataset_basic():
    req = LauncherRequest(
        provider="ollama",
        model="llama3.2:1b",
        eval_set_ids=["evals_dataset.json"],
    )
    settings = launcher_to_settings_dict(req, run_id="abc-123")

    assert settings["adapter"] == "ollama"
    assert settings["model"] == "llama3.2:1b"
    assert settings["model_name"] == "llama3.2:1b"
    assert settings["dataset"] == "evals_dataset.json"
    assert settings["output"] == "launcher_abc-123.csv"
    assert settings["tier"] == "quick"
    assert settings["temperature"] == 0.7


def test_multi_dataset_uses_first_with_note():
    """v1 takes the first eval set. Multi-set merging is a v2 TODO."""
    req = LauncherRequest(
        provider="ollama",
        model="llama3.2:1b",
        eval_set_ids=["evals_dataset.json", "evals_tone_sycophancy.json"],
    )
    settings = launcher_to_settings_dict(req, run_id="def-456")

    assert settings["dataset"] == "evals_dataset.json"


def test_provider_normalized_to_adapter_name():
    req = LauncherRequest(
        provider="OpenRouter",
        model="anthropic/claude-3-haiku",
        eval_set_ids=["evals_dataset.json"],
    )
    settings = launcher_to_settings_dict(req, run_id="xyz-789")

    assert settings["adapter"] == "openrouter"


def test_eval_set_ids_required_non_empty():
    with pytest.raises(ValueError):
        LauncherRequest(provider="ollama", model="x", eval_set_ids=[])


def test_dataset_id_path_traversal_rejected():
    """Reject relative paths or absolute paths — eval_set_ids are bare filenames only."""
    req = LauncherRequest(
        provider="ollama",
        model="llama3.2:1b",
        eval_set_ids=["../etc/passwd"],
    )
    with pytest.raises(ValueError, match="must be a bare filename"):
        launcher_to_settings_dict(req, run_id="bad")


def test_dataset_id_must_match_evals_pattern():
    req = LauncherRequest(
        provider="ollama",
        model="llama3.2:1b",
        eval_set_ids=["evals_dataset.json"],
    )
    settings = launcher_to_settings_dict(req, run_id="ok")
    assert settings["dataset"] == "evals_dataset.json"

    bad = LauncherRequest(
        provider="ollama",
        model="llama3.2:1b",
        eval_set_ids=["random_other.json"],
    )
    with pytest.raises(ValueError, match="must start with 'evals_'"):
        launcher_to_settings_dict(bad, run_id="bad")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_launcher_translate.py -v
```

Expected: ImportError.

- [ ] **Step 3: Write launcher_translate.py**

Create `promptpressure/launcher_translate.py`:

```python
"""
Translate a LauncherRequest from the web UI into a Settings dict.

Strict allowlist: dataset filenames must match `evals_*.json` and contain no
path separators, so the launcher cannot smuggle arbitrary paths into Settings.
"""
import re
from typing import List

from pydantic import BaseModel, Field, field_validator


_DATASET_RE = re.compile(r"^evals_[A-Za-z0-9_]+\.json$")


class LauncherRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=256)
    eval_set_ids: List[str] = Field(min_length=1, max_length=8)

    @field_validator("eval_set_ids")
    @classmethod
    def _validate_ids(cls, v: List[str]) -> List[str]:
        for entry in v:
            if "/" in entry or "\\" in entry or ".." in entry:
                raise ValueError(f"eval_set_id must be a bare filename, got: {entry!r}")
            if not _DATASET_RE.match(entry):
                raise ValueError(f"eval_set_id must start with 'evals_' and end '.json', got: {entry!r}")
        return v


def launcher_to_settings_dict(req: LauncherRequest, run_id: str) -> dict:
    """Map a LauncherRequest + run_id to a kwargs dict for Settings(**...)."""
    for entry in req.eval_set_ids:
        if "/" in entry or "\\" in entry or ".." in entry:
            raise ValueError(f"eval_set_id must be a bare filename, got: {entry!r}")
        if not _DATASET_RE.match(entry):
            raise ValueError(f"eval_set_id must start with 'evals_' and end '.json', got: {entry!r}")

    return {
        "adapter": req.provider.lower(),
        "model": req.model,
        "model_name": req.model,
        "dataset": req.eval_set_ids[0],
        "output": f"launcher_{run_id}.csv",
        "output_dir": "outputs",
        "temperature": 0.7,
        "tier": "quick",
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_launcher_translate.py -v
```

Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add promptpressure/launcher_translate.py tests/test_launcher_translate.py
git commit -m "feat(launcher): pure translator from LauncherRequest to Settings dict"
```

---

## Task 4: Wire RunBus + LauncherRequest into api.py

**Files:**
- Modify: `promptpressure/api.py`

**What changes:**
1. Add module-import auth gate (Finding #4): import-time `RuntimeError` unless `PROMPTPRESSURE_API_SECRET` or `PROMPTPRESSURE_DEV_NO_AUTH=1`.
2. Replace `EVENT_QUEUES` global with a singleton `RunBus`.
3. Add `LauncherRequest` import; extend `EvalRequest` with XOR validator.
4. Update `/evaluate` to dispatch via either path.
5. Update `/stream/{run_id}` to use `bus.subscribe()`.
6. Update `run_eval_background` to publish via the bus and mark completion.
7. Wire `bus.start_reaper()` / `bus.stop_reaper()` into FastAPI `startup` / `shutdown`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_launcher.py` (this file will grow across Tasks 4-8 — start it now):

```python
"""Integration tests for the launcher endpoints and the RunBus-backed /evaluate flow."""
import importlib
import os
import time

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


def test_stream_unknown_run_id_returns_404(client):
    r = client.get("/stream/does-not-exist")
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api_launcher.py -v
```

Expected: tests fail (no XOR validator, `LauncherRequest` doesn't exist on EvalRequest, no import-time gate).

- [ ] **Step 3: Modify api.py — top of file (imports, gate, RunBus, schemas)**

Replace lines 1-33 (imports + EVENT_QUEUES) of `promptpressure/api.py` with:

```python
import asyncio
import json
import logging
import os
import hmac
import hashlib
import time
from contextlib import asynccontextmanager
from typing import Dict, Any, AsyncGenerator, Optional, List

from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, model_validator

from promptpressure.config import Settings
from promptpressure.cli import run_evaluation_suite
from promptpressure.launcher_translate import LauncherRequest, launcher_to_settings_dict
from promptpressure.run_bus import RunBus

# Module-import auth gate (Finding #4 in the spec).
# Either PROMPTPRESSURE_API_SECRET or PROMPTPRESSURE_DEV_NO_AUTH=1 must be set
# or this module raises immediately. tests/conftest.py sets the dev flag.
if not os.getenv("PROMPTPRESSURE_API_SECRET") and os.getenv("PROMPTPRESSURE_DEV_NO_AUTH") != "1":
    raise RuntimeError(
        "PROMPTPRESSURE_API_SECRET is required, or set PROMPTPRESSURE_DEV_NO_AUTH=1 for local dev."
    )

bus = RunBus()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await bus.start_reaper()
    try:
        yield
    finally:
        await bus.stop_reaper()


app = FastAPI(title="PromptPressure API", version="3.1.0", lifespan=lifespan)

_default_origins = ["http://localhost:3000", "http://localhost:8000",
                    "http://127.0.0.1:3000", "http://127.0.0.1:8000"]
_cors_origins = (os.getenv("PROMPTPRESSURE_CORS_ORIGINS", "").split(",")
                 if os.getenv("PROMPTPRESSURE_CORS_ORIGINS")
                 else _default_origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

API_SECRET = os.getenv("PROMPTPRESSURE_API_SECRET")
```

(Keep `_verify_token` and `require_auth` as-is — they're untouched from current api.py.)

- [ ] **Step 4: Modify api.py — replace EvalRequest + /evaluate + /stream + run_eval_background**

Replace lines 67-106 (current `EvalRequest`, `/evaluate`, `/stream/{run_id}`) AND lines 249-267 (current `run_eval_background`) with:

```python
class EvalRequest(BaseModel):
    """
    Accepts EITHER the existing config dict OR the new launcher_request shape.
    Backward-compatible at the data level: existing {config: {...}} bodies
    still validate and dispatch identically.
    """
    config: Optional[Dict[str, Any]] = None
    launcher_request: Optional[LauncherRequest] = None

    @model_validator(mode="after")
    def exactly_one(self):
        if (self.config is None) == (self.launcher_request is None):
            raise ValueError("specify config OR launcher_request, not both")
        return self


@app.post("/evaluate", dependencies=[Depends(require_auth)])
async def trigger_evaluation(request: EvalRequest, background_tasks: BackgroundTasks):
    import uuid
    run_id = str(uuid.uuid4())

    if request.launcher_request is not None:
        config_dict = launcher_to_settings_dict(request.launcher_request, run_id=run_id)
    else:
        config_dict = dict(request.config)  # copy; we'll mutate _callback

    try:
        Settings(**config_dict)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    bus.start(run_id)
    background_tasks.add_task(run_eval_background, run_id, config_dict)
    return {"run_id": run_id, "status": "started", "stream_url": f"/stream/{run_id}"}


@app.get("/stream/{run_id}")
async def stream_events(run_id: str):
    from sse_starlette.sse import EventSourceResponse
    if not bus.has(run_id):
        raise HTTPException(status_code=404, detail="Run ID not found")

    async def event_generator() -> AsyncGenerator[dict, None]:
        async for item in bus.subscribe(run_id):
            yield item

    return EventSourceResponse(event_generator())


async def run_eval_background(run_id: str, config_dict: Dict[str, Any]):
    async def log_callback(event_type: str, data: Any):
        await bus.publish(run_id, {"event": event_type, "data": data})

    try:
        config_dict["_callback"] = log_callback
        await run_evaluation_suite(config_dict, config_dict.get("adapter"))
        await bus.mark_completed(run_id, {"event": "complete", "data": "Evaluation finished"})
    except Exception as e:
        logging.error(f"Run {run_id} failed: {e}")
        await bus.mark_completed(run_id, {"event": "error", "data": str(e)})
```

Delete the now-orphaned `EVENT_QUEUES` line and any references to it.

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_api_launcher.py tests/test_run_bus.py tests/test_launcher_translate.py -v
```

Expected: 5 new + 7 RunBus + 6 translate = 18 PASS.

- [ ] **Step 6: Run the full suite to confirm no regression**

```bash
pytest --tb=short 2>&1 | tail -10
```

Expected: previous-baseline pass count plus the new tests; nothing newly broken.

- [ ] **Step 7: Commit**

```bash
git add promptpressure/api.py tests/test_api_launcher.py
git commit -m "feat(api): RunBus + XOR launcher_request schema for /evaluate"
```

---

## Task 5: /providers endpoint

**Files:**
- Modify: `promptpressure/api.py`
- Modify: `tests/test_api_launcher.py`

**What it does:** GET `/providers` returns `[{id, label, available, reason}]` for the 9 adapters. `available` is true when:
- `mock`: always true
- `ollama`: `ollama_adapter.check_health()` resolves true
- everything else: a relevant API key env var is present (groq → `GROQ_API_KEY`, openrouter → `OPENROUTER_API_KEY`, openai → `OPENAI_API_KEY`, deepseek → `OPENROUTER_API_KEY`, claude_code → `ANTHROPIC_API_KEY`, opencode → no key check (CLI tool), litellm → at least one of: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `XAI_API_KEY`, `GROQ_API_KEY`, `GOOGLE_API_KEY`, `DEEPSEEK_API_KEY`, `LITELLM_API_KEY`, `lmstudio`: nothing to check at request time, mark available=true (it's a local server).

Cached for 60s, keyed by endpoint path (no query params here yet).

- [ ] **Step 1: Add cachetools dependency**

Edit `pyproject.toml`, in the `dependencies` list, add:

```toml
    "cachetools>=5.0,<6.0",
```

Then:

```bash
pip install -e .
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_api_launcher.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_api_launcher.py -v -k providers
```

Expected: 404 / not implemented.

- [ ] **Step 4: Implement /providers in api.py**

Add this section to `promptpressure/api.py` after the `lifespan` block:

```python
from cachetools import TTLCache

_providers_cache: TTLCache = TTLCache(maxsize=1, ttl=60)
_models_cache: TTLCache = TTLCache(maxsize=64, ttl=60)
_eval_sets_cache: TTLCache = TTLCache(maxsize=1, ttl=60)


_PROVIDER_DEFS: List[Dict[str, Any]] = [
    {"id": "mock", "label": "Mock (deterministic)"},
    {"id": "ollama", "label": "Ollama (local)"},
    {"id": "openrouter", "label": "OpenRouter", "env": "OPENROUTER_API_KEY"},
    {"id": "groq", "label": "Groq", "env": "GROQ_API_KEY"},
    {"id": "openai", "label": "OpenAI", "env": "OPENAI_API_KEY"},
    {"id": "deepseek", "label": "DeepSeek (via OpenRouter)", "env": "OPENROUTER_API_KEY"},
    {"id": "claude_code", "label": "Claude Code", "env": "ANTHROPIC_API_KEY"},
    {"id": "opencode", "label": "OpenCode (CLI)"},
    {"id": "lmstudio", "label": "LM Studio (local)"},
    {"id": "litellm", "label": "LiteLLM (multi-provider)",
     "env_any": ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY",
                 "XAI_API_KEY", "GROQ_API_KEY", "GOOGLE_API_KEY",
                 "DEEPSEEK_API_KEY", "LITELLM_API_KEY"]},
]


async def _provider_status(definition: Dict[str, Any]) -> Dict[str, Any]:
    pid = definition["id"]
    out: Dict[str, Any] = {"id": pid, "label": definition["label"], "available": False, "reason": None}

    if pid == "mock":
        out["available"] = True
        return out

    if pid == "ollama":
        from promptpressure.adapters import ollama_adapter
        try:
            healthy = await ollama_adapter.check_health()
        except Exception:
            healthy = False
        out["available"] = healthy
        out["reason"] = None if healthy else "ollama not reachable on http://localhost:11434"
        return out

    if "env" in definition:
        env = definition["env"]
        if os.getenv(env):
            out["available"] = True
        else:
            out["reason"] = f"{env} not set"
        return out

    if "env_any" in definition:
        present = [e for e in definition["env_any"] if os.getenv(e)]
        if present:
            out["available"] = True
        else:
            out["reason"] = f"none of {definition['env_any']} are set"
        return out

    # opencode / lmstudio: no env to check
    out["available"] = True
    return out


@app.get("/providers")
async def list_providers():
    cache_key = "providers"
    if cache_key in _providers_cache:
        return _providers_cache[cache_key]
    result = [await _provider_status(d) for d in _PROVIDER_DEFS]
    _providers_cache[cache_key] = result
    return result
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_api_launcher.py -v -k providers
```

Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml promptpressure/api.py tests/test_api_launcher.py
git commit -m "feat(api): /providers endpoint with availability detection"
```

---

## Task 6: /models endpoint (ollama dropdown + free-text suggestions)

**Files:**
- Modify: `promptpressure/api.py`
- Modify: `tests/test_api_launcher.py`

**What it does:** GET `/models?provider=X` returns `{models: [...], note: str|None, free_text: bool}`. For ollama, `models` is a real list from `ollama_adapter.list_models()`, `free_text=False`. For everything else, `models` is the deduplicated set of `model:` values across `configs/*.yaml` filtered by `adapter: X`, `free_text=True`, and `note` instructs the user to type their own. Cache key includes `provider` (Finding #8).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api_launcher.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api_launcher.py -v -k models
```

Expected: 404s.

- [ ] **Step 3: Implement /models**

Add to `promptpressure/api.py`:

```python
import glob

import yaml as _yaml


_VALID_PROVIDERS = {p["id"] for p in _PROVIDER_DEFS}


def _suggestions_from_configs(provider: str) -> List[str]:
    """Aggregate model: values across configs/*.yaml filtered by adapter:."""
    suggestions: List[str] = []
    for path in sorted(glob.glob("configs/*.yaml")):
        try:
            with open(path) as f:
                data = _yaml.safe_load(f) or {}
        except Exception:
            continue
        if (data.get("adapter") or "").lower() == provider.lower():
            m = data.get("model")
            if isinstance(m, str) and m and m not in suggestions:
                suggestions.append(m)
    return suggestions


@app.get("/models")
async def list_models(provider: str):
    if provider not in _VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    cache_key = ("models", provider)
    if cache_key in _models_cache:
        return _models_cache[cache_key]

    if provider == "ollama":
        from promptpressure.adapters import ollama_adapter
        try:
            raw = await ollama_adapter.list_models()
            models = [m.get("name") for m in raw if m.get("name")]
            payload = {"models": models, "note": None, "free_text": False}
        except Exception as e:
            payload = {"models": [], "note": f"ollama unavailable: {e}", "free_text": True}
    else:
        suggestions = _suggestions_from_configs(provider)
        payload = {
            "models": suggestions,
            "note": "Type any model id this provider accepts. Suggestions come from existing configs/*.yaml.",
            "free_text": True,
        }

    _models_cache[cache_key] = payload
    return payload
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_api_launcher.py -v -k models
```

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add promptpressure/api.py tests/test_api_launcher.py
git commit -m "feat(api): /models endpoint with ollama dropdown + free-text fallback"
```

---

## Task 7: /eval-sets endpoint (datasets only)

**Files:**
- Modify: `promptpressure/api.py`
- Modify: `tests/test_api_launcher.py`

**What it does:** GET `/eval-sets` returns `[{id, label, count}]` for `evals_*.json` files at repo root. `count` is the number of entries (length of the JSON array). No configs (Finding #3 → A).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api_launcher.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api_launcher.py -v -k eval_sets
```

Expected: 404.

- [ ] **Step 3: Implement /eval-sets**

Add to `promptpressure/api.py`:

```python
@app.get("/eval-sets")
async def list_eval_sets():
    cache_key = "eval_sets"
    if cache_key in _eval_sets_cache:
        return _eval_sets_cache[cache_key]

    out: List[Dict[str, Any]] = []
    for path in sorted(glob.glob("evals_*.json")):
        try:
            with open(path) as f:
                entries = json.load(f)
            count = len(entries) if isinstance(entries, list) else 0
        except Exception:
            count = 0
        label = path.removeprefix("evals_").removesuffix(".json").replace("_", " ").title()
        out.append({"id": path, "label": label, "count": count})

    _eval_sets_cache[cache_key] = out
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_api_launcher.py -v -k eval_sets
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add promptpressure/api.py tests/test_api_launcher.py
git commit -m "feat(api): /eval-sets endpoint, datasets only"
```

---

## Task 8: /health launcher field + StaticFiles mount

**Files:**
- Modify: `promptpressure/api.py`
- Modify: `tests/test_api_launcher.py`

**What it does:**
1. `/health` includes `"launcher": true` only when `PROMPTPRESSURE_LAUNCHER=1` (Finding #6).
2. `app.mount("/", StaticFiles(directory="frontend", html=True))` so `pp` opening `127.0.0.1:<port>/` serves `index.html`.

The mount goes LAST so it doesn't shadow API routes.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api_launcher.py`:

```python
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
    # frontend/ is created in Task 9; this test file ordering means
    # we add the assertion now and stub the file in this test.
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api_launcher.py -v -k "health or static"
```

Expected: failures.

- [ ] **Step 3: Modify /health**

Replace the current `/health` definition in `promptpressure/api.py` with:

```python
@app.get("/health")
async def health_check():
    body: Dict[str, Any] = {"status": "ok", "version": "3.1.0"}
    if os.getenv("PROMPTPRESSURE_LAUNCHER") == "1":
        body["launcher"] = True
    return body
```

- [ ] **Step 4: Mount StaticFiles at the bottom of api.py**

Add at the very bottom of `promptpressure/api.py`, AFTER all `@app.get`/`@app.post` decorators but BEFORE the `if __name__ == "__main__":` block:

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

_frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if _frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_api_launcher.py -v -k "health or static"
```

Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add promptpressure/api.py tests/test_api_launcher.py
git commit -m "feat(api): launcher field on /health + StaticFiles mount"
```

---

## Task 9: Frontend HTML shell

**Files:**
- Create: `frontend/index.html`

**What it does:** Single page with three controls + Run button + status panel. Tailwind via CDN. Loads `/app.js` at end of body.

- [ ] **Step 1: Create the file**

Create `frontend/index.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>PromptPressure Launcher</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="/styles.css" />
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen">
  <main class="max-w-3xl mx-auto p-6 space-y-6">
    <header>
      <h1 class="text-2xl font-bold">PromptPressure</h1>
      <p class="text-slate-400 text-sm">Pick a provider, model, and dataset. Hit Run.</p>
    </header>

    <section id="loading" class="text-slate-400" aria-live="polite">Loading providers and datasets…</section>

    <section id="empty" class="hidden text-amber-400" aria-live="polite">
      No providers reachable. Set <code>OPENROUTER_API_KEY</code> or start ollama, then refresh.
    </section>

    <form id="run-form" class="hidden space-y-4">
      <div>
        <label for="provider" class="block text-sm font-medium mb-1">Provider</label>
        <select id="provider" class="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2"></select>
      </div>

      <div>
        <label for="model" class="block text-sm font-medium mb-1">Model</label>
        <input id="model" list="model-suggestions" class="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 hidden" />
        <select id="model-select" class="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 hidden"></select>
        <datalist id="model-suggestions"></datalist>
        <p id="model-note" class="text-xs text-slate-500 mt-1"></p>
      </div>

      <fieldset>
        <legend class="text-sm font-medium mb-1">Eval sets</legend>
        <div id="eval-sets" class="space-y-1"></div>
      </fieldset>

      <button id="run-btn" type="submit"
              class="bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-700 px-4 py-2 rounded font-medium">
        Run
      </button>
    </form>

    <section>
      <h2 class="text-sm font-medium text-slate-300 mb-2">Status</h2>
      <pre id="status-panel"
           class="bg-slate-800 border border-slate-700 rounded p-3 text-xs whitespace-pre-wrap min-h-32 max-h-96 overflow-auto"
           aria-live="polite"></pre>
    </section>
  </main>

  <script src="/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Verify it serves via the static mount**

```bash
PROMPTPRESSURE_DEV_NO_AUTH=1 python -c "
from fastapi.testclient import TestClient
from promptpressure.api import app
with TestClient(app) as c:
    r = c.get('/')
    assert r.status_code == 200
    assert 'PromptPressure Launcher' in r.text
    print('OK')
"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html
git commit -m "feat(frontend): launcher page shell"
```

---

## Task 10: Frontend app.js — fetch + dropdowns + run + SSE

**Files:**
- Create: `frontend/app.js`

**What it does:** On load, fetches `/providers`, `/eval-sets`, populates the form. On provider change, fetches `/models?provider=X` and switches between `<select>` (ollama) and `<input list>` (free-text). On submit, POSTs `/evaluate` with `launcher_request`, opens an `EventSource` to `/stream/{run_id}`, appends events into the status panel. Auto-reconnects on EventSource error (browser default behavior is sufficient — the RunBus handles server side).

- [ ] **Step 1: Create the file**

Create `frontend/app.js`:

```javascript
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

  function append(line) {
    els.statusPanel.textContent += (els.statusPanel.textContent ? "\n" : "") + line;
    els.statusPanel.scrollTop = els.statusPanel.scrollHeight;
  }

  function appendError(msg) {
    const span = document.createElement("span");
    span.className = "text-red-400";
    span.textContent = (els.statusPanel.textContent ? "\n" : "") + msg;
    els.statusPanel.appendChild(span);
    els.statusPanel.scrollTop = els.statusPanel.scrollHeight;
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
      const id = `eval-${s.id}`;
      const wrap = document.createElement("label");
      wrap.className = "flex items-center gap-2 text-sm";
      wrap.innerHTML = `
        <input type="checkbox" id="${id}" value="${s.id}" class="accent-emerald-500" />
        <span>${s.label} <span class="text-slate-500">(${s.count})</span></span>
      `;
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
    if (!model) { appendError("Pick or type a model."); return; }
    if (ids.length === 0) { appendError("Pick at least one eval set."); return; }

    els.runBtn.disabled = true;
    els.statusPanel.textContent = "";
    append(`POST /evaluate provider=${provider} model=${model} eval_sets=${ids.join(",")}`);

    let body;
    try {
      const r = await fetch("/evaluate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          launcher_request: { provider, model, eval_set_ids: ids },
        }),
      });
      body = await r.json();
      if (!r.ok) throw new Error(body.detail || r.status);
    } catch (e) {
      appendError("evaluate failed: " + e.message);
      els.runBtn.disabled = false;
      return;
    }

    append(`run_id=${body.run_id} streaming…`);
    if (currentEventSource) { currentEventSource.close(); }

    currentEventSource = new EventSource(body.stream_url);
    currentEventSource.onmessage = (ev) => {
      let parsed = ev.data;
      try { parsed = JSON.stringify(JSON.parse(ev.data)); } catch (_) {}
      append(parsed);
    };
    currentEventSource.addEventListener("complete", (ev) => {
      append("complete: " + ev.data);
      currentEventSource.close();
      els.runBtn.disabled = false;
    });
    currentEventSource.addEventListener("error", (ev) => {
      const data = ev.data || "(connection error)";
      appendError("error: " + data);
      currentEventSource.close();
      els.runBtn.disabled = false;
    });
  }

  init();
})();
```

- [ ] **Step 2: Smoke test by serving and curling the page**

```bash
PROMPTPRESSURE_DEV_NO_AUTH=1 python -c "
from fastapi.testclient import TestClient
from promptpressure.api import app
with TestClient(app) as c:
    r = c.get('/app.js')
    assert r.status_code == 200
    assert 'launcher_request' in r.text
    print('OK')
"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add frontend/app.js
git commit -m "feat(frontend): app.js with provider/model/eval-set form + SSE"
```

---

## Task 11: Frontend styles.css

**Files:**
- Create: `frontend/styles.css`

**What it does:** Tailwind handles 95%. This file holds the few overrides Tailwind doesn't cover (status panel monospace + scrollbar tint).

- [ ] **Step 1: Create the file**

Create `frontend/styles.css`:

```css
#status-panel {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, monospace;
}

#status-panel::-webkit-scrollbar { width: 8px; }
#status-panel::-webkit-scrollbar-track { background: rgb(15 23 42); }
#status-panel::-webkit-scrollbar-thumb { background: rgb(51 65 85); border-radius: 4px; }
```

- [ ] **Step 2: Commit**

```bash
git add frontend/styles.css
git commit -m "style(frontend): minimal CSS overrides for status panel"
```

---

## Task 12: Launcher CLI (`pp` command)

**Files:**
- Create: `promptpressure/launcher.py`
- Create: `tests/test_launcher_cli.py`

**What it does:** `pp` finds a free port in 8000-8019, sets `PROMPTPRESSURE_DEV_NO_AUTH=1` and `PROMPTPRESSURE_LAUNCHER=1` in a copy of `os.environ`, spawns `uvicorn promptpressure.api:app --host 127.0.0.1 --port <port>`, polls `/health` for up to 10s, opens `webbrowser.open("http://127.0.0.1:<port>/")`, and waits for SIGINT to clean up. If a port already has a launcher (`/health` returns `launcher: true`), reuse it.

The parent `pp` process MUST NOT import `promptpressure.api` (Finding #5).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_launcher_cli.py`:

```python
import os
import socket
from unittest.mock import MagicMock, patch

import httpx
import pytest


def test_find_free_port_finds_one():
    from promptpressure.launcher import find_free_port
    p = find_free_port(8000, 8019)
    assert 8000 <= p <= 8019
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", p))
    finally:
        s.close()


def test_find_free_port_raises_when_all_taken():
    from promptpressure.launcher import find_free_port

    sockets = []
    try:
        for port in range(9050, 9055):
            s = socket.socket()
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", port))
            s.listen(1)
            sockets.append(s)
        with pytest.raises(RuntimeError, match="Could not find a free port"):
            find_free_port(9050, 9054)
    finally:
        for s in sockets:
            s.close()


def test_build_subprocess_env_preserves_path_and_adds_launcher_flags():
    from promptpressure.launcher import build_subprocess_env
    parent = {"PATH": "/usr/bin", "OPENROUTER_API_KEY": "secret", "HOME": "/home/x"}
    env = build_subprocess_env(parent)
    assert env["PATH"] == "/usr/bin"
    assert env["OPENROUTER_API_KEY"] == "secret"
    assert env["HOME"] == "/home/x"
    assert env["PROMPTPRESSURE_DEV_NO_AUTH"] == "1"
    assert env["PROMPTPRESSURE_LAUNCHER"] == "1"


def test_build_subprocess_env_does_not_mutate_input():
    from promptpressure.launcher import build_subprocess_env
    parent = {"PATH": "/usr/bin"}
    _ = build_subprocess_env(parent)
    assert parent == {"PATH": "/usr/bin"}


def test_probe_existing_launcher_returns_port_when_health_says_launcher_true():
    from promptpressure.launcher import probe_existing_launcher

    def mock_get(url, timeout):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"status": "ok", "launcher": True}
        return resp

    with patch.object(httpx, "get", side_effect=mock_get):
        port = probe_existing_launcher((8000,))
    assert port == 8000


def test_probe_existing_launcher_skips_non_launcher_servers():
    from promptpressure.launcher import probe_existing_launcher

    def mock_get(url, timeout):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"status": "ok"}  # No launcher field
        return resp

    with patch.object(httpx, "get", side_effect=mock_get):
        port = probe_existing_launcher((8000, 8001))
    assert port is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_launcher_cli.py -v
```

Expected: ImportError.

- [ ] **Step 3: Write launcher.py**

Create `promptpressure/launcher.py`:

```python
"""
`pp` launcher CLI: spawn the API server in a subprocess and open a browser.

Parent process MUST NOT import promptpressure.api (it would trigger the same
auth-gate RuntimeError that the subprocess handles via env vars).
"""
import argparse
import os
import socket
import subprocess
import sys
import time
import webbrowser
from typing import Iterable, Optional

import httpx

PORT_RANGE = range(8000, 8020)
HEALTH_TIMEOUT_SECONDS = 10.0


def find_free_port(start: int, end: int) -> int:
    """Return the first port in [start, end] inclusive that's bindable on 127.0.0.1."""
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(
        f"Could not find a free port in {start}-{end}. "
        f"Stop another launcher or kill whatever is using these ports: lsof -i :{start}-{end}"
    )


def build_subprocess_env(parent_env: Optional[dict] = None) -> dict:
    """Copy parent env, add launcher flags. Never mutates input."""
    env = dict(parent_env if parent_env is not None else os.environ)
    env["PROMPTPRESSURE_DEV_NO_AUTH"] = "1"
    env["PROMPTPRESSURE_LAUNCHER"] = "1"
    return env


def probe_existing_launcher(ports: Iterable[int]) -> Optional[int]:
    """Return the first port whose /health response includes launcher: true."""
    for port in ports:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        try:
            body = r.json()
        except Exception:
            continue
        if body.get("launcher") is True:
            return port
    return None


def wait_for_health(port: int, timeout: float = HEALTH_TIMEOUT_SECONDS) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5)
            if r.status_code == 200 and r.json().get("launcher") is True:
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="pp",
        description="PromptPressure launcher: spawns the API and opens a browser. Binds 127.0.0.1 only.",
    )
    parser.add_argument("--version", action="store_true", help="Print package version and exit")
    args = parser.parse_args()

    if args.version:
        try:
            from importlib.metadata import version
            print(version("promptpressure"))
        except Exception:
            print("unknown")
        return 0

    existing = probe_existing_launcher(PORT_RANGE)
    if existing is not None:
        url = f"http://127.0.0.1:{existing}/"
        print(f"Found running launcher at {url}. Opening browser. (--new not yet implemented; v2)")
        webbrowser.open(url)
        return 0

    port = find_free_port(PORT_RANGE.start, PORT_RANGE.stop - 1)
    env = build_subprocess_env()
    cmd = [sys.executable, "-m", "uvicorn", "promptpressure.api:app",
           "--host", "127.0.0.1", "--port", str(port)]

    print(f"Starting PromptPressure launcher on http://127.0.0.1:{port}/")
    proc = subprocess.Popen(cmd, env=env)

    try:
        if not wait_for_health(port, HEALTH_TIMEOUT_SECONDS):
            print(
                f"PromptPressure server didn't respond on http://127.0.0.1:{port}/health "
                f"within {HEALTH_TIMEOUT_SECONDS:.0f} seconds. Check the subprocess output above for the real error. "
                f"Common causes: missing env vars, port collision, broken venv.",
                file=sys.stderr,
            )
            proc.terminate()
            return 2

        webbrowser.open(f"http://127.0.0.1:{port}/")
        print("Press Ctrl-C to stop.")
        proc.wait()
        return proc.returncode or 0

    except KeyboardInterrupt:
        print("\nShutting down…")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run unit tests**

```bash
pytest tests/test_launcher_cli.py -v
```

Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add promptpressure/launcher.py tests/test_launcher_cli.py
git commit -m "feat(launcher): pp CLI with port discovery + subprocess + browser open"
```

---

## Task 13: Wire `pp` entry point in pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Edit pyproject.toml**

In the `[project.scripts]` section, add the `pp` line so it reads:

```toml
[project.scripts]
promptpressure = "promptpressure.cli:main"
pp = "promptpressure.launcher:main"
```

- [ ] **Step 2: Reinstall and verify entry point**

```bash
pip install -e .
which pp
pp --version
```

Expected: `pp` resolves to a path; `pp --version` prints `3.1.0` (matching the api.py version bump).

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: register pp launcher entry point"
```

---

## Task 14: README + TODOS.md

**Files:**
- Modify: `README.md`
- Create: `TODOS.md`

- [ ] **Step 1: Find README's section structure**

```bash
grep -n "^## " README.md | head -20
```

Note where to insert "Launcher" — typically right after Quick Start / Installation.

- [ ] **Step 2: Add Launcher section to README.md**

Insert this block at the chosen location (after the install/quick-start section):

```markdown
## Launcher

One command. Three dropdowns. One button.

```bash
pip install -e .
pp
```

`pp` starts the API on `127.0.0.1` (first free port in 8000-8019) and opens a browser. Pick a provider, model, and one or more eval sets. Hit Run. Output streams into the status panel.

**Security:** `pp` binds 127.0.0.1 only. For remote access, run `uvicorn promptpressure.api:app --host 0.0.0.0` with `PROMPTPRESSURE_API_SECRET` set.

**Stop:** Ctrl-C in the terminal that started `pp`. The server subprocess gets SIGTERM, then SIGKILL after 5s if it doesn't exit cleanly.

**Known v1 limitation:** if you reload the browser mid-run, the EventSource auto-reconnects to the same `run_id` and resumes — but only within 5 minutes of completion. After that, the run state has been reaped. Check `/evaluations/{run_id}` for completed runs.

`pp --help` and `pp --version` work as expected.
```

- [ ] **Step 3: Create TODOS.md**

Create `TODOS.md`:

```markdown
# TODOS

## v2 launcher follow-ups

- Real `/v1/models` enumeration in OpenAI-compatible adapters (openrouter, openai, groq, lmstudio, litellm-proxy). Replaces the free-text + suggestions fallback for those providers. ~20 lines per adapter.
- "Load saved config" UI affordance: pre-fill the launcher dropdowns from a chosen `configs/*.yaml` and disable them with a "config-driven" badge. ~30 lines in app.js + 1 endpoint.
- `pp --new` flag to force a new launcher instance even if one is already running on a port in 8000-8019.
- Run cancellation UI button. Server-side cancellation is trivial via queue close; the UI piece is the work.
- Multi-dataset runs: currently `launcher_to_settings_dict` takes only `eval_set_ids[0]`. v2 should concatenate or run sequentially.
```

- [ ] **Step 4: Commit**

```bash
git add README.md TODOS.md
git commit -m "docs: launcher README section + TODOS.md for v2 deferrals"
```

---

## Task 15: End-to-end smoke

**Files:** none — verification only.

- [ ] **Step 1: Run the full test suite**

```bash
pytest --tb=short 2>&1 | tail -15
```

Expected: all new tests pass; existing test pass count unchanged.

- [ ] **Step 2: Manual end-to-end with mock adapter**

```bash
pp &
sleep 5
curl -s http://127.0.0.1:8000/providers | python -m json.tool | head -20
curl -s "http://127.0.0.1:8000/models?provider=mock" | python -m json.tool
curl -s http://127.0.0.1:8000/eval-sets | python -m json.tool
curl -s -X POST http://127.0.0.1:8000/evaluate \
  -H "Content-Type: application/json" \
  -d '{"launcher_request":{"provider":"mock","model":"test","eval_set_ids":["evals_dataset.json"]}}'
```

Expected: each curl returns a valid JSON body. The POST returns `{"run_id":"...","status":"started","stream_url":"/stream/..."}`.

Stop the launcher with `kill %1` (or Ctrl-C if foregrounded).

- [ ] **Step 3: Manual browser smoke**

Start `pp`, confirm the browser opens, the form populates, picking `mock` + `test-model` + `evals_dataset.json` + Run produces streaming output in the status panel.

- [ ] **Step 4: ARCHITECTURE.md update (per CLAUDE.md mandate)**

If `ARCHITECTURE.md` exists at repo root, update it to mention:
- new files: `frontend/`, `promptpressure/run_bus.py`, `promptpressure/launcher.py`, `promptpressure/launcher_translate.py`
- new endpoints: `/providers`, `/models`, `/eval-sets`
- `/evaluate` schema change (XOR validator)
- `pp` entry point

If it doesn't exist, create a minimal one — but check first; don't blindly overwrite a file you haven't read.

- [ ] **Step 5: Final commit (only if step 4 changed anything)**

```bash
git add ARCHITECTURE.md
git commit -m "docs(architecture): launcher additions"
```

---

## Self-Review

**Spec coverage check:**

| Spec finding | Resolved in task |
|---|---|
| #1 EvalRequest schema XOR | Task 4 |
| #2 /models free-text + suggestions | Task 6 |
| #3 /eval-sets datasets only | Task 7 |
| #4 tests/conftest.py with DEV_NO_AUTH + import-time gate | Task 1 + Task 4 |
| #5 subprocess env merge + parent doesn't import api | Task 12 |
| #6 /health launcher field gated by env | Task 8 |
| #7 CORS unchanged (same-origin) | inherited; nothing to do |
| #8 cache key includes query params | Task 6 (models) — `(provider,)` tuple key |
| #9 SSE drain-after-completion + 5min TTL + reaper | Task 2 + Task 4 |
| #10 frontend size budget | observed: index.html ~50 lines, app.js ~190 lines, css ~10 lines — well under |

**Acceptance criteria check:**

| Acceptance criterion | Resolved in task |
|---|---|
| `pp` opens browser | Task 12 |
| Provider/Model/Eval-set dropdowns populate from API | Tasks 5/6/7 + Task 10 |
| Free-text fallback for non-ollama providers | Task 6 + Task 10 |
| End-to-end eval streams | Tasks 4 + 9 + 10 + 12 |
| Failure modes surface in panel | Task 10 (appendError) |
| Mid-stream EventSource reconnect | Task 2 (RunBus subscribe) |
| New code has tests, existing tests pass | Tasks 1, 2, 3, 4, 5, 6, 7, 8, 12, 15 |
| README "Launcher" section | Task 14 |
| `pp --help` and `pp --version` | Task 12 |
| `/evaluate` accepts both shapes (XOR) | Task 4 |
| `/health` launcher field | Task 8 |

**Branch check:** `feat/launcher` off `main`. Verified at the start of writing this plan. ✓

**Placeholder scan:** no TBDs, no "implement later", every step has runnable code or a runnable command. ✓

**Type/name consistency:** `LauncherRequest` defined in `launcher_translate.py` (Task 3), imported into `api.py` (Task 4), used in test bodies (Tasks 4, 5, 6, 7, 10). `RunBus` defined in Task 2, instantiated in Task 4, methods used identically across both. `_providers_cache` / `_models_cache` / `_eval_sets_cache` defined in Task 5, referenced by name in Tasks 5, 6, 7. ✓

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-25-launcher-implementation.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Good when you want minimum context bloat and per-task adversarial review.

2. **Inline Execution** — Execute tasks in this session using executing-plans, batch with checkpoints. Good when you want to watch the work tick through.

Which approach?
