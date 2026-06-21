import asyncio
import glob
import json
import logging
import os
import hmac
import hashlib
import time
import sys
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any, AsyncGenerator, Optional, List, Literal
from uuid import uuid4

import yaml as _yaml

from cachetools import TTLCache
from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, Depends, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, model_validator

from promptpressure.config import Settings
from promptpressure.cli import run_evaluation_suite
from promptpressure.launcher_translate import LauncherRequest, launcher_to_settings_dict
from promptpressure.run_bus import RunBus, RunCancelled

# Module-import auth gate (Finding #4 in the spec).
# Either PROMPTPRESSURE_API_SECRET or PROMPTPRESSURE_DEV_NO_AUTH=1 must be set
# or this module raises immediately. tests/conftest.py sets the dev flag.
if not os.getenv("PROMPTPRESSURE_API_SECRET") and os.getenv("PROMPTPRESSURE_DEV_NO_AUTH") != "1":
    raise RuntimeError(
        "PROMPTPRESSURE_API_SECRET is required, or set PROMPTPRESSURE_DEV_NO_AUTH=1 for local dev."
    )

bus = RunBus()

_providers_cache: TTLCache = TTLCache(maxsize=1, ttl=60)
_models_cache: TTLCache = TTLCache(maxsize=64, ttl=60)
_eval_sets_cache: TTLCache = TTLCache(maxsize=1, ttl=60)
_app_configs_cache: TTLCache = TTLCache(maxsize=1, ttl=60)

APP_THEME_SUFFIX = ".pp-theme.json"
APP_PROVIDER_SUFFIX = ".pp-provider.json"
THEME_SCHEMA_VERSION = 1
PROVIDER_SCHEMA_VERSION = 1
LOCKED_DRIFT_COLORS = {
    "hold": "#20B7A8",
    "partial": "#F0B24A",
    "drift": "#F05D7F",
}
BUILT_IN_THEME_PRESETS = [
    {"id": "signal-dark", "name": "Signal Dark", "base": "dark", "accent": "#5269FF", "density": "comfortable", "chartIntensity": "standard"},
    {"id": "ember", "name": "Ember", "base": "dark", "accent": "#F05D7F", "density": "comfortable", "chartIntensity": "high"},
    {"id": "paper-lab", "name": "Paper Lab", "base": "light", "accent": "#1F7A5C", "density": "comfortable", "chartIntensity": "standard"},
    {"id": "mono-console", "name": "Mono Console", "base": "dark", "accent": "#D1D5DB", "density": "compact", "chartIntensity": "muted"},
]

_PROVIDER_DEFS: List[Dict[str, Any]] = [
    {"id": "mock", "label": "Mock (deterministic)"},
    {"id": "ollama", "label": "Ollama (local)"},
    {"id": "openrouter", "label": "OpenRouter", "env": "OPENROUTER_API_KEY"},
    {"id": "groq", "label": "Groq", "env": "GROQ_API_KEY"},
    {"id": "openai", "label": "OpenAI", "env": "OPENAI_API_KEY"},
    {"id": "deepseek_native", "label": "DeepSeek (native API)", "env": "DEEPSEEK_API_KEY",
     "models": ["deepseek-chat", "deepseek-reasoner", "deepseek-v4-flash"]},
    {"id": "deepseek", "label": "DeepSeek R1 (via OpenRouter)", "env": "OPENROUTER_API_KEY",
     "models": ["deepseek/deepseek-r1"]},
    {"id": "claude_code", "label": "Claude Code", "env": "ANTHROPIC_API_KEY"},
    {"id": "opencode", "label": "OpenCode (CLI)"},
    {"id": "lmstudio", "label": "LM Studio (local)"},
    {"id": "litellm", "label": "LiteLLM (multi-provider)",
     "env_any": ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY",
                 "XAI_API_KEY", "GROQ_API_KEY", "GOOGLE_API_KEY",
                 "DEEPSEEK_API_KEY", "LITELLM_API_KEY"]},
]

_VALID_PROVIDERS = {p["id"] for p in _PROVIDER_DEFS}
_TERMINAL_JOB_STATUSES = {"completed", "failed", "cancelled"}

PROVIDER_REMEDIATION_HINTS: dict[str, str] = {
    "openrouter": "Set OPENROUTER_API_KEY in your environment.",
    "ollama": "Start the ollama daemon: `ollama serve` (or run `ollama run <model>`).",
    "openai": "Set OPENAI_API_KEY in your environment.",
    "groq": "Set GROQ_API_KEY in your environment.",
    "deepseek_native": "Set DEEPSEEK_API_KEY in your environment.",
    "deepseek": "Set OPENROUTER_API_KEY in your environment (DeepSeek R1 routes via OpenRouter).",
    "claude_code": "Set ANTHROPIC_API_KEY in your environment.",
    "opencode": "Install the opencode CLI and ensure it is on your PATH.",
    "lmstudio": "Start LM Studio and enable the local server (default: http://localhost:1234).",
    "litellm": "Set at least one provider API key (ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY, etc.).",
    "mock": "No configuration required — mock provider is always available.",
    # staged: anthropic and gemini providers not yet in _PROVIDER_DEFS;
    # kept here so they're ready when added.
    "anthropic": "Set ANTHROPIC_API_KEY in your environment.",
    "gemini": "Set GEMINI_API_KEY in your environment.",
}


