"""Database connection setup (SQLAlchemy 2.0).

Only DATABASE_URL changes between SQLite (local) and Supabase Postgres (production).
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Parent class for all ORM models."""


def make_engine(url: str):
    # SQLite needs check_same_thread=False because FastAPI may use the
    # connection from a different thread than the one that created it.
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    # pool_pre_ping avoids errors from stale connections on hosted Postgres.
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Create tables if they don't exist. (Week 8 may add migrations.)"""
    from app import models  # noqa: F401  - import registers the models with Base

    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
