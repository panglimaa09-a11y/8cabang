"""User management and permission grants.

- POST /api/users, GET /api/users, PATCH /api/users/{id}: owner, or admin
  holding users.manage.
- POST /api/permissions/grant|revoke: owner ONLY. Admins can never grant
  financial permissions to themselves (or anyone).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..common import write_audit
from ..models import Branch, BranchMembership, Profile, UserPermission
from ..schemas import PermissionGrant, UserCreate, UserOut, UserUpdate
from ..security.auth import (
    get_current_user, get_db, hash_password, require_permission, require_role,
)
from ..services.permissions import ALL_PERMISSIONS, branch_scope_ids

router = APIRouter(prefix="/api", tags=["users"])

manage_users = require_permission("users.manage")
owner_only = require_role("owner")


def _validate_branch_ids(db: Session, branch_ids: list[UUID]) -> None:
    if not branch_ids:
        return
    found = set(db.scalars(select(Branch.id).where(Branch.id.in_(branch_ids))))
    missing = set(branch_ids) - found
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Unknown branch ids: {sorted(str(m) for m in missing)}")


def _user_out(db: Session, profile: Profile) -> UserOut:
    return UserOut(
        id=profile.id, email=profile.email, full_name=profile.full_name,
        role=profile.role, is_active=profile.is_active,
        branch_ids=branch_scope_ids(profile, db),
    )


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, actor: Profile = Depends(manage_users),
                db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if db.scalar(select(Profile).where(Profile.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Email already registered")
    if payload.role == "owner" and actor.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only owner can create another owner")
    if payload.role == "karyawan" and not payload.branch_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Karyawan must be assigned to at least one branch")
    _validate_branch_ids(db, payload.branch_ids)

    profile = Profile(email=email, full_name=payload.full_name,
                      role=payload.role, password_hash=hash_password(payload.password))
    db.add(profile)
    db.flush()
    for bid in payload.branch_ids:
        db.add(BranchMembership(profile_id=profile.id, branch_id=bid))
    write_audit(db, actor_id=actor.id, action="user.create", entity_type="profiles",
                entity_id=profile.id,
                after={"email": email, "role": payload.role,
                       "branch_ids": [str(b) for b in payload.branch_ids]})
    db.commit()
    return _user_out(db, profile)


@router.get("/users", response_model=list[UserOut])
def list_users(actor: Profile = Depends(manage_users), db: Session = Depends(get_db)):
    profiles = db.scalars(select(Profile).order_by(Profile.created_at)).all()
    return [_user_out(db, p) for p in profiles]


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: UUID, payload: UserUpdate, actor: Profile = Depends(manage_users),
                db: Session = Depends(get_db)):
    profile = db.get(Profile, user_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if profile.id == actor.id and payload.is_active is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Cannot deactivate your own account")
    before = {"full_name": profile.full_name, "role": profile.role,
              "is_active": profile.is_active}
    if payload.full_name is not None:
        profile.full_name = payload.full_name
    if payload.role is not None:
        if actor.role != "owner":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Only owner can change roles")
        if profile.role == "owner" and payload.role != "owner" and actor.id == profile.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Cannot demote your own owner account")
        profile.role = payload.role
    if payload.is_active is not None:
        profile.is_active = payload.is_active
    if payload.branch_ids is not None:
        _validate_branch_ids(db, payload.branch_ids)
        db.execute(delete(BranchMembership).where(BranchMembership.profile_id == profile.id))
        for bid in payload.branch_ids:
            db.add(BranchMembership(profile_id=profile.id, branch_id=bid))
    write_audit(db, actor_id=actor.id, action="user.update", entity_type="profiles",
                entity_id=profile.id, before=before,
                after={"full_name": profile.full_name, "role": profile.role,
                       "is_active": profile.is_active,
                       "branch_ids": [str(b) for b in (payload.branch_ids or [])]})
    db.commit()
    return _user_out(db, profile)


@router.post("/permissions/grant", status_code=status.HTTP_200_OK)
def grant_permission(payload: PermissionGrant, actor: Profile = Depends(owner_only),
                     db: Session = Depends(get_db)):
    if payload.permission_key not in ALL_PERMISSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Unknown permission: {payload.permission_key}")
    target = db.get(Profile, payload.profile_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    existing = db.get(UserPermission, (payload.profile_id, payload.permission_key))
    if existing is None:
        db.add(UserPermission(profile_id=payload.profile_id,
                              permission_key=payload.permission_key,
                              granted_by=actor.id))
    write_audit(db, actor_id=actor.id, action="permission.grant", entity_type="profiles",
                entity_id=payload.profile_id,
                after={"permission_key": payload.permission_key})
    db.commit()
    return {"ok": True}


@router.post("/permissions/revoke", status_code=status.HTTP_200_OK)
def revoke_permission(payload: PermissionGrant, actor: Profile = Depends(owner_only),
                      db: Session = Depends(get_db)):
    if payload.permission_key not in ALL_PERMISSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Unknown permission: {payload.permission_key}")
    db.execute(delete(UserPermission).where(
        UserPermission.profile_id == payload.profile_id,
        UserPermission.permission_key == payload.permission_key))
    write_audit(db, actor_id=actor.id, action="permission.revoke", entity_type="profiles",
                entity_id=payload.profile_id,
                after={"permission_key": payload.permission_key})
    db.commit()
    return {"ok": True}