def _suggestions_from_configs(provider: str) -> List[str]:
    """Aggregate model: values across configs/*.yaml filtered by adapter:."""
    suggestions: List[str] = []
    for path in sorted(glob.glob("configs/*.yaml")):
        try:
            with open(path) as f:
                data = _yaml.safe_load(f) or {}
        except Exception as e:
            logging.warning("Failed to parse %s: %s", path, e)
            continue
        if (data.get("adapter") or "").lower() == provider.lower():
            m = data.get("model")
            if isinstance(m, str) and m and m not in suggestions:
                suggestions.append(m)
    return suggestions


@asynccontextmanager
async def lifespan(app: FastAPI):
    await bus.start_reaper()
    try:
        yield
    finally:
        await bus.stop_reaper()


app = FastAPI(title="PromptPressure API", version="3.2.1", lifespan=lifespan)

_default_origins = ["http://localhost:3000", "http://localhost:8000",
                    "http://127.0.0.1:3000", "http://127.0.0.1:8000"]
_cors_origins = (os.getenv("PROMPTPRESSURE_CORS_ORIGINS", "").split(",")
                 if os.getenv("PROMPTPRESSURE_CORS_ORIGINS")
                 else _default_origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

API_SECRET = os.getenv("PROMPTPRESSURE_API_SECRET")


def _verify_token(token: str) -> bool:
    """Verify a bearer token. Token format: timestamp.signature"""
    if not API_SECRET:
        return True
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return False
        ts, sig = parts
        expected = hmac.HMAC(API_SECRET.encode(), ts.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False
        # Token expires after 24h
        if abs(time.time() - int(ts)) > 86400:
            return False
        return True
    except Exception:
        return False


async def require_auth(authorization: Optional[str] = Header(None)):
    """Dependency that enforces auth when API_SECRET is set."""
    if not API_SECRET:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization[7:]
    if not _verify_token(token):
        raise HTTPException(status_code=401, detail="Invalid or expired token")


class EvalRequest(BaseModel):
    """
    Accepts EITHER the existing config dict OR the new launcher_request shape.
    Backward-compatible at the data level: existing {config: {...}} bodies
    still validate and dispatch identically.
    """
    model_config = ConfigDict(extra="forbid")

    config: Optional[Dict[str, Any]] = None
    launcher_request: Optional[LauncherRequest] = None

    @model_validator(mode="after")
    def exactly_one(self):
        if (self.config is None) == (self.launcher_request is None):
            raise ValueError("specify config OR launcher_request, not both")
        return self


class ThemePreset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal[1]
    id: str
    name: str
    base: Literal["dark", "light", "system"]
    accent: str
    density: Literal["comfortable", "compact", "dense"] = "comfortable"
    chartIntensity: Literal["muted", "standard", "high"] = "standard"
    surfaces: Optional[Dict[str, str]] = None
    text: Optional[Dict[str, str]] = None

    @model_validator(mode="after")
    def validate_colors(self):
        import re
        color_re = re.compile(r"^#[0-9A-Fa-f]{6}$")
        if not color_re.match(self.accent):
            raise ValueError("accent must be a #RRGGBB color")
        for group_name, group in (("surfaces", self.surfaces), ("text", self.text)):
            if not group:
                continue
            for key, value in group.items():
                if key in LOCKED_DRIFT_COLORS:
                    raise ValueError(f"{group_name}.{key} cannot override locked drift semantics")
                if not isinstance(value, str) or not color_re.match(value):
                    raise ValueError(f"{group_name}.{key} must be a #RRGGBB color")
        return self


class CustomProviderPreset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal[1]
    id: str
    name: str
    apiStyle: Literal[
        "openai_chat",
        "anthropic_messages",
        "openai_responses",
        "gemini_generate_content",
        "local_openai_chat",
    ]
    baseURL: str
    apiKeyEnv: str
    models: List[str]
    modelsEndpoint: Optional[str] = None
    headers: Optional[Dict[str, str]] = None

    @model_validator(mode="after")
    def validate_provider(self):
        import re
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_-]{1,63}$", self.id):
            raise ValueError("id must start with a letter and contain only letters, numbers, _ or -")
        if self.id in _VALID_PROVIDERS:
            raise ValueError(f"id conflicts with built-in provider: {self.id}")
        if not (self.baseURL.startswith("https://") or self.baseURL.startswith("http://127.0.0.1") or self.baseURL.startswith("http://localhost")):
            raise ValueError("baseURL must be https:// or a localhost URL")
        if not re.match(r"^[A-Z][A-Z0-9_]*$", self.apiKeyEnv):
            raise ValueError("apiKeyEnv must be an uppercase environment variable name")
        if not self.models:
            raise ValueError("models must contain at least one model id")
        return self


class AppEvaluationJobRequest(BaseModel):
    provider: str
    model: str
    eval_set_ids: List[str]
    tier: Literal["smoke", "quick", "full", "deep"] = "full"
    batch: bool = False


class DriftRunJobRequest(BaseModel):
    suite: str = "drift-v0.1"
    provider: str
    model: str
    temperature: Optional[float] = None
    concurrency: int = 3
    turn_delay: float = 0.0
    timeout: float = 90.0


class DriftCalibrateJobRequest(BaseModel):
    suite: str = "drift-v0.1"
    judge_provider: str
    judge_model: str
    runs: int = 3
    temperature: float = 0.0
    concurrency: int = 4
    bootstrap: int = 2000
    seed: int = 0
    transcripts: Optional[str] = None


class AppJobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, Dict[str, Any]] = {}

    def create(self, job_type: str, config: Dict[str, Any], job_id: Optional[str] = None) -> Dict[str, Any]:
        now = _utcnow()
        job_id = job_id or str(uuid4())
        job = {
            "id": job_id,
            "type": job_type,
            "status": "queued",
            "phase": "queued",
            "created_at": now,
            "updated_at": now,
            "progress": {"completed": 0, "total": 0, "current": None},
            "summary": {},
            "outputs": [],
            "error": None,
            "config": _safe_config(config),
            "events": [],
        }
        self._jobs[job_id] = job
        return job

    def has(self, job_id: str) -> bool:
        return job_id in self._jobs

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        job = self._jobs.get(job_id)
        return _public_job(job) if job else None

    def list(self) -> List[Dict[str, Any]]:
        return [
            _public_job(job)
            for job in sorted(self._jobs.values(), key=lambda item: item["created_at"], reverse=True)
        ]

    def update(self, job_id: str, **updates: Any) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        for key, value in updates.items():
            if value is not None:
                job[key] = value
        job["updated_at"] = _utcnow()

    def merge_summary(self, job_id: str, values: Dict[str, Any]) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        job["summary"].update(values)
        job["updated_at"] = _utcnow()

    def record_event(self, job_id: str, event: str, data: Any) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        if isinstance(data, str):
            raw = data
            parsed = _try_json(raw)
        else:
            parsed = data
            raw = json.dumps(data, default=str)
        job["events"].append({"event": event, "data": raw, "timestamp": _utcnow()})
        if event == "start_prompt":
            job["status"] = "running"
            job["phase"] = "running"
            _merge_progress(job, parsed)
        elif event == "end_prompt":
            job["status"] = "running"
            job["phase"] = "running"
            _merge_progress(job, parsed, increment=True)
        job["updated_at"] = _utcnow()

    def complete(self, job_id: str, summary: Dict[str, Any], outputs: List[Dict[str, Any]]) -> None:
        self.update(job_id, status="completed", phase="completed", error=None, outputs=outputs)
        self.merge_summary(job_id, summary)

    def fail(self, job_id: str, error: str) -> None:
        self.update(job_id, status="failed", phase="failed", error=error)

    def cancel(self, job_id: str) -> None:
        self.update(job_id, status="cancelled", phase="cancelled", error=None)


