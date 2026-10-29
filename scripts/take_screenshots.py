"""Week 8: screenshot every page for the README and the user guide (docs/screenshots/).

Logs in with the demo accounts and moves between pages with the SIDEBAR links: a full page
reload starts a new Streamlit session, which logs you out.

Setup once:  pip install -r requirements-dev.txt  &&  python -m playwright install chromium
Usage:
    python scripts/take_screenshots.py                                    # local: http://localhost:8501
    python scripts/take_screenshots.py --web https://schoolconnect-web.onrender.com
The password is DEMO_STAFF_PASSWORD (environment or .env), or typed at a hidden prompt.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
DOMAIN = "ubuntu-demo.school.example"
DESKTOP = {"width": 1400, "height": 1000}
PHONE = {"width": 390, "height": 844}

# (file name, who logs in, sidebar link to click, how far to scroll down)
STAFF_PAGES = [
    ("03_my_work_deputy", "deputy", "My work", 0),
    ("04_staff_inbox", "principal", "Staff inbox", 0),
    ("05_ticket_detail", "principal", "Staff inbox", 1000),
    ("06_fee_exemptions", "principal", "Fee exemptions", 0),
    ("07_analytics", "principal", "Analytics", 0),
    ("08_weekly_reports", "principal", "Weekly reports", 0),
    ("09_forecast", "principal", "Forecast and workload", 0),
    ("10_risk_and_compliance", "principal", "Risk and compliance", 0),
]


def password() -> str:
    value = os.environ.get("DEMO_STAFF_PASSWORD", "")
    env = ROOT / ".env"
    if not value and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("DEMO_STAFF_PASSWORD="):
                value = line.split("=", 1)[1].strip()
    return value or getpass.getpass("Demo staff password: ")


async def settle(page, extra_ms: int = 2500) -> None:
    """Wait until Streamlit has finished running the script (the 'running' widget disappears)."""
    await page.wait_for_timeout(800)
    for _ in range(240):                     # up to 2 minutes for a sleeping free server
        if await page.locator('[data-testid="stStatusWidget"]').count() == 0:
            break
        await page.wait_for_timeout(500)
    await page.wait_for_timeout(extra_ms)


async def shot(page, name: str, scroll: int = 0) -> None:
    if scroll:
        await page.mouse.move(900, 600)
        await page.mouse.wheel(0, scroll)
        await page.wait_for_timeout(1200)
    path = OUT / f"{name}.png"
    await page.screenshot(path=str(path))
    errors = await page.locator('[data-testid="stException"]').count()
    print(f"{'OK  ' if not errors else 'ERROR'} {path.relative_to(ROOT)}")


async def login(page, web: str, user: str, pw: str) -> None:
    await page.goto(f"{web}/My_work")
    await settle(page)
    await page.get_by_label("Work email").fill(f"{user}@{DOMAIN}")
    await page.get_by_role("textbox", name="Password").fill(pw)
    await page.get_by_role("button", name="Log in").click()
    await settle(page, 4000)


async def nav(page, label: str) -> None:
    await page.locator('[data-testid="stSidebarNavLink"]', has_text=label).click()
    await settle(page, 4000)


async def main(web: str) -> None:
    from playwright.async_api import async_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    pw = password()
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        page = await browser.new_page(viewport=DESKTOP)
        await page.goto(web)
        await settle(page, 5000)
        await shot(page, "01_home")

        phone = await browser.new_page(viewport=PHONE)
        await phone.goto(f"{web}/Send_a_message")
        await settle(phone)
        await shot(phone, "02_parent_send_message_phone")
        await phone.close()

        current = None
        for name, user, link, scroll in STAFF_PAGES:
            if user != current:
                await page.close()
                page = await browser.new_page(viewport=DESKTOP)
                await login(page, web, user, pw)
                current = user
            await nav(page, link)
            if name == "09_forecast":            # the January backtest view used in the demo
                await page.get_by_text("Backtest demo").click()
                await settle(page, 5000)
            await shot(page, name, scroll)
        await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--web", default="http://localhost:8501", help="Address of the Streamlit app")
    asyncio.run(main(parser.parse_args().web.rstrip("/")))
