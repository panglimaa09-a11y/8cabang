"""Inventory tests — perpetual stock rules (CONTRACT.md section 5).

- Stock can never go negative without an explicit owner override.
- Every movement records qty_before/qty_after consistently.
- Inbound postings recompute the moving weighted average.
"""
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.models import InventoryBalance, InventoryMovement
from app.services.inventory import NegativeStockError, post_movement

from .conftest import dec


def _ids(seed):
    b = seed["branches"]["C1"].id
    p = seed["products"]["TL-AYAM-RAS"].id
    u = seed["users"]["karyawan"].id
    return b, p, u


def _balance(db, branch_id, product_id):
    return db.scalar(select(InventoryBalance).where(
        InventoryBalance.branch_id == branch_id,
        InventoryBalance.product_id == product_id))


def _movements(db, branch_id, product_id):
    # Order by SQLite rowid for deterministic insertion order (created_at
    # ties are common when several rows share the same second). Test-only.
    return db.scalars(select(InventoryMovement).where(
        InventoryMovement.branch_id == branch_id,
        InventoryMovement.product_id == product_id).order_by(
        text("rowid"))).all()


def test_purchase_receipt_increases_stock_and_avg(db, seed):
    b, p, u = _ids(seed)
    bal, mov = post_movement(db, branch_id=b, product_id=p,
                             txn_type="purchase_receive", txn_ref="PB-1",
                             qty_delta_base=dec(18000), unit_cost=dec(574),
                             created_by=u)
    db.commit()
    assert dec(bal.qty_base) == dec(18000)
    assert dec(bal.avg_cost) == dec(574)
    assert dec(mov.qty_before) == dec(0)
    assert dec(mov.qty_after) == dec(18000)
    assert dec(mov.qty_base) == dec(18000)


def test_sale_decreases_stock_keeps_avg(db, seed):
    b, p, u = _ids(seed)
    post_movement(db, branch_id=b, product_id=p, txn_type="purchase_receive",
                  txn_ref="PB-1", qty_delta_base=dec(18000), unit_cost=dec(574),
                  created_by=u)
    bal, mov = post_movement(db, branch_id=b, product_id=p, txn_type="sale",
                             txn_ref="PJ-1", qty_delta_base=dec(-7200),
                             created_by=u)
    db.commit()
    assert dec(bal.qty_base) == dec(10800)
    assert dec(bal.avg_cost) == dec(574)  # outbound never changes avg
    assert dec(mov.qty_before) == dec(18000)
    assert dec(mov.qty_after) == dec(10800)


def test_weighted_average_recompute(db, seed):
    b, p, u = _ids(seed)
    post_movement(db, branch_id=b, product_id=p, txn_type="purchase_receive",
                  txn_ref="PB-1", qty_delta_base=dec(18000), unit_cost=dec(500),
                  created_by=u)
    bal, _ = post_movement(db, branch_id=b, product_id=p,
                           txn_type="purchase_receive", txn_ref="PB-2",
                           qty_delta_base=dec(9000), unit_cost=dec(600),
                           created_by=u)
    db.commit()
    expected = (dec(18000) * dec(500) + dec(9000) * dec(600)) / dec(27000)
    assert abs(dec(bal.avg_cost) - expected) < dec("0.001")
    assert dec(bal.qty_base) == dec(27000)


def test_negative_stock_rejected(db, seed):
    b, p, u = _ids(seed)
    post_movement(db, branch_id=b, product_id=p, txn_type="purchase_receive",
                  txn_ref="PB-1", qty_delta_base=dec(100), unit_cost=dec(500),
                  created_by=u)
    db.commit()
    with pytest.raises(NegativeStockError):
        post_movement(db, branch_id=b, product_id=p, txn_type="sale",
                      txn_ref="PJ-1", qty_delta_base=dec(-101), created_by=u)
    db.rollback()
    # Failed posting changed nothing.
    assert dec(_balance(db, b, p).qty_base) == dec(100)
    assert len(_movements(db, b, p)) == 1


def test_negative_stock_allowed_only_with_override(db, seed):
    b, p, u = _ids(seed)
    bal, mov = post_movement(db, branch_id=b, product_id=p, txn_type="sale",
                             txn_ref="PJ-1", qty_delta_base=dec(-50),
                             created_by=u, allow_negative=True)
    db.commit()
    assert dec(bal.qty_base) == dec(-50)
    assert dec(mov.qty_after) == dec(-50)


def test_movement_chain_is_consistent(db, seed):
    """qty_after of movement N must equal qty_before of movement N+1."""
    b, p, u = _ids(seed)
    post_movement(db, branch_id=b, product_id=p, txn_type="purchase_receive",
                  txn_ref="PB-1", qty_delta_base=dec(1000), unit_cost=dec(500),
                  created_by=u)
    post_movement(db, branch_id=b, product_id=p, txn_type="sale",
                  txn_ref="PJ-1", qty_delta_base=dec(-300), created_by=u)
    post_movement(db, branch_id=b, product_id=p, txn_type="damage",
                  txn_ref="DM-1", qty_delta_base=dec(-50), created_by=u)
    post_movement(db, branch_id=b, product_id=p, txn_type="sales_return",
                  txn_ref="RT-1", qty_delta_base=dec(100), unit_cost=dec(500),
                  created_by=u)
    db.commit()
    moves = _movements(db, b, p)
    assert len(moves) == 4
    for prev, nxt in zip(moves, moves[1:]):
        assert dec(nxt.qty_before) == dec(prev.qty_after)
        assert dec(nxt.qty_after) == dec(nxt.qty_before) + dec(nxt.qty_base)
    bal = _balance(db, b, p)
    assert dec(bal.qty_base) == dec(moves[-1].qty_after) == dec(750)
