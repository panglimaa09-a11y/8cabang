"""Return endpoint: sales returns (stock in) and purchase returns (stock out)."""
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..common import (
    get_idempotency_key, lookup_idempotency, new_txn_no, store_idempotency,
    unit_factor, write_audit,
)
from ..models import (
    Product, Profile, PurchaseItem, PurchaseTransaction, Return,
    SalesItem, SalesTransaction,
)
from ..schemas import ReturnCreate, TxnOut
from ..security.auth import get_current_user, get_db, require_branch_access
from ..services import accounting as acct
from ..services.costing import money, qty, restore_unit_value
from ..services.inventory import post_movement

router = APIRouter(prefix="/api", tags=["returns"])


@router.post("/returns", status_code=status.HTTP_201_CREATED)
def create_return(payload: ReturnCreate, request: Request,
                  user: Profile = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    require_branch_access(payload.branch_id, user, db)
    idem_key = get_idempotency_key(request, payload.model_dump(mode="json"))
    if idem_key:
        rec = lookup_idempotency(db, idem_key, "POST /api/returns")
        if rec:
            return JSONResponse(content=rec.response, status_code=rec.status_code)

    product = db.get(Product, payload.product_id)
    if product is None or not product.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Unknown or inactive product")
    try:
        factor = unit_factor(product, payload.unit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc
    qty_base = qty(Decimal(str(payload.qty)) * factor)

    if payload.return_type == "sales_return":
        amount, unit_value = _sales_return_value(db, payload, qty_base)
        delta = qty_base
        txn_type = "sales_return"
    else:
        amount, unit_value = _purchase_return_value(db, payload, qty_base)
        delta = -qty_base
        txn_type = "purchase_return"

    txn = Return(
        branch_id=payload.branch_id, txn_no=new_txn_no(db, "RT"),
        return_type=payload.return_type, ref_txn_id=payload.ref_txn_id,
        product_id=product.id, qty_base=qty_base, amount=amount,
        reason=payload.reason, status="posted",
        idempotency_key=idem_key, created_by=user.id)
    db.add(txn)
    db.flush()

    post_movement(db, branch_id=payload.branch_id, product_id=product.id,
                  txn_type=txn_type, txn_ref=txn.txn_no,
                  qty_delta_base=delta, unit_cost=unit_value if delta > 0 else None,
                  created_by=user.id)

    if payload.return_type == "sales_return":
        restore_value = money(Decimal(str(unit_value)) * qty_base)
        acct.post_journal(
            db, branch_id=payload.branch_id, entry_date=date.today(),
            lines=[("Retur Penjualan", amount, Decimal("0")),
                   ("Kas", Decimal("0"), amount),
                   ("Persediaan", restore_value, Decimal("0")),
                   ("HPP", Decimal("0"), restore_value)],
            ref_type="return", ref_id=txn.id, description=f"Return {txn.txn_no}")
    else:
        acct.post_journal(
            db, branch_id=payload.branch_id, entry_date=date.today(),
            lines=[("Kas", amount, Decimal("0")),
                   ("Persediaan", Decimal("0"), amount)],
            ref_type="return", ref_id=txn.id, description=f"Return {txn.txn_no}")

    write_audit(db, actor_id=user.id, branch_id=payload.branch_id,
                action="return.create", entity_type="returns", entity_id=txn.id,
                after={"txn_no": txn.txn_no, "return_type": payload.return_type,
                       "qty_base": str(qty_base), "amount": str(amount)})
    db.commit()

    body = TxnOut(id=txn.id, txn_no=txn.txn_no, status=txn.status,
                  total=amount).model_dump(mode="json")
    if idem_key:
        store_idempotency(db, key=idem_key, profile_id=user.id,
                          endpoint="POST /api/returns",
                          response=body, status_code=201)
        db.commit()
    return JSONResponse(content=body, status_code=201)


def _sales_return_value(db: Session, payload: ReturnCreate, qty_base: Decimal):
    """Restored value = original line COGS per base unit (fallback: current avg)."""
    item = None
    if payload.ref_txn_id:
        item = db.scalar(select(SalesItem).where(
            SalesItem.sale_id == payload.ref_txn_id,
            SalesItem.product_id == payload.product_id))
    if item is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="ref_txn_id must reference the original sale line")
    orig_qty = Decimal(str(item.qty_base))
    if qty_base > orig_qty:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Return qty exceeds original sale qty")
    unit_value = restore_unit_value(item.cogs, orig_qty)
    amount = money(Decimal(str(item.unit_price)) / orig_qty * qty_base)
    return amount, unit_value


def _purchase_return_value(db: Session, payload: ReturnCreate, qty_base: Decimal):
    item = None
    if payload.ref_txn_id:
        item = db.scalar(select(PurchaseItem).where(
            PurchaseItem.purchase_id == payload.ref_txn_id,
            PurchaseItem.product_id == payload.product_id))
    if item is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="ref_txn_id must reference the original purchase line")
    orig_qty = Decimal(str(item.qty_base))
    if qty_base > orig_qty:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Return qty exceeds original purchase qty")
    unit_value = restore_unit_value(item.line_total, orig_qty)
    amount = money(Decimal(str(item.line_total)) / orig_qty * qty_base)
    return amount, unit_value
