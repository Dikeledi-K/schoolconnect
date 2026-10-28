"""The demo scripts must keep working: they are what we run in front of the panel.

Each script runs as a separate process against a temporary SQLite file (never the real
database), with the offline rules classifier and a fast password-hash setting.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PASSWORD = "test-demo-password"


def run_script(name: str, db_file: Path, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_file}", "LLM_PROVIDER": "rules",
           "ANTHROPIC_API_KEY": "", "GEMINI_API_KEY": "", "API_KEY": "",
           "PASSWORD_HASH_ITERATIONS": "1000", "NOTIFY_MODE": "dry_run"}
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / name), *args], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, f"{name} failed:\n{result.stdout[-2000:]}\n{result.stderr[-3000:]}"
    return result.stdout


@pytest.fixture
def db_file(tmp_path):
    return tmp_path / "demo.db"


def test_demo_week6_runs_and_guardrail_holds(db_file):
    out = run_script("demo_week6.py", db_file, "--password", PASSWORD)
    assert "kept at: critical" in out


def test_demo_week7_runs_end_to_end(db_file):
    out = run_script("demo_week7.py", db_file, "--password", PASSWORD)
    assert "Second run escalated 0 (idempotent)" in out
    assert "parent_notified" in out


def test_demo_scripts_can_run_one_after_the_other(db_file):
    """The order in the README: Week 6 demo, then Week 7 demo, on the same database."""
    run_script("demo_week6.py", db_file, "--password", PASSWORD)
    run_script("demo_week7.py", db_file, "--password", PASSWORD)


def test_demo_needs_a_password(db_file):
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_file}", "DEMO_STAFF_PASSWORD": ""}
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "demo_week6.py")], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode != 0 and "password" in (result.stdout + result.stderr).lower()


def test_make_weekly_reports_script(db_file):
    """Weeks 3-4: the README's report command works after the Week 7 demo, and is idempotent."""
    run_script("demo_week7.py", db_file, "--password", PASSWORD)
    out = run_script("make_weekly_reports.py", db_file, "--no-outlook")
    assert "made 6 report(s)" in out
    again = run_script("make_weekly_reports.py", db_file, "--no-outlook")
    assert "made 0 report(s), kept 6 existing" in again
