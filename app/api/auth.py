"""Week 7: staff login endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.auth import service
from app.auth.deps import bearer, current_staff
from app.db import get_db
from app.models import Staff
from app.schemas import LoginRequest, LoginResult, StaffOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResult)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginResult:
    """Email + password -> bearer token (valid 8 hours). 5 wrong passwords lock the account for 15 minutes."""
    try:
        staff = service.authenticate(db, body.email, body.password)
    except service.LoginError as err:
        raise HTTPException(status_code=423 if err.locked else 401, detail=str(err))
    token, expires_at = service.start_session(db, staff)
    return LoginResult(token=token, expires_at=expires_at, staff=StaffOut.model_validate(staff))


@router.post("/logout", status_code=204)
def logout(credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
           _: Staff = Depends(current_staff), db: Session = Depends(get_db)) -> None:
    service.end_session(db, credentials.credentials)


@router.get("/me", response_model=StaffOut)
def me(staff: Staff = Depends(current_staff)) -> Staff:
    return staff
