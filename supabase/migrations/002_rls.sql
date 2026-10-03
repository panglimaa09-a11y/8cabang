-- 002_rls.sql — Row Level Security for Sistem Manajemen Penjualan Telur 8 Cabang
-- Pattern: Supabase Auth standard — auth.uid() matches profiles.id.
-- The backend connects via DATABASE_URL (superuser / service role) and BYPASSES RLS.
-- These policies protect direct access via the anon key / Supabase client.

-- Enable RLS on every table.
ALTER TABLE branches              ENABLE ROW LEVEL SECURITY;
ALTER TABLE profiles              ENABLE ROW LEVEL SECURITY;
ALTER TABLE branch_memberships    ENABLE ROW LEVEL SECURITY;
ALTER TABLE role_permissions      ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_permissions      ENABLE ROW LEVEL SECURITY;
ALTER TABLE products              ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory_balances    ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory_movements   ENABLE ROW LEVEL SECURITY;
ALTER TABLE purchase_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE purchase_items        ENABLE ROW LEVEL SECURITY;
ALTER TABLE sales_transactions    ENABLE ROW LEVEL SECURITY;
ALTER TABLE sales_items           ENABLE ROW LEVEL SECURITY;
ALTER TABLE expense_transactions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE returns               ENABLE ROW LEVEL SECURITY;
ALTER TABLE stocktakes            ENABLE ROW LEVEL SECURITY;
ALTER TABLE transfers             ENABLE ROW LEVEL SECURITY;
ALTER TABLE accounting_entries    ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs            ENABLE ROW LEVEL SECURITY;
ALTER TABLE idempotency_records   ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_settings          ENABLE ROW LEVEL SECURITY;

-- Helper: is the current auth user an active owner?
CREATE OR REPLACE FUNCTION public.is_owner()
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.profiles
        WHERE id = auth.uid() AND role = 'owner' AND is_active
    );
$$;

-- Helper: does the current auth user hold a permission (role-based or per-user grant)?
CREATE OR REPLACE FUNCTION public.has_permission(p_key text)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
    SELECT public.is_owner()
        OR EXISTS (
            SELECT 1
            FROM public.profiles pr
            JOIN public.role_permissions rp ON rp.role = pr.role
            WHERE pr.id = auth.uid() AND rp.permission_key = p_key
        )
        OR EXISTS (
            SELECT 1 FROM public.user_permissions up
            WHERE up.profile_id = auth.uid() AND up.permission_key = p_key
        );
$$;

-- Helper: is a branch inside the current auth user's scope?
CREATE OR REPLACE FUNCTION public.in_my_branch(b_id uuid)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
    SELECT public.is_owner()
        OR EXISTS (
            SELECT 1 FROM public.branch_memberships
            WHERE profile_id = auth.uid() AND branch_id = b_id
        );
$$;

-- ── branches: everyone authenticated can read; writes need branches.manage ──
CREATE POLICY branches_select ON branches
    FOR SELECT TO authenticated USING (true);
CREATE POLICY branches_write ON branches
    FOR ALL TO authenticated USING (public.has_permission('branches.manage'))
    WITH CHECK (public.has_permission('branches.manage'));

-- ── profiles: read own row, or all with users.manage ──
CREATE POLICY profiles_select ON profiles
    FOR SELECT TO authenticated
    USING (auth.uid() = id OR public.has_permission('users.manage'));
CREATE POLICY profiles_insert ON profiles
    FOR INSERT TO authenticated
    WITH CHECK (public.has_permission('users.manage'));
CREATE POLICY profiles_update ON profiles
    FOR UPDATE TO authenticated
    USING (auth.uid() = id OR public.has_permission('users.manage'))
    WITH CHECK (auth.uid() = id OR public.has_permission('users.manage'));
-- No DELETE policy: profiles are deactivated, never deleted.

-- ── branch_memberships ──
CREATE POLICY memberships_select ON branch_memberships
    FOR SELECT TO authenticated
    USING (profile_id = auth.uid() OR public.has_permission('users.manage'));
CREATE POLICY memberships_write ON branch_memberships
    FOR ALL TO authenticated
    USING (public.has_permission('users.manage'))
    WITH CHECK (public.has_permission('users.manage'));

-- ── role_permissions: readable, owner-managed via backend ──
CREATE POLICY role_permissions_select ON role_permissions
    FOR SELECT TO authenticated USING (true);

-- ── user_permissions ──
CREATE POLICY user_permissions_select ON user_permissions
    FOR SELECT TO authenticated
    USING (profile_id = auth.uid() OR public.is_owner());

