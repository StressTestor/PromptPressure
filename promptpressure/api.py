import asyncio
import json
import logging
import os
import hmac
import hashlib
import time
from typing import Dict, Any, AsyncGenerator, Optional

from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from promptpressure.config import Settings
from promptpressure.cli import run_evaluation_suite

app = FastAPI(title="PromptPressure API", version="3.0.0")

# CORS: localhost-only by default, overridable via PROMPTPRESSURE_CORS_ORIGINS env var
_default_origins = ["http://localhost:3000", "http://localhost:8000", "http://127.0.0.1:3000", "http://127.0.0.1:8000"]
_cors_origins = os.getenv("PROMPTPRESSURE_CORS_ORIGINS", "").split(",") if os.getenv("PROMPTPRESSURE_CORS_ORIGINS") else _default_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

# JWT-like auth using HMAC-SHA256 bearer tokens
# Set PROMPTPRESSURE_API_SECRET to enable auth. If unset, auth is disabled (local dev).
API_SECRET = os.getenv("PROMPTPRESSURE_API_SECRET")

EVENT_QUEUES: Dict[str, asyncio.Queue] = {}


def _verify_token(token: str) -> bool:
    """Verify a bearer token. Token format: timestamp.signature"""
    if not API_SECRET:
        return True
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return False
        ts, sig = parts
        expected = hmac.new(API_SECRET.encode(), ts.encode(), hashlib.sha256).hexdigest()
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
    config: Dict[str, Any]


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "3.0.0"}


@app.post("/evaluate", dependencies=[Depends(require_auth)])
async def trigger_evaluation(request: EvalRequest, background_tasks: BackgroundTasks):
    import uuid
    run_id = str(uuid.uuid4())
    EVENT_QUEUES[run_id] = asyncio.Queue()

    try:
        Settings(**request.config)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    background_tasks.add_task(run_eval_background, run_id, request.config)
    return {"run_id": run_id, "status": "started", "stream_url": f"/stream/{run_id}"}


@app.get("/stream/{run_id}")
async def stream_events(run_id: str):
    from sse_starlette.sse import EventSourceResponse
    if run_id not in EVENT_QUEUES:
        raise HTTPException(status_code=404, detail="Run ID not found")

    queue = EVENT_QUEUES[run_id]

    async def event_generator() -> AsyncGenerator[dict, None]:
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

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
    queue = EVENT_QUEUES.get(run_id)

    async def log_callback(event_type: str, data: Any):
        if queue:
            await queue.put({"event": event_type, "data": data})

    try:
        config_dict['_callback'] = log_callback
        await run_evaluation_suite(config_dict, config_dict.get("adapter"))

        if queue:
            await queue.put({"event": "complete", "data": "Evaluation finished"})
            await queue.put(None)
    except Exception as e:
        logging.error(f"Run {run_id} failed: {e}")
        if queue:
            await queue.put({"event": "error", "data": str(e)})
            await queue.put(None)


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
