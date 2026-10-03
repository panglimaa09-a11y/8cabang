# PRD V2 — SISTEM MANAJEMEN PENJUALAN TELUR 8 CABANG

Versi: 2.0
Tanggal: 1 Oktober 2026
Status: Spesifikasi produk dan teknis

## 1. RINGKASAN PROYEK

Membangun aplikasi web untuk mengelola usaha penjualan telur dengan 8 cabang. Setiap cabang memiliki data transaksi dan persediaan masing-masing. Semua data tersimpan secara terpusat di PostgreSQL melalui Supabase dan dapat dipantau secara online oleh Owner.

Karyawan hanya boleh menginput transaksi dan tidak dapat mengubah atau menghapus transaksi yang telah disimpan. Owner memiliki akses ke semua cabang, laporan keuangan, HPP, laba, dan margin. Admin hanya dapat melihat informasi keuntungan jika Owner memberikan izin khusus.

Aplikasi wajib menggunakan Python, FastAPI, PostgreSQL, Supabase, GitHub, HTML, index.html, CSS, Tailwind CSS, JavaScript, REST API, Docker, dan aset gambar.

Tidak boleh ada fitur palsu, data transaksi statis dalam produksi, atau status sukses palsu.

## 2. TUJUAN UTAMA

1. Memantau 8 cabang dari satu dashboard pusat.
2. Memisahkan data operasional setiap cabang.
3. Mencatat pemasukan, penjualan telur, pembelian stok, dan pengeluaran.
4. Memperbarui stok secara otomatis berdasarkan transaksi.
5. Menghitung HPP secara otomatis menggunakan metode moving weighted average.
6. Menghitung laporan kas, laba-rugi, dan margin gabungan 8 cabang.
7. Membatasi akses keuntungan berdasarkan role dan izin.
8. Menyimpan audit log atas tindakan penting.
9. Menyinkronkan transaksi secara online langsung ke server.
10. Mendukung deployment yang terdokumentasi melalui Docker dan GitHub.

## 3. TEKNOLOGI WAJIB

- Python: bahasa backend.
- FastAPI: REST API, validasi, autentikasi, otorisasi, dan logika bisnis.
- PostgreSQL: database utama.
- Supabase: layanan PostgreSQL terkelola, autentikasi, dan RLS.
- GitHub: repository source code, version control, dan CI.
- HTML dan index.html: struktur halaman web.
- CSS: styling khusus.
- Tailwind CSS: utility styling dan layout responsif.
- JavaScript: komunikasi frontend dengan REST API.
- Docker: container untuk aplikasi.
- REST API: komunikasi frontend dan backend.
- Pictures/assets: logo, ikon, gambar telur, dan ilustrasi dashboard.

Arsitektur:
Frontend HTML + Tailwind CSS + JavaScript -> REST API FastAPI -> Supabase PostgreSQL.

Semua perubahan transaksi harus melalui backend dan kebijakan database. Jangan menaruh service role key Supabase di frontend.

## 4. ROLE DAN HAK AKSES

### A. OWNER

Owner memiliki akses penuh terhadap seluruh 8 cabang.

Hak Owner:
- Melihat Cabang 1 sampai Cabang 8.
- Melihat seluruh transaksi pemasukan dan pengeluaran.
- Melihat stok dan nilai persediaan.
- Melihat HPP, laba-rugi, keuntungan, dan margin.
- Melihat laporan gabungan seluruh cabang.
- Mengoreksi transaksi dengan alasan dan audit log.
- Mengelola Admin dan karyawan.
- Menempatkan pengguna ke cabang.
- Memberikan atau mencabut izin khusus Admin.
- Melihat audit log dan aktivitas penting.
- Mengatur produk, satuan, konversi, serta konfigurasi usaha.

### B. ADMIN

Admin memiliki akses berdasarkan penugasan dan izin Owner.

Hak Admin:
- Melihat dan mengelola data operasional sesuai kewenangan.
- Memeriksa transaksi.
- Memproses koreksi jika diizinkan.
- Mengelola akun jika mendapat kewenangan.
- Melihat HPP, keuntungan, atau margin hanya jika Owner memberikan izin khusus.
- Tidak boleh mengubah role Owner.
- Tidak boleh memberikan izin finansial kepada dirinya sendiri.
- Tidak boleh mengakses cabang di luar cakupan izinnya.

Contoh izin:
- reports.view_profit
- reports.view_margin
- inventory.view_cost
- transactions.correct
- users.manage
- audit.view

### C. KARYAWAN

