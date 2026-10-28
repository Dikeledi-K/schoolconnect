"""Week 8: measure the API's peak memory and response times for the heavy requests.

Runs the REAL API in-process (FastAPI TestClient) on a COPY of the local SQLite database, so
nothing in your data changes. Memory = the process's resident set size (RSS), sampled every 20 ms.

    python scripts/measure_performance.py                 # full speed
    python scripts/measure_performance.py --cpu 0.1       # Windows: cap this process at 0.1 of one core
                                                          # (like Render's free instance)
Needs psutil (requirements-dev.txt). Prints a Markdown table for docs/TECHNICAL.md.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def cap_cpu_windows(cores: float) -> str:
    """Put this process in a Windows Job Object with a HARD CPU cap (a fraction of ONE core)."""
    import ctypes
    from ctypes import wintypes

    class CpuRate(ctypes.Structure):
        _fields_ = [("ControlFlags", wintypes.DWORD), ("CpuRate", wintypes.DWORD)]

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job = kernel32.CreateJobObjectW(None, None)
    # CpuRate is in 1/100ths of a percent of the WHOLE machine (all cores together).
    rate = max(1, int(cores / os.cpu_count() * 100 * 100))
    info = CpuRate(0x1 | 0x4, rate)                 # ENABLE | HARD_CAP
    if not kernel32.SetInformationJobObject(job, 15, ctypes.byref(info), ctypes.sizeof(info)):
        return "could not set the CPU cap"
    if not kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess()):
        return "could not join the job object"
    return f"capped at {cores} core ({rate / 100:.2f}% of {os.cpu_count()} cores)"


class PeakRss:
    """Samples memory in a background thread; `phase()` records the peak of each step."""

    def __init__(self):
        import psutil

        self.proc = psutil.Process()
        self.peak = self.current()
        self._stop = False
        threading.Thread(target=self._run, daemon=True).start()

    def current(self) -> float:
        return self.proc.memory_info().rss / 2**20

    def _run(self):
        while not self._stop:
            self.peak = max(self.peak, self.current())
            time.sleep(0.02)

    def reset(self):
        self.peak = self.current()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=str(ROOT / "schoolconnect.db"), help="SQLite database to copy")
    parser.add_argument("--cpu", type=float, help="Cap CPU at this many cores (Windows only), e.g. 0.1")
    args = parser.parse_args()

    copy = Path(tempfile.mkdtemp()) / "measure.db"
    shutil.copy(args.db, copy)
    os.environ.update(DATABASE_URL=f"sqlite:///{copy}", JOBS_TOKEN="measure-token", API_KEY="",
                      ENVIRONMENT="development", PASSWORD_HASH_ITERATIONS="1000", NOTIFY_MODE="dry_run")
    note = cap_cpu_windows(args.cpu) if args.cpu and os.name == "nt" else "full speed"

    rss = PeakRss()
    rows = [("Python started", 0.0, 0.0, rss.current())]
    t0, c0 = time.perf_counter(), time.process_time()
    from fastapi.testclient import TestClient

    from app.auth.service import create_staff, get_staff_by_email
    from app.db import SessionLocal, init_db
    from app.forecasting import service as fc
    from app.main import app
    rows.append(("API imported (baseline)", time.perf_counter() - t0, time.process_time() - c0, rss.peak))

    init_db()                                      # same as the app's start-up (adds new tables)
    with SessionLocal() as db:
        if get_staff_by_email(db, "measure@local.test") is None:
            create_staff(db, "Measure", "measure@local.test", "principal", "measure-password-123")
        from app.models import StoredForecast
        db.query(StoredForecast).delete()          # measure a real computation, not a stored read
        db.commit()

    def step(name, fn):
        rss.reset()
        t, c = time.perf_counter(), time.process_time()
        result = fn()
        rows.append((name, time.perf_counter() - t, time.process_time() - c, rss.peak))
        return result

    with TestClient(app) as client:
        token = client.post("/auth/login", json={"email": "measure@local.test",
                                                 "password": "measure-password-123"}).json()["token"]
        auth = {"Authorization": f"Bearer {token}"}
        params = {"as_of": "2025-12-15", "days": 45}

        def forecast_all():
            for path in ("/forecast", "/forecast/workload", "/forecast/surges", "/forecast/insights"):
                assert client.get(path, params=params, headers=auth).status_code == 200, path

        fc.clear_cache()
        step("Forecast 2025-12-15, computed (4 endpoints)", forecast_all)
        step("Same forecast again (memory cache)", forecast_all)
        with SessionLocal() as db:
            step("Store forecast for 2025-12-15 (nightly job)", lambda: fc.refresh_stored(db, ["2025-12-15"]))
        fc.clear_cache()
        step("Forecast 2025-12-15 after a restart (stored)", forecast_all)

        def reports():
            r = client.post("/jobs/weekly-reports", params={"force": "true"}, headers={"X-Jobs-Token": "measure-token"})
            assert r.status_code == 200, r.text
            return r.json()

        made = step("All 6 weekly reports with outlook", reports)
        latest = client.get("/reports", headers=auth).json()[0]["id"]
        step("Weekly report PDF download", lambda: client.get(f"/reports/{latest}/pdf", headers=auth).content)
        step("Risk & compliance page data (/risk/summary)",
             lambda: client.get("/risk/summary", params={"days": 30}, headers=auth).json())
        step("Risk & compliance again (classifier check cached)",
             lambda: client.get("/risk/summary", params={"days": 30}, headers=auth).json())
        step("Risk report PDF (built on request)", lambda: client.get("/risk/report.pdf", headers=auth).content)

    rss._stop = True
    print(f"\nMeasured {time.strftime('%Y-%m-%d')}, {note}, {sys.version.split()[0]}, "
          f"{len(made.get('created', []))} reports made\n")
    print("| Step | Wall time (s) | CPU time (s) | Peak memory (MB) |")
    print("|---|---:|---:|---:|")
    for name, wall, cpu, peak in rows:
        print(f"| {name} | {wall:.1f} | {cpu:.1f} | {peak:.0f} |")
    print(f"\nHighest peak: {max(r[3] for r in rows):.0f} MB")


if __name__ == "__main__":
    main()
