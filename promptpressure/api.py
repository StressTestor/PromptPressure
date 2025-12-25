import asyncio
import json
import logging
from typing import Dict, Any, AsyncGenerator, Optional

from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

from config import Settings
from run_eval import run_evaluation_suite

app = FastAPI(title="PromptPressure Headless API", version="1.9.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global event queue for streaming logs (simple implementation for single-worker)
# In production, this would be a Redis Pub/Sub or similar
EVENT_QUEUES: Dict[str, asyncio.Queue] = {}

class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Log state-changing operations
        if request.method in ["POST", "PUT", "DELETE"] and response.status_code < 400:
            user_id = request.headers.get("X-User-ID", "anonymous")
            path = request.url.path
            
            # Fire and forget logging (in background task ideally, but here async inline for simplicity or robust loop)
            # Since middleware cannot easily access DB session safely without new scope, 
            # we'll just queue it or use a separate helper. 
            # For this prototype, we'll do a quick DB insert via a helper function.
            await self.log_audit(user_id, path, request.method)
            
        return response

    async def log_audit(self, user_id: str, path: str, method: str):
        from database import init_db, get_db_session, AuditLog
        try:
             engine = await init_db()
             async for session in get_db_session(engine):
                 log = AuditLog(
                     action=f"{method} {path}",
                     user_id=user_id,
                     target_type="http_resource",
                     target_id=path,
                     details={"method": method, "path": path}
                 )
                 session.add(log)
                 await session.commit()
        except Exception as e:
            print(f"Failed to write audit log: {e}")

app.add_middleware(AuditMiddleware)

async def get_current_user(x_user_id: str = Header(None)):
    if not x_user_id:
        return None # Anonymous
    from database import get_db_session, init_db, User
    from sqlalchemy import select
    engine = await init_db()
    async for session in get_db_session(engine):
        result = await session.execute(select(User).where(User.id == x_user_id))
        user = result.scalar_one_or_none()
        return user

class EvalRequest(BaseModel):
    config: Dict[str, Any]
    project_id: Optional[str] = None

class TeamCreate(BaseModel):
    id: str
    name: str

class UserCreate(BaseModel):
    id: str
    username: str
    team_id: Optional[str] = None
    role: str = "viewer"

class CommentCreate(BaseModel):
    result_id: int
    user_id: str
    content: str

class ProjectCreate(BaseModel):
    id: str
    name: str

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "1.9.0"}

@app.post("/projects")
async def create_project(project: ProjectCreate):
    from database import get_db_session, init_db, Project
    engine = await init_db()
    async for session in get_db_session(engine):
        db_project = Project(id=project.id, name=project.name)
        session.add(db_project)
        await session.commit()
    return project

@app.get("/projects")
async def list_projects():
    from database import get_db_session, init_db, Project
    from sqlalchemy import select
    engine = await init_db()
    async for session in get_db_session(engine):
        result = await session.execute(select(Project))
        projects = result.scalars().all()
        return [{"id": p.id, "name": p.name} for p in projects]

@app.post("/teams")
async def create_team(team: TeamCreate):
    from database import get_db_session, init_db, Team
    engine = await init_db()
    async for session in get_db_session(engine):
        db_team = Team(id=team.id, name=team.name)
        session.add(db_team)
        try:
            await session.commit()
        except:
            raise HTTPException(status_code=400, detail="Team already exists")
    return team

@app.get("/teams")
async def list_teams():
    from database import get_db_session, init_db, Team
    from sqlalchemy import select
    engine = await init_db()
    async for session in get_db_session(engine):
        result = await session.execute(select(Team))
        teams = result.scalars().all()
        return [{"id": t.id, "name": t.name} for t in teams]

@app.post("/users")
async def create_user(user: UserCreate):
    from database import get_db_session, init_db, User
    engine = await init_db()
    async for session in get_db_session(engine):
        db_user = User(id=user.id, username=user.username, role=user.role, team_id=user.team_id)
        session.add(db_user)
        try:
            await session.commit()
        except:
            raise HTTPException(status_code=400, detail="User already exists")
    return user

@app.post("/comments")
async def add_comment(comment: CommentCreate):
    from database import get_db_session, init_db, Comment
    engine = await init_db()
    async for session in get_db_session(engine):
        db_comment = Comment(
            result_id=comment.result_id,
            user_id=comment.user_id,
            content=comment.content
        )
        session.add(db_comment)
        await session.commit()
    return comment

@app.get("/comments/{result_id}")
async def get_comments(result_id: int):
    from database import get_db_session, init_db, Comment
    from sqlalchemy import select
    engine = await init_db()
    async for session in get_db_session(engine):
        result = await session.execute(select(Comment).where(Comment.result_id == result_id))
        comments = result.scalars().all()
        return [{"id": c.id, "user_id": c.user_id, "content": c.content, "timestamp": c.timestamp.isoformat()} for c in comments]

