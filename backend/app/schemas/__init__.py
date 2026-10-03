"""Pydantic v2 request/response schemas."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


# ── auth ──────────────────────────────────────────────────────────
class LoginIn(BaseModel):
    email: str
    password: str


class ProfileOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str

    model_config = {"from_attributes": True}


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    profile: ProfileOut


class MeOut(BaseModel):
    profile: ProfileOut
    permissions: list[str]
    branch_ids: list[UUID]


# ── users ─────────────────────────────────────────────────────────
class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=6)
    full_name: str
    role: str = Field(pattern="^(owner|admin|karyawan)$")
    branch_ids: list[UUID] = []


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = Field(default=None, pattern="^(owner|admin|karyawan)$")
    is_active: bool | None = None
    branch_ids: list[UUID] | None = None


class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    branch_ids: list[UUID] = []

    model_config = {"from_attributes": True}


class PermissionGrant(BaseModel):
    profile_id: UUID
    permission_key: str


# ── transactions ──────────────────────────────────────────────────
class TxnItemIn(BaseModel):
    product_id: UUID
    qty: Decimal = Field(gt=0)
    unit: str
    unit_price: Decimal = Field(ge=0)
    idempotency_key: str | None = None


class PurchaseCreate(BaseModel):
    branch_id: UUID
    supplier: str | None = None
    freight_cost: Decimal = Field(default=Decimal("0"), ge=0)
    items: list[TxnItemIn] = Field(min_length=1)
    idempotency_key: str | None = None


class SaleCreate(BaseModel):
    branch_id: UUID
    customer: str | None = None
    discount: Decimal = Field(default=Decimal("0"), ge=0)
    items: list[TxnItemIn] = Field(min_length=1)
    allow_negative: bool = False
    idempotency_key: str | None = None


class ExpenseCreate(BaseModel):
    branch_id: UUID
    category: str
    description: str | None = None
    amount: Decimal = Field(gt=0)
    expense_date: date
    idempotency_key: str | None = None


class ReturnCreate(BaseModel):
    branch_id: UUID
    return_type: str = Field(pattern="^(sales_return|purchase_return)$")
    ref_txn_id: UUID | None = None
    product_id: UUID
    qty: Decimal = Field(gt=0)
    unit: str
    reason: str | None = None
    idempotency_key: str | None = None


class StocktakeCreate(BaseModel):
    branch_id: UUID
    product_id: UUID
    counted_qty: Decimal = Field(ge=0)
    unit: str
    idempotency_key: str | None = None


class TransferCreate(BaseModel):
    branch_id_from: UUID
    branch_id_to: UUID
    product_id: UUID
    qty: Decimal = Field(gt=0)
    unit: str
    idempotency_key: str | None = None


class ReverseIn(BaseModel):
    reason: str = Field(min_length=3)
    idempotency_key: str | None = None


class TxnOut(BaseModel):
    id: UUID
    txn_no: str
    status: str
    total: Decimal | None = None


class StocktakeOut(BaseModel):
    id: UUID
    txn_no: str
    status: str
    counted_qty_base: Decimal
    system_qty_base: Decimal
    variance: Decimal


# ── generic paged ─────────────────────────────────────────────────
class PagedOut(BaseModel):
    items: list[dict]
    page: int
    limit: int
    total: int
