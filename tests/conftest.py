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
os.environ["PASSWORD_HASH_ITERATIONS"] = "1000"   # fast hashing in tests (real default: 600 000)

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


# --------------------------------------------------------------------------
# Week 7: staff accounts. Staff endpoints need a login, so `client` is logged in as the
# principal (who may see everything). `anon_client` is a parent / not logged in.
# --------------------------------------------------------------------------
TEST_PASSWORD = "test-password-123"
PRINCIPAL_NAME = "Ms Dlamini"


def add_staff(db, name: str, role: str, email: str | None = None, active: bool = True):
    from app.auth.service import create_staff

    email = email or f"{role}.{name.split()[-1].lower()}@test.example"
    return create_staff(db, name, email, role, TEST_PASSWORD, active=active)


def login_headers(client, email: str, password: str = TEST_PASSWORD) -> dict:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
def anon_client(db_session):
    """Test client wired to the test database, NOT logged in."""
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client(db_session):
    """Test client logged in as the principal ("Ms Dlamini")."""
    app.dependency_overrides[get_db] = lambda: db_session
    principal = add_staff(db_session, PRINCIPAL_NAME, "principal", email="principal@test.example")
    with TestClient(app) as c:
        c.headers.update(login_headers(c, principal.email))
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def login_as(db_session, anon_client):
    """login_as("admin_clerk", "Mr Khumalo") -> (staff, auth headers) for a new account."""

    def _login(role: str, name: str | None = None):
        staff = add_staff(db_session, name or f"Test {role}", role)
        return staff, login_headers(anon_client, staff.email)

    return _login


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

    from app.auth.service import get_staff_by_email

    with history_sessionmaker() as db:
        if get_staff_by_email(db, "principal@test.example") is None:
            add_staff(db, PRINCIPAL_NAME, "principal", email="principal@test.example")

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        c.headers.update(login_headers(c, "principal@test.example"))
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