Karyawan hanya dapat menginput data untuk cabang yang ditugaskan.

Hak karyawan:
- Menginput penjualan telur.
- Menginput pemasukan lain yang diizinkan.
- Menginput pengeluaran operasional.
- Melihat status transaksi yang dikirim.
- Melihat riwayat input yang diperbolehkan.
- Tidak dapat mengedit atau menghapus transaksi yang telah disimpan.
- Tidak dapat melihat laba, margin, HPP, atau laporan keuntungan.
- Tidak dapat membaca transaksi cabang lain.
- Tidak dapat mengubah penugasan cabang.
- Tidak dapat melewati pembatasan melalui panggilan API langsung.

Penyembunyian tombol di frontend tidak cukup. Backend dan database wajib menolak akses yang tidak sah.

## 5. DASHBOARD OWNER

Dashboard Owner wajib menampilkan:

- Delapan kartu Cabang 1 sampai Cabang 8.
- Total penjualan.
- Total penerimaan kas.
- Total pengeluaran kas.
- Nilai persediaan.
- HPP penjualan.
- Laba-rugi.
- Margin keuntungan.
- Grafik performa cabang.
- Status transaksi terbaru.
- Stok menipis.
- Telur rusak dan retur.
- Selisih stok opname.
- Filter tanggal dan cabang.
- Ekspor laporan sesuai izin.

Setiap kartu cabang membuka halaman detail dengan tabel transaksi khusus cabang tersebut.

Semua angka harus dihitung dari data database. Tidak boleh menggunakan angka statis sebagai data produksi.

## 6. HALAMAN CABANG

Setiap cabang memiliki halaman terpisah dengan struktur tabel seragam.

Data yang ditampilkan:
- Tanggal.
- Nomor transaksi.
- Jenis transaksi.
- Produk.
- Jumlah dan satuan.
- Harga jual atau harga pembelian.
- Nilai transaksi.
- HPP jika pengguna berhak melihatnya.
- Status transaksi.
- Petugas pencatat.
- Waktu pencatatan.
- Riwayat koreksi sesuai izin.

Halaman yang diperlukan:
- Cabang 1.
- Cabang 2.
- Cabang 3.
- Cabang 4.
- Cabang 5.
- Cabang 6.
- Cabang 7.
- Cabang 8.

Setiap transaksi harus memiliki branch_id yang diverifikasi di server.

## 7. MODUL STOK PERPETUAL OTOMATIS

Sistem harus memperbarui persediaan setiap kali transaksi yang memengaruhi stok berhasil diposting.

### Transaksi yang memengaruhi stok

- Pembelian telur yang diterima: stok bertambah.
- Penjualan telur: stok berkurang.
- Telur rusak atau pecah: stok berkurang melalui pencatatan kerusakan.
- Retur penjualan yang diterima kembali: stok bertambah setelah pemeriksaan.
- Retur pembelian: stok berkurang.
- Transfer antar cabang: stok keluar dari cabang asal dan masuk ke cabang tujuan.
- Stok opname: penyesuaian dilakukan setelah otorisasi.

### Ketentuan persediaan

- Setiap produk memiliki SKU, nama, satuan, dan faktor konversi.
- Satuan dapat mencakup peti, rak, kilogram, dan butir.
- Faktor konversi ditetapkan secara eksplisit per produk.
- Stok tidak boleh negatif kecuali Owner mengaktifkan pengecualian dengan audit.
- Transaksi yang sama tidak boleh mengurangi stok dua kali.
- Setiap pergerakan stok memiliki referensi transaksi.
- Catat stok sebelum dan sesudah transaksi.
- Catat cabang, waktu, dan pengguna.
- Transfer yang belum diterima harus berstatus dalam perjalanan.
- Sistem dapat mendukung tanggal kedaluwarsa atau kelompok penerimaan.
- Saldo persediaan harus konsisten dengan riwayat pergerakan stok.

## 8. PERHITUNGAN HPP OTOMATIS

Metode awal: moving weighted average atau rata-rata tertimbang bergerak.

Rumus:

Rata-rata HPP per unit =
(Nilai stok sebelum + Nilai pembelian masuk) /
(Jumlah stok sebelum + Jumlah pembelian masuk)

HPP penjualan =
Jumlah unit terjual x HPP per unit

Nilai stok akhir =
Jumlah stok akhir x HPP per unit

Biaya perolehan yang relevan, seperti ongkos angkut pembelian, dapat dimasukkan berdasarkan kebijakan akuntansi.

### Aturan HPP

