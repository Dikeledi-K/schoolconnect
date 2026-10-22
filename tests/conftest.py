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