@app.get("/admin/export")
async def export_data():
    from database import get_db_session, init_db, Team, User, Project, Evaluation, Result, Comment
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    
    engine = await init_db()
    data = {}
    async for session in get_db_session(engine):
        # Dump Teams
        teams = (await session.execute(select(Team))).scalars().all()
        data["teams"] = [{"id": t.id, "name": t.name} for t in teams]
        
        # Dump Users
        users = (await session.execute(select(User))).scalars().all()
        data["users"] = [{"id": u.id, "username": u.username, "role": u.role, "team_id": u.team_id} for u in users]
        
        # Dump Projects
        projects = (await session.execute(select(Project))).scalars().all()
        data["projects"] = [{"id": p.id, "name": p.name, "team_id": p.team_id} for p in projects]
        
        # Dump Evaluations (simplify for export, maybe just ID and status to avoid huge dumps)
        evals = (await session.execute(select(Evaluation))).scalars().all()
        data["evaluations"] = [{"id": e.id, "project_id": e.project_id, "status": e.status, "timestamp": e.timestamp.isoformat()} for e in evals]

        # Dump Comments
        comments = (await session.execute(select(Comment))).scalars().all()
        data["comments"] = [{"id": c.id, "result_id": c.result_id, "user_id": c.user_id, "content": c.content, "timestamp": c.timestamp.isoformat()} for c in comments]
        
    return data

@app.get("/audit-logs")
async def get_audit_logs():
    from database import get_db_session, init_db, AuditLog
    from sqlalchemy import select
    engine = await init_db()
    async for session in get_db_session(engine):
        result = await session.execute(select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(100))
        logs = result.scalars().all()
        return [{"id": l.id, "action": l.action, "user_id": l.user_id, "timestamp": l.timestamp.isoformat(), "details": l.details} for l in logs]

# Mock SSO Endpoints
@app.post("/auth/sso/login")
async def sso_login(provider: str):
    # In real app, redirect to IDP
    return {"status": "redirect", "url": f"https://mock-idp.com/login?provider={provider}"}

@app.post("/auth/sso/callback")
async def sso_callback(code: str):
    # Exchange code for token
    return {"token": "mock_jwt_token", "user": {"id": "sso-user", "email": "user@example.com"}}

@app.post("/admin/import")
async def import_data(data: Dict[str, Any]):
    return {"status": "not_implemented", "message": "Import logic is complex and risky, stubbed for safety."}


class InstallPluginRequest(BaseModel):
    name: str

@app.get("/plugins")
async def list_plugins():
    from plugins.core import PluginManager
    manager = PluginManager()
    return manager.list_available_plugins()

