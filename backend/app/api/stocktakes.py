"""Stocktake endpoints: create (pending) + approve/reject.

A stocktake never edits stock directly. Approving a pending stocktake posts a
single stocktake_adjust movement for the variance.
"""
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..common import (
    get_idempotency_key, lookup_idempotency, new_txn_no, store_idempotency,
    unit_factor, write_audit,
)
from ..models import Product, Profile, Stocktake
from ..schemas import StocktakeCreate, StocktakeOut
from ..security.auth import (
    get_current_user, get_db, require_branch_access, require_permission,
)
from ..services.costing import qty
from ..services.inventory import get_balance_for_update, post_movement

router = APIRouter(prefix="/api", tags=["stocktakes"])

approve_guard = require_permission("transactions.correct")


@router.post("/stocktakes", status_code=status.HTTP_201_CREATED)
def create_stocktake(payload: StocktakeCreate, request: Request,
                     user: Profile = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    require_branch_access(payload.branch_id, user, db)
    idem_key = get_idempotency_key(request, payload.model_dump(mode="json"))
    if idem_key:
        rec = lookup_idempotency(db, idem_key, "POST /api/stocktakes")
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
    counted = qty(Decimal(str(payload.counted_qty)) * factor)

    bal = get_balance_for_update(db, payload.branch_id, product.id)
    system_qty = Decimal(str(bal.qty_base))
    variance = qty(counted - system_qty)

    txn = Stocktake(
        branch_id=payload.branch_id, txn_no=new_txn_no(db, "SO"),
        product_id=product.id, counted_qty_base=counted,
        system_qty_base=system_qty, variance=variance,
        status="pending", created_by=user.id)
    db.add(txn)
    db.flush()
    write_audit(db, actor_id=user.id, branch_id=payload.branch_id,
                action="stocktake.create", entity_type="stocktakes",
                entity_id=txn.id,
                after={"txn_no": txn.txn_no, "counted": str(counted),
                       "system": str(system_qty), "variance": str(variance)})
    db.commit()

    body = StocktakeOut(id=txn.id, txn_no=txn.txn_no, status=txn.status,
                        counted_qty_base=counted, system_qty_base=system_qty,
                        variance=variance).model_dump(mode="json")
    if idem_key:
        store_idempotency(db, key=idem_key, profile_id=user.id,
                          endpoint="POST /api/stocktakes",
                          response=body, status_code=201)
        db.commit()
    return JSONResponse(content=body, status_code=201)


def _get_pending(db: Session, stocktake_id: UUID, user: Profile) -> Stocktake:
    txn = db.get(Stocktake, stocktake_id)
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Stocktake not found")
    require_branch_access(txn.branch_id, user, db)
    if txn.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Stocktake is {txn.status}, only pending can be decided")
    return txn


@router.post("/stocktakes/{stocktake_id}/approve")
def approve_stocktake(stocktake_id: UUID, request: Request,
                      user: Profile = Depends(approve_guard),
                      db: Session = Depends(get_db)):
    """Approve: post the variance as a stocktake_adjust movement. Atomic."""
    idem_key = get_idempotency_key(request)
    if idem_key:
        rec = lookup_idempotency(db, idem_key, "POST /api/stocktakes/{id}/approve")
        if rec:
            return JSONResponse(content=rec.response, status_code=rec.status_code)

    txn = _get_pending(db, stocktake_id, user)
    variance = Decimal(str(txn.variance))
    if variance != 0:
        # avg_cost is intentionally untouched by stocktakes; unit_cost=None.
        post_movement(db, branch_id=txn.branch_id, product_id=txn.product_id,
                      txn_type="stocktake_adjust", txn_ref=txn.txn_no,
                      qty_delta_base=variance, unit_cost=None, created_by=user.id)
    before = {"status": "pending"}
    txn.status = "approved"
    txn.approved_by = user.id
    write_audit(db, actor_id=user.id, branch_id=txn.branch_id,
                action="stocktake.approve", entity_type="stocktakes",
                entity_id=txn.id, before=before,
                after={"status": "approved", "variance": str(variance)})
    db.commit()

    body = {"id": str(txn.id), "txn_no": txn.txn_no, "status": txn.status,
            "variance": str(variance)}
    if idem_key:
        store_idempotency(db, key=idem_key, profile_id=user.id,
                          endpoint="POST /api/stocktakes/{id}/approve",
                          response=body, status_code=200)
        db.commit()
    return body


@router.post("/stocktakes/{stocktake_id}/reject")
def reject_stocktake(stocktake_id: UUID,
                     user: Profile = Depends(approve_guard),
                     db: Session = Depends(get_db)):
    txn = _get_pending(db, stocktake_id, user)
    txn.status = "rejected"
    txn.approved_by = user.id
    write_audit(db, actor_id=user.id, branch_id=txn.branch_id,
                action="stocktake.reject", entity_type="stocktakes",
                entity_id=txn.id, before={"status": "pending"},
                after={"status": "rejected"})
    db.commit()
    return {"id": str(txn.id), "txn_no": txn.txn_no, "status": txn.status}
