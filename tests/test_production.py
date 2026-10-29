"""Week 8: Supabase engine settings, refusing to start half-configured, the demo banner."""

import inspect
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, check_production_settings
from app.db import engine_options, make_engine, normalise_url
from app.main import app

POOLER = "postgresql://postgres.abcdefgh:secret@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
SESSION = "postgresql://postgres.abcdefgh:secret@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"


# ---- Database engine --------------------------------------------------------
def test_sqlite_settings_are_unchanged():
    assert engine_options("sqlite:///./schoolconnect.db") == {
        "connect_args": {"check_same_thread": False}, "pool_pre_ping": True}


def test_supabase_url_uses_psycopg3():
    assert normalise_url(POOLER).startswith("postgresql+psycopg://postgres.abcdefgh:")
    assert normalise_url("postgres://u:p@h:6543/db") == "postgresql+psycopg://u:p@h:6543/db"
    assert normalise_url("postgresql+psycopg://u:p@h/db") == "postgresql+psycopg://u:p@h/db"


def test_transaction_pooler_turns_off_prepared_statements_and_uses_a_small_pool():
    opts = engine_options(POOLER)
    assert opts["connect_args"] == {"connect_timeout": 10, "sslmode": "require", "prepare_threshold": None}
    assert (opts["pool_size"], opts["max_overflow"], opts["pool_pre_ping"]) == (3, 2, True)
    assert opts["pool_recycle"] == 300


def test_session_pooler_keeps_prepared_statements_and_url_sslmode_wins():
    assert "prepare_threshold" not in engine_options(SESSION)["connect_args"]
    assert "sslmode" not in engine_options(POOLER + "?sslmode=verify-full")["connect_args"]


def test_make_engine_builds_a_postgres_engine_without_connecting():
    engine = make_engine(POOLER)
    assert engine.dialect.name == "postgresql" and engine.dialect.driver == "psycopg"
    assert engine.pool.size() == 3
    engine.dispose()


# ---- Production safety -------------------------------------------------------
GOOD = dict(environment="production", api_key="k" * 32, jobs_token="j" * 32, database_url=POOLER,
            password_hash_iterations=600_000)


def test_development_never_blocks():
    check_production_settings(Settings(environment="development", api_key="", jobs_token=""))


def test_complete_production_settings_pass():
    check_production_settings(Settings(**GOOD))


@pytest.mark.parametrize("change,message", [
    ({"api_key": ""}, "API_KEY is empty"),
    ({"jobs_token": ""}, "JOBS_TOKEN is empty"),
    ({"password_hash_iterations": 1000}, "PASSWORD_HASH_ITERATIONS"),
    ({"database_url": "sqlite:///./schoolconnect.db"}, "SQLite"),
])
def test_production_refuses_missing_or_weak_settings(change, message):
    with pytest.raises(RuntimeError, match=message):
        check_production_settings(Settings(**{**GOOD, **change}))


def test_the_app_refuses_to_start_in_production_without_secrets(set_env):
    set_env(ENVIRONMENT="production", API_KEY="", JOBS_TOKEN="")
    with pytest.raises(RuntimeError, match="Refusing to start"):
        with TestClient(app):
            pass


# ---- "This is a demo" banner --------------------------------------------------
def test_api_docs_say_it_is_a_demo(client):
    assert "Demo: fictional school, synthetic data" in client.get("/openapi.json").json()["info"]["description"]


def test_every_page_shows_the_demo_banner():
    pytest.importorskip("streamlit")
    frontend = Path(__file__).resolve().parent.parent / "frontend"
    sys.path.insert(0, str(frontend))
    import ui

    assert "Demo: fictional school, synthetic data" in ui.DEMO_TEXT
    assert "demo_banner()" in inspect.getsource(ui.page)
    for page in [frontend / "Home.py", *sorted((frontend / "pages").glob("*.py"))]:
        assert "ui.page(" in page.read_text(encoding="utf-8"), page.name


def test_every_sidebar_page_has_a_colour_and_an_icon():
    """A page without a colour rule showed a white label on a white button when selected."""
    import re

    frontend = Path(__file__).resolve().parent.parent / "frontend"
    css = (frontend / "ui.py").read_text(encoding="utf-8")
    pages = 1 + len(list((frontend / "pages").glob("*.py")))          # Home + pages/
    colours = set(re.findall(r'li:nth-child\((\d+)\) a \{ --accent', css))
    icons = set(re.findall(r'li:nth-child\((\d+)\) a p::before', css))
    assert colours >= {str(i) for i in range(1, pages + 1)} and icons >= {str(i) for i in range(1, pages + 1)}


def test_pasted_secrets_lose_surrounding_whitespace(monkeypatch):
    """A DATABASE_URL secret pasted with a trailing newline broke the GitHub job (database "postgres\n")."""
    monkeypatch.setenv("DATABASE_URL", POOLER + "\n")
    monkeypatch.setenv("JOBS_TOKEN", "  tok \n")
    settings = Settings()
    assert settings.database_url == POOLER and settings.jobs_token == "tok"
    assert make_engine(settings.database_url).url.database == "postgres"
