"""Week 8: call one SchoolConnect URL from a scheduled GitHub Actions job.

Free Render services sleep after 15 minutes and take about a minute to wake, so:
- every request gets a generous timeout (default 180 s);
- one retry after a short pause if the first attempt fails (timeout, network error, non-2xx);
- the script exits with an error if it still fails, so the GitHub run turns red and you get an email.

Usage:
    python scripts/call_endpoint.py POST https://schoolconnect-api.onrender.com/jobs/escalate --jobs-token
    python scripts/call_endpoint.py GET  https://schoolconnect-web.onrender.com/
The jobs token is read from the JOBS_TOKEN environment variable (a GitHub secret), never an argument.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import httpx

RETRY_PAUSE_SECONDS = 20


def call(method: str, url: str, token: str | None = None, timeout: float = 180.0,
         attempts: int = 2, pause: float = RETRY_PAUSE_SECONDS, client: httpx.Client | None = None) -> bool:
    """True if a 2xx answer arrived within `attempts` tries. Prints one line per attempt."""
    headers = {"X-Jobs-Token": token} if token else {}
    client = client or httpx.Client(timeout=timeout, follow_redirects=True)
    for attempt in range(1, attempts + 1):
        start = time.perf_counter()
        try:
            response = client.request(method, url, headers=headers)
            took = time.perf_counter() - start
            print(f"attempt {attempt}: {method} {url} -> {response.status_code} in {took:.1f} s")
            if 200 <= response.status_code < 300:
                print(response.text[:500])
                return True
            print(f"  body: {response.text[:300]}")
        except httpx.HTTPError as exc:
            print(f"attempt {attempt}: {method} {url} -> {type(exc).__name__} after "
                  f"{time.perf_counter() - start:.1f} s")
        if attempt < attempts:
            time.sleep(pause)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("method", choices=["GET", "POST"])
    parser.add_argument("url")
    parser.add_argument("--jobs-token", action="store_true", help="Send X-Jobs-Token from $JOBS_TOKEN")
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()
    # .strip(): a secret pasted with a trailing newline must not break the header or the URL.
    token = os.environ.get("JOBS_TOKEN", "").strip() if args.jobs_token else None
    args.url = args.url.strip()
    if args.jobs_token and not token:
        sys.exit("JOBS_TOKEN is not set (add it as a GitHub secret).")
    if not call(args.method, args.url, token, args.timeout):
        sys.exit(f"FAILED: {args.method} {args.url}")


if __name__ == "__main__":
    main()