app_jobs = AppJobStore()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_config(config: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in config.items()
        if not key.startswith("_")
        and not any(secret in key.lower() for secret in ("api_key", "secret", "token", "password"))
    }


def _public_job(job: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in job.items() if key != "events"}


def _try_json(value: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return value


def _merge_progress(job: Dict[str, Any], data: Any, increment: bool = False) -> None:
    progress = dict(job.get("progress") or {})
    if isinstance(data, dict):
        if "total" in data:
            progress["total"] = data["total"]
        if "current" in data:
            if isinstance(data["current"], int):
                if increment:
                    progress["completed"] = data["current"]
                else:
                    progress["current_index"] = data["current"]
            else:
                progress["current"] = data["current"]
        if "id" in data:
            progress["current"] = data["id"]
    if increment:
        progress["completed"] = max(int(progress.get("completed") or 0), 1)
    job["progress"] = progress


def _default_app_support_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PromptPressure"
    return Path.home() / ".promptpressure"


def _app_support_dir() -> Path:
    return Path(os.getenv("PROMPTPRESSURE_APP_SUPPORT_DIR") or _default_app_support_dir()).expanduser()


def _app_paths(create: bool = True) -> Dict[str, Path]:
    root = _app_support_dir()
    paths = {
        "root": root,
        "data": root / "data",
        "outputs": Path(os.getenv("PROMPTPRESSURE_OUTPUT_DIR") or root / "outputs").expanduser(),
        "themes": Path(os.getenv("PROMPTPRESSURE_THEMES_DIR") or root / "themes").expanduser(),
        "providers": Path(os.getenv("PROMPTPRESSURE_PROVIDERS_DIR") or root / "providers").expanduser(),
    }
    if create:
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
    return paths


def _safe_rel(path: Path) -> str:
    try:
        return str(path.resolve())
    except Exception:
        return str(path)


def _read_theme_file(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)
    theme = ThemePreset(**raw)
    body = theme.model_dump()
    body["source"] = "custom"
    body["path"] = _safe_rel(path)
    return body


def _read_provider_file(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)
    provider = CustomProviderPreset(**raw)
    return {
        "schemaVersion": provider.schemaVersion,
        "id": provider.id,
        "name": provider.name,
        "apiStyle": provider.apiStyle,
        "api_style": provider.apiStyle,
        "baseURL": provider.baseURL,
        "base_url": provider.baseURL,
        "apiKeyEnv": provider.apiKeyEnv,
        "api_key_env": provider.apiKeyEnv,
        "models": provider.models,
        "modelsEndpoint": provider.modelsEndpoint,
        "models_endpoint": provider.modelsEndpoint,
        "headers": provider.headers,
        "source": "custom",
        "path": _safe_rel(path),
    }


def _custom_provider_catalog() -> tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    providers_dir = _app_paths()["providers"]
    custom: List[Dict[str, Any]] = []
    invalid: List[Dict[str, str]] = []
    for path in sorted(providers_dir.glob(f"*{APP_PROVIDER_SUFFIX}")):
        try:
            custom.append(_read_provider_file(path))
        except Exception as e:
            invalid.append({"path": _safe_rel(path), "name": path.name, "error": str(e)})
    return custom, invalid


def _provider_definitions() -> List[Dict[str, Any]]:
    custom, _ = _custom_provider_catalog()
    definitions = list(_PROVIDER_DEFS)
    for provider in custom:
        definitions.append({
            "id": provider["id"],
            "label": provider["name"],
            "env": provider["api_key_env"],
            "models": provider["models"],
            "custom": True,
            "api_style": provider["api_style"],
            "base_url": provider["base_url"],
            "headers": provider.get("headers") or {},
        })
    return definitions


def _provider_definition(provider_id: str) -> Optional[Dict[str, Any]]:
    return next((item for item in _provider_definitions() if item["id"] == provider_id), None)


def _apply_custom_provider_config(config: Dict[str, Any]) -> Dict[str, Any]:
    definition = _provider_definition(config.get("adapter", ""))
    if not definition or not definition.get("custom"):
        return config
    env_key = definition["env"]
    mapped = dict(config)
    mapped["provider_id"] = definition["id"]
    mapped["adapter"] = "litellm"
    mapped["litellm_endpoint"] = definition["base_url"]
    mapped["litellm_api_style"] = definition["api_style"]
    mapped["litellm_headers"] = definition.get("headers") or {}
    if os.getenv(env_key):
        mapped["litellm_api_key"] = os.getenv(env_key)
    return mapped


@app.get("/health")
async def health_check():
    paths = _app_paths(create=False)
    body: Dict[str, Any] = {
        "status": "ok",
        "version": "3.2.1",
        "sidecar": True,
        "theme_suffix": APP_THEME_SUFFIX,
        "data_paths": {key: _safe_rel(path) for key, path in paths.items()},
    }
    if os.getenv("PROMPTPRESSURE_LAUNCHER") == "1":
        body["launcher"] = True
    return body


@app.post("/evaluate", dependencies=[Depends(require_auth)])
async def trigger_evaluation(request: EvalRequest, background_tasks: BackgroundTasks):
    import uuid
    run_id = str(uuid.uuid4())

    if request.launcher_request is not None:
        config_dict = launcher_to_settings_dict(request.launcher_request, run_id=run_id)
    else:
        config_dict = dict(request.config)  # copy; we'll mutate _callback
    config_dict["_evaluation_id"] = run_id

    try:
        Settings(**config_dict)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    bus.start(run_id)
    background_tasks.add_task(run_eval_background, run_id, config_dict)
    return {"run_id": run_id, "status": "started", "stream_url": f"/stream/{run_id}"}


@app.post("/evaluations/{run_id}/cancel", dependencies=[Depends(require_auth)])
async def cancel_evaluation(run_id: str):
    if not bus.has(run_id):
        raise HTTPException(status_code=404, detail="Run ID not found")
    if not bus.cancel(run_id):
        raise HTTPException(status_code=409, detail="Run is already completed or cannot be cancelled")
    return {"run_id": run_id, "status": "cancelling"}


@app.get("/stream/{run_id}")
async def stream_events(run_id: str):
    from sse_starlette.sse import EventSourceResponse
    if not bus.has(run_id):
        raise HTTPException(status_code=404, detail="Run ID not found")

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            async for item in bus.subscribe(run_id):
                yield item
        except KeyError:
            return  # run was reaped between has() and subscribe()

    return EventSourceResponse(event_generator())


@app.get("/evaluations", dependencies=[Depends(require_auth)])
async def list_evaluations():
    from promptpressure.database import get_db_session, init_db, Evaluation
    from sqlalchemy import select
    engine = await init_db()
    async for session in get_db_session(engine):
        result = await session.execute(select(Evaluation).order_by(Evaluation.timestamp.desc()))
        evals = result.scalars().all()
        return [{"id": e.id, "status": e.status, "timestamp": e.timestamp.isoformat()} for e in evals]


@app.get("/evaluations/{eval_id}", dependencies=[Depends(require_auth)])
async def get_evaluation(eval_id: str):
    from promptpressure.database import get_db_session, init_db, Evaluation, Result
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    engine = await init_db()
    async for session in get_db_session(engine):
        query = select(Evaluation).where(Evaluation.id == eval_id).options(selectinload(Evaluation.results))
        result = await session.execute(query)
        evaluation = result.scalar_one_or_none()

        if not evaluation:
            raise HTTPException(status_code=404, detail="Evaluation not found")

        return {
            "id": evaluation.id,
            "status": evaluation.status,
            "timestamp": evaluation.timestamp.isoformat(),
            "results": [{
                "id": r.id,
                "prompt_text": r.prompt_text,
                "response_text": r.response_text,
                "model": r.model,
                "success": r.success,
                "latency_ms": r.latency_ms,
            } for r in evaluation.results]
        }


@app.get("/schema")
async def get_schema():
    return Settings.model_json_schema()


@app.get("/app/metadata")
async def app_metadata():
    paths = _app_paths()
    return {
        "app": "PromptPressure",
        "version": "3.2.1",
        "sidecar": True,
        "launcher": os.getenv("PROMPTPRESSURE_LAUNCHER") == "1",
        "theme_suffix": APP_THEME_SUFFIX,
        "provider_suffix": APP_PROVIDER_SUFFIX,
        "theme_schema_version": THEME_SCHEMA_VERSION,
        "provider_schema_version": PROVIDER_SCHEMA_VERSION,
        "locked_drift_colors": LOCKED_DRIFT_COLORS,
        "paths": {key: _safe_rel(path) for key, path in paths.items()},
    }


@app.get("/app/configs")
async def app_configs():
    cache_key = "app_configs"
    if cache_key in _app_configs_cache:
        return _app_configs_cache[cache_key]

    configs: List[Dict[str, Any]] = []
    for path in sorted(Path("configs").glob("*.yaml")):
        try:
            with path.open(encoding="utf-8") as f:
                raw = _yaml.safe_load(f) or {}
        except Exception as e:
            configs.append({
                "id": path.name,
                "label": path.stem.replace("config_", "").replace("_", " ").title(),
                "path": str(path),
                "valid": False,
                "error": str(e),
            })
            continue

        configs.append({
            "id": path.name,
            "label": path.stem.replace("config_", "").replace("_", " ").title(),
            "path": str(path),
            "valid": True,
            "adapter": raw.get("adapter"),
            "model": raw.get("model") or raw.get("model_name"),
            "tier": raw.get("tier"),
            "dataset": raw.get("dataset"),
        })

    _app_configs_cache[cache_key] = {"configs": configs}
    return _app_configs_cache[cache_key]


def _output_entry(path: Path) -> Dict[str, Any]:
    files = []
    if path.is_dir():
        for child in sorted(path.iterdir()):
            if child.is_file():
                files.append(child.name)
    stat = path.stat()
    return {
        "name": path.name,
        "path": _safe_rel(path),
        "kind": "directory" if path.is_dir() else "file",
        "modified_at": stat.st_mtime,
        "files": files,
        "report_html": _safe_rel(path / "report.html") if (path / "report.html").exists() else None,
        "report_markdown": _safe_rel(path / "report.md") if (path / "report.md").exists() else None,
        "metrics_json": _safe_rel(path / "metrics.json") if (path / "metrics.json").exists() else None,
    }


@app.get("/app/outputs")
async def app_outputs():
    paths = _app_paths()
    roots = [Path("outputs"), paths["outputs"]]
    seen: set[str] = set()
    entries: List[Dict[str, Any]] = []
    for root in roots:
        if not root.exists():
            continue
        for child in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if child.name.startswith("."):
                continue
            key = _safe_rel(child)
            if key in seen:
                continue
            seen.add(key)
            if child.is_dir() or child.suffix.lower() in {".csv", ".json", ".html", ".md"}:
                entries.append(_output_entry(child))
    return {"outputs": entries}


@app.get("/app/themes")
async def app_themes():
    paths = _app_paths()
    themes_dir = paths["themes"]
    custom: List[Dict[str, Any]] = []
    invalid: List[Dict[str, str]] = []
    for path in sorted(themes_dir.glob(f"*{APP_THEME_SUFFIX}")):
        try:
            custom.append(_read_theme_file(path))
        except Exception as e:
            invalid.append({"path": _safe_rel(path), "name": path.name, "error": str(e)})
    return {
        "theme_suffix": APP_THEME_SUFFIX,
        "schema_version": THEME_SCHEMA_VERSION,
        "locked_drift_colors": LOCKED_DRIFT_COLORS,
        "built_in": BUILT_IN_THEME_PRESETS,
        "custom": custom,
        "invalid": invalid,
    }


@app.get("/app/providers")
async def app_providers():
    custom, invalid = _custom_provider_catalog()
    return {
        "provider_suffix": APP_PROVIDER_SUFFIX,
        "schema_version": PROVIDER_SCHEMA_VERSION,
        "built_in": _PROVIDER_DEFS,
        "custom": custom,
        "invalid": invalid,
    }


@app.get("/app/jobs")
async def app_job_list():
    return {"jobs": app_jobs.list()}


@app.get("/app/jobs/{job_id}")
async def app_job_detail(job_id: str):
    job = app_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/app/jobs/{job_id}/events")
async def app_job_events(job_id: str):
    from sse_starlette.sse import EventSourceResponse

    job = app_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator() -> AsyncGenerator[dict, None]:
        if bus.has(job_id):
            async for item in bus.subscribe(job_id):
                yield item
            return
        if job["status"] in _TERMINAL_JOB_STATUSES:
            yield {"event": job["status"], "data": job.get("error") or "Job finished"}

    return EventSourceResponse(event_generator())


@app.post("/app/jobs/{job_id}/cancel")
async def app_job_cancel(job_id: str):
    job = app_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] in _TERMINAL_JOB_STATUSES:
        raise HTTPException(status_code=409, detail="Job is already terminal")
    if bus.has(job_id):
        bus.cancel(job_id)
    app_jobs.update(job_id, phase="cancelling")
    return app_jobs.get(job_id)


