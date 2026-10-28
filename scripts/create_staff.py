"""Create a staff account. The password is typed at a prompt and never stored in the repo.

Usage:
    python scripts/create_staff.py --name "Mrs Pillay" --email pillay@school.example --role finance_clerk

Roles: admin_clerk, finance_clerk, class_teacher, deputy_principal, it_support, principal
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.auth.service import create_staff  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.taxonomy import ACCOUNT_ROLES  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a SchoolConnect staff account.")
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", required=True, choices=list(ACCOUNT_ROLES))
    args = parser.parse_args()

    # getpass hides what you type, so the password never appears on screen or in shell history.
    password = getpass.getpass("Password (at least 10 characters): ")
    if password != getpass.getpass("Type it again: "):
        sys.exit("The passwords do not match.")

    init_db()
    with SessionLocal() as db:
        try:
            staff = create_staff(db, args.name, args.email, args.role, password)
        except ValueError as err:
            sys.exit(str(err))
    print(f"Created {staff.name} ({ACCOUNT_ROLES[staff.role]}), login: {staff.email}")


if __name__ == "__main__":
    main()
