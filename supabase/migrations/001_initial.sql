-- 001_initial.sql — Initial schema: Sistem Manajemen Penjualan Telur 8 Cabang (PRD V2)
-- PostgreSQL / Supabase. UUID PKs, NUMERIC money, TIMESTAMPTZ timestamps.
-- Run order: 001_initial.sql -> 002_rls.sql -> 003_seed.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 1. branches
CREATE TABLE branches (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code        TEXT NOT NULL UNIQUE CHECK (code IN ('C1','C2','C3','C4','C5','C6','C7','C8')),
    name        TEXT NOT NULL,
    address     TEXT,
    phone       TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. profiles (application users; id matches Supabase auth.users.id when used)
CREATE TABLE profiles (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT NOT NULL UNIQUE,
    full_name     TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('owner','admin','karyawan')),
    password_hash TEXT NOT NULL,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_profiles_role ON profiles(role);

-- 3. branch_memberships
CREATE TABLE branch_memberships (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    branch_id  UUID NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    UNIQUE (profile_id, branch_id)
);
CREATE INDEX idx_memberships_profile ON branch_memberships(profile_id);
CREATE INDEX idx_memberships_branch  ON branch_memberships(branch_id);

-- 4. role_permissions
CREATE TABLE role_permissions (
    role           TEXT NOT NULL CHECK (role IN ('owner','admin','karyawan')),
    permission_key TEXT NOT NULL CHECK (permission_key IN (
        'reports.view_profit','reports.view_margin','inventory.view_cost',
        'transactions.correct','users.manage','audit.view',
        'branches.manage','settings.manage')),
    PRIMARY KEY (role, permission_key)
);

-- 5. user_permissions (per-user overrides granted by owner)
CREATE TABLE user_permissions (
    profile_id     UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    permission_key TEXT NOT NULL CHECK (permission_key IN (
        'reports.view_profit','reports.view_margin','inventory.view_cost',
        'transactions.correct','users.manage','audit.view',
        'branches.manage','settings.manage')),
    granted_by     UUID REFERENCES profiles(id),
    granted_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (profile_id, permission_key)
);

-- 6. products
CREATE TABLE products (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sku        TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL,
    base_unit  TEXT NOT NULL DEFAULT 'butir',
    units      JSONB NOT NULL DEFAULT '{"butir": 1}'::jsonb,
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 7. inventory_balances
CREATE TABLE inventory_balances (
    branch_id  UUID NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id),
    qty_base   NUMERIC(20,4) NOT NULL DEFAULT 0,
    avg_cost   NUMERIC(20,4) NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (branch_id, product_id)
);
CREATE INDEX idx_balances_branch ON inventory_balances(branch_id);

-- 8. inventory_movements
CREATE TABLE inventory_movements (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id  UUID NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id),
    txn_type   TEXT NOT NULL CHECK (txn_type IN (
        'purchase_receive','sale','damage','sales_return','purchase_return',
        'transfer_out','transfer_in','stocktake_adjust')),
    txn_ref    TEXT NOT NULL,
    qty_base   NUMERIC(20,4) NOT NULL,
    qty_before NUMERIC(20,4) NOT NULL,
    qty_after  NUMERIC(20,4) NOT NULL,
    unit_cost  NUMERIC(20,4),
    created_by UUID REFERENCES profiles(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_movements_branch_product ON inventory_movements(branch_id, product_id, created_at DESC);
CREATE INDEX idx_movements_txn_ref ON inventory_movements(txn_ref);

-- 9. purchase_transactions
CREATE TABLE purchase_transactions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id       UUID NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    txn_no          TEXT NOT NULL UNIQUE,
    supplier        TEXT,
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft','received','cancelled')),
    subtotal        NUMERIC(20,2) NOT NULL DEFAULT 0,
    freight_cost    NUMERIC(20,2) NOT NULL DEFAULT 0,
    total           NUMERIC(20,2) NOT NULL DEFAULT 0,
    idempotency_key TEXT UNIQUE,
    received_at     TIMESTAMPTZ,
    created_by      UUID REFERENCES profiles(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_purchases_branch_created ON purchase_transactions(branch_id, created_at DESC);
CREATE INDEX idx_purchases_status ON purchase_transactions(status);

-- 10. purchase_items
CREATE TABLE purchase_items (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    purchase_id UUID NOT NULL REFERENCES purchase_transactions(id) ON DELETE CASCADE,
    product_id  UUID NOT NULL REFERENCES products(id),
    qty_base    NUMERIC(20,4) NOT NULL CHECK (qty_base > 0),
    unit        TEXT NOT NULL,
    unit_price  NUMERIC(20,2) NOT NULL CHECK (unit_price >= 0),
    line_total  NUMERIC(20,2) NOT NULL CHECK (line_total >= 0)
);
CREATE INDEX idx_purchase_items_purchase ON purchase_items(purchase_id);

-- 11. sales_transactions
CREATE TABLE sales_transactions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id       UUID NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    txn_no          TEXT NOT NULL UNIQUE,
    customer        TEXT,
    status          TEXT NOT NULL DEFAULT 'posted'
                    CHECK (status IN ('posted','voided')),
    subtotal        NUMERIC(20,2) NOT NULL DEFAULT 0,
    discount        NUMERIC(20,2) NOT NULL DEFAULT 0 CHECK (discount >= 0),
    total           NUMERIC(20,2) NOT NULL DEFAULT 0,
    idempotency_key TEXT UNIQUE,
    created_by      UUID REFERENCES profiles(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_sales_branch_created ON sales_transactions(branch_id, created_at DESC);
CREATE INDEX idx_sales_status ON sales_transactions(status);

-- 12. sales_items
CREATE TABLE sales_items (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sale_id     UUID NOT NULL REFERENCES sales_transactions(id) ON DELETE CASCADE,
    product_id  UUID NOT NULL REFERENCES products(id),
    qty_base    NUMERIC(20,4) NOT NULL CHECK (qty_base > 0),
    unit        TEXT NOT NULL,
    unit_price  NUMERIC(20,2) NOT NULL CHECK (unit_price >= 0),
    line_total  NUMERIC(20,2) NOT NULL CHECK (line_total >= 0),
    cogs        NUMERIC(20,2) NOT NULL DEFAULT 0 CHECK (cogs >= 0)
);
CREATE INDEX idx_sales_items_sale ON sales_items(sale_id);

-- 13. expense_transactions
CREATE TABLE expense_transactions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id       UUID NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    txn_no          TEXT NOT NULL UNIQUE,
    category        TEXT NOT NULL,
    description     TEXT,
    amount          NUMERIC(20,2) NOT NULL CHECK (amount > 0),
    expense_date    DATE NOT NULL,
    idempotency_key TEXT UNIQUE,
    created_by      UUID REFERENCES profiles(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_expenses_branch_date ON expense_transactions(branch_id, expense_date DESC);

-- 14. returns
CREATE TABLE returns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id       UUID NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    txn_no          TEXT NOT NULL UNIQUE,
    return_type     TEXT NOT NULL CHECK (return_type IN ('sales_return','purchase_return')),
    ref_txn_id      UUID,
    product_id      UUID NOT NULL REFERENCES products(id),
    qty_base        NUMERIC(20,4) NOT NULL CHECK (qty_base > 0),
    amount          NUMERIC(20,2) NOT NULL DEFAULT 0 CHECK (amount >= 0),
    reason          TEXT,
    status          TEXT NOT NULL DEFAULT 'posted' CHECK (status IN ('posted')),
    idempotency_key TEXT UNIQUE,
    created_by      UUID REFERENCES profiles(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_returns_branch_created ON returns(branch_id, created_at DESC);
CREATE INDEX idx_returns_ref ON returns(ref_txn_id);

-- 15. stocktakes
CREATE TABLE stocktakes (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id        UUID NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    txn_no           TEXT NOT NULL UNIQUE,
    product_id       UUID NOT NULL REFERENCES products(id),
    counted_qty_base NUMERIC(20,4) NOT NULL CHECK (counted_qty_base >= 0),
    system_qty_base  NUMERIC(20,4) NOT NULL,
    variance         NUMERIC(20,4) NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','approved','rejected')),
    approved_by      UUID REFERENCES profiles(id),
    created_by       UUID REFERENCES profiles(id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_stocktakes_branch_status ON stocktakes(branch_id, status);

-- 16. transfers
CREATE TABLE transfers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id_from  UUID NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    branch_id_to    UUID NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    txn_no          TEXT NOT NULL UNIQUE,
    product_id      UUID NOT NULL REFERENCES products(id),
    qty_base        NUMERIC(20,4) NOT NULL CHECK (qty_base > 0),
    status          TEXT NOT NULL DEFAULT 'in_transit'
                    CHECK (status IN ('in_transit','received','cancelled')),
    idempotency_key TEXT UNIQUE,
    created_by      UUID REFERENCES profiles(id),
    received_by     UUID REFERENCES profiles(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (branch_id_from <> branch_id_to)
);
CREATE INDEX idx_transfers_from ON transfers(branch_id_from, created_at DESC);
CREATE INDEX idx_transfers_to   ON transfers(branch_id_to, created_at DESC);

-- 17. accounting_entries (simple journal)
CREATE TABLE accounting_entries (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id   UUID NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    entry_date  DATE NOT NULL,
    account     TEXT NOT NULL,
    debit       NUMERIC(20,2) NOT NULL DEFAULT 0 CHECK (debit >= 0),
    credit      NUMERIC(20,2) NOT NULL DEFAULT 0 CHECK (credit >= 0),
    ref_type    TEXT,
    ref_id      UUID,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (debit > 0 OR credit > 0)
);
CREATE INDEX idx_entries_branch_date ON accounting_entries(branch_id, entry_date DESC);
CREATE INDEX idx_entries_ref ON accounting_entries(ref_type, ref_id);

-- 18. audit_logs (append-only by convention; no UPDATE/DELETE policies for app roles)
CREATE TABLE audit_logs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id    UUID REFERENCES profiles(id),
    branch_id   UUID REFERENCES branches(id),
    action      TEXT NOT NULL,
    entity_type TEXT,
    entity_id   UUID,
    before_data JSONB,
    after_data  JSONB,
    reason      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_actor_created ON audit_logs(actor_id, created_at DESC);
CREATE INDEX idx_audit_branch_created ON audit_logs(branch_id, created_at DESC);
CREATE INDEX idx_audit_entity ON audit_logs(entity_type, entity_id);

-- 19. idempotency_records
CREATE TABLE idempotency_records (
    key         TEXT PRIMARY KEY,
    profile_id  UUID REFERENCES profiles(id),
    endpoint    TEXT NOT NULL,
    response    JSONB NOT NULL,
    status_code INT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '7 days')
);
CREATE INDEX idx_idem_expires ON idempotency_records(expires_at);

-- 20. app_settings
CREATE TABLE app_settings (
    key        TEXT PRIMARY KEY,
    value      JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
