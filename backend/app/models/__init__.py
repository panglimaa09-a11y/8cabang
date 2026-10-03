"""SQLAlchemy models mirroring supabase/migrations/001_initial.sql."""
import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index,
    Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import CHAR, TypeDecorator


class GUID(TypeDecorator):
    """UUID that works on PostgreSQL (native) and SQLite (CHAR(32)) for tests."""
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        if isinstance(value, uuid.UUID):
            return value.hex
        return uuid.UUID(str(value)).hex

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class Base(DeclarativeBase):
    pass


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(GUID(), primary_key=True, default=uuid.uuid4)


def _ts() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False,
                         server_default=func.now())


class Branch(Base):
    __tablename__ = "branches"
    id: Mapped[uuid.UUID] = _pk()
    code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = _ts()


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[uuid.UUID] = _pk()
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # owner|admin|karyawan
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = _ts()


class BranchMembership(Base):
    __tablename__ = "branch_memberships"
    id: Mapped[uuid.UUID] = _pk()
    profile_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role: Mapped[str] = mapped_column(String(16), primary_key=True)
    permission_key: Mapped[str] = mapped_column(String(40), primary_key=True)


class UserPermission(Base):
    __tablename__ = "user_permissions"
    profile_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    permission_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("profiles.id"))
    granted_at: Mapped[datetime] = _ts()


class Product(Base):
    __tablename__ = "products"
    id: Mapped[uuid.UUID] = _pk()
    sku: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    base_unit: Mapped[str] = mapped_column(Text, nullable=False, default="butir")
    units: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = _ts()


class InventoryBalance(Base):
    __tablename__ = "inventory_balances"
    branch_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("branches.id", ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("products.id"), primary_key=True)
    qty_base: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False, default=0)
    avg_cost: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now())


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    id: Mapped[uuid.UUID] = _pk()
    branch_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("products.id"), nullable=False)
    txn_type: Mapped[str] = mapped_column(String(32), nullable=False)
    txn_ref: Mapped[str] = mapped_column(Text, nullable=False)
    qty_base: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)
    qty_before: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)
    qty_after: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)
    unit_cost: Mapped[float | None] = mapped_column(Numeric(20, 4))
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("profiles.id"))
    created_at: Mapped[datetime] = _ts()


class PurchaseTransaction(Base):
    __tablename__ = "purchase_transactions"
    id: Mapped[uuid.UUID] = _pk()
    branch_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    txn_no: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    supplier: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    subtotal: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    freight_cost: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    total: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    idempotency_key: Mapped[str | None] = mapped_column(Text, unique=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("profiles.id"))
    created_at: Mapped[datetime] = _ts()


class PurchaseItem(Base):
    __tablename__ = "purchase_items"
    id: Mapped[uuid.UUID] = _pk()
    purchase_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("purchase_transactions.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("products.id"), nullable=False)
    qty_base: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False)
    line_total: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False)


class SalesTransaction(Base):
    __tablename__ = "sales_transactions"
    id: Mapped[uuid.UUID] = _pk()
    branch_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    txn_no: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    customer: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="posted")
    subtotal: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    discount: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    total: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    idempotency_key: Mapped[str | None] = mapped_column(Text, unique=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("profiles.id"))
    created_at: Mapped[datetime] = _ts()


class SalesItem(Base):
    __tablename__ = "sales_items"
    id: Mapped[uuid.UUID] = _pk()
    sale_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("sales_transactions.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("products.id"), nullable=False)
    qty_base: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False)
    line_total: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False)
    cogs: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False, default=0)


class ExpenseTransaction(Base):
    __tablename__ = "expense_transactions"
    id: Mapped[uuid.UUID] = _pk()
    branch_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    txn_no: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(Text, unique=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("profiles.id"))
    created_at: Mapped[datetime] = _ts()


class Return(Base):
    __tablename__ = "returns"
    id: Mapped[uuid.UUID] = _pk()
    branch_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    txn_no: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    return_type: Mapped[str] = mapped_column(String(16), nullable=False)
    ref_txn_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    product_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("products.id"), nullable=False)
    qty_base: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="posted")
    idempotency_key: Mapped[str | None] = mapped_column(Text, unique=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("profiles.id"))
    created_at: Mapped[datetime] = _ts()


class Stocktake(Base):
    __tablename__ = "stocktakes"
    id: Mapped[uuid.UUID] = _pk()
    branch_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    txn_no: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("products.id"), nullable=False)
    counted_qty_base: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)
    system_qty_base: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)
    variance: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("profiles.id"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("profiles.id"))
    created_at: Mapped[datetime] = _ts()


class Transfer(Base):
    __tablename__ = "transfers"
    id: Mapped[uuid.UUID] = _pk()
    branch_id_from: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    branch_id_to: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    txn_no: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("products.id"), nullable=False)
    qty_base: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="in_transit")
    idempotency_key: Mapped[str | None] = mapped_column(Text, unique=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("profiles.id"))
    received_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("profiles.id"))
    created_at: Mapped[datetime] = _ts()


class AccountingEntry(Base):
    __tablename__ = "accounting_entries"
    id: Mapped[uuid.UUID] = _pk()
    branch_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    account: Mapped[str] = mapped_column(Text, nullable=False)
    debit: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    credit: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    ref_type: Mapped[str | None] = mapped_column(Text)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = _pk()
    actor_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("profiles.id"))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("branches.id"))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    before_data: Mapped[dict | None] = mapped_column(JSON)
    after_data: Mapped[dict | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("profiles.id"))
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[dict] = mapped_column(JSON, nullable=False)
    status_code: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = _ts()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now())


Index("idx_profiles_role", Profile.role)
Index("idx_memberships_profile", BranchMembership.profile_id)
Index("idx_memberships_branch", BranchMembership.branch_id)
Index("idx_movements_branch_product", InventoryMovement.branch_id,
      InventoryMovement.product_id, InventoryMovement.created_at.desc())
Index("idx_movements_txn_ref", InventoryMovement.txn_ref)
