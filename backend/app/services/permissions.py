"""Permission resolution.

Rules (CONTRACT.md section 4/5):
  - owner: holds every permission and sees every branch.
  - admin / karyawan: role_permissions for their role + per-user user_permissions
    grants. Branch scope comes from branch_memberships.
  - karyawan can NEVER see financial data — enforced by the API layer via
    require_permission(), which they cannot satisfy for financial keys.
"""
from uuid import UUID

from sqlalchemy import select

from ..models import Branch, BranchMembership, Profile, RolePermission, UserPermission

ALL_PERMISSIONS = frozenset({
    "reports.view_profit",
    "reports.view_margin",
    "inventory.view_cost",
    "transactions.correct",
    "users.manage",
    "audit.view",
    "branches.manage",
    "settings.manage",
})


def resolve_permissions(profile: Profile, session) -> set[str]:
    """Return the effective permission-key set for a profile."""
    if profile.role == "owner":
        return set(ALL_PERMISSIONS)
    perms = {
        row.permission_key
        for row in session.scalars(
            select(RolePermission).where(RolePermission.role == profile.role)
        )
    }
    perms.update(
        row.permission_key
        for row in session.scalars(
            select(UserPermission).where(UserPermission.profile_id == profile.id)
        )
    )
    return perms


def has_permission(profile: Profile, session, permission_key: str) -> bool:
    return permission_key in resolve_permissions(profile, session)


def branch_scope_ids(profile: Profile, session) -> list[UUID]:
    """Branch ids the user may read/write. Owner: all active branches."""
    if profile.role == "owner":
        return list(session.scalars(
            select(Branch.id).where(Branch.is_active.is_(True)).order_by(Branch.code)
        ))
    return list(session.scalars(
        select(BranchMembership.branch_id)
        .where(BranchMembership.profile_id == profile.id)
        .join(Branch, Branch.id == BranchMembership.branch_id)
        .where(Branch.is_active.is_(True))
    ))


def can_access_branch(profile: Profile, session, branch_id: UUID) -> bool:
    return branch_id in set(branch_scope_ids(profile, session))


def may_view_cost(profile: Profile, session) -> bool:
    """Gate for avg_cost / cogs fields in API responses."""
    return has_permission(profile, session, "inventory.view_cost")
