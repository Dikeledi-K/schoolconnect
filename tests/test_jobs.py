"""Week 8: scheduled-job calls (wake-up time, one retry, loud failure) and the schedule itself."""

import re
import sys
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.call_endpoint import call  # noqa: E402

WORKFLOW = yaml.safe_load((ROOT / ".github" / "workflows" / "jobs.yml").read_text(encoding="utf-8"))
SCHEDULES = [s["cron"] for s in WORKFLOW[True]["schedule"]]   # YAML reads the key "on" as True


def _client(answers: list):
    """A fake HTTP client that answers with these status codes / exceptions in turn."""
    seen = []

    def handler(request: httpx.Request):
        seen.append(request)
        answer = answers[len(seen) - 1]
        if isinstance(answer, Exception):
            raise answer
        return httpx.Response(answer, text="{}")

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_success_first_time_sends_the_token():
    client, seen = _client([200])
    assert call("POST", "https://api.example/jobs/escalate", "tok", client=client, pause=0)
    assert len(seen) == 1 and seen[0].headers["X-Jobs-Token"] == "tok"


def test_a_sleeping_service_gets_one_retry():
    client, seen = _client([httpx.ReadTimeout("waking up"), 200])
    assert call("GET", "https://api.example/health", client=client, pause=0)
    assert len(seen) == 2 and "X-Jobs-Token" not in seen[0].headers


def test_non_2xx_twice_fails_loudly():
    client, seen = _client([502, 401])
    assert not call("POST", "https://api.example/jobs/escalate", "bad", client=client, pause=0)
    assert len(seen) == 2


def test_cli_exits_non_zero_on_failure(monkeypatch):
    import pytest

    from scripts import call_endpoint

    monkeypatch.setattr(call_endpoint, "call", lambda *a, **k: False)
    monkeypatch.setattr(sys, "argv", ["call_endpoint.py", "GET", "https://web.example/"])
    with pytest.raises(SystemExit) as exc:
        call_endpoint.main()
    assert "FAILED" in str(exc.value)


# ---- The schedule ----------------------------------------------------------------
def _job_for(cron: str) -> list[str]:
    return [name for name, job in WORKFLOW["jobs"].items() if f"'{cron}'" in job["if"]]


def test_every_schedule_runs_exactly_one_job_and_every_job_can_be_run_by_hand():
    for cron in SCHEDULES:
        assert len(_job_for(cron)) == 1, cron
    choices = WORKFLOW[True]["workflow_dispatch"]["inputs"]["job"]["options"]
    assert set(choices) == set(WORKFLOW["jobs"])


def _utc_hours(cron: str) -> list[int]:
    hours = cron.split()[1]
    if "-" in hours:
        a, b = map(int, hours.split("-"))
        return list(range(a, b + 1))
    return [int(hours)]


def test_times_fit_the_school_day_in_south_african_time():
    sast = {name: [] for name in WORKFLOW["jobs"]}
    for cron in SCHEDULES:
        sast[_job_for(cron)[0]] += [h + 2 for h in _utc_hours(cron)]
    assert min(sast["escalate"]) == 6 and max(sast["escalate"]) == 17
    assert min(sast["keep-warm"]) == 7 and max(sast["keep-warm"]) == 16
    assert sast["forecasts"] == [5] and sast["weekly-reports"] == [6]
    for name in ("escalate", "keep-warm"):           # weekdays only
        assert all(c.split()[4] == "1-5" for c in SCHEDULES if _job_for(c) == [name])
    assert any(c.endswith("* * 1") for c in SCHEDULES if _job_for(c) == ["weekly-reports"])
    keep_warm = [c for c in SCHEDULES if _job_for(c) == ["keep-warm"] and c.startswith("*/")]
    assert keep_warm and int(re.match(r"\*/(\d+)", keep_warm[0]).group(1)) < 15   # before the 15-min sleep


def test_retention_stays_a_dry_run():
    step = WORKFLOW["jobs"]["retention-dry-run"]["steps"][-1]["run"]
    assert "dry_run=true" in step and "dry_run=false" not in str(WORKFLOW)


def test_heavy_jobs_run_on_github_against_supabase_with_the_same_pinned_dates():
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    api_env = {v["key"]: v.get("value") for v in blueprint["services"][0]["envVars"]}
    for name, script in (("forecasts", "refresh_forecasts.py"), ("weekly-reports", "make_weekly_reports.py")):
        step = WORKFLOW["jobs"][name]["steps"][-1]
        assert script in step["run"] and step["env"]["DATABASE_URL"] == "${{ secrets.DATABASE_URL }}"
    assert WORKFLOW["jobs"]["forecasts"]["steps"][-1]["env"]["FORECAST_PINNED_DATES"] == api_env["FORECAST_PINNED_DATES"]
