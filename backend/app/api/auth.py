"""Auth endpoints: login + current user."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Profile
from ..schemas import LoginIn, LoginOut, MeOut, ProfileOut
from ..security.auth import (
    create_access_token, get_current_user, get_db, verify_password,
)
from ..services.permissions import branch_scope_ids, resolve_permissions

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
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
