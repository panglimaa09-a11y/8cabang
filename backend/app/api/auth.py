"""Auth endpoints: login + current user."""
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Profile
from ..schemas import LoginIn, LoginOut, MeOut, ProfileOut
from ..security.auth import (
    create_access_token, get_current_user, get_db, verify_password,
)
from ..services.permissions import branch_scope_ids, resolve_permissions

router = APIRouter(prefix="/api/auth", tags=["auth"])


# Anti brute-force login: in-memory per instance, tanpa dependensi baru.
# Batas: 10 percobaan per IP per 5 menit (jendela geser).
_LOGIN_ATTEMPTS: dict[str, deque] = defaultdict(deque)
_MAX_LOGIN_ATTEMPTS = 10
_LOGIN_WINDOW_SECONDS = 300


def _check_login_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    attempts = _LOGIN_ATTEMPTS[ip]
    while attempts and now - attempts[0] > _LOGIN_WINDOW_SECONDS:
        attempts.popleft()
    if len(attempts) >= _MAX_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Terlalu banyak percobaan login, coba lagi dalam beberapa menit.",
            headers={"Retry-After": str(_LOGIN_WINDOW_SECONDS)},
        )
    attempts.append(now)


@router.post("/login", response_model=LoginOut)
def login(request: Request, payload: LoginIn, db: Session = Depends(get_db)):
    _check_login_rate_limit(request)
    profile = db.scalar(
        select(Profile).where(Profile.email == payload.email.strip().lower()))
    if profile is None or not profile.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid email or password")
    if not verify_password(payload.password, profile.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid email or password")
    token = create_access_token(profile.id)
    return LoginOut(access_token=token, profile=ProfileOut.model_validate(profile))


@router.get("/me", response_model=MeOut)
def me(user: Profile = Depends(get_current_user), db: Session = Depends(get_db)):
    return MeOut(
        profile=ProfileOut.model_validate(user),
        permissions=sorted(resolve_permissions(user, db)),
        branch_ids=branch_scope_ids(user, db),
    )