@app.post("/app/jobs/evaluations")
async def app_evaluation_job(request: AppEvaluationJobRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid4())
    launcher = LauncherRequest(
        provider=request.provider,
        model=request.model,
        eval_set_ids=request.eval_set_ids,
    )
    config_dict = launcher_to_settings_dict(launcher, run_id=job_id)
    config_dict["tier"] = request.tier
    config_dict["batch"] = request.batch
    config_dict["_evaluation_id"] = job_id
    config_dict["_app_job_type"] = "evaluation"
    config_dict = _apply_custom_provider_config(config_dict)

    try:
        Settings(**config_dict)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    job = app_jobs.create("evaluation", config_dict, job_id=job_id)
    app_jobs.merge_summary(job_id, {
        "provider": request.provider,
        "model": request.model,
        "eval_sets": list(request.eval_set_ids),
    })
    bus.start(job_id)
    background_tasks.add_task(run_eval_background, job_id, config_dict, "completed")
    return app_jobs.get(job["id"])


@app.post("/app/jobs/drift/run")
async def app_drift_run_job(request: DriftRunJobRequest, background_tasks: BackgroundTasks):
    config = request.model_dump()
    job = app_jobs.create("drift_run", config)
    bus.start(job["id"])
    background_tasks.add_task(_run_app_drift_job, job["id"], "drift_run", config)
    return app_jobs.get(job["id"])


