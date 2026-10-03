# KONTRAK TEKNIS — Sistem Manajemen Penjualan Telur 8 Cabang (PRD V2)

Dokumen ini adalah kontrak yang MENGIKAT untuk semua pekerja (backend, frontend, DB).
Jangan menyimpang tanpa persetujuan. Bahasa kode & komentar: Inggris. Bahasa UI: Indonesia.

## 1. Repo root
`/home/hatch/workspace/telur-branch-management/`
Sudah ada: `PRD-V2.md`. Jangan ubah file itu.

## 2. Env vars (backend membaca dari environment, TIDAK dari file di repo)
- `DATABASE_URL` — SQLAlchemy URL Postgres (Supabase). Contoh format: `postgresql+psycopg2://postgres:PASSWORD@db.xxx.supabase.co:5432/postgres`
- `JWT_SECRET` — rahasia penandatangan JWT (wajib di production)
- `JWT_EXPIRE_MINUTES` — default 720
- `SUPABASE_URL`, `SUPABASE_ANON_KEY` — dipakai frontend (anon key BOLEH di frontend; service role TIDAK BOLEH)
- `SUPABASE_SERVICE_ROLE_KEY` — hanya backend (opsional; backend memakai DATABASE_URL langsung)
- `BOOTSTRAP_OWNER_EMAIL`, `BOOTSTRAP_OWNER_PASSWORD` — sekali pakai saat DB kosong: buat akun owner pertama. Setelah owner ada, abaikan.
- `ALLOW_NEGATIVE_STOCK` — `false` default; hanya owner bisa override per transaksi via flag `allow_negative` (dicatat di audit).
- `CORS_ORIGINS` — koma-dipisah, default `*` untuk dev.

## 3. Skema database (PostgreSQL, UUID PK, NUMERIC uang, TIMESTAMPTZ waktu)
Tabel (kolom inti; FK + index wajib):
1. `branches(id, code UNIQUE ['C1'..'C8'], name, address, phone, is_active, created_at)`
2. `profiles(id, email UNIQUE, full_name, role ['owner','admin','karyawan'], password_hash, is_active, created_at)`
3. `branch_memberships(id, profile_id FK, branch_id FK, UNIQUE(profile_id,branch_id))`
4. `role_permissions(role, permission_key, PRIMARY KEY(role,permission_key))`
   permission_key ∈ {reports.view_profit, reports.view_margin, inventory.view_cost, transactions.correct, users.manage, audit.view, branches.manage, settings.manage}
   Seed: owner=all; admin={audit.view} saja (profit/margin/cost default TIDAK); karyawan={} .
5. `user_permissions(profile_id FK, permission_key, granted_by FK, granted_at, PRIMARY KEY(profile_id,permission_key))` — override per-user oleh owner.
6. `products(id, sku UNIQUE, name, base_unit DEFAULT 'butir', units JSONB {"butir":1,"rak":30,"peti":180,"kg":16}, is_active, created_at)`
   Seed produk: `TL-AYAM-RAS` "Telur Ayam Ras", `TL-AYAM-KAMPUNG` "Telur Ayam Kampung", `TL-BEBEK` "Telur Bebek", `TL-PUYUH` "Telur Puyuh".
7. `inventory_balances(branch_id FK, product_id FK, qty_base NUMERIC, avg_cost NUMERIC, updated_at, PK(branch_id,product_id))`
8. `inventory_movements(id, branch_id FK, product_id FK, txn_type, txn_ref TEXT, qty_base NUMERIC signed, qty_before, qty_after, unit_cost NUMERIC, created_by FK, created_at)`
   txn_type ∈ {purchase_receive, sale, damage, sales_return, purchase_return, transfer_out, transfer_in, stocktake_adjust}