-- ── products: readable by all authenticated; managed via backend ──
CREATE POLICY products_select ON products
    FOR SELECT TO authenticated USING (is_active OR public.has_permission('settings.manage'));

-- ── inventory_balances / inventory_movements: read-only via direct access ──
CREATE POLICY balances_select ON inventory_balances
    FOR SELECT TO authenticated USING (public.in_my_branch(branch_id));
CREATE POLICY movements_select ON inventory_movements
    FOR SELECT TO authenticated USING (public.in_my_branch(branch_id));

-- ── Operational transaction tables: read + insert within own branch scope.
--     Corrections / status changes go through the backend only.
--     (purchase_items / sales_items inherit scope through their parent row.)
CREATE POLICY purchases_select ON purchase_transactions
    FOR SELECT TO authenticated USING (public.in_my_branch(branch_id));
CREATE POLICY purchases_insert ON purchase_transactions
    FOR INSERT TO authenticated WITH CHECK (public.in_my_branch(branch_id));

CREATE POLICY purchase_items_select ON purchase_items
    FOR SELECT TO authenticated
    USING (EXISTS (SELECT 1 FROM purchase_transactions p
                   WHERE p.id = purchase_items.purchase_id
                     AND public.in_my_branch(p.branch_id)));
CREATE POLICY purchase_items_insert ON purchase_items
    FOR INSERT TO authenticated
    WITH CHECK (EXISTS (SELECT 1 FROM purchase_transactions p
                       WHERE p.id = purchase_items.purchase_id
                         AND public.in_my_branch(p.branch_id)));

CREATE POLICY sales_select ON sales_transactions
    FOR SELECT TO authenticated USING (public.in_my_branch(branch_id));
CREATE POLICY sales_insert ON sales_transactions
    FOR INSERT TO authenticated WITH CHECK (public.in_my_branch(branch_id));

CREATE POLICY sales_items_select ON sales_items
    FOR SELECT TO authenticated
    USING (EXISTS (SELECT 1 FROM sales_transactions s
                   WHERE s.id = sales_items.sale_id
                     AND public.in_my_branch(s.branch_id)));
CREATE POLICY sales_items_insert ON sales_items
    FOR INSERT TO authenticated
    WITH CHECK (EXISTS (SELECT 1 FROM sales_transactions s
                       WHERE s.id = sales_items.sale_id
                         AND public.in_my_branch(s.branch_id)));

CREATE POLICY expenses_select ON expense_transactions
    FOR SELECT TO authenticated USING (public.in_my_branch(branch_id));
CREATE POLICY expenses_insert ON expense_transactions
    FOR INSERT TO authenticated WITH CHECK (public.in_my_branch(branch_id));

CREATE POLICY returns_select ON returns
    FOR SELECT TO authenticated USING (public.in_my_branch(branch_id));
CREATE POLICY returns_insert ON returns
    FOR INSERT TO authenticated WITH CHECK (public.in_my_branch(branch_id));

CREATE POLICY stocktakes_select ON stocktakes
    FOR SELECT TO authenticated USING (public.in_my_branch(branch_id));
CREATE POLICY stocktakes_insert ON stocktakes
    FOR INSERT TO authenticated WITH CHECK (public.in_my_branch(branch_id));

CREATE POLICY transfers_select ON transfers
    FOR SELECT TO authenticated
    USING (public.in_my_branch(branch_id_from) OR public.in_my_branch(branch_id_to));
CREATE POLICY transfers_insert ON transfers
    FOR INSERT TO authenticated
    WITH CHECK (public.in_my_branch(branch_id_from));

CREATE POLICY entries_select ON accounting_entries
    FOR SELECT TO authenticated USING (public.in_my_branch(branch_id));

-- ── audit_logs: readable only with audit.view; append-only (no update/delete) ──
CREATE POLICY audit_select ON audit_logs
    FOR SELECT TO authenticated USING (public.has_permission('audit.view'));

-- ── idempotency_records: users see only their own keys ──
CREATE POLICY idem_select ON idempotency_records
    FOR SELECT TO authenticated
    USING (profile_id = auth.uid() OR public.is_owner());
CREATE POLICY idem_insert ON idempotency_records
    FOR INSERT TO authenticated WITH CHECK (profile_id = auth.uid());

-- ── app_settings: readable; writable only with settings.manage ──
CREATE POLICY settings_select ON app_settings
    FOR SELECT TO authenticated USING (true);
CREATE POLICY settings_write ON app_settings
    FOR ALL TO authenticated
    USING (public.has_permission('settings.manage'))
    WITH CHECK (public.has_permission('settings.manage'));
