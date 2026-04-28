import asyncio
import glob
import json
import logging
import os
import hmac
import hashlib
import time
from contextlib import asynccontextmanager
from typing import Dict, Any, AsyncGenerator, Optional, List

import yaml as _yaml

from cachetools import TTLCache
from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, model_validator

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

_VALID_PROVIDERS = {p["id"] for p in _PROVIDER_DEFS}

PROVIDER_REMEDIATION_HINTS: dict[str, str] = {
    "openrouter": "Set OPENROUTER_API_KEY in your environment.",
    "ollama": "Start the ollama daemon: `ollama serve` (or run `ollama run <model>`).",
    "openai": "Set OPENAI_API_KEY in your environment.",
    "groq": "Set GROQ_API_KEY in your environment.",
    "deepseek": "Set OPENROUTER_API_KEY in your environment (DeepSeek routes via OpenRouter).",
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


@app.get("/health")
async def health_check():
    body: Dict[str, Any] = {"status": "ok", "version": "3.1.0"}
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
    cache_key = "providers"
    if cache_key in _providers_cache:
        return _providers_cache[cache_key]
    result = [await _provider_status(d) for d in _PROVIDER_DEFS]
    _providers_cache[cache_key] = result
    return result


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


@app.post("/ollama/models/pull", dependencies=[Depends(require_auth)])
async def pull_ollama_model(request: OllamaModelRequest, background_tasks: BackgroundTasks):
    from promptpressure.adapters import ollama_adapter

    async def do_pull():
        try:
            await ollama_adapter.pull_model(request.name)
        except Exception as e:
            logging.error(f"Failed to pull model {request.name}: {e}")

    background_tasks.add_task(do_pull)
    return {"status": "pulling", "model": request.name}


@app.delete("/ollama/models/{model_name}", dependencies=[Depends(require_auth)])
async def delete_ollama_model(model_name: str):
    from promptpressure.adapters import ollama_adapter
    try:
        await ollama_adapter.delete_model(model_name)
        return {"status": "deleted", "model": model_name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Plugin management (auth-gated)
class InstallPluginRequest(BaseModel):
    name: str


@app.get("/plugins", dependencies=[Depends(require_auth)])
async def list_plugins():
    from promptpressure.plugins.core import PluginManager
    manager = PluginManager()
    return manager.list_available_plugins()


@app.post("/plugins/install", dependencies=[Depends(require_auth)])
async def install_plugin(request: InstallPluginRequest):
    from promptpressure.plugins.core import PluginManager
    manager = PluginManager()
    try:
        manager.install_plugin(request.name)
        return {"status": "installed", "name": request.name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


async def run_eval_background(run_id: str, config_dict: Dict[str, Any]):
    async def log_callback(event_type: str, data: Any):
        # JSON-encode dict/list payloads so SSE clients can parse cleanly.
        # sse-starlette serializes via str() by default, which yields Python repr
        # for dicts (single-quoted), breaking the frontend's JSON.parse(ev.data).
        if isinstance(data, (dict, list)):
            data = json.dumps(data, default=str)
        await bus.publish(run_id, {"event": event_type, "data": data})

    try:
        config_dict["_callback"] = log_callback
        await run_evaluation_suite(config_dict, config_dict.get("adapter"))
        await bus.mark_completed(run_id, {"event": "complete", "data": "Evaluation finished"})
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
        await bus.mark_completed(run_id, {"event": "error", "data": msg})


from pathlib import Path
from fastapi.staticfiles import StaticFiles

_frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
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
