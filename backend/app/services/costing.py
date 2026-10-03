"""Costing service — moving weighted average (PRD V2 section 8).

Pure Decimal math, no database access, so it is trivially unit-testable.

Rounding rules (CONTRACT.md section 5):
  - money: ROUND_HALF_UP to 2 decimals
  - qty_base: up to 4 decimals
  - avg_cost per unit: kept at 4 decimals; money display rounds to 2
"""
from decimal import Decimal, ROUND_HALF_UP

MONEY_PLACES = Decimal("0.01")
QTY_PLACES = Decimal("0.0001")
AVG_COST_PLACES = Decimal("0.0001")


def money(value) -> Decimal:
    """Round to 2 decimals, HALF_UP. Accepts Decimal/int/float/str."""
    return Decimal(str(value)).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def qty(value) -> Decimal:
    """Round to 4 decimals, HALF_UP."""
    return Decimal(str(value)).quantize(QTY_PLACES, rounding=ROUND_HALF_UP)


def new_avg_cost(qty_before, value_before, qty_in, value_in) -> Decimal:
    """Moving weighted average after an inbound purchase.

    avg = (value_before + value_in) / (qty_before + qty_in)

    value_in INCLUDES freight allocated to this product (per CONTRACT.md section 4).
    Returns avg cost per base unit rounded to 4 decimals.
    """
    qb = Decimal(str(qty_before))
    vb = Decimal(str(value_before))
    qi = Decimal(str(qty_in))
    vi = Decimal(str(value_in))
    total_qty = qb + qi
    if total_qty <= 0:
        return Decimal("0")
    return ((vb + vi) / total_qty).quantize(AVG_COST_PLACES, rounding=ROUND_HALF_UP)


def cogs_for_sale(qty_sold_base, avg_cost) -> Decimal:
    """Historical COGS for a sale line: qty x avg cost at posting time.

    This value is STORED on the sales item and never recalculated,
    so later purchase-price changes cannot silently rewrite history.
    """
    result = Decimal(str(qty_sold_base)) * Decimal(str(avg_cost))
    return result.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def to_base_qty(qty_in_unit, unit_factor) -> Decimal:
    """Convert a quantity expressed in a display unit to base units."""
    return qty(Decimal(str(qty_in_unit)) * Decimal(str(unit_factor)))


def restore_unit_value(cogs_total, qty_base) -> Decimal:
    """Unit value to restore on a sales return (original COGS / qty), 4dp."""
    q = Decimal(str(qty_base))
    if q <= 0:
        return Decimal("0")
    return (Decimal(str(cogs_total)) / q).quantize(AVG_COST_PLACES, rounding=ROUND_HALF_UP)
