# Sistem Manajemen Penjualan Telur — 8 Cabang

Aplikasi web untuk mengelola usaha penjualan telur dengan 8 cabang: transaksi terpusat,
stok perpetual otomatis, HPP moving weighted average, laporan kas & laba-rugi, kontrol
akses berbasis role (Owner / Admin / Karyawan), dan audit log. Sesuai **PRD V2**
(`PRD-V2.md`).

## Arsitektur

```
┌─────────────────────────────┐      HTTPS / REST + JWT       ┌──────────────────────────────┐
│  Frontend                   │ ───────────────────────────▶  │  Backend (FastAPI)             │
│  index.html + Tailwind CSS  │                               │  backend/app                   │
│  + JavaScript (SPA)         │ ◀───────────────────────────  │  · auth, RBAC, validasi cabang │
└─────────────────────────────┘      JSON                     │  · stok perpetual, HPP (MWA)   │
                                                              │  · idempotency, audit log      │
                                                              └──────────────┬───────────────┘
                                                                             │ psycopg2
                                                             ┌───────────────▼───────────────┐
                                                             │  Supabase (PostgreSQL)        │
                                                             │  · 20 tabel + RLS             │
                                                             │  · migrasi di supabase/       │
                                                             └───────────────────────────────┘
```

- **Online-first**: transaksi resmi hanya diakui setelah server commit ke database.
- **Idempotency key** di setiap POST transaksi — kirim ulang karena jaringan tidak
  membuat transaksi ganda.
- **Keamanan berlapis**: JWT → verifikasi role & izin di backend → verifikasi
  `branch_id` per request → Row Level Security di database. Menyembunyikan tombol di
  frontend saja TIDAK cukup dan tidak dilakukan sebagai satu-satunya perlindungan.

## Teknologi

Python 3.11 · FastAPI · SQLAlchemy · PostgreSQL (Supabase) · HTML + Tailwind CSS +
JavaScript · Docker · GitHub Actions.

## Struktur repository

```
telur-branch-management/
├── index.html                  # entry SPA (memuat frontend/)
├── frontend/
│   ├── css/app.css
│   ├── js/ (api, auth, app, dashboard, inventory, transactions)
│   └── assets/ (logo.svg, icons/, pictures/)
├── backend/
│   ├── app/ (main, api/, models/, schemas/, services/, security/)
│   ├── tests/
│   └── requirements.txt
├── supabase/migrations/        # 001_initial.sql, 002_rls.sql, 003_seed.sql
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── .github/workflows/tests.yml
```

## Cara menjalankan

### 1. Siapkan Supabase

1. Buat project di [supabase.com](https://supabase.com).
2. Buka **SQL Editor**, jalankan berurutan:
   - `supabase/migrations/001_initial.sql`
   - `supabase/migrations/002_rls.sql`
   - `supabase/migrations/003_seed.sql`
3. Catat **Project URL**, **anon key**, dan password database
   (Settings → Database → Connection string, mode Session).

### 2. Konfigurasi environment

```bash
cp .env.example .env
# isi DATABASE_URL, JWT_SECRET, SUPABASE_URL, SUPABASE_ANON_KEY,
# BOOTSTRAP_OWNER_EMAIL, BOOTSTRAP_OWNER_PASSWORD
```

> `BOOTSTRAP_OWNER_EMAIL/PASSWORD` hanya dipakai sekali saat tabel `profiles`
> masih kosong untuk membuat akun Owner pertama. Setelah itu abaikan/hapus.

### 3. Jalankan dengan Docker

```bash
docker compose up --build
# buka http://localhost:8000
```

### 4. Jalankan lokal tanpa Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
export $(cat .env | xargs)   # atau pakai direnv
export FRONTEND_DIR=$(pwd)   # repo root = direktori yang berisi index.html
uvicorn app.main:app --app-dir backend --reload
```

### 5. Tes otomatis

```bash
pip install pytest
python -m pytest backend/tests -q
```

CI GitHub Actions (`tests.yml`) menjalankan compile-check, pytest, dan `docker build`
setiap push/PR.

## Role & hak akses (ringkas)

| Kemampuan | Owner | Admin | Karyawan |
|---|---|---|---|
| 8 cabang, semua transaksi | ✅ | sesuai penugasan | cabang sendiri |
| Input penjualan/pembelian/pengeluaran | ✅ | ✅ | ✅ |
| Edit/hapus transaksi tersimpan | ❌ (via reverse + audit) | ❌ (via reverse + izin) | ❌ |
| HPP, laba, margin | ✅ | hanya jika diberi izin | ❌ (API 403) |
| Kelola user & izin | ✅ | jika `users.manage` | ❌ |
| Audit log | ✅ | jika `audit.view` | ❌ |

Permission key: `reports.view_profit`, `reports.view_margin`, `inventory.view_cost`,
`transactions.correct`, `users.manage`, `audit.view`, `branches.manage`, `settings.manage`.

## Troubleshooting

| Gejala | Penyebab umum / solusi |
|---|---|
| `401 Unauthorized` | Token kedaluwarsa — login ulang. |
| `403` di laporan | Role tidak punya izin finansial — minta Owner grant. |
| `Stok tidak mencukupi` | Kurangi qty, atau Owner pakai flag `allow_negative` (tercatat di audit). |
| Transaksi ganda setelah retry | Pastikan client mengirim `Idempotency-Key` yang sama. |
| `could not connect` ke DB | Cek `DATABASE_URL`; untuk Supabase gunakan port 5432 + password benar. |
| Migrasi gagal di tengah | Jalankan ulang per file berurutan; `001` idempoten memakai `IF NOT EXISTS`. |
| Port 8000 dipakai | Ganti mapping port di `docker-compose.yml`. |

## Catatan

- Semua angka dashboard dihitung dari database — tidak ada data statis produksi.
- HPP memakai *moving weighted average* dengan aritmetika desimal; contoh
  perhitungan ada di PRD V2 §8 dan diuji di `backend/tests/test_costing.py`.
- Kebijakan akuntansi resmi (perlakuan ongkir, diskon, retur) perlu ditinjau
  pihak akuntansi yang bertanggung jawab sebelum dipakai operasional.
