"""Tests for /api/dashboard/summary — the single-request dashboard endpoint.

Guards (CONTRACT.md sections 4/5):
- users only see their branch scope (karyawan C1 never sees C2);
- profit fields (cogs / net_profit / margin_pct) are owner-only;
- totals match the old accounting math: net = sales - cogs - expenses.
"""
from datetime import date
from decimal import Decimal

from app.api.dashboard import dashboard_summary
from app.models import (
    ExpenseTransaction, InventoryBalance, PurchaseTransaction,
    SalesItem, SalesTransaction,
)


def _seed_txn_data(db, seed):
    c1 = seed["branches"]["C1"]
    owner = seed["users"]["owner"]
    prod = seed["products"]["TL-AYAM-RAS"]
    # Posted sale C1: subtotal 1000 - discount 100 -> revenue_net 900, total 900.
    s = SalesTransaction(branch_id=c1.id, txn_no="JUAL-D-001", customer="A",
                         status="posted", subtotal=1000, discount=100, total=900,
                         created_by=owner.id)
    db.add(s)
    db.flush()
    db.add(SalesItem(sale_id=s.id, product_id=prod.id, qty_base=30,
                     unit="rak", unit_price=30, line_total=900, cogs=600))
    # Received purchase C1, total 500.
    db.add(PurchaseTransaction(branch_id=c1.id, txn_no="BELI-D-001", supplier="S",
                               status="received", subtotal=500, total=500,
                               created_by=owner.id))
    # Expense C1, 200.
    db.add(ExpenseTransaction(branch_id=c1.id, txn_no="BIAYA-D-001",
                              category="Listrik", description="x", amount=200,
                              expense_date=date.today(), created_by=owner.id))
    # Low stock balance C1: 100 butir < default threshold 1800.
    db.add(InventoryBalance(branch_id=c1.id, product_id=prod.id,
                            qty_base=100, avg_cost=20))
    db.commit()


def _call(db, user, **kw):
    return dashboard_summary(from_=kw.get("from_"), to=kw.get("to"),
                             user=user, db=db)


def test_owner_sees_all_branches_and_profit(db, seed):
    _seed_txn_data(db, seed)
    out = _call(db, seed["users"]["owner"])
    assert out["owner"] is True
    assert {b["code"] for b in out["branches"]} == {"C1", "C2"}

    c1 = next(b for b in out["branches"] if b["code"] == "C1")
    assert c1["sales"] == Decimal("900.00")
    assert c1["cash_in"] == Decimal("900.00")
    assert c1["cash_out"] == Decimal("700.00")  # 500 purchase + 200 expense
    assert c1["inventory_value"] == Decimal("2000.00")  # 100 x 20
    assert c1["cogs"] == Decimal("600.00")
    assert len(c1["low_stock"]) == 1
    assert c1["low_stock"][0]["sku"] == "TL-AYAM-RAS"
    kinds = {r["type"] for r in c1["recent"]}
    assert {"sale", "purchase", "expense"} <= kinds
    assert all(r["branch_id"] == c1["id"] for r in c1["recent"])

    t = out["totals"]
    assert t["sales"] == Decimal("900.00")
    assert t["cogs"] == Decimal("600.00")
    # net = sales - cogs - expenses (same as profit_loss_report)
    assert t["net_profit"] == Decimal("100.00")
    assert t["margin_pct"] == round(100 / 900 * 100, 2)


def test_karyawan_scope_and_no_profit_fields(db, seed):
    _seed_txn_data(db, seed)
    out = _call(db, seed["users"]["karyawan"])
    assert out["owner"] is False
    # karyawan in the seed belongs to C1 only.
    assert [b["code"] for b in out["branches"]] == ["C1"]
    c1 = out["branches"][0]
    assert c1["sales"] == Decimal("900.00")
    assert "cogs" not in c1
    t = out["totals"]
    assert "net_profit" not in t
    assert "margin_pct" not in t
    assert t["sales"] == Decimal("900.00")


def test_admin_scope_limited_to_membership(db, seed):
    # admin di seed hanya member C1 -> tidak boleh melihat C2.
    out = _call(db, seed["users"]["admin"])
    assert out["owner"] is False
    assert [b["code"] for b in out["branches"]] == ["C1"]
    assert "net_profit" not in out["totals"]
