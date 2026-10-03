"""Inventory service — perpetual stock with row-level locking.

Every stock change writes exactly one inventory_movements row (qty_before /
qty_after) and updates inventory_balances inside the SAME database
transaction. The balance row is locked with SELECT ... FOR UPDATE so
concurrent postings cannot corrupt the balance.
"""
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from ..models import InventoryBalance, InventoryMovement
from .costing import new_avg_cost, qty


class NegativeStockError(Exception):
    """Raised when a posting would drive stock below zero without permission."""


def get_balance_for_update(session, branch_id: UUID, product_id: UUID) -> InventoryBalance:
    """Fetch (creating if needed) the balance row, locked FOR UPDATE."""
    stmt = (
        select(InventoryBalance)
        .where(InventoryBalance.branch_id == branch_id,
               InventoryBalance.product_id == product_id)
        .with_for_update()
    )
    bal = session.scalar(stmt)
    if bal is None:
        bal = InventoryBalance(branch_id=branch_id, product_id=product_id,
                               qty_base=Decimal("0"), avg_cost=Decimal("0"))
        session.add(bal)
        session.flush()
        # Re-select with lock so the freshly inserted row is also locked.
        bal = session.scalar(stmt)
    return bal


def post_movement(
    session,
    *,
    branch_id: UUID,
    product_id: UUID,
    txn_type: str,
    txn_ref: str,
    qty_delta_base,
    unit_cost=None,
    created_by: UUID | None = None,
    allow_negative: bool = False,
) -> tuple[InventoryBalance, InventoryMovement]:
    """Post one stock movement atomically (caller owns the DB transaction).

    Args:
        qty_delta_base: signed quantity in base units (Decimal).
        unit_cost: per-base-unit cost for INBOUND movements; triggers a
            moving-weighted-average recompute of avg_cost. Ignored for
            outbound movements (delta < 0) and stocktake adjustments.
        allow_negative: only honoured when the caller already verified the
            actor is owner and logged the override in the audit log.

    Returns (balance, movement). Raises NegativeStockError.
    """
    delta = qty(qty_delta_base)
    bal = get_balance_for_update(session, branch_id, product_id)

    qty_before = Decimal(str(bal.qty_base))
    qty_after = qty(qty_before + delta)

    if qty_after < 0 and not allow_negative:
        raise NegativeStockError(
            f"Insufficient stock: have {qty_before}, need {abs(delta)} "
            f"(branch={branch_id}, product={product_id})"
        )

    if delta > 0 and unit_cost is not None:
        value_before = qty_before * Decimal(str(bal.avg_cost))
        value_in = delta * Decimal(str(unit_cost))
        bal.avg_cost = new_avg_cost(qty_before, value_before, delta, value_in)

    bal.qty_base = qty_after

    movement = InventoryMovement(
        branch_id=branch_id,
        product_id=product_id,
        txn_type=txn_type,
        txn_ref=txn_ref,
        qty_base=delta,
        qty_before=qty_before,
        qty_after=qty_after,
        unit_cost=(Decimal(str(unit_cost)).quantize(Decimal("0.0001"))
                   if unit_cost is not None else None),
        created_by=created_by,
    )
    session.add(movement)
    session.flush()
    return bal, movement
