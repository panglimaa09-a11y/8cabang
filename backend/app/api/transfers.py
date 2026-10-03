"""Transfer endpoints: create (in_transit, stock out of source) + receive.

The source unit cost is carried on the transfer_out movement row, so the
destination's moving average can be recomputed exactly on receive.
"""
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
from ..models import InventoryMovement, Product, Profile, Transfer
from ..schemas import TransferCreate, TxnOut
from ..security.auth import get_current_user, get_db, require_branch_access
from ..services import accounting as acct
from ..services.costing import money, qty
from ..services.inventory import (
    NegativeStockError, get_balance_for_update, post_movement,
)

router = APIRouter(prefix="/api", tags=["transfers"])


@router.post("/transfers", status_code=status.HTTP_201_CREATED)
def create_transfer(payload: TransferCreate, request: Request,
                    user: Profile = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if payload.branch_id_from == payload.branch_id_to:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Source and destination branches must differ")
    require_branch_access(payload.branch_id_from, user, db)
    idem_key = get_idempotency_key(request, payload.model_dump(mode="json"))
    if idem_key:
        rec = lookup_idempotency(db, idem_key, "POST /api/transfers")
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

    txn = Transfer(
        branch_id_from=payload.branch_id_from, branch_id_to=payload.branch_id_to,
        txn_no=new_txn_no(db, "TR"), product_id=product.id, qty_base=qty_base,
        status="in_transit", idempotency_key=idem_key, created_by=user.id)
    db.add(txn)
    db.flush()

    try:
        # Lock the source balance so the carried unit cost matches the
        # stock that actually left, even under concurrency.
        src_bal = get_balance_for_update(db, payload.branch_id_from, product.id)
        src_avg = Decimal(str(src_bal.avg_cost))
        post_movement(db, branch_id=payload.branch_id_from, product_id=product.id,
                      txn_type="transfer_out", txn_ref=txn.txn_no,
                      qty_delta_base=-qty_base, unit_cost=src_avg,
                      created_by=user.id)
    except NegativeStockError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=str(exc)) from exc

    write_audit(db, actor_id=user.id, branch_id=payload.branch_id_from,
                action="transfer.create", entity_type="transfers", entity_id=txn.id,
                after={"txn_no": txn.txn_no, "qty_base": str(qty_base),
                       "from": str(payload.branch_id_from),
                       "to": str(payload.branch_id_to)})
    db.commit()

    body = TxnOut(id=txn.id, txn_no=txn.txn_no, status=txn.status,
                  total=None).model_dump(mode="json")
    if idem_key:
        store_idempotency(db, key=idem_key, profile_id=user.id,
                          endpoint="POST /api/transfers",
                          response=body, status_code=201)
        db.commit()
    return JSONResponse(content=body, status_code=201)


@router.post("/transfers/{transfer_id}/receive")
def receive_transfer(transfer_id: UUID, request: Request,
                     user: Profile = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    idem_key = get_idempotency_key(request)
    if idem_key:
        rec = lookup_idempotency(db, idem_key, "POST /api/transfers/{id}/receive")
        if rec:
            return JSONResponse(content=rec.response, status_code=rec.status_code)

    txn = db.get(Transfer, transfer_id)
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Transfer not found")
    require_branch_access(txn.branch_id_to, user, db)
    if txn.status != "in_transit":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Transfer is {txn.status}, only in_transit can be received")

    out_move = db.scalar(select(InventoryMovement).where(
        InventoryMovement.txn_ref == txn.txn_no,
        InventoryMovement.txn_type == "transfer_out"))
    if out_move is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Transfer_out movement missing — data inconsistent")
    unit_cost = Decimal(str(out_move.unit_cost or 0))

    post_movement(db, branch_id=txn.branch_id_to, product_id=txn.product_id,
                  txn_type="transfer_in", txn_ref=txn.txn_no,
                  qty_delta_base=Decimal(str(txn.qty_base)),
                  unit_cost=unit_cost, created_by=user.id)

    value = money(unit_cost * Decimal(str(txn.qty_base)))
    acct.post_journal(
        db, branch_id=txn.branch_id_to, entry_date=date.today(),
        lines=[("Persediaan", value, Decimal("0")),
               ("Transfer Antar Cabang", Decimal("0"), value)],
        ref_type="transfer", ref_id=txn.id, description=f"Receive {txn.txn_no}")

    txn.status = "received"
    txn.received_by = user.id
    write_audit(db, actor_id=user.id, branch_id=txn.branch_id_to,
                action="transfer.receive", entity_type="transfers",
                entity_id=txn.id, before={"status": "in_transit"},
                after={"status": "received", "unit_cost": str(unit_cost)})
    db.commit()

    body = {"id": str(txn.id), "txn_no": txn.txn_no, "status": txn.status}
    if idem_key:
        store_idempotency(db, key=idem_key, profile_id=user.id,
                          endpoint="POST /api/transfers/{id}/receive",
                          response=body, status_code=200)
        db.commit()
    return body
