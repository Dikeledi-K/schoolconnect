"""Shared test setup.

Environment variables are set BEFORE the app is imported, so tests never use
a real API key, never call the internet, and never touch the local database.
Real environment variables beat the .env file in pydantic-settings.
"""

import os

os.environ["LLM_PROVIDER"] = "rules"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["API_KEY"] = ""
os.environ["DATABASE_URL"] = "sqlite://"  # in-memory

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import models  # noqa: E402,F401  - registers tables
from app.config import get_settings  # noqa: E402
from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def db_session():
    """A fresh in-memory database for each test.

    StaticPool keeps ONE connection so every session sees the same in-memory DB.
    """
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    """FastAPI test client wired to the test database."""
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def set_env(monkeypatch):
    """Change a setting for one test, e.g. set_env(API_KEY="secret")."""

    def _set(**values):
        for key, value in values.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()


# --------------------------------------------------------------------------
# Week 5 forecasting fixtures: ~15 months of synthetic history, built once.
# --------------------------------------------------------------------------

HISTORY_START, HISTORY_END = "2024-11-01", "2026-02-01"
DEMO_AS_OF = "2025-12-15"   # forecast the January 2026 opening rush from mid-December


@pytest.fixture(scope="session")
def history_sessionmaker(tmp_path_factory):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from sqlalchemy import insert

    from app.models import Ticket
    from app.synthetic import generate_tickets

    path = tmp_path_factory.mktemp("history") / "history.db"
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    now = datetime(2026, 2, 2, 8, 0, tzinfo=ZoneInfo("Africa/Johannesburg"))
    with Session() as db:
        db.execute(insert(Ticket), generate_tickets(HISTORY_START, HISTORY_END, seed=7, now=now))
        db.commit()
    return Session


@pytest.fixture
def history_client(history_sessionmaker):
    """API client wired to the synthetic-history database."""
    from app.forecasting import service

    service.clear_cache()

    def override():
        db = history_sessionmaker()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def demo_bundle(history_sessionmaker):
    """The full forecasting pipeline run from mid-December 2025 (shared by tests)."""
    from app import crud
    from app.forecasting import service

    with history_sessionmaker() as db:
        rows = crud.ticket_timestamps(db)
    return service.compute_bundle(rows, DEMO_AS_OF)

