"""Pesan stok-kurang yang ramah (sales API).

Aturan: pesan untuk user harus Bahasa Indonesia, menyebut nama produk dan
jumlah dengan format Indonesia, dan TIDAK boleh memuat UUID teknis.
"""
from decimal import Decimal

from app.api.sales import _fmt_qty_id, _friendly_stock_error


def test_fmt_qty_id():
    assert _fmt_qty_id(8000) == "8.000"
    assert _fmt_qty_id(1500.5) == "1.500,5"
    assert _fmt_qty_id(0) == "0"


def test_friendly_stock_error_tanpa_uuid(db, seed):
    c1 = seed["branches"]["C1"]
    prod = seed["products"]["TL-AYAM-KAMPUNG"]
    msg = _friendly_stock_error(db, c1.id, prod.id, Decimal("8000"))
    assert "Telur Ayam Kampung" in msg
    assert "8.000" in msg
    assert "tidak mencukupi" in msg
    assert str(prod.id) not in msg
    assert str(c1.id) not in msg
