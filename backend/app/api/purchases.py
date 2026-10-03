"""Purchase endpoints: create (draft) + receive (stock in, avg cost, journal)."""
from datetime import date, datetime, timezone
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
    Product, Profile, PurchaseItem, PurchaseTransaction,
)
from ..schemas import PurchaseCreate, TxnOut
from ..security.auth import get_current_user, get_db, require_branch_access
from ..services import accounting as acct
from ..services.costing import money, qty
from ..services.inventory import post_movement

router = APIRouter(prefix="/api", tags=["purchases"])


def _get_product(db: Session, product_id: UUID) -> Product:
    product = db.get(Product, product_id)
    if product is None or not product.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Unknown or inactive product {product_id}")
    return product


def _build_lines(db: Session, items) -> tuple[list[dict], Decimal, Decimal]:
    """Validate items -> (lines, subtotal, total_qty_base). Raises 400 on bad input."""
    lines: list[dict] = []
    subtotal = Decimal("0")
    for it in items:
        product = _get_product(db, it.product_id)
        try:
            factor = unit_factor(product, it.unit)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=str(exc)) from exc
        qty_base = qty(Decimal(str(it.qty)) * factor)
        line_total = money(Decimal(str(it.qty)) * Decimal(str(it.unit_price)))
        subtotal += line_total
        lines.append({"product": product, "qty_base": qty_base,
                      "unit": it.unit, "unit_price": money(it.unit_price),
                      "line_total": line_total})
    return lines, money(subtotal), sum((l["qty_base"] for l in lines), Decimal("0"))


@router.post("/purchases", status_code=status.HTTP_201_CREATED)
def create_purchase(payload: PurchaseCreate, request: Request,
                    user: Profile = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    require_branch_access(payload.branch_id, user, db)
    idem_key = get_idempotency_key(request, payload.model_dump(mode="json"))
    if idem_key:
        rec = lookup_idempotency(db, idem_key, "POST /api/purchases")
        if rec:
            return JSONResponse(content=rec.response, status_code=rec.status_code)

    lines, subtotal, _ = _build_lines(db, payload.items)
    freight = money(payload.freight_cost)
    total = money(subtotal + freight)

    txn = PurchaseTransaction(
        branch_id=payload.branch_id, txn_no=new_txn_no(db, "PB"),
        supplier=payload.supplier, status="draft",
        subtotal=subtotal, freight_cost=freight, total=total,
        idempotency_key=idem_key, created_by=user.id)
    db.add(txn)
    db.flush()
    for line in lines:
        db.add(PurchaseItem(purchase_id=txn.id, product_id=line["product"].id,
                            qty_base=line["qty_base"], unit=line["unit"],
                            unit_price=line["unit_price"], line_total=line["line_total"]))
    write_audit(db, actor_id=user.id, branch_id=payload.branch_id,
                action="purchase.create", entity_type="purchase_transactions",
                entity_id=txn.id,
                after={"txn_no": txn.txn_no, "total": str(total),
                       "items": len(lines)})
    db.commit()

    body = TxnOut(id=txn.id, txn_no=txn.txn_no, status=txn.status,
                  total=total).model_dump(mode="json")
    if idem_key:
        store_idempotency(db, key=idem_key, profile_id=user.id,
                          endpoint="POST /api/purchases",
                          response=body, status_code=201)
        db.commit()
    return JSONResponse(content=body, status_code=201)


@router.post("/purchases/{purchase_id}/receive")
def receive_purchase(purchase_id: UUID, request: Request,
                     user: Profile = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    """Receive a draft purchase: stock +, weighted-average cost, journal.

    Freight is allocated to items proportionally by line_total so the landed
    cost per base unit is exact. The whole receive is one atomic transaction.
    """
    idem_key = get_idempotency_key(request)
    if idem_key:
        rec = lookup_idempotency(db, idem_key, "POST /api/purchases/{id}/receive")
        if rec:
            return JSONResponse(content=rec.response, status_code=rec.status_code)

    txn = db.get(PurchaseTransaction, purchase_id)
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase not found")
    require_branch_access(txn.branch_id, user, db)
    if txn.status != "draft":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Purchase is {txn.status}, only draft can be received")

    items = db.scalars(select(PurchaseItem)
                       .where(PurchaseItem.purchase_id == txn.id)).all()
    if not items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Purchase has no items")

    subtotal = Decimal(str(txn.subtotal))
    freight = Decimal(str(txn.freight_cost))
    total_qty = sum((Decimal(str(i.qty_base)) for i in items), Decimal("0"))

    for item in items:
        line_total = Decimal(str(item.line_total))
        if subtotal > 0:
            freight_share = freight * line_total / subtotal
        elif total_qty > 0:
            freight_share = freight * Decimal(str(item.qty_base)) / total_qty
        else:
            freight_share = Decimal("0")
        value_in = money(line_total + freight_share)
        qty_base = Decimal(str(item.qty_base))
        unit_cost = (value_in / qty_base) if qty_base > 0 else Decimal("0")
        post_movement(db, branch_id=txn.branch_id, product_id=item.product_id,
                      txn_type="purchase_receive", txn_ref=txn.txn_no,
                      qty_delta_base=qty_base, unit_cost=unit_cost,
                      created_by=user.id)

    txn.status = "received"
    txn.received_at = datetime.now(timezone.utc)

    acct.post_journal(
        db, branch_id=txn.branch_id, entry_date=date.today(),
        lines=[("Persediaan", Decimal(str(txn.total)), Decimal("0")),
               ("Kas", Decimal("0"), Decimal(str(txn.total)))],
        ref_type="purchase", ref_id=txn.id,
        description=f"Receive {txn.txn_no}")

    write_audit(db, actor_id=user.id, branch_id=txn.branch_id,
                action="purchase.receive", entity_type="purchase_transactions",
                entity_id=txn.id,
                before={"status": "draft"}, after={"status": "received"},
                reason=None)
    db.commit()

    body = {"id": str(txn.id), "txn_no": txn.txn_no, "status": txn.status,
            "total": str(money(txn.total))}
    if idem_key:
        store_idempotency(db, key=idem_key, profile_id=user.id,
                          endpoint="POST /api/purchases/{id}/receive",
                          response=body, status_code=200)
        db.commit()
    return body
