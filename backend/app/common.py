"""Shared helpers for API routers: idempotency, transaction numbers, audit."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AppSetting, AuditLog, IdempotencyRecord

if TYPE_CHECKING:  # fastapi is only needed for type hints here
    from fastapi import Request

IDEMPOTENCY_TTL_DAYS = 7


def get_idempotency_key(request: Request, payload: dict | None = None) -> str | None:
    """Idempotency-Key header wins; body field `idempotency_key` is the fallback."""
    header_key = request.headers.get("Idempotency-Key") or request.headers.get("idempotency-key")
    if header_key:
        return header_key.strip()
    if payload:
        key = payload.get("idempotency_key")
        return str(key).strip() if key else None
    return None


def lookup_idempotency(session: Session, key: str, endpoint: str) -> IdempotencyRecord | None:
    rec = session.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == key))
    if rec is None:
        return None
    # SQLite returns naive datetimes for TIMESTAMPTZ; Postgres returns aware.
    # Normalize so the comparison works on both.
    expires_at = rec.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        session.delete(rec)
        session.flush()
        return None
    return rec


def store_idempotency(session: Session, *, key: str, profile_id: UUID | None,
                      endpoint: str, response: dict, status_code: int) -> None:
    session.add(IdempotencyRecord(
        key=key,
        profile_id=profile_id,
        endpoint=endpoint,
        response=response,
        status_code=status_code,
        expires_at=datetime.now(timezone.utc) + timedelta(days=IDEMPOTENCY_TTL_DAYS),
    ))
    session.flush()


def new_txn_no(session: Session, prefix: str) -> str:
    """Generate PREFIX-YYYYMMDD-#### with a per-day counter in app_settings.

    Must be called inside the posting transaction so a rollback also rolls
    back the counter — no gaps are skipped permanently on failure, and
    concurrent calls serialize on the row lock.
    """
    day = date.today().strftime("%Y%m%d")
    key = f"txnseq:{prefix}:{day}"
    stmt = select(AppSetting).where(AppSetting.key == key).with_for_update()
    row = session.scalar(stmt)
    seq = 1
    if row is not None:
        seq = int(row.value.get("seq", 0)) + 1
        row.value = {"seq": seq}
    else:
        session.add(AppSetting(key=key, value={"seq": seq}))
    session.flush()
    return f"{prefix}-{day}-{seq:04d}"


def write_audit(session: Session, *, actor_id: UUID | None, branch_id: UUID | None = None,
                action: str, entity_type: str | None = None, entity_id: UUID | None = None,
                before: dict | None = None, after: dict | None = None,
                reason: str | None = None) -> None:
    session.add(AuditLog(
        actor_id=actor_id, branch_id=branch_id, action=action,
        entity_type=entity_type, entity_id=entity_id,
        before_data=before, after_data=after, reason=reason))
    session.flush()


def unit_factor(product, unit: str) -> Decimal:
    """Conversion factor from a display unit to base units. Raises ValueError."""
    units = product.units or {}
    if unit not in units:
        raise ValueError(f"Unknown unit '{unit}' for product {product.sku}")
    return Decimal(str(units[unit]))