1. HPP penjualan disimpan sebagai nilai historis ketika penjualan diposting.
2. Pembelian stok menambah nilai persediaan dan bukan otomatis menjadi seluruh biaya penjualan hari tersebut.
3. Perubahan harga pembelian berikutnya tidak boleh mengubah HPP historis secara diam-diam.
4. Retur, kerusakan, diskon, dan biaya angkut ditangani sesuai kebijakan yang ditetapkan.
5. Koreksi transaksi dilakukan melalui pembalikan dan transaksi pengganti.
6. Gunakan aritmetika desimal dan aturan pembulatan yang konsisten.
7. Kebijakan HPP dan laporan akuntansi resmi perlu ditinjau pihak akuntansi yang bertanggung jawab.

Contoh simulasi:
- Stok awal: 100 peti senilai Rp10.000.000.
- Pembelian baru: 50 peti senilai Rp5.500.000.
- Total stok tersedia: 150 peti.
- Nilai stok tersedia: Rp15.500.000.
- Rata-rata HPP: Rp103.333,33 per peti.
- Penjualan: 40 peti.
- HPP penjualan sekitar Rp4.133.333,33 sebelum aturan pembulatan.

Angka di atas hanya contoh perhitungan, bukan data nyata.

## 9. LAPORAN KEUANGAN

Sistem harus memisahkan laporan kas dari laporan laba-rugi.

### Laporan kas

Total penerimaan kas dikurangi total pengeluaran kas.

Laporan ini menunjukkan arus uang, bukan otomatis keuntungan.

### Laporan laba-rugi

Laba kotor = Pendapatan penjualan bersih - HPP penjualan.

Laba operasional = Laba kotor - Beban operasional.

Laba bersih = Laba operasional - beban lain yang relevan + pendapatan lain yang relevan, sesuai kebijakan akuntansi.

Margin bersih = Laba bersih / Pendapatan penjualan bersih x 100%.

Jika pendapatan penjualan bersih nol, margin tidak boleh dihitung dengan pembagian nol.

### Laporan gabungan

Owner dapat melihat:
- Data masing-masing dari 8 cabang.
- Total penjualan.
- Total pengeluaran.
- HPP.
- Nilai persediaan.
- Laba-rugi.
- Margin gabungan.

Margin gabungan dihitung berdasarkan nilai gabungan seluruh cabang, bukan rata-rata sederhana persentase margin masing-masing cabang.

Admin hanya dapat melihat laporan keuntungan jika memiliki izin khusus dari Owner. Karyawan tidak boleh menerima data keuntungan melalui API, ekspor, atau respons tersembunyi.

## 10. SINKRONISASI ONLINE LANGSUNG

Keputusan final: online-first.

Alur:
1. Karyawan login.
2. Karyawan menginput transaksi.
3. Frontend mengirim data melalui HTTPS.
4. FastAPI memvalidasi identitas, cabang, data, nominal, satuan, dan stok.
5. Backend memproses transaksi database secara atomik.
6. Database mengonfirmasi commit.
7. Backend mengirim nomor transaksi dan status sukses.
8. Dashboard Owner memperbarui data melalui Supabase Realtime atau polling berkala.

Jika server gagal menyimpan, aplikasi tidak boleh menampilkan status sukses.

Gunakan idempotency key agar pengiriman ulang akibat jaringan bermasalah tidak menghasilkan transaksi ganda.

Draft lokal boleh tersedia, tetapi transaksi resmi baru dianggap tersimpan setelah server mengonfirmasi commit. Mode offline bukan sumber transaksi resmi pada versi ini.

## 11. KEAMANAN DAN RLS

- Gunakan Supabase Auth atau autentikasi server yang aman.
- Backend memverifikasi token dan identitas pengguna.
- Gunakan Row Level Security untuk membatasi akses baris.
- Backend dan RLS harus menerapkan pembatasan cabang.
- Jangan mempercayai branch_id yang dikirim browser tanpa verifikasi.
- Service role key hanya tersedia di lingkungan backend yang terlindungi.
- Jangan menyimpan kredensial dalam frontend atau GitHub.
- Karyawan tidak dapat mengedit atau menghapus transaksi lama.
- Koreksi oleh Admin atau Owner harus memiliki alasan dan audit log.
- Terapkan validasi server-side, pembatasan percobaan login, HTTPS, dan manajemen sesi.
- Laporan keuntungan hanya boleh dikembalikan kepada pengguna berizin.
- Audit log penting harus terlindungi dari perubahan akun operasional biasa.

## 12. STRUKTUR DATABASE

Tabel yang diperlukan:

1. branches
2. profiles
3. branch_memberships
4. role_permissions
5. user_permissions
6. products
7. inventory_balances
8. inventory_movements
9. purchase_transactions
10. sales_transactions
11. sales_items
12. expense_transactions
13. returns
14. stocktakes
15. accounting_entries
16. audit_logs
17. idempotency_records
18. app_settings

Ketentuan database:
- Gunakan UUID untuk ID utama.
- Gunakan NUMERIC untuk nominal uang.
- Gunakan TIMESTAMPTZ untuk waktu.
- Gunakan foreign key, constraint, dan indeks.
- Gunakan branch_id pada data operasional yang relevan.
- Jangan menghapus permanen transaksi yang telah diposting melalui operasi biasa.
- Gunakan migrasi database yang tersimpan di repository.
- Perubahan stok, HPP, transaksi, dan audit harus konsisten.
- Operasi stok harus aman terhadap transaksi bersamaan.

## 13. REST API

Endpoint minimum:

- GET /api/branches
- GET /api/branches/{id}/summary
- GET /api/branches/{id}/inventory
- GET /api/branches/{id}/transactions
- POST /api/purchases
- POST /api/purchases/{id}/receive
- POST /api/sales
- POST /api/expenses
- POST /api/returns
- POST /api/stocktakes
- POST /api/transactions/{id}/reverse
- GET /api/reports/consolidated
- GET /api/reports/profit-margin
- GET /api/audit-logs
- GET /api/health

Semua endpoint wajib memiliki autentikasi, validasi otorisasi, penanganan kesalahan, dan dokumentasi.

Endpoint keuntungan harus memeriksa izin finansial. Endpoint transaksi harus memeriksa penugasan cabang. Endpoint penjualan harus memvalidasi stok dan menyimpan transaksi secara atomik.

## 14. AUDIT LOG

Catat:
- Identitas pengguna.
- Cabang.
- Waktu tindakan.
- Jenis tindakan.
- ID transaksi.
- Nilai sebelum dan sesudah koreksi.
- Alasan koreksi.
- Referensi transaksi pembalik dan pengganti.
- Perubahan izin.
- Aktivitas administratif penting.
- Percobaan akses yang ditolak jika relevan.

Transaksi yang telah diposting tidak boleh diubah diam-diam. Gunakan pembalikan dan transaksi pengganti agar riwayat stok dan keuangan dapat ditelusuri.

## 15. DESAIN FRONTEND

Gunakan:
- index.html.
- HTML.
- CSS.
- Tailwind CSS.
- JavaScript.
- Folder aset gambar dan ikon.

Halaman wajib:
1. Login.
2. Dashboard Owner.
3. Detail Cabang 1 sampai Cabang 8.
4. Tabel pemasukan.
5. Tabel pengeluaran.
6. Penjualan telur.
7. Pembelian dan penerimaan stok.
8. Persediaan dan HPP.
9. Stok opname.
10. Retur dan kerusakan.
11. Laporan kas.
12. Laporan laba-rugi.
13. Laporan margin.
14. Manajemen pengguna.
15. Pengaturan izin.
16. Audit log.
17. Halaman akses ditolak.

Desain harus responsif untuk Android, tablet, dan desktop. Gunakan tema hijau tua yang profesional, tipografi jelas, tabel responsif, pencarian, filter, pagination, label status, dan format mata uang Rupiah.

Navigasi harus menyesuaikan role. Data rahasia tidak boleh hanya disembunyikan dengan CSS.

## 16. STRUKTUR REPOSITORY

telur-branch-management/
- index.html
- frontend/css/app.css
- frontend/js/api.js
- frontend/js/auth.js
- frontend/js/dashboard.js
- frontend/js/inventory.js
- frontend/js/transactions.js
- frontend/assets/logo.svg
- frontend/assets/icons/
- frontend/assets/pictures/
- backend/app/main.py
- backend/app/api/
- backend/app/models/
- backend/app/schemas/
- backend/app/services/inventory.py
- backend/app/services/costing.py
- backend/app/services/accounting.py
- backend/app/services/permissions.py
- backend/app/security/
- backend/tests/
- backend/requirements.txt
- supabase/migrations/
- supabase/seed.sql
- Dockerfile
- docker-compose.yml
- .env.example
- .gitignore
- .github/workflows/tests.yml
- README.md
- LICENSE

## 17. DOCKER DAN GITHUB

