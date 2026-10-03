"""Sales endpoint: post a sale (stock -, historical COGS, journal)."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..common import (
    get_idempotency_key, lookup_idempotency, new_txn_no, store_idempotency,
    unit_factor, write_audit,
)
from ..models import Product, Profile, SalesItem, SalesTransaction
from ..schemas import SaleCreate, TxnOut
from ..security.auth import get_current_user, get_db, require_branch_access
from ..services import accounting as acct
from ..services.costing import cogs_for_sale, money, qty
from ..services.inventory import NegativeStockError, get_balance_for_update, post_movement

router = APIRouter(prefix="/api", tags=["sales"])


@router.post("/sales", status_code=status.HTTP_201_CREATED)
def create_sale(payload: SaleCreate, request: Request,
                user: Profile = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """Post a sale atomically: validate stock, move stock, store historical
    COGS per line, write journal. Idempotent via Idempotency-Key."""
    require_branch_access(payload.branch_id, user, db)
    idem_key = get_idempotency_key(request, payload.model_dump(mode="json"))
    if idem_key:
        rec = lookup_idempotency(db, idem_key, "POST /api/sales")
        if rec:
            return JSONResponse(content=rec.response, status_code=rec.status_code)

    # allow_negative is an owner-only override and is always audit-logged.
    allow_negative = False
    if payload.allow_negative:
        if user.role != "owner":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="allow_negative is owner-only")
        allow_negative = True

    lines: list[dict] = []
    subtotal = Decimal("0")
    total_cogs = Decimal("0")
    for it in payload.items:
        product = db.get(Product, it.product_id)
        if product is None or not product.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"Unknown or inactive product {it.product_id}")
        try:
            factor = unit_factor(product, it.unit)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=str(exc)) from exc
        qty_base = qty(Decimal(str(it.qty)) * factor)
        line_total = money(Decimal(str(it.qty)) * Decimal(str(it.unit_price)))
        subtotal += line_total

        # Lock the balance first so the COGS snapshot and the stock move
        # see the same avg_cost even under concurrency.
        bal = get_balance_for_update(db, payload.branch_id, product.id)
        avg_cost = Decimal(str(bal.avg_cost))
        line_cogs = cogs_for_sale(qty_base, avg_cost)
        total_cogs += line_cogs
        lines.append({"product_id": product.id, "qty_base": qty_base,
                      "unit": it.unit, "unit_price": money(it.unit_price),
                      "line_total": line_total, "cogs": line_cogs})

    discount = money(payload.discount)
    if discount > subtotal:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Discount cannot exceed subtotal")
    total = money(subtotal - discount)

    txn = SalesTransaction(
        branch_id=payload.branch_id, txn_no=new_txn_no(db, "PJ"),
        customer=payload.customer, status="posted",
        subtotal=money(subtotal), discount=discount, total=total,
        idempotency_key=idem_key, created_by=user.id)
    db.add(txn)
    db.flush()

    for line in lines:
        db.add(SalesItem(sale_id=txn.id, product_id=line["product_id"],
                         qty_base=line["qty_base"], unit=line["unit"],
                         unit_price=line["unit_price"],
                         line_total=line["line_total"], cogs=line["cogs"]))
        try:
            post_movement(db, branch_id=payload.branch_id,
                          product_id=line["product_id"], txn_type="sale",
                          txn_ref=txn.txn_no, qty_delta_base=-line["qty_base"],
                          created_by=user.id, allow_negative=allow_negative)
        except NegativeStockError as exc:
            # Roll back EVERYTHING: no partial sale, no fake success.
            db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=str(exc)) from exc

    acct.post_journal(
        db, branch_id=payload.branch_id, entry_date=date.today(),
        lines=[("Kas", total, Decimal("0")),
               ("Pendapatan Penjualan", Decimal("0"), total),
               ("HPP", money(total_cogs), Decimal("0")),
               ("Persediaan", Decimal("0"), money(total_cogs))],
        ref_type="sale", ref_id=txn.id, description=f"Sale {txn.txn_no}")

    if allow_negative:
        write_audit(db, actor_id=user.id, branch_id=payload.branch_id,
                    action="stock.allow_negative", entity_type="sales_transactions",
                    entity_id=txn.id, after={"txn_no": txn.txn_no},
                    reason="Owner override: sale posted despite insufficient stock")

    write_audit(db, actor_id=user.id, branch_id=payload.branch_id,
                action="sale.create", entity_type="sales_transactions",
                entity_id=txn.id,
                after={"txn_no": txn.txn_no, "total": str(total),
                       "cogs": str(money(total_cogs))})
    db.commit()

    body = TxnOut(id=txn.id, txn_no=txn.txn_no, status=txn.status,
                  total=total).model_dump(mode="json")
    if idem_key:
        store_idempotency(db, key=idem_key, profile_id=user.id,
                          endpoint="POST /api/sales",
                          response=body, status_code=201)
        db.commit()
    return JSONResponse(content=body, status_code=201)
