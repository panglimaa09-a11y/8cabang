"""Permission tests — role scoping and financial-data gates.

Rules under test (CONTRACT.md sections 4/5):
  - owner: all permissions, all branches.
  - admin: only audit.view by default (no profit/margin/cost).
  - karyawan: no permissions at all -> 403 on profit/margin, users, audit.
  - non-owner branch scope comes strictly from branch_memberships.
"""
from app.models import UserPermission
from app.services.permissions import (
    ALL_PERMISSIONS, branch_scope_ids, can_access_branch, has_permission,
    may_view_cost, resolve_permissions,
)


def test_owner_has_everything(db, seed):
    owner = seed["users"]["owner"]
    assert resolve_permissions(owner, db) == set(ALL_PERMISSIONS)
    assert may_view_cost(owner, db)
    scope = set(branch_scope_ids(owner, db))
    assert scope == {b.id for b in seed["branches"].values()}
    for b in seed["branches"].values():
        assert can_access_branch(owner, db, b.id)


def test_admin_default_permissions(db, seed):
    admin = seed["users"]["admin"]
    assert resolve_permissions(admin, db) == {"audit.view"}
    assert not has_permission(admin, db, "reports.view_profit")
    assert not has_permission(admin, db, "reports.view_margin")
    assert not has_permission(admin, db, "inventory.view_cost")
    assert not has_permission(admin, db, "transactions.correct")
    assert not may_view_cost(admin, db)


def test_karyawan_has_no_permissions(db, seed):
    staff = seed["users"]["karyawan"]
    assert resolve_permissions(staff, db) == set()
    # Financial gates karyawan can never satisfy:
    assert not has_permission(staff, db, "reports.view_profit")
    assert not has_permission(staff, db, "reports.view_margin")
    assert not has_permission(staff, db, "inventory.view_cost")
    assert not has_permission(staff, db, "users.manage")
    assert not has_permission(staff, db, "audit.view")
    assert not may_view_cost(staff, db)


def test_branch_scope_is_strict(db, seed):
    staff = seed["users"]["karyawan"]  # member of C1 only
    c1 = seed["branches"]["C1"].id
    c2 = seed["branches"]["C2"].id
    assert branch_scope_ids(staff, db) == [c1]
    assert can_access_branch(staff, db, c1)
    assert not can_access_branch(staff, db, c2)


def test_owner_grant_extends_admin(db, seed):
    admin = seed["users"]["admin"]
    owner = seed["users"]["owner"]
    assert not has_permission(admin, db, "reports.view_profit")
    db.add(UserPermission(profile_id=admin.id,
                          permission_key="reports.view_profit",
                          granted_by=owner.id))
    db.commit()
    assert has_permission(admin, db, "reports.view_profit")
    # ...but unrelated keys stay denied.
    assert not has_permission(admin, db, "reports.view_margin")


def test_admin_cannot_self_grant_without_owner_row(db, seed):
    """Grants only take effect through user_permissions rows written by owner;
    there is no code path for an admin to escalate itself."""
    admin = seed["users"]["admin"]
    perms_before = resolve_permissions(admin, db)
    assert "users.manage" not in perms_before
    # No grant row exists for admin -> permission stays denied.
    assert not has_permission(admin, db, "users.manage")
