import os
from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Text, DateTime, Float, ForeignKey, Integer, Boolean, JSON

# Use SQLite by default, but allow override for PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///promptpressure.db")

class Base(DeclarativeBase):
    pass

class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=True)
    project: Mapped["Project"] = relationship(back_populates="evaluations")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    config_snapshot: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending, running, completed, failed
    
    results: Mapped[list["Result"]] = relationship(back_populates="evaluation", cascade="all, delete-orphan")
    metrics: Mapped[list["Metric"]] = relationship(back_populates="evaluation", cascade="all, delete-orphan")

class AdapterConfig(Base):
    __tablename__ = "adapter_configs"
    
    id: Mapped[str] = mapped_column(primary_key=True)
    base_type: Mapped[str] = mapped_column(String)
    api_key: Mapped[str] = mapped_column(String, nullable=True)
    model_name: Mapped[str] = mapped_column(String)
    api_base: Mapped[str] = mapped_column(String, nullable=True)
    parameters: Mapped[dict] = mapped_column(JSON, default={})

class Project(Base):
    __tablename__ = "projects"
    
    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    evaluations: Mapped[list["Evaluation"]] = relationship(back_populates="project")
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=True)
    team: Mapped["Team"] = relationship(back_populates="projects")


class Result(Base):
    __tablename__ = "results"

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id"))
    prompt_id: Mapped[str] = mapped_column(String, nullable=True) # ID from the dataset
    prompt_text: Mapped[str] = mapped_column(Text)
    response_text: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String)
    adapter: Mapped[str] = mapped_column(String)
    latency_ms: Mapped[float] = mapped_column(Float)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    
    evaluation: Mapped["Evaluation"] = relationship(back_populates="results")
    comments: Mapped[list["Comment"]] = relationship(back_populates="result", cascade="all, delete-orphan")

class Team(Base):
    __tablename__ = "teams"
    
    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    users: Mapped[list["User"]] = relationship(back_populates="team")
    projects: Mapped[list["Project"]] = relationship(back_populates="team")

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[str] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True)
    role: Mapped[str] = mapped_column(String, default="viewer")
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=True)
    
    team: Mapped["Team"] = relationship(back_populates="users")
    comments: Mapped[list["Comment"]] = relationship(back_populates="user")

class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("results.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    result: Mapped["Result"] = relationship(back_populates="comments")
    user: Mapped["User"] = relationship(back_populates="comments")

class Metric(Base):
    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id"))
    name: Mapped[str] = mapped_column(String)
    value: Mapped[float] = mapped_column(Float)
    tags: Mapped[dict] = mapped_column(JSON, nullable=True)

    evaluation: Mapped["Evaluation"] = relationship(back_populates="metrics")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String) # e.g., "create_team", "add_comment"
    user_id: Mapped[str] = mapped_column(String)
    target_type: Mapped[str] = mapped_column(String) # e.g., "team", "comment"
    target_id: Mapped[str] = mapped_column(String)
    details: Mapped[dict] = mapped_column(JSON, default={})
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


async def init_db():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine

async def get_db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