@app.post("/app/jobs/drift/calibrate")
async def app_drift_calibrate_job(request: DriftCalibrateJobRequest, background_tasks: BackgroundTasks):
    config = request.model_dump()
    job = app_jobs.create("drift_calibrate", config)
    bus.start(job["id"])
    background_tasks.add_task(_run_app_drift_job, job["id"], "drift_calibrate", config)
    return app_jobs.get(job["id"])


async def _run_app_drift_job(job_id: str, job_type: str, payload: Dict[str, Any]):
    app_jobs.update(job_id, status="running", phase="running")
    try:
        if job_type == "drift_run":
            result = await _execute_drift_run_job(app_jobs.get(job_id), payload)
        else:
            result = await _execute_drift_calibrate_job(app_jobs.get(job_id), payload)
        outputs = result.get("outputs") or []
        summary = result.get("summary") or {
            key: value for key, value in result.items()
            if key not in {"outputs"}
        }
        app_jobs.complete(job_id, summary=summary, outputs=outputs)
        await bus.mark_completed(job_id, {"event": "completed", "data": "Drift job finished"})
    except (asyncio.CancelledError, RunCancelled):
        app_jobs.cancel(job_id)
        await bus.mark_completed(job_id, {"event": "cancelled", "data": "Drift job cancelled"})
    except Exception as e:
        msg = str(e) or repr(e)
        app_jobs.fail(job_id, msg)
        await bus.mark_completed(job_id, {"event": "failed", "data": msg})


