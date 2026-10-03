"""Accounting service — journal entries and financial reports.

All money math uses Decimal (NUMERIC in the DB). Reports are computed from
the database only — never static numbers (CONTRACT.md section 5).
"""
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select

from ..models import (
    AccountingEntry, ExpenseTransaction, InventoryBalance,
    PurchaseTransaction, SalesItem, SalesTransaction,
)
from .costing import money


def post_journal(session, *, branch_id: UUID, entry_date: date,
                 lines: list[tuple[str, Decimal, Decimal]],
                 ref_type: str | None = None, ref_id: UUID | None = None,
                 description: str | None = None) -> None:
    """Append balanced journal lines. Each line: (account, debit, credit)."""
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    for account, debit, credit in lines:
        d, c = money(debit), money(credit)
        if d <= 0 and c <= 0:
            raise ValueError("Journal line must have a debit or credit")
        total_debit += d
        total_credit += c
        session.add(AccountingEntry(
            branch_id=branch_id, entry_date=entry_date, account=account,
            debit=d, credit=c, ref_type=ref_type, ref_id=ref_id,
            description=description))
    if total_debit != total_credit:
        raise ValueError(f"Unbalanced journal: debit {total_debit} != credit {total_credit}")
    session.flush()


def _branch_filter(query_branch_ids, model_branch_col):
    return model_branch_col.in_(query_branch_ids)


def _sum(session, model, column, branch_ids, date_col=None, date_from=None, date_to=None,
         extra=None):
    stmt = select(func.coalesce(func.sum(column), 0)).where(_branch_filter(branch_ids, model.branch_id))
    if extra is not None:
        stmt = stmt.where(*extra) if isinstance(extra, (list, tuple)) else stmt.where(extra)
    if date_col is not None:
        if date_from:
            stmt = stmt.where(date_col >= date_from)
        if date_to:
            stmt = stmt.where(date_col <= date_to)
    return Decimal(str(session.scalar(stmt) or 0))


def sales_totals(session, branch_ids, date_from=None, date_to=None) -> dict:
    """Posted sales: revenue_net (subtotal - discount), cogs, count."""
    filters = [SalesTransaction.status == "posted"]
    revenue = _sum(session, SalesTransaction, SalesTransaction.subtotal, branch_ids,
                   SalesTransaction.created_at, date_from, date_to, filters)
    discount = _sum(session, SalesTransaction, SalesTransaction.discount, branch_ids,
                    SalesTransaction.created_at, date_from, date_to, filters)
    cogs = Decimal(str(session.scalar(
        select(func.coalesce(func.sum(SalesItem.cogs), 0))
        .join(SalesTransaction, SalesItem.sale_id == SalesTransaction.id)
        .where(SalesTransaction.branch_id.in_(branch_ids),
               SalesTransaction.status == "posted",
               *([SalesTransaction.created_at >= date_from] if date_from else []),
               *([SalesTransaction.created_at <= date_to] if date_to else []))
    ) or 0))
    revenue_net = money(revenue - discount)
    return {"revenue_net": revenue_net, "cogs": money(cogs)}


def expense_total(session, branch_ids, date_from=None, date_to=None) -> Decimal:
    return money(_sum(session, ExpenseTransaction, ExpenseTransaction.amount, branch_ids,
                      ExpenseTransaction.expense_date, date_from, date_to))


def purchase_received_total(session, branch_ids, date_from=None, date_to=None) -> Decimal:
    return money(_sum(
        session, PurchaseTransaction, PurchaseTransaction.total, branch_ids,
        PurchaseTransaction.created_at, date_from, date_to,
        [PurchaseTransaction.status == "received"]))


def inventory_value(session, branch_ids) -> Decimal:
    total = session.scalar(
        select(func.coalesce(
            func.sum(InventoryBalance.qty_base * InventoryBalance.avg_cost), 0))
        .where(InventoryBalance.branch_id.in_(branch_ids))) or 0
    return money(total)


def cash_report(session, branch_ids, date_from=None, date_to=None) -> dict:
    """Cash flow: cash_in - cash_out. This is cash movement, NOT profit."""
    cash_in = money(_sum(session, SalesTransaction, SalesTransaction.total, branch_ids,
                         SalesTransaction.created_at, date_from, date_to,
                         [SalesTransaction.status == "posted"]))
    cash_out = money(purchase_received_total(session, branch_ids, date_from, date_to)
                     + expense_total(session, branch_ids, date_from, date_to))
    return {"cash_in": cash_in, "cash_out": cash_out, "net": money(cash_in - cash_out)}


def profit_loss_report(session, branch_ids, date_from=None, date_to=None) -> dict:
    """P&L: gross = revenue_net - cogs; operating = gross - opex."""
    s = sales_totals(session, branch_ids, date_from, date_to)
    opex = expense_total(session, branch_ids, date_from, date_to)
    gross = money(s["revenue_net"] - s["cogs"])
    net = money(gross - opex)
    return {
        "revenue_net": s["revenue_net"],
        "cogs": s["cogs"],
        "gross_profit": gross,
        "opex": opex,
        "other_income": money(0),
        "net_profit": net,
    }


def margin_report(session, branch_ids, date_from=None, date_to=None) -> dict:
    """Net margin from COMBINED totals (never the average of per-branch %)."""
    pl = profit_loss_report(session, branch_ids, date_from, date_to)
    revenue = pl["revenue_net"]
    margin_pct = None
    if revenue != 0:
        margin_pct = (pl["net_profit"] / revenue * 100).quantize(Decimal("0.01"))
    return {
        "net_profit": pl["net_profit"],
        "revenue_net": revenue,
        "margin_pct": float(margin_pct) if margin_pct is not None else None,
    }
