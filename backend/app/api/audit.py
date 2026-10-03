"""Audit log query endpoint. Requires audit.view (owner always passes)."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import AuditLog, Profile
from ..security.auth import get_current_user, get_db, require_permission

router = APIRouter(prefix="/api", tags=["audit"])

audit_guard = require_permission("audit.view")


@router.get("/audit-logs")
def list_audit_logs(
    branch_id: UUID | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None, alias="to"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    user: Profile = Depends(audit_guard),
    db: Session = Depends(get_db),
):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if branch_id is not None:
        stmt = stmt.where(AuditLog.branch_id == branch_id)
    if from_ is not None:
        stmt = stmt.where(AuditLog.created_at >= from_)
    if to is not None:
        stmt = stmt.where(AuditLog.created_at <= to)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.offset((page - 1) * limit).limit(limit)).all()
    return {
        "items": [{
            "id": r.id, "actor_id": r.actor_id, "branch_id": r.branch_id,
            "action": r.action, "entity_type": r.entity_type,
            "entity_id": r.entity_id, "before": r.before_data,
            "after": r.after_data, "reason": r.reason,
            "created_at": r.created_at,
        } for r in rows],
        "page": page, "limit": limit, "total": total,
    }