async def _execute_drift_run_job(job: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    from promptpressure.drift.schema import load_suite
    from promptpressure.drift import runner
    from promptpressure.adapters import load_adapter

    suite = load_suite(payload["suite"], strict=True)
    adapter_fn = load_adapter(payload["provider"])
    cfg = {
        "adapter": payload["provider"],
        "model": payload["model"],
        "model_name": payload["model"],
    }
    if payload.get("temperature") is not None:
        cfg["temperature"] = payload["temperature"]
    result = await runner.run_suite(
        suite.sequences,
        adapter_fn,
        cfg,
        concurrency=payload.get("concurrency", 3),
        turn_delay=payload.get("turn_delay", 0.0),
        timeout=payload.get("timeout", 90.0),
    )
    out_dir = _app_paths()["outputs"] / "drift" / suite.name / f"{payload['provider']}-{job['id']}"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "transcripts.json"
    path.write_text(json.dumps({
        "suite": suite.name,
        "provider": payload["provider"],
        "model": payload["model"],
        "transcripts": result["transcripts"],
        "runs": result["runs"],
    }, indent=2), encoding="utf-8")
    completed = sum(r["completed"] for r in result["runs"].values())
    total = sum(r["total"] for r in result["runs"].values())
    return {
        "summary": {"suite": suite.name, "completed_turns": completed, "total_turns": total},
        "outputs": [_output_entry(path)],
    }


async def _execute_drift_calibrate_job(job: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    from promptpressure.drift.schema import load_suite
    from promptpressure.drift.cli import _load_transcripts, _judge_n_times
    from promptpressure.drift import pipeline, report

    suite = load_suite(payload["suite"], strict=True)
    class Args:
        transcripts = payload.get("transcripts")
    transcripts, source = _load_transcripts(suite, Args())
    judge_runs = await _judge_n_times(
        suite,
        transcripts,
        payload["judge_provider"],
        payload["judge_model"],
        payload.get("temperature", 0.0),
        payload.get("runs", 3),
        payload.get("concurrency", 4),
    )
    result = pipeline.run_calibration(
        suite,
        judge_runs,
        judge_name=f"{payload['judge_provider']}/{payload['judge_model']}",
        n_boot=payload.get("bootstrap", 2000),
        seed=payload.get("seed", 0),
    )
    out_dir = _app_paths()["outputs"] / "drift" / suite.name / f"calibrate-{job['id']}"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "method.md"
    json_path = out_dir / "method.json"
    report_path.write_text(report.render_method_report(result, model_under_test=source, generated=_utcnow()), encoding="utf-8")
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    overall = result.get("judge_vs_human", {}).get("overall", {})
    return {
        "summary": {
            "suite": suite.name,
            "judge": f"{payload['judge_provider']}/{payload['judge_model']}",
            "kappa": overall.get("kappa"),
            "band": overall.get("band"),
        },
        "outputs": [_output_entry(report_path), _output_entry(json_path)],
    }


@app.get("/diagnostics", dependencies=[Depends(require_auth)])
async def get_diagnostics():
    from promptpressure.database import init_db, get_db_session
    from sqlalchemy import text
    import importlib.util
    import shutil

    checks = {}
    try:
        engine = await init_db()
        async for session in get_db_session(engine):
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"

    total, used, free = shutil.disk_usage(".")
    checks["disk_space"] = {
        "total_gb": round(total / (1024**3), 2),
        "free_gb": round(free / (1024**3), 2),
        "status": "ok" if free > 1024**2 * 100 else "low"
    }

    return {"status": "ok", "checks": checks}


async def _provider_status(definition: Dict[str, Any]) -> Dict[str, Any]:
    pid = definition["id"]
    out: Dict[str, Any] = {
        "id": pid,
        "label": definition["label"],
        "available": False,
        "reason": None,
        "remediation_hint": PROVIDER_REMEDIATION_HINTS.get(
            pid,
            f"Configure {pid} (see project README).",
        ),
    }

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
    return [await _provider_status(d) for d in _provider_definitions()]


@app.get("/models")
async def list_models(provider: str):
    definition = _provider_definition(provider)
    if definition is None:
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
    elif "models" in definition:
        suggestions = list(dict.fromkeys(definition["models"] + _suggestions_from_configs(provider)))
        payload = {
            "models": suggestions,
            "note": "Common model ids are prefilled. Type any model id this provider accepts.",
            "free_text": True,
        }
    else:
        suggestions = _suggestions_from_configs(provider)
        payload = {
            "models": suggestions,
            "note": "Type any model id this provider accepts. Suggestions come from existing configs/*.yaml.",
            "free_text": True,
        }

    _models_cache[cache_key] = payload
    return payload


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
        except Exception as e:
            logging.warning("Failed to parse %s: %s", path, e)
            count = 0
        label = path.removeprefix("evals_").removesuffix(".json").replace("_", " ").title()
        out.append({"id": path, "label": label, "count": count})

    _eval_sets_cache[cache_key] = out
    return out


# Ollama model management (local only)
@app.get("/ollama/health")
async def ollama_health():
    from promptpressure.adapters import ollama_adapter
    is_healthy = await ollama_adapter.check_health()
    return {"status": "ok" if is_healthy else "unavailable", "ollama": is_healthy}


@app.get("/ollama/models", dependencies=[Depends(require_auth)])
async def list_ollama_models():
    from promptpressure.adapters import ollama_adapter
    try:
        models = await ollama_adapter.list_models()
        return {"models": models}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Ollama unavailable: {str(e)}")


class OllamaModelRequest(BaseModel):
    name: str
    confirm: bool = False


@app.post("/ollama/models/pull", dependencies=[Depends(require_auth)])
async def pull_ollama_model(request: OllamaModelRequest, background_tasks: BackgroundTasks):
    if not request.confirm:
        raise HTTPException(status_code=409, detail="Confirmation required to pull an Ollama model")
    from promptpressure.adapters import ollama_adapter

    async def do_pull():
        try:
            await ollama_adapter.pull_model(request.name)
        except Exception as e:
            logging.error(f"Failed to pull model {request.name}: {e}")

    background_tasks.add_task(do_pull)
    return {"status": "pulling", "model": request.name}


@app.delete("/ollama/models/{model_name}", dependencies=[Depends(require_auth)])
async def delete_ollama_model(model_name: str, confirm: bool = Query(False)):
    if not confirm:
        raise HTTPException(status_code=409, detail="Confirmation required to delete an Ollama model")
    from promptpressure.adapters import ollama_adapter
    try:
        await ollama_adapter.delete_model(model_name)
        return {"status": "deleted", "model": model_name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Plugin management (auth-gated)
class InstallPluginRequest(BaseModel):
    name: str
    confirm: bool = False


@app.get("/plugins", dependencies=[Depends(require_auth)])
async def list_plugins():
    from promptpressure.plugins.core import PluginManager
    manager = PluginManager()
    return manager.list_available_plugins()


@app.post("/plugins/install", dependencies=[Depends(require_auth)])
async def install_plugin(request: InstallPluginRequest):
    if not request.confirm:
        raise HTTPException(status_code=409, detail="Confirmation required to install a plugin")
    from promptpressure.plugins.core import PluginManager
    manager = PluginManager()
    try:
        manager.install_plugin(request.name)
        return {"status": "installed", "name": request.name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def _outputs_from_run_result(result: Any) -> List[Dict[str, Any]]:
    output_dir = None
    if isinstance(result, tuple) and len(result) >= 2:
        output_dir = result[1]
    if not output_dir:
        return []
    path = Path(output_dir)
    if not path.exists():
        return []
    return [_output_entry(path)]


async def _set_evaluation_status(eval_id: str, status: str) -> None:
    try:
        from promptpressure.database import get_db_session, init_db, Evaluation
        engine = await init_db()
        async for session in get_db_session(engine):
            record = await session.get(Evaluation, eval_id)
            if record:
                record.status = status
                await session.commit()
        await engine.dispose()
    except Exception as e:
        logging.warning("Failed to update evaluation %s status to %s: %s", eval_id, status, e)


async def run_eval_background(run_id: str, config_dict: Dict[str, Any], completion_event_name: str = "complete"):
    bus.register_task(run_id, asyncio.current_task())
    if app_jobs.has(run_id):
        app_jobs.update(run_id, status="running", phase="starting")

    async def log_callback(event_type: str, data: Any):
        bus.raise_if_cancelled(run_id)
        if app_jobs.has(run_id):
            app_jobs.record_event(run_id, event_type, data)
        # JSON-encode dict/list payloads so SSE clients can parse cleanly.
        # sse-starlette serializes via str() by default, which yields Python repr
        # for dicts (single-quoted), breaking the frontend's JSON.parse(ev.data).
        if isinstance(data, (dict, list)):
            data = json.dumps(data, default=str)
        await bus.publish(run_id, {"event": event_type, "data": data})

    try:
        config_dict["_callback"] = log_callback
        config_dict["_is_cancelled"] = lambda: bus.is_cancelled(run_id)
        result = await run_evaluation_suite(config_dict, config_dict.get("adapter"))
        if app_jobs.has(run_id):
            app_jobs.complete(
                run_id,
                summary={
                    "provider": config_dict.get("provider_id") or config_dict.get("adapter"),
                    "model": config_dict.get("model") or config_dict.get("model_name"),
                    "eval_sets": config_dict.get("eval_set_ids") or [config_dict.get("dataset")],
                },
                outputs=_outputs_from_run_result(result),
            )
        await bus.mark_completed(run_id, {"event": completion_event_name, "data": "Evaluation finished"})
    except (asyncio.CancelledError, RunCancelled):
        logging.info("Run %s cancelled", run_id)
        if app_jobs.has(run_id):
            app_jobs.cancel(run_id)
        await _set_evaluation_status(config_dict.get("_evaluation_id") or run_id, "cancelled")
        await bus.mark_completed(run_id, {"event": "cancelled", "data": "Evaluation cancelled"})
    except (Exception, SystemExit) as e:
        # SystemExit is BaseException, not Exception — without catching it
        # explicitly, sys.exit() inside the eval pipeline (e.g., cli.py's
        # "Tier matched 0 entries" path) escaped the background task silently
        # and the SSE stream hung forever. Now any exit propagates as an
        # event:error frame so the frontend can surface it and unlock the form.
        if isinstance(e, SystemExit):
            msg = f"Eval task exited with code {e.code}"
        else:
            msg = str(e) or repr(e) or type(e).__name__
        logging.error(f"Run {run_id} failed: {msg}", exc_info=True)
        if app_jobs.has(run_id):
            app_jobs.fail(run_id, msg)
        await _set_evaluation_status(config_dict.get("_evaluation_id") or run_id, "failed")
        await bus.mark_completed(run_id, {"event": "error", "data": msg})
    finally:
        bus.unregister_task(run_id)

from fastapi.staticfiles import StaticFiles

# Frontend lives inside the package so pip-installed copies still find it.
# The Path(__file__).parent path resolves to the installed location at runtime
# (site-packages/promptpressure/frontend/) and the source tree location
# (<repo>/promptpressure/frontend/) interchangeably.
_frontend_dir = Path(__file__).resolve().parent / "frontend"
if _frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="PromptPressure API Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to run on")
    parser.add_argument("--cors-origins", help="Comma-separated CORS origins (overrides default localhost-only)")
    args = parser.parse_args()

    if args.cors_origins:
        os.environ["PROMPTPRESSURE_CORS_ORIGINS"] = args.cors_origins

    uvicorn.run(app, host=args.host, port=args.port)
