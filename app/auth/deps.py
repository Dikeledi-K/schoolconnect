"""FastAPI dependencies: "who is logged in?" and "may this role do this?".

Staff send  Authorization: Bearer <token>  (from POST /auth/login).
HTTPBearer also adds an "Authorize" button to the /docs page.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.service import staff_for_token
from app.db import get_db
from app.models import Staff
from app.taxonomy import ACCOUNT_ROLES

bearer = HTTPBearer(auto_error=False)


def current_staff(credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                  db: Session = Depends(get_db)) -> Staff:
    staff = staff_for_token(db, credentials.credentials) if credentials else None
    if staff is None:
        raise HTTPException(status_code=401, detail="Please log in (missing, invalid or expired token)",
                            headers={"WWW-Authenticate": "Bearer"})
    return staff


def require_roles(*roles: str):
    """Dependency factory: only these roles may call the endpoint (403 otherwise)."""
    names = ", ".join(ACCOUNT_ROLES[r] for r in roles)

    def check(staff: Staff = Depends(current_staff)) -> Staff:
        if staff.role not in roles:
            raise HTTPException(status_code=403, detail=f"Only {names} may do this")
        return staff

    return check
