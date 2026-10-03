"""Financial reports. Every figure is computed from the database.

Access rules (CONTRACT.md section 4/5):
  - karyawan: ALWAYS 403 on every report endpoint below.
  - /profit-loss needs reports.view_profit; /profit-margin needs reports.view_margin.
  - /cash needs an operational role (owner/admin).
  - /consolidated is owner-only; branch_id is optional, and non-owners are
    restricted to their own branch scope.
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Branch, Profile
from ..security.auth import (
    assert_karyawan_blocked, get_current_user, get_db, require_permission,
)
from ..services import accounting as acct
from ..services.permissions import branch_scope_ids, can_access_branch

router = APIRouter(prefix="/api/reports", tags=["reports"])

profit_guard = require_permission("reports.view_profit")
margin_guard = require_permission("reports.view_margin")


def _scope(user: Profile, db: Session, branch_id: UUID | None) -> list[UUID]:
    assert_karyawan_blocked(user)
    if branch_id is not None:
        if not can_access_branch(user, db, branch_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Branch out of scope")
        return [branch_id]
    return branch_scope_ids(user, db)


@router.get("/cash")
def cash_report(branch_id: UUID | None = None,
                from_: datetime | None = Query(default=None, alias="from"),
                to: datetime | None = Query(default=None, alias="to"),
                user: Profile = Depends(get_current_user),
                db: Session = Depends(get_db)):
    ids = _scope(user, db, branch_id)
    return acct.cash_report(db, ids, from_, to)


@router.get("/profit-loss")
def profit_loss(branch_id: UUID | None = None,
                from_: datetime | None = Query(default=None, alias="from"),
                to: datetime | None = Query(default=None, alias="to"),
                user: Profile = Depends(profit_guard),
                db: Session = Depends(get_db)):
    assert_karyawan_blocked(user)
    ids = _scope(user, db, branch_id)
    return acct.profit_loss_report(db, ids, from_, to)


@router.get("/profit-margin")
def profit_margin(branch_id: UUID | None = None,
                from_: datetime | None = Query(default=None, alias="from"),
                to: datetime | None = Query(default=None, alias="to"),
                user: Profile = Depends(margin_guard),
                db: Session = Depends(get_db)):
    assert_karyawan_blocked(user)
    ids = _scope(user, db, branch_id)
    return acct.margin_report(db, ids, from_, to)


@router.get("/consolidated")
def consolidated(from_: datetime | None = Query(default=None, alias="from"),
                 to: datetime | None = Query(default=None, alias="to"),
                 user: Profile = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    if user.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Consolidated report is owner-only")
    branches = db.scalars(select(Branch).where(Branch.is_active.is_(True))
                          .order_by(Branch.code)).all()
    per_branch = []
    for b in branches:
        pl = acct.profit_loss_report(db, [b.id], from_, to)
        margin = acct.margin_report(db, [b.id], from_, to)["margin_pct"]
        per_branch.append({
            "branch_id": b.id, "code": b.code, "name": b.name,
            "revenue_net": pl["revenue_net"], "cogs": pl["cogs"],
            "gross_profit": pl["gross_profit"], "opex": pl["opex"],
            "net_profit": pl["net_profit"], "margin_pct": margin,
            "inventory_value": acct.inventory_value(db, [b.id]),
        })
    totals = acct.profit_loss_report(db, [b.id for b in branches], from_, to)
    totals_margin = acct.margin_report(db, [b.id for b in branches], from_, to)["margin_pct"]
    return {
        "branches": per_branch,
        "total": {**totals, "margin_pct": totals_margin,
                  "inventory_value": acct.inventory_value(db, [b.id for b in branches])},
    }