9. `purchase_transactions(id, branch_id FK, txn_no UNIQUE 'PB-YYYYMMDD-####', supplier, status ['draft','received','cancelled'], subtotal, freight_cost, total, idempotency_key UNIQUE, received_at, created_by FK, created_at)`
10. `purchase_items(id, purchase_id FK, product_id FK, qty_base NUMERIC, unit TEXT, unit_price NUMERIC, line_total NUMERIC)`
11. `sales_transactions(id, branch_id FK, txn_no UNIQUE 'PJ-YYYYMMDD-####', customer, status ['posted','voided'], subtotal, discount, total, idempotency_key UNIQUE, created_by FK, created_at)`
12. `sales_items(id, sale_id FK, product_id FK, qty_base NUMERIC, unit TEXT, unit_price NUMERIC, line_total NUMERIC, cogs NUMERIC)`
13. `expense_transactions(id, branch_id FK, txn_no UNIQUE 'KK-YYYYMMDD-####', category, description, amount NUMERIC, expense_date DATE, idempotency_key UNIQUE, created_by FK, created_at)`
14. `returns(id, branch_id FK, txn_no UNIQUE 'RT-YYYYMMDD-####', return_type ['sales_return','purchase_return'], ref_txn_id UUID, product_id FK, qty_base NUMERIC, amount NUMERIC, reason, status ['posted'], idempotency_key UNIQUE, created_by FK, created_at)`
15. `stocktakes(id, branch_id FK, txn_no UNIQUE 'SO-YYYYMMDD-####', product_id FK, counted_qty_base, system_qty_base, variance, status ['pending','approved','rejected'], approved_by FK, created_by FK, created_at)`
16. `transfers(id, branch_id_from FK, branch_id_to FK, txn_no UNIQUE 'TR-YYYYMMDD-####', product_id FK, qty_base NUMERIC, status ['in_transit','received','cancelled'], idempotency_key UNIQUE, created_by FK, received_by FK, created_at)`
17. `accounting_entries(id, branch_id FK, entry_date DATE, account TEXT, debit NUMERIC, credit NUMERIC, ref_type TEXT, ref_id UUID, description, created_at)`
18. `audit_logs(id, actor_id FK, branch_id FK NULL, action TEXT, entity_type TEXT, entity_id UUID NULL, before_data JSONB, after_data JSONB, reason TEXT, created_at)`
19. `idempotency_records(key PK, profile_id FK, endpoint TEXT, response JSONB, status_code INT, created_at, expires_at)`
20. `app_settings(key PK, value JSONB, updated_at)`

Migrasi di `supabase/migrations/`: `001_initial.sql` (semua tabel+index+FK), `002_rls.sql` (ENABLE RLS + policy pakai `auth.uid()` = profiles.id; backend pakai service role/DATABASE_URL langsung), `003_seed.sql` (8 cabang C1..C8 "Cabang 1".. dst, produk, role_permissions).
Seed TANPA password owner di repo. Bootstrap owner lewat env (lihat §2).

## 4. REST API (prefix /api, JSON, JWT Bearer)
Auth:
- `POST /api/auth/login` {email,password} → {access_token, token_type, profile:{id,email,full_name,role}}
- `GET /api/auth/me`
- `POST /api/users` (owner, atau admin dgn users.manage) {email,password,full_name,role,branch_ids[]}
- `GET /api/users`, `PATCH /api/users/{id}` (owner / users.manage)
- `POST /api/permissions/grant` {profile_id, permission_key} & `/revoke` (owner only)

Cabang:
- `GET /api/branches` → cabang sesuai scope user (owner: semua; admin/karyawan: membership)
- `GET /api/branches/{id}/summary` {branch, totals:{sales, cash_in, cash_out, inventory_value}, low_stock[], recent[]}
- `GET /api/branches/{id}/inventory` → per produk: qty per satuan tampil + qty_base + avg_cost (avg_cost hanya jika boleh lihat cost)
- `GET /api/branches/{id}/transactions?type=&from=&to=&page=&limit=`

Transaksi (semua POST terima `Idempotency-Key` header ATAU field `idempotency_key`; duplikat → kembalikan respons tersimpan, TANPA efek ganda):
- `POST /api/purchases` {branch_id, supplier, freight_cost, items:[{product_id, qty, unit, unit_price}]} → status draft
- `POST /api/purchases/{id}/receive` → stok +, avg_cost baru = (nilai_lama + nilai_beli_termasuk_freight) / (qty_lama + qty_beli); jurnal akuntansi; movement purchase_receive
- `POST /api/sales` {branch_id, customer, discount, items:[{product_id, qty, unit, unit_price}]} → cek stok (tolak jika kurang kecuali allow_negative+owner), stok -, cogs per item = qty_base × avg_cost saat itu (historis, TIDAK berubah lagi), jurnal
- `POST /api/expenses` {branch_id, category, description, amount, expense_date}
- `POST /api/returns` {branch_id, return_type, ref_txn_id, product_id, qty, unit, reason} → sales_return: stok + (nilai kembali = cogs asal jika bisa dilacak, fallback avg_cost); purchase_return: stok -
- `POST /api/stocktakes` {branch_id, product_id, counted_qty, unit} → status pending; `POST /api/stocktakes/{id}/approve` (owner/admin dgn transactions.correct) → movement stocktake_adjust
- `POST /api/transfers` {branch_id_from, branch_id_to, product_id, qty, unit} → transfer_out (stok - di asal), status in_transit; `POST /api/transfers/{id}/receive` → transfer_in (stok + di tujuan)
- `POST /api/transactions/{id}/reverse` {reason} → void sale/purchase/expense (buat reversal, stok dikembalikan, audit log; TIDAK hapus baris)