- Docker harus membangun dan menjalankan aplikasi sesuai dokumentasi.
- PostgreSQL produksi menggunakan Supabase.
- Migrasi harus dapat diterapkan secara berulang dan terdokumentasi.
- GitHub Actions menjalankan tes otomatis dan pemeriksaan kode.
- .env.example hanya berisi nama variabel dan contoh nilai nonrahasia.
- .gitignore mengecualikan file rahasia dan data sensitif.
- README menyertakan gambar antarmuka, diagram arsitektur, konfigurasi Supabase, cara menjalankan Docker, dan troubleshooting.
- Dokumentasikan Windows, Linux, macOS, serta Termux sesuai dukungan dependensi.
- Jangan mengklaim integrasi GitHub, Supabase, atau deployment berhasil sebelum benar-benar diuji.

## 18. PENGUJIAN WAJIB

1. Owner dapat melihat 8 cabang.
2. Karyawan tidak dapat membaca transaksi cabang lain.
3. Karyawan tidak dapat mengakses laporan keuntungan.
4. Admin tanpa izin finansial ditolak oleh backend.
5. Admin dengan izin hanya mendapat akses sesuai cakupan yang diberikan.
6. Pembelian memperbarui stok dan nilai persediaan.
7. Penjualan mengurangi stok dan mencatat HPP.
8. Retur dan kerusakan memperbarui stok dengan benar.
9. Transfer antar cabang menjaga konsistensi stok.
10. Stok tidak menjadi negatif tanpa izin pengecualian.
11. Transaksi bersamaan tidak merusak saldo stok.
12. Pengiriman ulang tidak membuat transaksi ganda.
13. Kegagalan database membatalkan seluruh perubahan terkait.
14. Audit log mencatat koreksi.
15. Dashboard hanya menganggap transaksi sukses setelah commit.
16. Perhitungan HPP dan margin cocok dengan hasil pengujian independen.
17. Migrasi, Docker build, dan tes otomatis berhasil.
18. Kredensial tidak bocor ke frontend atau repository.

## 19. TAHAPAN IMPLEMENTASI

Tahap 1: Fondasi
- Setup repository GitHub.
- Setup FastAPI dan Supabase.
- Setup Docker.
- Buat migrasi database.
- Buat autentikasi dan role.
- Buat delapan cabang.
- Terapkan RLS.

Tahap 2: Persediaan
- Master produk dan satuan.
- Pembelian dan penerimaan.
- Saldo stok.
- Riwayat pergerakan.
- Validasi stok.

Tahap 3: Penjualan dan HPP
- Form penjualan.
- Perhitungan moving weighted average.
- HPP historis.
- Retur dan kerusakan.
- Transfer antar cabang.

Tahap 4: Keuangan
- Pencatatan pengeluaran.
- Laporan kas.
- Laporan laba-rugi.
- Margin gabungan.
- Izin finansial Admin.
- Audit log.

Tahap 5: Dashboard
- Delapan tabel cabang.
- Ringkasan gabungan.
- Grafik dan filter.
- Status sinkronisasi.
- Ekspor laporan sesuai izin.

Tahap 6: QA dan deployment
- Pengujian keamanan.
- Pengujian stok dan HPP.
- Pengujian transaksi bersamaan.
- Pengujian migrasi.
- Docker build.
- Dokumentasi.
- Pipeline CI.

## 20. DEFINISI SELESAI

Proyek hanya dinyatakan selesai jika:
- Delapan cabang berfungsi.
- Data setiap cabang terisolasi.
- Karyawan hanya dapat menginput transaksi sesuai penugasan.
- Karyawan tidak dapat mengedit atau menghapus transaksi lama.
- Owner dapat memantau stok, HPP, keuangan, laba, dan margin.
- Admin hanya dapat melihat keuntungan jika diberi izin khusus.
- Stok perpetual konsisten dengan seluruh transaksi.
- HPP otomatis teruji dan tersimpan secara historis.
- Sinkronisasi online bekerja dengan konfirmasi server.
- Transaksi ganda dicegah.
- Audit log dapat ditelusuri.
- Repository, Docker, migrasi, pengujian, dan README tersedia.
- Seluruh fitur inti lulus pengujian.

## 21. STATUS DAN BATASAN

Dokumen ini adalah PRD V2 dan spesifikasi teknis. Dokumen ini belum berarti aplikasi sudah dibuat, database sudah terhubung, atau repository GitHub sudah diperbarui.

Semua implementasi harus menggunakan data nyata dari database, bukan simulasi dalam lingkungan produksi. Setiap fitur harus memiliki validasi, penanganan kesalahan, kontrol akses, dan pengujian yang sesuai.
