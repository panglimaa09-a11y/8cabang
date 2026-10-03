"""Authentication and authorization.

- JWT HS256 signed with JWT_SECRET (python-jose).
- Passwords hashed with bcrypt (passlib). Hashes never leave the backend.
- get_current_user: FastAPI dependency validating the Bearer token.
- require_role / require_permission / require_branch_access: guards used by
  routers. Hiding a button in the frontend is NOT enough — the backend and
  the database (RLS) enforce these rules independently.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..models import Profile
from ..services.permissions import can_access_branch, has_permission

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


# ── password helpers ──────────────────────────────────────────────
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


# ── JWT helpers ─────────────────────────────────────────────────────
def create_access_token(profile_id: UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": str(profile_id), "exp": expire, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> UUID:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET,
                             algorithms=[settings.JWT_ALGORITHM])
        return UUID(payload["sub"])
    except (JWTError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid or expired token") from exc


# ── FastAPI dependencies ────────────────────────────────────────────
def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Profile:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Missing bearer token")
    profile_id = decode_token(credentials.credentials)
    profile = db.scalar(select(Profile).where(Profile.id == profile_id))
    if profile is None or not profile.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="User not found or inactive")
    return profile


def require_role(*roles: str):
    """Guard: user must have one of the given roles."""
    def guard(user: Profile = Depends(get_current_user)) -> Profile:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Insufficient role")
        return user
    return guard


def require_permission(permission_key: str):
    """Guard: user must hold the permission key (owner always passes).

    Karyawan can never hold financial keys (reports.view_profit,
    reports.view_margin, inventory.view_cost), so they get 403 here —
    including for hidden fields: the API simply never returns that data.
    """
    def guard(user: Profile = Depends(get_current_user),
              db: Session = Depends(get_db)) -> Profile:
        if not has_permission(user, db, permission_key):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"Missing permission: {permission_key}")
        return user
    return guard


def require_branch_access(branch_id: UUID, user: Profile, db: Session) -> None:
    """Raise 403 unless the branch is inside the user's scope.

    The branch_id from the client is ALWAYS verified server-side.
    """
    if not can_access_branch(user, db, branch_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Branch out of scope")


def assert_karyawan_blocked(user: Profile) -> None:
    """Financial report endpoints: karyawan are ALWAYS 403, no exceptions."""
    if user.role == "karyawan":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Karyawan cannot access financial reports")
