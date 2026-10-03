-- 003_seed.sql — Seed data: 8 branches, 4 products, role permissions.
-- NO passwords, NO secrets in this file. The first owner account is created
-- via BOOTSTRAP_OWNER_EMAIL / BOOTSTRAP_OWNER_PASSWORD environment variables
-- at backend startup (see backend/app/main.py).

-- 8 branches
INSERT INTO branches (code, name) VALUES
    ('C1', 'Cabang 1'),
    ('C2', 'Cabang 2'),
    ('C3', 'Cabang 3'),
    ('C4', 'Cabang 4'),
    ('C5', 'Cabang 5'),
    ('C6', 'Cabang 6'),
    ('C7', 'Cabang 7'),
    ('C8', 'Cabang 8')
ON CONFLICT (code) DO NOTHING;

-- 4 products. units: conversion factor to base unit "butir".
INSERT INTO products (sku, name, base_unit, units) VALUES
    ('TL-AYAM-RAS',     'Telur Ayam Ras',     'butir', '{"butir": 1, "rak": 30, "peti": 180, "kg": 16}'::jsonb),
    ('TL-AYAM-KAMPUNG', 'Telur Ayam Kampung', 'butir', '{"butir": 1, "rak": 30, "peti": 180, "kg": 16}'::jsonb),
    ('TL-BEBEK',        'Telur Bebek',        'butir', '{"butir": 1, "rak": 30, "peti": 180, "kg": 16}'::jsonb),
    ('TL-PUYUH',        'Telur Puyuh',        'butir', '{"butir": 1, "rak": 30, "peti": 180, "kg": 16}'::jsonb)
ON CONFLICT (sku) DO NOTHING;

-- role_permissions: owner gets all 8; admin gets audit.view only; karyawan gets none.
INSERT INTO role_permissions (role, permission_key) VALUES
    ('owner', 'reports.view_profit'),
    ('owner', 'reports.view_margin'),
    ('owner', 'inventory.view_cost'),
    ('owner', 'transactions.correct'),
    ('owner', 'users.manage'),
    ('owner', 'audit.view'),
    ('owner', 'branches.manage'),
    ('owner', 'settings.manage'),
    ('admin', 'audit.view')
ON CONFLICT DO NOTHING;

-- Default app settings
INSERT INTO app_settings (key, value) VALUES
    ('low_stock_threshold_butir', '1800'::jsonb),
    ('currency', '"IDR"'::jsonb)
ON CONFLICT (key) DO NOTHING;
