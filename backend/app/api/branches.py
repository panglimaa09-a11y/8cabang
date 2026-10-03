"""Branch endpoints: list, summary, inventory, unified transactions, products."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    AppSetting, Branch, ExpenseTransaction, InventoryBalance, InventoryMovement, Product,
    Profile, PurchaseTransaction, Return, SalesItem, SalesTransaction, Stocktake, Transfer,
)
from ..security.auth import get_current_user, get_db, require_branch_access
from ..services import accounting as acct
from ..services.costing import money
from ..services.permissions import branch_scope_ids, may_view_cost

router = APIRouter(prefix="/api", tags=["branches"])


def _branch_or_404(db: Session, branch_id: UUID) -> Branch:
    branch = db.get(Branch, branch_id)
    if branch is None or not branch.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
    return branch


@router.get("/branches")
def list_branches(user: Profile = Depends(get_current_user), db: Session = Depends(get_db)):
    ids = branch_scope_ids(user, db)
    branches = db.scalars(
        select(Branch).where(Branch.id.in_(ids)).order_by(Branch.code)).all()
    return [{"id": b.id, "code": b.code, "name": b.name,
             "address": b.address, "phone": b.phone} for b in branches]


@router.get("/branches/{branch_id}/summary")
def branch_summary(branch_id: UUID, user: Profile = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    require_branch_access(branch_id, user, db)
    branch = _branch_or_404(db, branch_id)
    ids = [branch_id]

    sales = acct.sales_totals(db, ids)
    cash = acct.cash_report(db, ids)
    inv_value = acct.inventory_value(db, ids)

    # Low stock: balances below the configured threshold (base units).
    threshold = Decimal("1800")
    setting = db.get(AppSetting, "low_stock_threshold_butir")
    if setting is not None:
        try:
            threshold = Decimal(str(setting.value))
        except Exception:
            pass
    low_stock = _low_stock(db, branch_id, threshold)
    recent = _recent_transactions(db, branch_id, limit=10,
                                  show_cost=may_view_cost(user, db))
    return {
        "branch": {"id": branch.id, "code": branch.code, "name": branch.name},
        "totals": {
            "sales": sales["revenue_net"],
            "cash_in": cash["cash_in"],
            "cash_out": cash["cash_out"],
            "inventory_value": inv_value,
        },
        "low_stock": low_stock,
        "recent": recent,
    }


def _low_stock(db: Session, branch_id: UUID, threshold: Decimal) -> list[dict]:
    rows = db.execute(
        select(InventoryBalance, Product)
        .join(Product, Product.id == InventoryBalance.product_id)
        .where(InventoryBalance.branch_id == branch_id,
               InventoryBalance.qty_base < threshold)
        .order_by(InventoryBalance.qty_base)).all()
    return [{"product_id": p.id, "sku": p.sku, "name": p.name,
             "qty_base": b.qty_base, "threshold": threshold}
            for b, p in rows]


def _recent_transactions(db: Session, branch_id: UUID, limit: int,
                         show_cost: bool) -> list[dict]:
    items: list[dict] = []
    for model, kind, no_attr, total_attr in [
        (SalesTransaction, "sale", "txn_no", "total"),
        (PurchaseTransaction, "purchase", "txn_no", "total"),
        (ExpenseTransaction, "expense", "txn_no", "amount"),
        (Return, "return", "txn_no", "amount"),
        (Stocktake, "stocktake", "txn_no", None),
        (Transfer, "transfer", "txn_no", None),
    ]:
        if kind == "transfer":
            stmt = (select(model).where(
                (model.branch_id_from == branch_id) | (model.branch_id_to == branch_id))
                .order_by(model.created_at.desc()).limit(limit))
        else:
            stmt = (select(model).where(model.branch_id == branch_id)
                    .order_by(model.created_at.desc()).limit(limit))
        for row in db.scalars(stmt):
            entry = {"id": row.id, "type": kind, "txn_no": getattr(row, no_attr),
                     "status": getattr(row, "status", "posted"),
                     "created_at": row.created_at}
            if total_attr:
                entry["total"] = money(getattr(row, total_attr))
            items.append(entry)
    items.sort(key=lambda e: e["created_at"], reverse=True)
    return items[:limit]


@router.get("/branches/{branch_id}/inventory")
def branch_inventory(branch_id: UUID, user: Profile = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    """Per-product stock. avg_cost is included ONLY for cost-permitted users."""
    require_branch_access(branch_id, user, db)
    _branch_or_404(db, branch_id)
    show_cost = may_view_cost(user, db)
    rows = db.execute(
        select(Product, InventoryBalance)
        .outerjoin(InventoryBalance,
                   (InventoryBalance.product_id == Product.id)
                   & (InventoryBalance.branch_id == branch_id))
        .where(Product.is_active.is_(True))
        .order_by(Product.sku)).all()
    out = []
    for product, bal in rows:
        qty_base = Decimal(str(bal.qty_base)) if bal else Decimal("0")
        units_display = {}
        for unit, factor in (product.units or {}).items():
            f = Decimal(str(factor))
            units_display[unit] = float(qty_base / f) if f else 0.0
        entry = {"product_id": product.id, "sku": product.sku, "name": product.name,
                 "base_unit": product.base_unit, "units": units_display,
                 "qty_base": qty_base}
        if show_cost:
            entry["avg_cost"] = Decimal(str(bal.avg_cost)) if bal else Decimal("0")
            entry["stock_value"] = money(qty_base * entry["avg_cost"])
        out.append(entry)
    return out


@router.get("/branches/{branch_id}/transactions")
def branch_transactions(
    branch_id: UUID,
    type: str | None = Query(default=None, pattern="^(sale|purchase|expense|return|stocktake|transfer)$"),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None, alias="to"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    user: Profile = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_branch_access(branch_id, user, db)
    _branch_or_404(db, branch_id)
    show_cost = may_view_cost(user, db)

    kinds = [type] if type else ["sale", "purchase", "expense", "return", "stocktake", "transfer"]
    items: list[dict] = []
    for kind in kinds:
        items.extend(_transactions_of_kind(db, branch_id, kind, from_, to, show_cost))
    items.sort(key=lambda e: e["created_at"], reverse=True)
    total = len(items)
    start = (page - 1) * limit
    return {"items": items[start:start + limit], "page": page, "limit": limit, "total": total}


def _date_filter(model, from_, to_):
    conds = []
    if from_:
        conds.append(model.created_at >= from_)
    if to_:
        conds.append(model.created_at <= to_)
    return conds


def _transactions_of_kind(db, branch_id, kind, from_, to_, show_cost) -> list[dict]:
    out: list[dict] = []
    if kind == "sale":
        rows = db.scalars(select(SalesTransaction).where(
            SalesTransaction.branch_id == branch_id, *_date_filter(SalesTransaction, from_, to_)))
        for r in rows:
            e = {"id": r.id, "type": "sale", "txn_no": r.txn_no, "customer": r.customer,
                 "subtotal": money(r.subtotal), "discount": money(r.discount),
                 "total": money(r.total), "status": r.status,
                 "created_by": r.created_by, "created_at": r.created_at}
            if show_cost:
                e["cogs"] = money(db.scalar(
                    select(func.coalesce(func.sum(SalesItem.cogs), 0))
                    .where(SalesItem.sale_id == r.id)) or 0)
            out.append(e)
    elif kind == "purchase":
        rows = db.scalars(select(PurchaseTransaction).where(
            PurchaseTransaction.branch_id == branch_id, *_date_filter(PurchaseTransaction, from_, to_)))
        for r in rows:
            out.append({"id": r.id, "type": "purchase", "txn_no": r.txn_no,
                        "supplier": r.supplier, "subtotal": money(r.subtotal),
                        "freight_cost": money(r.freight_cost), "total": money(r.total),
                        "status": r.status, "created_by": r.created_by, "created_at": r.created_at})
    elif kind == "expense":
        rows = db.scalars(select(ExpenseTransaction).where(
            ExpenseTransaction.branch_id == branch_id, *_date_filter(ExpenseTransaction, from_, to_)))
        for r in rows:
            out.append({"id": r.id, "type": "expense", "txn_no": r.txn_no,
                        "category": r.category, "description": r.description,
                        "amount": money(r.amount), "expense_date": r.expense_date,
                        "created_by": r.created_by, "created_at": r.created_at})
    elif kind == "return":
        rows = db.scalars(select(Return).where(
            Return.branch_id == branch_id, *_date_filter(Return, from_, to_)))
        for r in rows:
            out.append({"id": r.id, "type": "return", "txn_no": r.txn_no,
                        "return_type": r.return_type, "ref_txn_id": r.ref_txn_id,
                        "amount": money(r.amount), "status": r.status,
                        "created_by": r.created_by, "created_at": r.created_at})
    elif kind == "stocktake":
        rows = db.scalars(select(Stocktake).where(
            Stocktake.branch_id == branch_id, *_date_filter(Stocktake, from_, to_)))
        for r in rows:
            out.append({"id": r.id, "type": "stocktake", "txn_no": r.txn_no,
                        "variance": Decimal(str(r.variance)), "status": r.status,
                        "created_by": r.created_by, "created_at": r.created_at})
    elif kind == "transfer":
        rows = db.scalars(select(Transfer).where(
            ((Transfer.branch_id_from == branch_id) | (Transfer.branch_id_to == branch_id)),
            *_date_filter(Transfer, from_, to_)))
        for r in rows:
            out.append({"id": r.id, "type": "transfer", "txn_no": r.txn_no,
                        "branch_id_from": r.branch_id_from, "branch_id_to": r.branch_id_to,
                        "qty_base": Decimal(str(r.qty_base)), "status": r.status,
                        "created_by": r.created_by, "created_at": r.created_at})
    return out


@router.get("/products")
def list_products(user: Profile = Depends(get_current_user), db: Session = Depends(get_db)):
    products = db.scalars(select(Product).where(Product.is_active.is_(True))
                          .order_by(Product.sku)).all()
    return [{"id": p.id, "sku": p.sku, "name": p.name,
             "base_unit": p.base_unit, "units": p.units} for p in products]
