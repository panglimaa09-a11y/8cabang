"""Costing tests — moving weighted average, PRD V2 section 8 example.

PRD example (unit-agnostic, here in peti):
  stock: 100 peti @ Rp10.000.000  +  purchase: 50 peti @ Rp5.500.000
  -> avg cost Rp103.333,33/peti; sell 40 peti -> COGS +/-Rp4.133.333,33
"""
from decimal import Decimal

from app.services.costing import (
    cogs_for_sale, money, new_avg_cost, qty, restore_unit_value, to_base_qty,
)


def test_prd_section8_example():
    avg = new_avg_cost(100, 10_000_000, 50, 5_500_000)
    # avg per peti rounded to 2 decimals for money display
    assert money(avg) == Decimal("103333.33")
    cogs = cogs_for_sale(40, avg)
    assert abs(cogs - Decimal("4133333.33")) <= Decimal("0.02")


def test_avg_cost_zero_qty_returns_zero():
    assert new_avg_cost(0, 0, 0, 0) == Decimal("0")


def test_first_purchase_sets_avg():
    avg = new_avg_cost(0, 0, 180, 1_800_000)  # 1 peti = 180 butir
    assert avg == Decimal("10000.0000")


def test_historical_cogs_does_not_change():
    """A later purchase at a different price must not rewrite old COGS."""
    avg1 = new_avg_cost(100, 10_000_000, 50, 5_500_000)
    cogs_before = cogs_for_sale(40, avg1)
    # New purchase at a much higher price changes the average...
    avg2 = new_avg_cost(150, 15_500_000, 10, 2_000_000)
    assert avg2 != avg1
    # ...but the already-stored COGS value is untouched.
    assert cogs_for_sale(40, avg1) == cogs_before


def test_money_rounding_half_up():
    assert money("2.345") == Decimal("2.35")
    assert money("2.335") == Decimal("2.34")
    assert money("103333.335") == Decimal("103333.34")


def test_qty_four_decimals():
    assert qty("1.23456") == Decimal("1.2346")


def test_to_base_qty_unit_conversion():
    # 2 peti @ 180 butir/peti
    assert to_base_qty(2, 180) == Decimal("360.0000")
    assert to_base_qty(1, 30) == Decimal("30.0000")


def test_restore_unit_value_sales_return():
    # Original line: 180 butir sold, COGS Rp103333.33 -> per-butir restore value
    unit = restore_unit_value(Decimal("103333.33"), 180)
    assert unit == (Decimal("103333.33") / Decimal("180")).quantize(Decimal("0.0001"))
    assert restore_unit_value(0, 0) == Decimal("0")
