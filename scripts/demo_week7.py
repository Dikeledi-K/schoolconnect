"""Week 7 demo: staff accounts, the full workflow, a signed webhook, a fee exemption and an escalation.

Everything goes through the REAL API (in-process), so masking, classification, guardrails,
audit, auto-assignment, SLAs and the outbox all run exactly as in production.
All names, emails and numbers are SYNTHETIC.

Usage (after seed_db.py or generate_history.py):
    python scripts/demo_week7.py --password "choose-a-demo-password"
    # or:  set DEMO_STAFF_PASSWORD=...  then  python scripts/demo_week7.py

The password is used for every demo account. It is never stored in the repo or printed.
NOTIFY_MODE should stay dry_run for the demo (nothing is really emailed).
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DOMAIN = "ubuntu-demo.school.example"     # fictional
STAFF = [   # (name, email user, role)
    ("Mrs N. Dlamini", "principal", "principal"),
    ("Mr T. Mokoena", "deputy", "deputy_principal"),
    ("Ms L. Khumalo", "admin", "admin_clerk"),
    ("Mrs P. Pillay", "finance", "finance_clerk"),
    ("Mr J. Nel", "teacher", "class_teacher"),
    ("Mr S. Dube", "it", "it_support"),
]
MESSAGES = [
    {"message": "Good day, I want to apply for admission to Grade 1. What documents do I need for registration?",
     "parent_contact": "sipho.demo@example.com", "learner_grade": "R"},
    {"message": "The scholar transport bus did not come this morning.", "parent_contact": "082 555 0101",
     "learner_grade": "3"},
    {"message": "My daughter says older learners are bullying her at break and she is scared.",
     "parent_contact": "lerato.demo@example.com", "learner_grade": "5"},
    {"message": "I cannot log in to the portal, the OTP never arrives.", "learner_grade": "11"},
]
FEES_MESSAGE = {"message": "I lost my job in March. How do I apply for a school fee exemption?",
                "parent_name": "Thandi Mokoena", "parent_contact": "thandi.demo@example.com", "learner_grade": "4"}
LATE_MESSAGE = {"message": "When will the Grade 7 maths test marks be on the report? I need them urgently.",
                "parent_contact": "nomsa.demo@example.com", "learner_grade": "7"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--password", default=os.getenv("DEMO_STAFF_PASSWORD"),
                        help="Password for every demo account (or set DEMO_STAFF_PASSWORD)")
    args = parser.parse_args()
    if not args.password or len(args.password) < 10:
        sys.exit("Give a demo password of at least 10 characters: --password ... or DEMO_STAFF_PASSWORD")

    # The demo calls the jobs and webhook endpoints, which are disabled without secrets.
    # If .env has none, use throwaway ones for THIS process only.
    from app.config import get_settings

    for key in ("JOBS_TOKEN", "INBOUND_SECRET"):
        if not getattr(get_settings(), key.lower()):
            os.environ[key] = secrets.token_hex(16)
    get_settings.cache_clear()
    settings = get_settings()

    from fastapi.testclient import TestClient

    from app.auth.service import create_staff, get_staff_by_email
    from app.db import SessionLocal
    from app.integrations.inbound import sign
    from app.main import app
    from app.models import Ticket

    with TestClient(app) as client, SessionLocal() as db:
        # 1. Staff accounts (existing ones are kept)
        for name, user, role in STAFF:
            email = f"{user}@{DOMAIN}"
            if get_staff_by_email(db, email) is None:
                create_staff(db, name, email, role, args.password)

        def login(user: str) -> dict:
            r = client.post("/auth/login", json={"email": f"{user}@{DOMAIN}", "password": args.password})
            if r.status_code != 200:
                sys.exit(f"Login failed for {user}@{DOMAIN}: {r.json().get('detail')} "
                         "(accounts that already exist keep their old password)")
            return {"Authorization": f"Bearer {r.json()['token']}"}

        principal, finance, admin = login("principal"), login("finance"), login("admin")

        # 2. Parent messages through the normal web path
        print("\n1) Parent messages (web form):")
        created = []
        for body in MESSAGES:
            t = client.post("/tickets", json=body).json()
            created.append(t)
            owner = client.get(f"/tickets/{t['id']}", headers=principal).json()["assigned_to"]
            print(f"   {t['reference']}  {t['category']:<16} {t['urgency']:<8} assigned to staff #{owner}")

        # 3. A WhatsApp message through the signed webhook
        payload = json.dumps({"channel": "whatsapp", "message": "Sawubona, ngicela ukwazi ukuthi ngingakhokha "
                              "imali yesikole kanjani?", "sender_contact": "+27 82 555 0199"}).encode()
        ts = str(int(time.time()))
        r = client.post("/integrations/inbound-message", content=payload, headers={
            "X-Timestamp": ts, "X-Signature": sign(settings.inbound_secret, ts, payload),
            "Content-Type": "application/json"})
        print(f"\n2) Signed WhatsApp webhook: {r.status_code} {r.json()}")

        # 4. A reply drafted and approved (goes through the outbox, dry run)
        admissions = created[0]
        draft = client.post(f"/tickets/{admissions['id']}/responses", headers=admin, json={"tone": "friendly"}).json()
        approved = client.post(f"/responses/{draft['id']}/approve", headers=admin, json={}).json()
        print(f"\n3) Reply to {admissions['reference']} approved by Ms L. Khumalo: {approved['delivery_status']}")

        # 5. Fee exemption, start to finish
        fees = client.post("/tickets", json=FEES_MESSAGE).json()
        fe = client.post(f"/tickets/{fees['id']}/fee-exemption", headers=finance).json()
        client.post(f"/fee-exemptions/{fe['id']}/start-review", headers=finance)
        client.put(f"/fee-exemptions/{fe['id']}/checklist", headers=finance,
                   json={"received": [True] * len(fe["checklist"])})
        client.post(f"/fee-exemptions/{fe['id']}/finance-decision", headers=finance, json={"decision": "approve"})
        client.post(f"/fee-exemptions/{fe['id']}/principal-decision", headers=principal, json={"decision": "approve"})
        done = client.post(f"/fee-exemptions/{fe['id']}/notify-parent", headers=finance).json()
        print(f"\n4) Fee exemption for {fees['reference']}: {done['status']} (letter: {done['delivery_status']})")

        # A second request left waiting for the principal, to show the queue in the UI.
        fees2 = client.post("/tickets", json={**FEES_MESSAGE, "parent_name": None,
                                              "parent_contact": "zanele.demo@example.com"}).json()
        fe2 = client.post(f"/tickets/{fees2['id']}/fee-exemption", headers=finance).json()
        client.post(f"/fee-exemptions/{fe2['id']}/start-review", headers=finance)
        client.put(f"/fee-exemptions/{fe2['id']}/checklist", headers=finance,
                   json={"received": [True] * len(fe2["checklist"])})
        client.post(f"/fee-exemptions/{fe2['id']}/finance-decision", headers=finance, json={"decision": "approve"})
        print(f"   {fees2['reference']}: waiting for the principal's decision")

        # 6. Back-date one ticket so it is overdue, then run the escalation job
        late = client.post("/tickets", json=LATE_MESSAGE).json()
        ticket = db.get(Ticket, late["id"])
        db.refresh(ticket)
        ticket.urgency = "high"
        ticket.created_at = datetime.now(timezone.utc) - timedelta(days=5)
        db.commit()
        jobs = {"X-Jobs-Token": settings.jobs_token}
        run1 = client.post("/jobs/escalate", headers=jobs).json()
        run2 = client.post("/jobs/escalate", headers=jobs).json()
        mine = [e for e in run1["escalated"] if e["reference"] == late["reference"]]
        print(f"\n5) Escalation job: {late['reference']} -> {mine[0]['to_role'] if mine else '?'}; "
              f"{len(run1['escalated'])} escalated in total. Second run escalated "
              f"{len(run2['escalated'])} (idempotent).")

    print("\nDemo staff logins (password: the one you just gave):")
    for name, user, role in STAFF:
        print(f"   {name:<16} {role:<17} {user}@{DOMAIN}")
    print("\nNow run:  uvicorn app.main:app --reload   and   streamlit run frontend/Home.py")


if __name__ == "__main__":
    main()
