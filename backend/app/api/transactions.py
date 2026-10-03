"""Transaction reversal: void a sale / purchase / expense via compensating
postings. Posted rows are NEVER edited silently or deleted — the original
keeps its history and the reversal is fully audit-logged (before/after).
"""
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..common import (
    get_idempotency_key, lookup_idempotency, store_idempotency, write_audit,
)
from ..models import (
    ExpenseTransaction, Profile, PurchaseItem, PurchaseTransaction,
    SalesItem, SalesTransaction,
)
from ..schemas import ReverseIn
from ..security.auth import get_current_user, get_db, require_permission
from ..services import accounting as acct
from ..services.costing import money, restore_unit_value
from ..services.inventory import NegativeStockError, post_movement

router = APIRouter(prefix="/api", tags=["transactions"])

correct_guard = require_permission("transactions.correct")


def _find_posted(db: Session, txn_id: UUID):
    """Locate a posted transaction across the three reversible types."""
    sale = db.get(SalesTransaction, txn_id)
    if sale is not None:
        return "sale", sale
    purchase = db.get(PurchaseTransaction, txn_id)
    if purchase is not None:
        return "purchase", purchase
    expense = db.get(ExpenseTransaction, txn_id)
    if expense is not None:
        return "expense", expense
    return None, None


@router.post("/transactions/{txn_id}/reverse")
def reverse_transaction(txn_id: UUID, payload: ReverseIn, request: Request,
                        user: Profile = Depends(correct_guard),
                        db: Session = Depends(get_db)):
    idem_key = get_idempotency_key(request, payload.model_dump(mode="json"))
    if idem_key:
        rec = lookup_idempotency(db, idem_key, "POST /api/transactions/{id}/reverse")
        if rec:
            return JSONResponse(content=rec.response, status_code=rec.status_code)

    kind, txn = _find_posted(db, txn_id)
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Transaction not found")
    ref = f"RV-{txn.txn_no}"
    before = {"status": txn.status, "total": str(money(txn.total if kind != 'expense' else txn.amount))}

    try:
        if kind == "sale":
            _reverse_sale(db, txn, ref, user)
        elif kind == "purchase":
            _reverse_purchase(db, txn, ref, user)
        else:
            _reverse_expense(db, txn, ref, user)
    except NegativeStockError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=str(exc)) from exc

    write_audit(db, actor_id=user.id, branch_id=txn.branch_id,
                action="transaction.reverse", entity_type=f"{kind}_transactions",
                entity_id=txn.id, before=before,
                after={"status": txn.status, "reversal_ref": ref},
                reason=payload.reason)
    db.commit()

    body = {"id": str(txn.id), "txn_no": txn.txn_no, "status": txn.status,
            "reversal_ref": ref}
    if idem_key:
        store_idempotency(db, key=idem_key, profile_id=user.id,
                          endpoint="POST /api/transactions/{id}/reverse",
                          response=body, status_code=200)
        db.commit()
    return body


def _reverse_sale(db: Session, txn: SalesTransaction, ref: str, user: Profile) -> None:
    if txn.status != "posted":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Sale is {txn.status}, only posted can be reversed")
    items = db.scalars(select(SalesItem).where(SalesItem.sale_id == txn.id)).all()
    total_cogs = Decimal("0")
    for item in items:
        qty_base = Decimal(str(item.qty_base))
        unit_value = restore_unit_value(item.cogs, qty_base)
        total_cogs += Decimal(str(item.cogs))
        post_movement(db, branch_id=txn.branch_id, product_id=item.product_id,
                      txn_type="sale", txn_ref=ref, qty_delta_base=qty_base,
                      unit_cost=unit_value, created_by=user.id)
    total = Decimal(str(txn.total))
    total_cogs = money(total_cogs)
    acct.post_journal(
        db, branch_id=txn.branch_id, entry_date=date.today(),
        lines=[("Pendapatan Penjualan", total, Decimal("0")),
               ("Kas", Decimal("0"), total),
               ("Persediaan", total_cogs, Decimal("0")),
               ("HPP", Decimal("0"), total_cogs)],
        ref_type="reversal", ref_id=txn.id,
        description=f"Reverse sale {txn.txn_no}")
    txn.status = "voided"


def _reverse_purchase(db: Session, txn: PurchaseTransaction, ref: str, user: Profile) -> None:
    if txn.status != "received":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Purchase is {txn.status}, only received can be reversed")
    items = db.scalars(select(PurchaseItem).where(
        PurchaseItem.purchase_id == txn.id)).all()
    for item in items:
        post_movement(db, branch_id=txn.branch_id, product_id=item.product_id,
                      txn_type="purchase_return", txn_ref=ref,
                      qty_delta_base=-Decimal(str(item.qty_base)),
                      created_by=user.id)
    total = Decimal(str(txn.total))
    acct.post_journal(
        db, branch_id=txn.branch_id, entry_date=date.today(),
        lines=[("Kas", total, Decimal("0")),
               ("Persediaan", Decimal("0"), total)],
        ref_type="reversal", ref_id=txn.id,
        description=f"Reverse purchase {txn.txn_no}")
    txn.status = "cancelled"


def _reverse_expense(db: Session, txn: ExpenseTransaction, ref: str, user: Profile) -> None:
    amount = Decimal(str(txn.amount))
    acct.post_journal(
        db, branch_id=txn.branch_id, entry_date=date.today(),
        lines=[("Kas", amount, Decimal("0")),
               (f"Beban: {txn.category}", Decimal("0"), amount)],
        ref_type="reversal", ref_id=txn.id,
        description=f"Reverse expense {txn.txn_no}")
    # Expenses have no status lifecycle; mark the reversal in audit only.
    txn.description = (txn.description or "") + f" [REVERSED {ref}]"
