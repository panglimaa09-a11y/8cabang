"""Dashboard summary: everything the dashboard shows, in ONE request.

Problem it fixes (Oct 2026): the dashboard used to fetch
`/reports/consolidated` first (~80 SEQUENTIAL DB round trips, because
margin_report recomputes profit_loss_report a second time per branch) and
then N x `/branches/{id}/summary` (~15 queries each, each a separate
serverless cold start with a fresh DB connection). On a high-RTT link to
Supabase that meant 10-20+ seconds of skeleton loading.

This endpoint runs ~12 grouped (GROUP BY branch_id) queries in a single
serverless invocation instead of ~200 queries across 9 invocations.

Scope rules are unchanged: users only see their branch scope, and the
profit fields (net_profit / margin) are owner-only, same as /reports/consolidated.
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    AppSetting, Branch, ExpenseTransaction, InventoryBalance,
    Product, Profile, PurchaseTransaction, Return,
    SalesItem, SalesTransaction, Stocktake, Transfer,
)
from ..security.auth import get_current_user, get_db
from ..services.costing import money
from ..services.permissions import branch_scope_ids

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

RECENT_PER_BRANCH = 10


def _date_conds(col, from_, to_):
    conds = []
    if from_:
        conds.append(col >= from_)
    if to_:
        conds.append(col <= to_)
    return conds


def _grouped(rows, key_idx=0):
    out = {}
    for r in rows:
        out[r[key_idx]] = r
    return out


@router.get("/summary")
def dashboard_summary(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None, alias="to"),
    user: Profile = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = branch_scope_ids(user, db)
    owner = user.role == "owner"
    if not scope:
        return {"owner": owner, "branches": [], "totals": _empty_totals(owner)}

    branches = db.scalars(
        select(Branch).where(Branch.id.in_(scope)).order_by(Branch.code)
    ).all()
    by_id = {b.id: b for b in branches}
    ids = [b.id for b in branches]
    n = len(ids)
    date_conds_sales = _date_conds(SalesTransaction.created_at, from_, to)

    # 1) Sales aggregates per branch: revenue_net + cash_in.
    sales_rows = _grouped(db.execute(
        select(
            SalesTransaction.branch_id,
            func.coalesce(func.sum(SalesTransaction.subtotal
                                  - SalesTransaction.discount), 0).label("revenue_net"),
            func.coalesce(func.sum(SalesTransaction.total), 0).label("cash_in"),
        )
        .where(SalesTransaction.branch_id.in_(ids),
               SalesTransaction.status == "posted",
               *date_conds_sales)
        .group_by(SalesTransaction.branch_id)
    ).all())

    # 2) COGS per branch (single join, not per-sale subqueries).
    cogs_rows = _grouped(db.execute(
        select(
            SalesTransaction.branch_id,
            func.coalesce(func.sum(SalesItem.cogs), 0).label("cogs"),
        )
        .join(SalesItem, SalesItem.sale_id == SalesTransaction.id)
        .where(SalesTransaction.branch_id.in_(ids),
               SalesTransaction.status == "posted",
               *date_conds_sales)
        .group_by(SalesTransaction.branch_id)
    ).all())

    # 3) Purchases received per branch.
    purchase_rows = _grouped(db.execute(
        select(
            PurchaseTransaction.branch_id,
            func.coalesce(func.sum(PurchaseTransaction.total), 0).label("purchases"),
        )
        .where(PurchaseTransaction.branch_id.in_(ids),
               PurchaseTransaction.status == "received",
               *_date_conds(PurchaseTransaction.created_at, from_, to))
        .group_by(PurchaseTransaction.branch_id)
    ).all())

    # 4) Expenses per branch.
    expense_rows = _grouped(db.execute(
        select(
            ExpenseTransaction.branch_id,
            func.coalesce(func.sum(ExpenseTransaction.amount), 0).label("expenses"),
        )
        .where(ExpenseTransaction.branch_id.in_(ids),
               *_date_conds(ExpenseTransaction.expense_date, from_, to))
        .group_by(ExpenseTransaction.branch_id)
    ).all())

    # 5) Inventory value per branch.
    inv_rows = _grouped(db.execute(
        select(
            InventoryBalance.branch_id,
            func.coalesce(
                func.sum(InventoryBalance.qty_base * InventoryBalance.avg_cost), 0
            ).label("inv_value"),
        )
        .where(InventoryBalance.branch_id.in_(ids))
        .group_by(InventoryBalance.branch_id)
    ).all())

    # 6) Low stock across all scoped branches (one query).
    threshold = Decimal("1800")
    setting = db.get(AppSetting, "low_stock_threshold_butir")
    if setting is not None:
        try:
            threshold = Decimal(str(setting.value))
        except Exception:
            pass
    low_rows = db.execute(
        select(InventoryBalance, Product)
        .join(Product, Product.id == InventoryBalance.product_id)
        .where(InventoryBalance.branch_id.in_(ids),
               InventoryBalance.qty_base < threshold)
        .order_by(InventoryBalance.qty_base)
        .limit(RECENT_PER_BRANCH * n)
    ).all()
    low_by_branch: dict[UUID, list] = {bid: [] for bid in ids}
    for bal, prod in low_rows:
        low_by_branch[bal.branch_id].append({
            "product_id": prod.id, "sku": prod.sku, "name": prod.name,
            "qty_base": bal.qty_base, "threshold": threshold,
        })

    # 7) Recent transactions per branch: 6 models, one query each.
    recent_by_branch: dict[UUID, list] = {bid: [] for bid in ids}
    per_model = RECENT_PER_BRANCH * n
    simple = [
        (SalesTransaction, SalesTransaction.branch_id, "sale", "total"),
        (PurchaseTransaction, PurchaseTransaction.branch_id, "purchase", "total"),
        (ExpenseTransaction, ExpenseTransaction.branch_id, "expense", "amount"),
        (Return, Return.branch_id, "return", "amount"),
        (Stocktake, Stocktake.branch_id, "stocktake", None),
    ]
    for model, col, kind, total_attr in simple:
        for row in db.scalars(
            select(model).where(col.in_(ids))
            .order_by(model.created_at.desc())
            .limit(per_model)
        ):
            entry = {
                "id": row.id, "type": kind, "txn_no": row.txn_no,
                "status": getattr(row, "status", "posted"),
                "created_at": row.created_at, "branch_id": row.branch_id,
            }
            if total_attr:
                entry["total"] = money(getattr(row, total_attr))
            recent_by_branch[row.branch_id].append(entry)
    for row in db.scalars(
        select(Transfer)
        .where((Transfer.branch_id_from.in_(ids)) | (Transfer.branch_id_to.in_(ids)))
        .order_by(Transfer.created_at.desc())
        .limit(per_model)
    ):
        for side in (row.branch_id_from, row.branch_id_to):
            if side in recent_by_branch:
                recent_by_branch[side].append({
                    "id": row.id, "type": "transfer", "txn_no": row.txn_no,
                    "status": getattr(row, "status", "posted"),
                    "created_at": row.created_at, "branch_id": side,
                })
    for bid in recent_by_branch:
        recent_by_branch[bid].sort(key=lambda e: e["created_at"], reverse=True)
        del recent_by_branch[bid][RECENT_PER_BRANCH:]

    # Assemble per-branch payload.
    out_branches = []
    for b in branches:
        bid = b.id
        s = sales_rows.get(bid)
        c = cogs_rows.get(bid)
        p = purchase_rows.get(bid)
        e = expense_rows.get(bid)
        v = inv_rows.get(bid)
        revenue_net = money(s[1] if s else 0)
        cogs = money(c[1] if c else 0)
        cash_in = money(s[2] if s else 0)
        purchases = money(p[1] if p else 0)
        expenses = money(e[1] if e else 0)
        cash_out = money(purchases + expenses)
        inv_value = money(v[1] if v else 0)
        entry = {
            "id": bid, "code": b.code, "name": b.name,
            "sales": revenue_net, "cash_in": cash_in, "cash_out": cash_out,
            "inventory_value": inv_value,
            "low_stock": low_by_branch[bid],
            "recent": recent_by_branch[bid],
        }
        if owner:
            # P&L per cabang: laba kotor = sales - cogs; laba bersih = kotor - beban.
            entry["cogs"] = cogs
            entry["expenses"] = expenses
        out_branches.append(entry)

    return {
        "owner": owner,
        "branches": out_branches,
        "totals": _combined_totals(out_branches, owner),
    }


def _empty_totals(owner: bool) -> dict:
    t = {"sales": 0, "cash_in": 0, "cash_out": 0, "inventory_value": 0}
    if owner:
        t.update({"cogs": 0, "net_profit": 0, "margin_pct": None})
    return t


def _combined_totals(out_branches: list[dict], owner: bool) -> dict:
    t = {"sales": Decimal("0"), "cash_in": Decimal("0"),
         "cash_out": Decimal("0"), "inventory_value": Decimal("0")}
    cogs = Decimal("0")
    expenses = Decimal("0")
    for b in out_branches:
        t["sales"] += Decimal(str(b["sales"]))
        t["cash_in"] += Decimal(str(b["cash_in"]))
        t["cash_out"] += Decimal(str(b["cash_out"]))
        t["inventory_value"] += Decimal(str(b["inventory_value"]))
        if owner:
            cogs += Decimal(str(b.get("cogs", 0)))
            expenses += Decimal(str(b.get("expenses", 0)))
    out = {k: money(v) for k, v in t.items()}
    if owner:
        # Sama dengan profit_loss_report lama: net = sales - cogs - beban.
        out["cogs"] = money(cogs)
        net = money(out["sales"] - cogs - expenses)
        out["net_profit"] = net
        out["margin_pct"] = (
            float((net / out["sales"] * 100).quantize(Decimal("0.01")))
            if out["sales"] != 0 else None
        )
    return out