@app.post("/plugins/install")
async def install_plugin(request: InstallPluginRequest):
    from plugins.core import PluginManager
    manager = PluginManager()
    try:
        manager.install_plugin(request.name)
        return {"status": "installed", "name": request.name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class AdapterCreate(BaseModel):
    id: str
    base_type: str
    model_name: str
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    parameters: Dict[str, Any] = {}

@app.post("/adapters")
async def create_adapter(adapter: AdapterCreate):
    from database import get_db_session, init_db, AdapterConfig
    engine = await init_db()
    async for session in get_db_session(engine):
        db_adapter = AdapterConfig(
            id=adapter.id,
            base_type=adapter.base_type,
            model_name=adapter.model_name,
            api_key=adapter.api_key,
            api_base=adapter.api_base,
            parameters=adapter.parameters
        )
        session.add(db_adapter)
        await session.commit()
    return adapter

@app.get("/adapters")
async def list_adapters():
    from database import get_db_session, init_db, AdapterConfig
    from sqlalchemy import select
    engine = await init_db()
    async for session in get_db_session(engine):
        result = await session.execute(select(AdapterConfig))
        result = await session.execute(select(AdapterConfig))
        return result.scalars().all()

@app.get("/evaluations")
async def list_evaluations():
    from database import get_db_session, init_db, Evaluation
    from sqlalchemy import select
    engine = await init_db()
    async for session in get_db_session(engine):
        result = await session.execute(select(Evaluation).order_by(Evaluation.timestamp.desc()))
        evals = result.scalars().all()
        return [{"id": e.id, "project_id": e.project_id, "status": e.status, "timestamp": e.timestamp.isoformat()} for e in evals]

@app.get("/evaluations/{eval_id}")
async def get_evaluation(eval_id: int):
    from database import get_db_session, init_db, Evaluation, Result, Comment
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    engine = await init_db()
    async for session in get_db_session(engine):
        # Fetch evaluation with results AND comments for those results
        # This nested load is a bit tricky in async SQLAlchemy without proper chaining or separate queries.
        # Let's simplify: Fetch Eval + Results. Then Fetch Comments for those results.
        
        # 1. Fetch Eval + Results
        query = select(Evaluation).where(Evaluation.id == eval_id).options(selectinload(Evaluation.results))
        result = await session.execute(query)
        evaluation = result.scalar_one_or_none()
        
        if not evaluation:
            raise HTTPException(status_code=404, detail="Evaluation not found")
            
        # 2. Fetch comments for all results in this evaluation
        result_ids = [r.id for r in evaluation.results]
        comments_query = select(Comment).where(Comment.result_id.in_(result_ids))
        comments_result = await session.execute(comments_query)
        all_comments = comments_result.scalars().all()
        
        # Group comments by result_id
        comments_map = {}
        for c in all_comments:
            if c.result_id not in comments_map:
                comments_map[c.result_id] = []
            comments_map[c.result_id].append({
                "id": c.id, 
                "user_id": c.user_id, 
                "content": c.content, 
                "timestamp": c.timestamp.isoformat()
            })
            
        return {
            "id": evaluation.id,
            "project_id": evaluation.project_id,
            "status": evaluation.status,
            "timestamp": evaluation.timestamp.isoformat(),
            "results": [{
                "id": r.id,
                "prompt_text": r.prompt_text,
                "response_text": r.response_text,
                "model": r.model,
                "success": r.success,
                "latency_ms": r.latency_ms,
                "comments": comments_map.get(r.id, [])
            } for r in evaluation.results]
        }

@app.get("/analytics/trends")
async def get_analytics_trends():
    from database import get_db_session, init_db, Evaluation
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from collections import defaultdict
    from datetime import datetime

    engine = await init_db()
    async for session in get_db_session(engine):
        # Fetch completed evaluations with results loaded
        query = select(Evaluation).where(Evaluation.status == "completed").options(selectinload(Evaluation.results))
        result = await session.execute(query)
        evals = result.scalars().all()

        # Aggregate by date
        trends = defaultdict(lambda: {"date": "", "total_latency": 0.0, "total_requests": 0, "success_count": 0})

        for e in evals:
            date_str = e.timestamp.strftime("%Y-%m-%d")
            entry = trends[date_str]
            entry["date"] = date_str
            
            for r in e.results:
                entry["total_requests"] += 1
                if r.success:
                    entry["success_count"] += 1
                    entry["total_latency"] += r.latency_ms

        # Finalize averages
        output = []
        for date_str, data in sorted(trends.items()):
            count = data["total_requests"]
            if count > 0:
                output.append({
                    "date": date_str,
                    "avg_latency": round(data["total_latency"] / count, 2),
                    "success_rate": round((data["success_count"] / count) * 100, 2),
                    "total_requests": count
                })
        
        return output

@app.get("/schema")
async def get_schema():
    return Settings.model_json_schema()

async def run_eval_background(run_id: str, config_dict: Dict[str, Any]):
    queue = EVENT_QUEUES.get(run_id)
    
    async def log_callback(event_type: str, data: Any):
        if queue:
            await queue.put({"event": event_type, "data": data})

    try:
        # Inject callback into run_evaluation_suite (requires refactor in run_eval.py)
        # We'll pass a special config key or modified function signature
        # For now, let's assume we pass it via a wrapper or direct arg if we change it.
        # Since run_evaluation_suite signature is fixed in previous steps, we need to update it.
        
        # NOTE: We need to modify run_evaluation_suite to accept a callback.
        config_dict['_callback'] = log_callback 
        
        await run_evaluation_suite(config_dict, config_dict.get("adapter"))
        
        if queue:
            await queue.put({"event": "complete", "data": "Evaluation finished"})
            await queue.put(None) # Signal end
            
    except Exception as e:
        logging.error(f"Run {run_id} failed: {e}")
        if queue:
            await queue.put({"event": "error", "data": str(e)})
            await queue.put(None)

@app.post("/evaluate")
async def trigger_evaluation(request: EvalRequest, background_tasks: BackgroundTasks):
    import uuid
    run_id = str(uuid.uuid4())
    EVENT_QUEUES[run_id] = asyncio.Queue()
    
    # Validate config using Pydantic
    try:
        Settings(**request.config)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    background_tasks.add_task(run_eval_background, run_id, request.config)
    
    return {"run_id": run_id, "status": "started", "stream_url": f"/stream/{run_id}"}

@app.get("/stream/{run_id}")
async def stream_events(run_id: str):
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

@app.get("/diagnostics")
async def get_diagnostics():
    from database import init_db, get_db_session
    from sqlalchemy import text
    import importlib.util
    import shutil

    checks = {}

    # 1. Database Check
    try:
        engine = await init_db()
        async for session in get_db_session(engine):
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"

    # 2. Disk Space
    total, used, free = shutil.disk_usage(".")
    checks["disk_space"] = {
        "total_gb": round(total / (1024**3), 2),
        "free_gb": round(free / (1024**3), 2),
        "status": "ok" if free > 1024**2 * 100 else "low"
    }

    # 3. Dependencies
    required_packages = ["fastapi", "sqlalchemy", "pydantic", "uvicorn", "httpx"]
    pkg_status = {}
    for pkg in required_packages:
        spec = importlib.util.find_spec(pkg)
        pkg_status[pkg] = "installed" if spec else "missing"
    checks["dependencies"] = pkg_status

    return {"status": "ok", "checks": checks}
