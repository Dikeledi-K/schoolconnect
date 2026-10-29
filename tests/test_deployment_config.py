"""Week 8: the deployment files stay correct (no secrets in git, free plan, one Python version)."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SECRETS = {"DATABASE_URL", "API_KEY", "JOBS_TOKEN", "INBOUND_SECRET", "ANTHROPIC_API_KEY", "SMTP_PASSWORD"}


def _services() -> dict:
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    return {s["name"]: s for s in blueprint["services"]}


def test_two_free_python_web_services_from_main():
    services = _services()
    assert set(services) == {"schoolconnect-api", "schoolconnect-web"}
    for s in services.values():
        assert (s["type"], s["runtime"], s["plan"], s["branch"]) == ("web", "python", "free", "main")
        assert s["autoDeployTrigger"] == "commit"
        assert s["region"] == "frankfurt"          # same region as the Supabase project
    api, web = services["schoolconnect-api"], services["schoolconnect-web"]
    assert api["startCommand"] == "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
    assert api["healthCheckPath"] == "/health" and api["buildCommand"] == "pip install -r requirements.txt"
    assert web["startCommand"].startswith("streamlit run frontend/Home.py --server.port $PORT")
    assert web["buildCommand"] == "pip install -r frontend/requirements.txt"


def test_secrets_are_never_stored_in_the_blueprint():
    for service in _services().values():
        for var in service["envVars"]:
            if var["key"] in SECRETS or var["key"] in {"API_BASE_URL", "CORS_ORIGINS"}:
                assert var.get("sync") is False and "value" not in var, var["key"]


def test_production_plain_values():
    plain = {v["key"]: v["value"] for v in _services()["schoolconnect-api"]["envVars"] if "value" in v}
    assert plain["ENVIRONMENT"] == "production" and plain["LLM_PROVIDER"] == "rules"
    assert plain["NOTIFY_MODE"] == "dry_run" and plain["RETENTION_DAYS"] == "365"


def test_one_python_version_for_render_and_ci():
    assert (ROOT / ".python-version").read_text().strip() == "3.11"
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert 'python-version-file: ".python-version"' in ci and "requirements-dev.txt" in ci


def test_requirements_are_split():
    runtime = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    dev = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "pytest" not in runtime and "psycopg[binary]" in runtime
    assert "-r requirements.txt" in dev and "-r frontend/requirements.txt" in dev and "pytest" in dev