Laporan (wajib cek izin finansial; karyawan SELALU 403):
- `GET /api/reports/cash?branch_id=&from=&to=` → {cash_in, cash_out, net}
- `GET /api/reports/profit-loss?branch_id=&from=&to=` → {revenue_net, cogs, gross_profit, opex, other_income, net_profit} — butuh reports.view_profit
- `GET /api/reports/profit-margin?...` → {net_profit, revenue_net, margin_pct} (margin null jika revenue 0) — butuh reports.view_margin; gabungan = dari total gabungan, BUKAN rata-rata %
- `GET /api/reports/consolidated?from=&to=` (owner) → per cabang + total gabungan
- `GET /api/audit-logs?branch_id=&from=&to=&page=` — butuh audit.view (owner selalu boleh)

Lainnya:
- `GET /api/products`
- `GET /api/health` → {status:"ok", db:"up", version}

## 5. Aturan bisnis yang TIDAK BOLEH dilanggar
- Semua endpoint (kecuali /auth/login, /health) butuh JWT valid.
- Scope cabang: non-owner HANYA bisa baca/tulis cabang di branch_memberships-nya. branch_id dari client SELALU diverifikasi server.
- Karyawan: hanya POST transaksi + GET data operasional cabangnya. 403 untuk: laporan profit/margin (bahkan field cogs/avg_cost disembunyikan), /api/users, /api/audit-logs, cabang lain.
- avg_cost & cogs: NUMERIC presisi; pembulatan HALF_UP 2 desimal untuk uang; qty_base boleh 4 desimal.
- Setiap perubahan stok: 1 baris inventory_movements (qty_before, qty_after) + update inventory_balances dalam SATU transaksi DB; pakai SELECT ... FOR UPDATE pada balance agar konkuren aman.
- Semua POST transaksi: idempotency_records; respons duplikat = respons asli tersimpan.
- Kegagalan di tengah → rollback penuh, TIDAK ada status sukses palsu.
- Audit log untuk: reverse/koreksi (before/after + reason), grant/revoke izin, approve stocktake, allow_negative.
- Tidak ada angka statis di production; dashboard hitung dari DB.
- Kredensial TIDAK BOLEH di frontend / repo. Service role TIDAK di frontend.

## 6. Frontend (SPA satu index.html, hash routing)
Halaman (17): login, dashboard owner (8 kartu cabang + KPI + grafik + stok menipis + transaksi terbaru), detail cabang ×8 (satu template), pemasukan (tabel penjualan), pengeluaran, form penjualan, pembelian & penerimaan, persediaan & HPP, stok opname, retur & kerusakan, laporan kas, laporan laba-rugi, laporan margin, manajemen pengguna, pengaturan izin, audit log, akses ditolak (403).
- Tema: hijau tua profesional (#0b3d2e / emerald-900 dkk), Tailwind via CDN, responsif (Android/tablet/desktop).
- Nav & halaman disesuaikan role; data sensitif TIDAK BOLEH hanya disembunyikan CSS — jangan panggil endpoint terlarang, jangan render datanya.
- Format: Rupiah `Rp1.234.567`, tanggal `id-ID`.
- JS modular: `frontend/js/api.js` (fetch+JWT+refresh), `auth.js`, `dashboard.js`, `inventory.js`, `transactions.js`.
- Aset: `frontend/assets/logo.svg`, `icons/` (min 6 ikon svg: dashboard, box, cart, cash, chart, users, shield, logout), `pictures/` (min 2 ilustrasi svg: telur/hero, empty-state).

## 7. Docker & CI
- `Dockerfile`: python:3.11-slim, install requirements, copy backend + frontend, serve frontend statis dari FastAPI (`/` → index.html), `uvicorn app.main:app`.
- `docker-compose.yml`: service `app` (build ., env_file .env, port 8000); service `db` postgres:16 (profile: dev) untuk pengembangan lokal.
- `.github/workflows/tests.yml`: Python 3.11, pip install -r backend/requirements.txt, `pytest backend/tests -q`; job kedua: docker build.
- `.env.example`: SEMUA nama var §2, nilai contoh non-rahasia (password: `ganti-dengan-rahasia`).
- `.gitignore`: .env, __pycache__, *.pyc, .venv, data postgres, node_modules.

## 8. Definisi selesai per pekerja
- Backend: `pytest` hijau (uji: HPP weighted-average contoh PRD §8 → 103.333,33/peti; stok tidak negatif; idempotensi; karyawan 403 profit; konkuren aman), `python -m compileall` bersih, endpoint §4 lengkap & sesuai kontrak.
- Frontend: semua 17 halaman render, panggil endpoint §4 yang benar, tanpa kredensial tertanam, tanpa data statis produksi.
- Tidak ada file rahasia di repo. README + LICENSE (MIT) + diagram arsitektur (ASCII) di root.
