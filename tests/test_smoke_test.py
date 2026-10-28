"""Week 8: scripts/smoke_test_prod.py, run against the real app in-process (no internet)."""

import shutil
import sys
from datetime import date
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.main import app
from tests.conftest import TEST_PASSWORD, add_staff

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import smoke_test_prod  # noqa: E402


def _web(status=200):
    """A pretend Streamlit server."""
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status, text="ok")))


def test_all_checks_pass_on_a_working_deployment(history_sessionmaker, tmp_path, capsys):
    # Work on a COPY of the shared history database, so other tests are not affected.
    source = Path(history_sessionmaker.kw["bind"].url.database)
    shutil.copy(source, tmp_path / "smoke.db")
    engine = create_engine(f"sqlite:///{tmp_path / 'smoke.db'}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as db:
        from app.auth.service import get_staff_by_email

        if get_staff_by_email(db, "principal@test.example") is None:
            add_staff(db, "Ms Dlamini", "principal", email="principal@test.example")
        add_staff(db, "Mr Nel", "class_teacher", email="teacher@ubuntu-demo.school.example")
        from app.reports.weekly import run_weekly_job

        run_weekly_job(db, week_start=date(2026, 1, 19), include_outlook=False)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as api:
            # A learner-welfare ticket the class teacher must not see.
            assert api.post("/tickets", json={"message": "My son is being bullied at school"}).status_code == 201
            ok = smoke_test_prod.run("http://testserver", "https://web.example", "principal@test.example",
                                     TEST_PASSWORD, "", "teacher@ubuntu-demo.school.example", TEST_PASSWORD,
                                     http=api, web_http=_web())
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
    out = capsys.readouterr().out
    assert ok, out
    assert out.count("PASS") == 9 and "FAIL" not in out and "9/9 checks passed" in out
    assert "class teacher 404" in out and "2025-12-15" in out


def test_a_failing_check_is_reported_and_fails_the_run(client, capsys):
    ok = smoke_test_prod.run("http://testserver", "https://web.example", "principal@test.example",
                             TEST_PASSWORD, "", "nobody@test.example", TEST_PASSWORD,
                             http=client, web_http=_web(503))
    out = capsys.readouterr().out
    assert not ok
    assert "FAIL" in out and "web home page loads" in out and "PASS" in out   # health + login still pass


def test_secrets_come_from_env_or_dotenv_never_arguments(monkeypatch):
    monkeypatch.setenv("SMOKE_PASSWORD", "from-env")
    assert smoke_test_prod.secret("SMOKE_PASSWORD", "prompt: ") == "from-env"
    monkeypatch.delenv("SMOKE_PASSWORD")
    monkeypatch.setattr(smoke_test_prod, "_from_dotenv", lambda name: "")
    monkeypatch.setattr(smoke_test_prod.getpass, "getpass", lambda prompt: "typed")
    assert smoke_test_prod.secret("SMOKE_PASSWORD", "prompt: ") == "typed"
