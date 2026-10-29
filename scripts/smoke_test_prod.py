"""Week 8: check the LIVE deployment end to end and print PASS/FAIL with timings.

Usage:
    python scripts/smoke_test_prod.py --api https://schoolconnect-api-0yhr.onrender.com \\
        --web https://schoolconnect-web-cwa0.onrender.com --email principal@ubuntu-demo.school.example

Secrets are never arguments (they would end up in your shell history):
- the staff password is typed at a hidden prompt (or read from SMOKE_PASSWORD, then DEMO_STAFF_PASSWORD);
- the API key is read from PROD_API_KEY (environment or .env) or typed at a hidden prompt.

It creates ONE clearly labelled test ticket ("Smoke test - please ignore"). Exit code 1 if any check fails.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
WAKE_TIMEOUT = 180.0   # a sleeping free Render service takes about a minute to wake


def _from_dotenv(name: str) -> str:
    """Read one value from the local .env (so secrets need not be typed or exported)."""
    path = ROOT / ".env"
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    return ""


def secret(name: str, prompt: str, *fallbacks: str) -> str:
    for key in (name, *fallbacks):
        value = os.environ.get(key) or _from_dotenv(key)
        if value:
            return value
    return getpass.getpass(prompt)


class Smoke:
    def __init__(self, api: str, web: str, api_key: str, http: httpx.Client | None = None,
                 web_http: httpx.Client | None = None):
        self.api, self.web = api.rstrip("/"), web.rstrip("/")
        self.http = http or httpx.Client(timeout=WAKE_TIMEOUT, follow_redirects=True)
        if api_key:
            self.http.headers["X-API-Key"] = api_key
        self.web_http = web_http or self.http
        self.results: list[tuple[str, bool, float, str]] = []

    def check(self, name: str, fn) -> object:
        """Run one check; record PASS/FAIL, how long it took, and a short note."""
        start = time.perf_counter()
        try:
            value, note = fn()
            ok = True
        except Exception as exc:  # noqa: BLE001 - every failure becomes a FAIL line, never a crash
            value, note, ok = None, f"{type(exc).__name__}: {exc}"[:160], False
        took = time.perf_counter() - start
        self.results.append((name, ok, took, note))
        print(f"{'PASS' if ok else 'FAIL'}  {took:6.1f} s  {name}" + (f"  ({note})" if note else ""), flush=True)
        return value

    def get(self, path: str, token: str | None = None, **kw) -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.http.get(self.api + path, headers=headers, **kw)

    def login(self, email: str, password: str) -> tuple[str, str]:
        r = self.http.post(self.api + "/auth/login", json={"email": email, "password": password})
        _expect(r, 200)
        return r.json()["token"], f"logged in as {r.json()['staff']['name']} ({r.json()['staff']['role']})"


def _expect(r: httpx.Response, status: int) -> None:
    if r.status_code != status:
        raise AssertionError(f"HTTP {r.status_code}, expected {status}: {r.text[:120]}")


def run(api: str, web: str, email: str, password: str, api_key: str, teacher_email: str,
        teacher_password: str, http: httpx.Client | None = None, web_http: httpx.Client | None = None) -> bool:
    s = Smoke(api, web, api_key, http, web_http)
    print(f"Smoke test of {s.api} and {s.web}\n")

    def health():
        r = s.get("/health")
        _expect(r, 200)
        return r.json(), f"status {r.json()['status']}, AI mode {r.json()['llm_provider']} (first call includes wake-up)"

    s.check("API /health (wake-up)", health)
    token = s.check("staff login", lambda: s.login(email, password))

    def create_ticket():
        r = s.http.post(s.api + "/tickets", json={
            "message": "Smoke test - please ignore. When is the next parents' evening?", "channel": "web"})
        _expect(r, 201)
        return r.json(), f"{r.json()['reference']} ({r.json()['category']})"

    s.check("create a ticket with the API key", create_ticket)

    def my_work():
        r = s.get("/workflow/my-work", token)
        _expect(r, 200)
        return None, f"{len(r.json())} open ticket(s)"

    s.check("/workflow/my-work", my_work)

    def summary():
        r = s.get("/analytics/summary", token)
        _expect(r, 200)
        volume = r.json()["metrics"]["volume"]
        return None, f"{volume['total']} messages last week ({volume['previous']} the week before)"

    s.check("/analytics/summary", summary)

    def forecast():
        start = time.perf_counter()
        r = s.get("/forecast", token, params={"as_of": "2025-12-15", "days": 45, "category": "total"})
        _expect(r, 200)
        total = sum(row["forecast"] for row in r.json()["rows"])
        return None, f"{len(r.json()['rows'])} days, {total:.0f} expected, {time.perf_counter() - start:.1f} s"

    s.check("/forecast?as_of=2025-12-15 (January backtest)", forecast)

    def report_pdf():
        reports = s.get("/reports", token)
        _expect(reports, 200)
        if not reports.json():
            raise AssertionError("no weekly reports yet (run make_weekly_reports.py)")
        latest = reports.json()[0]
        r = s.get(f"/reports/{latest['id']}/pdf", token)
        _expect(r, 200)
        if not r.content.startswith(b"%PDF"):
            raise AssertionError("not a PDF")
        return None, f"report #{latest['id']}, {len(r.content) // 1024} KB"

    s.check("download the latest weekly report PDF", report_pdf)

    def welfare_hidden():
        r = s.get("/tickets", token, params={"category": "learner_welfare", "limit": 1})
        _expect(r, 200)
        if not r.json():
            raise AssertionError("no learner-welfare ticket to test with")
        welfare_id = r.json()[0]["id"]
        teacher_token, _ = s.login(teacher_email, teacher_password)
        hidden = s.get(f"/tickets/{welfare_id}", teacher_token)
        _expect(hidden, 404)
        return None, f"ticket #{welfare_id}: principal 200, class teacher 404"

    s.check("learner-welfare ticket hidden from a class teacher", welfare_hidden)

    def web_home():
        r = s.web_http.get(s.web + "/")
        _expect(r, 200)
        health = s.web_http.get(s.web + "/_stcore/health")
        _expect(health, 200)
        return None, "home page and /_stcore/health answer 200"

    s.check("web home page loads", web_home)

    failed = [r for r in s.results if not r[1]]
    total = sum(r[2] for r in s.results)
    print(f"\n{len(s.results) - len(failed)}/{len(s.results)} checks passed in {total:.1f} s")
    return not failed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", required=True, help="API URL, e.g. https://schoolconnect-api-0yhr.onrender.com")
    parser.add_argument("--web", required=True, help="Web URL, e.g. https://schoolconnect-web-cwa0.onrender.com")
    parser.add_argument("--email", required=True, help="Principal (or deputy) login email")
    parser.add_argument("--teacher-email", default="teacher@ubuntu-demo.school.example",
                        help="Class teacher login used for the welfare-visibility check")
    args = parser.parse_args()
    password = secret("SMOKE_PASSWORD", f"Password for {args.email}: ", "DEMO_STAFF_PASSWORD")
    teacher_password = os.environ.get("SMOKE_TEACHER_PASSWORD") or password   # demo accounts share one
    api_key = secret("PROD_API_KEY", "API key (as set on Render): ")
    sys.exit(0 if run(args.api, args.web, args.email, password, api_key, args.teacher_email,
                      teacher_password) else 1)


if __name__ == "__main__":
    main()
