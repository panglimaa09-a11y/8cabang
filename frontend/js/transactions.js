// Transaction views: branch detail, sales form, purchase+receive, expense,
// income/expense tables, transfer receive, reverse with reason.
import { api } from "./api.js";
import { myBranches, branchByCode, getProducts, isOwner, isKaryawan, hasPermission } from "./auth.js";
import {
  fmtRp, fmtNum, fmtDate, fmtDateTime, esc, skeletonRows, emptyState, errorAlert,
  statusBadge, txnTypeLabel, unitOptions, toast, confirmDialog, reasonDialog,
  filterBar, readFilter, paginate,
} from "./ui.js";

function canReverse() {
  return isOwner() || hasPermission("transactions.correct");
}

function branchOptions(branches, selectedId) {
  return branches
    .map((b) => `<option value="${esc(b.id)}" ${b.id === selectedId ? "selected" : ""}>${esc(b.code)} — ${esc(b.name || "")}</option>`)
    .join("");
}

function productOptions(products) {
  return products
    .map((p) => `<option value="${esc(p.id)}" data-units='${esc(JSON.stringify(p.units || { butir: 1 }))}'>${esc(p.name)} (${esc(p.sku)})</option>`)
    .join("");
}

function unitsOf(selectEl) {
  try {
    return JSON.parse(selectEl.selectedOptions[0].dataset.units || '{"butir":1}');
  } catch (e) {
    return { butir: 1 };
  }
}

function syncUnitSelect(prodSel, unitSel) {
  const units = unitsOf(prodSel);
  unitSel.innerHTML = unitOptions(units).map((u) => `<option value="${esc(u)}">${esc(u)}</option>`).join("");
}

/** Dynamic item rows for sale/purchase forms. Returns {tbody, addRow, readItems}. */
function itemRows(tbodyId, products) {
  const tbody = document.getElementById(tbodyId);
  function addRow() {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><select class="field-select it-product" required>${productOptions(products)}</select></td>
      <td><input type="number" class="field-input it-qty" min="0.01" step="0.01" required placeholder="0"></td>
      <td><select class="field-select it-unit"></select></td>
      <td><input type="number" class="field-input it-price" min="0" step="1" required placeholder="Rp"></td>
      <td class="num stat-num it-line font-semibold">Rp0</td>
      <td><button type="button" class="btn btn-ghost btn-sm it-del" aria-label="Hapus baris">✕</button></td>`;
    tbody.appendChild(tr);
    const prodSel = tr.querySelector(".it-product");
    const unitSel = tr.querySelector(".it-unit");
    syncUnitSelect(prodSel, unitSel);
    prodSel.addEventListener("change", () => { syncUnitSelect(prodSel, unitSel); recalc(); });
    tr.querySelector(".it-qty").addEventListener("input", recalc);
    tr.querySelector(".it-price").addEventListener("input", recalc);
    tr.querySelector(".it-del").addEventListener("click", () => { tr.remove(); recalc(); });
    recalc();
  }
  function recalc() {
    let total = 0;
    tbody.querySelectorAll("tr").forEach((tr) => {
      const qty = Number(tr.querySelector(".it-qty").value) || 0;
      const price = Number(tr.querySelector(".it-price").value) || 0;
      const line = qty * price;
      total += line;
      tr.querySelector(".it-line").textContent = fmtRp(line);
    });
    const totalEl = document.getElementById(tbodyId + "-total");
    if (totalEl) totalEl.textContent = fmtRp(total);
    return total;
  }
  function readItems() {
    const items = [];
    tbody.querySelectorAll("tr").forEach((tr) => {
      items.push({
        product_id: tr.querySelector(".it-product").value,
        qty: Number(tr.querySelector(".it-qty").value),
        unit: tr.querySelector(".it-unit").value,
        unit_price: Number(tr.querySelector(".it-price").value),
      });
    });
    return items;
  }
  return { addRow, readItems, recalc };
}

function successPanel(title, txnNo, extraHTML = "") {
  return `<div class="alert alert-info mb-4" style="background:#dcfce7;border-color:#bbf7d0;color:#14532d">
    <p class="font-bold">${esc(title)}</p>
    <p class="mt-1">Nomor transaksi: <span class="font-mono font-bold">${esc(txnNo)}</span></p>
    ${extraHTML}</div>`;
}

// ---------------- FORM PENJUALAN ----------------
export async function renderPenjualan(container) {
  const branches = await myBranches();
  const products = await getProducts();
  const defaultBranch = branches.length === 1 ? branches[0].id : (branches[0] || {}).id || "";
  container.innerHTML = `
    <h2 class="text-xl font-bold text-slate-800 mb-1">Penjualan Telur</h2>
    <p class="text-sm text-slate-500 mb-4">Stok berkurang otomatis & HPP tercatat saat penjualan tersimpan di server.</p>
    <div id="sale-result"></div>
    <div class="card card-pad">
      <form id="sale-form" class="space-y-4">
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div><label class="field-label">Cabang</label>
            <select id="sale-branch" class="field-select" required>${branchOptions(branches, defaultBranch)}</select></div>
          <div><label class="field-label">Pelanggan <span class="font-normal text-slate-400">(opsional)</span></label>
            <input type="text" id="sale-customer" class="field-input" placeholder="Nama pelanggan"></div>
          <div><label class="field-label">Diskon (Rp)</label>
            <input type="number" id="sale-discount" class="field-input" min="0" step="1" value="0"></div>
        </div>
        <div class="table-wrap"><table class="data-table">
          <thead><tr><th>Produk</th><th>Jumlah</th><th>Satuan</th><th>Harga / satuan</th><th class="num">Subtotal</th><th></th></tr></thead>
          <tbody id="sale-items"></tbody>
        </table></div>
        <div class="flex flex-col sm:flex-row sm:items-center gap-3">
          <button type="button" id="sale-add" class="btn btn-ghost">+ Tambah Produk</button>
          <div class="sm:ml-auto text-right">
            <span class="text-sm text-slate-500">Total: </span>
            <span id="sale-items-total" class="text-xl font-bold text-pine-900 stat-num">Rp0</span>
          </div>
        </div>
        <div id="sale-error" class="alert alert-error hidden"></div>
        <button type="submit" id="sale-submit" class="btn btn-primary w-full md:w-auto">Simpan Penjualan</button>
        <p class="text-xs text-slate-500">Nomor transaksi hanya diterbitkan setelah server mengonfirmasi penyimpanan.</p>
      </form>
    </div>`;

  const rows = itemRows("sale-items", products);
  rows.addRow();
  container.querySelector("#sale-add").addEventListener("click", rows.addRow);

  container.querySelector("#sale-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errBox = container.querySelector("#sale-error");
    errBox.classList.add("hidden");
    const items = rows.readItems().filter((it) => it.qty > 0 && it.unit_price >= 0 && it.product_id);
    if (!items.length) {
      errBox.textContent = "Tambahkan minimal satu produk dengan jumlah lebih dari 0.";
      errBox.classList.remove("hidden");
      return;
    }
    const btn = container.querySelector("#sale-submit");
    btn.disabled = true; btn.textContent = "Menyimpan...";
    try {
      // Idempotency key generated per submit; sent as header AND body field.
      const data = await api.post("/sales", {
        branch_id: container.querySelector("#sale-branch").value,
        customer: container.querySelector("#sale-customer").value.trim() || null,
        discount: Number(container.querySelector("#sale-discount").value) || 0,
        items,
      });
      container.querySelector("#sale-result").innerHTML = successPanel(
        "Penjualan berhasil tersimpan.", data.txn_no || data.id || "-",
        `<p class="text-sm mt-1">Total: <strong>${fmtRp(data.total ?? 0)}</strong></p>`);
      container.querySelector("#sale-result").scrollIntoView({ behavior: "smooth", block: "start" });
      e.target.reset();
      container.querySelector("#sale-items").innerHTML = "";
      rows.addRow();
      toast("Penjualan tersimpan.", "success");
    } catch (err) {
      errBox.textContent = err.message; // e.g. stok kurang — never fake success
      errBox.classList.remove("hidden");
    } finally {
      btn.disabled = false; btn.textContent = "Simpan Penjualan";
    }
  });
}

// ---------------- PEMBELIAN + PENERIMAAN ----------------
export async function renderPembelian(container) {
  const branches = await myBranches();
  const products = await getProducts();
  const defaultBranch = branches.length === 1 ? branches[0].id : (branches[0] || {}).id || "";
  container.innerHTML = `
    <h2 class="text-xl font-bold text-slate-800 mb-1">Pembelian & Penerimaan Stok</h2>
    <p class="text-sm text-slate-500 mb-4">Pembelian tercatat sebagai <em>draft</em>, stok bertambah saat tombol <strong>Terima</strong> ditekan.</p>
    <div id="buy-result"></div>
    <div class="card card-pad mb-5">
      <h3 class="font-bold text-slate-800 mb-3">Form Pembelian Baru</h3>
      <form id="buy-form" class="space-y-4">
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div><label class="field-label">Cabang</label>
            <select id="buy-branch" class="field-select" required>${branchOptions(branches, defaultBranch)}</select></div>
          <div><label class="field-label">Supplier</label>
            <input type="text" id="buy-supplier" class="field-input" placeholder="Nama supplier" required></div>
          <div><label class="field-label">Ongkos angkut (Rp)</label>
            <input type="number" id="buy-freight" class="field-input" min="0" step="1" value="0"></div>
        </div>
        <div class="table-wrap"><table class="data-table">
          <thead><tr><th>Produk</th><th>Jumlah</th><th>Satuan</th><th>Harga / satuan</th><th class="num">Subtotal</th><th></th></tr></thead>
          <tbody id="buy-items"></tbody>
        </table></div>
        <div class="flex flex-col sm:flex-row sm:items-center gap-3">
          <button type="button" id="buy-add" class="btn btn-ghost">+ Tambah Produk</button>
          <div class="sm:ml-auto text-right">
            <span class="text-sm text-slate-500">Total: </span>
            <span id="buy-items-total" class="text-xl font-bold text-pine-900 stat-num">Rp0</span>
          </div>
        </div>
        <div id="buy-error" class="alert alert-error hidden"></div>
        <button type="submit" id="buy-submit" class="btn btn-primary w-full md:w-auto">Simpan sebagai Draft</button>
      </form>
    </div>
    <div class="card card-pad">
      <h3 class="font-bold text-slate-800 mb-3">Menunggu Penerimaan</h3>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>Nomor</th><th>Cabang</th><th>Supplier</th><th class="num">Total</th><th>Status</th><th>Aksi</th></tr></thead>
        <tbody id="buy-pending">${skeletonRows(6, 5)}</tbody>
      </table></div>
    </div>`;

  const rows = itemRows("buy-items", products);
  rows.addRow();
  container.querySelector("#buy-add").addEventListener("click", rows.addRow);

  container.querySelector("#buy-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errBox = container.querySelector("#buy-error");
    errBox.classList.add("hidden");
    const items = rows.readItems().filter((it) => it.qty > 0 && it.unit_price >= 0 && it.product_id);
    if (!items.length) {
      errBox.textContent = "Tambahkan minimal satu produk dengan jumlah lebih dari 0.";
      errBox.classList.remove("hidden");
      return;
    }
    const btn = container.querySelector("#buy-submit");
    btn.disabled = true; btn.textContent = "Menyimpan...";
    try {
      const data = await api.post("/purchases", {
        branch_id: container.querySelector("#buy-branch").value,
        supplier: container.querySelector("#buy-supplier").value.trim(),
        freight_cost: Number(container.querySelector("#buy-freight").value) || 0,
        items,
      });
      container.querySelector("#buy-result").innerHTML = successPanel(
        "Pembelian tersimpan sebagai draft.", data.txn_no || data.id || "-",
        `<button class="btn btn-accent btn-sm mt-2" id="buy-receive-now">Terima Sekarang</button>`);
      const nowBtn = container.querySelector("#buy-receive-now");
      if (nowBtn && data.id) {
        nowBtn.addEventListener("click", () => receivePurchase(data.id, data.txn_no, nowBtn));
      }
      e.target.reset();
      container.querySelector("#buy-items").innerHTML = "";
      rows.addRow();
      loadPending();
      toast("Draft pembelian tersimpan.", "success");
    } catch (err) {
      errBox.textContent = err.message;
      errBox.classList.remove("hidden");
    } finally {
      btn.disabled = false; btn.textContent = "Simpan sebagai Draft";
    }
  });

  async function receivePurchase(id, txnNo, btn) {
    if (!await confirmDialog(`Terima pembelian ${txnNo || ""}? Stok & HPP akan diperbarui.`)) return;
    if (btn) btn.disabled = true;
    try {
      const data = await api.post(`/purchases/${id}/receive`, {});
      toast(`Pembelian ${data.txn_no || txnNo || ""} diterima. Stok bertambah.`, "success");
      loadPending();
    } catch (err) {
      toast(err.message, "error");
      if (btn) btn.disabled = false;
    }
  }

  async function loadPending() {
    const body = container.querySelector("#buy-pending");
    body.innerHTML = skeletonRows(6, 5);
    try {
      const rowsAll = [];
      const codeOf = {};
      branches.forEach((b) => { codeOf[b.id] = b.code; });
      for (const b of branches) {
        try {
          const d = await api.get(`/branches/${b.id}/transactions`, { params: { limit: 50 } });
          const list = Array.isArray(d) ? d : d.items || d.transactions || [];
          list.filter((r) => String(r.txn_no || "").startsWith("PB-") && r.status === "draft")
            .forEach((r) => rowsAll.push({ ...r, _code: codeOf[r.branch_id] || b.code }));
        } catch (e) { /* skip */ }
      }
      rowsAll.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
      if (!rowsAll.length) {
        body.innerHTML = `<tr><td colspan="6">${emptyState("Tidak ada draft", "Semua pembelian sudah diterima.")}</td></tr>`;
        return;
      }
      body.innerHTML = rowsAll.slice(0, 30).map((r, i) => `
        <tr>
          <td class="font-mono text-xs font-semibold">${esc(r.txn_no)}</td>
          <td>${esc(r._code)}</td>
          <td>${esc(r.supplier || "-")}</td>
          <td class="num stat-num">${fmtRp(r.total ?? 0)}</td>
          <td>${statusBadge(r.status)}</td>
          <td><button class="btn btn-accent btn-sm" data-buy-receive="${i}">Terima</button></td>
        </tr>`).join("");
      const sliced = rowsAll.slice(0, 30);
      body.querySelectorAll("[data-buy-receive]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const r = sliced[Number(btn.dataset.buyReceive)];
          receivePurchase(r.id, r.txn_no, btn);
        });
      });
    } catch (err) {
      body.innerHTML = `<tr><td colspan="6">${errorAlert(err.message)}</td></tr>`;
    }
  }

  await loadPending();
}

// ---------------- TABEL PEMASUKAN (penjualan) ----------------
export async function renderPemasukan(container) {
  await renderTxnTable(container, {
    title: "Pemasukan",
    subtitle: "Riwayat transaksi penjualan telur per cabang.",
    prefix: "PJ-",
    showReverse: true,
  });
}

// ---------------- TABEL PENGELUARAN + FORM ----------------
export async function renderPengeluaran(container) {
  const branches = await myBranches();
  const defaultBranch = branches.length === 1 ? branches[0].id : (branches[0] || {}).id || "";
  container.innerHTML = `
    <h2 class="text-xl font-bold text-slate-800 mb-1">Pengeluaran</h2>
    <p class="text-sm text-slate-500 mb-4">Catat pengeluaran operasional & lihat riwayatnya.</p>
    <div class="card card-pad mb-5">
      <h3 class="font-bold text-slate-800 mb-3">Catat Pengeluaran</h3>
      <form id="exp-form" class="grid grid-cols-1 md:grid-cols-5 gap-3">
        <div><label class="field-label">Cabang</label>
          <select id="exp-branch" class="field-select" required>${branchOptions(branches, defaultBranch)}</select></div>
        <div><label class="field-label">Kategori</label>
          <select id="exp-cat" class="field-select" required>
            <option value="operasional">Operasional</option><option value="gaji">Gaji</option>
            <option value="sewa">Sewa</option><option value="listrik">Listrik & Air</option>
            <option value="transport">Transport</option><option value="lainnya">Lainnya</option>
          </select></div>
        <div><label class="field-label">Tanggal</label>
          <input type="date" id="exp-date" class="field-input" required></div>
        <div><label class="field-label">Jumlah (Rp)</label>
          <input type="number" id="exp-amount" class="field-input" min="1" step="1" required></div>
        <div class="md:col-span-5"><label class="field-label">Keterangan</label>
          <input type="text" id="exp-desc" class="field-input" placeholder="cth: Bayar listrik bulan Oktober" required></div>
        <div class="md:col-span-5"><div id="exp-error" class="alert alert-error hidden"></div>
          <button class="btn btn-primary" type="submit">Simpan Pengeluaran</button></div>
      </form>
    </div>
    <div id="exp-table"></div>`;

  container.querySelector("#exp-date").value = new Date().toISOString().slice(0, 10);
  container.querySelector("#exp-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errBox = container.querySelector("#exp-error");
    errBox.classList.add("hidden");
    const btn = e.target.querySelector('button[type="submit"]');
    btn.disabled = true;
    try {
      const data = await api.post("/expenses", {
        branch_id: container.querySelector("#exp-branch").value,
        category: container.querySelector("#exp-cat").value,
        description: container.querySelector("#exp-desc").value.trim(),
        amount: Number(container.querySelector("#exp-amount").value),
        expense_date: container.querySelector("#exp-date").value,
      });
      toast(`Pengeluaran ${data.txn_no || "tersimpan"}.`, "success");
      e.target.reset();
      container.querySelector("#exp-date").value = new Date().toISOString().slice(0, 10);
      tableView.reload();
    } catch (err) {
      errBox.textContent = err.message;
      errBox.classList.remove("hidden");
    } finally { btn.disabled = false; }
  });

  const tableView = await renderTxnTable(container.querySelector("#exp-table"), {
    title: "",
    subtitle: "",
    prefix: "KK-",
    showReverse: true,
    hideHeader: true,
  });
  return () => {};
}

// ---------------- TABEL TRANSAKSI GENERIK ----------------
async function renderTxnTable(container, { title, subtitle, prefix, showReverse, hideHeader }) {
  const branches = await myBranches();
  if (!hideHeader) {
    container.innerHTML = `
      <h2 class="text-xl font-bold text-slate-800 mb-1">${esc(title)}</h2>
      <p class="text-sm text-slate-500 mb-4">${esc(subtitle)}</p>`;
  }
  const wrap = document.createElement("div");
  container.appendChild(wrap);

  let all = [];
  let page = 1;
  const perPage = 15;
  const fid = `flt-${prefix.replace("-", "").toLowerCase()}-${Math.random().toString(36).slice(2, 7)}`;

  async function fetchAll() {
    wrap.innerHTML = filterBar(fid) + `
      <div class="card card-pad"><div class="table-wrap"><table class="data-table">
        <thead><tr><th>Nomor</th><th>Tanggal</th><th>Cabang</th><th>Keterangan</th>
        <th class="num">Nilai</th><th>Status</th>${showReverse && canReverse() ? "<th>Aksi</th>" : ""}</tr></thead>
        <tbody id="${fid}-body">${skeletonRows(showReverse ? 7 : 6, 8)}</tbody>
      </table></div><div id="${fid}-pag"></div></div>`;
    const { from, to } = readFilter(fid);
    all = [];
    const codeOf = {};
    branches.forEach((b) => { codeOf[b.id] = b.code; });
    for (const b of branches) {
      try {
        const d = await api.get(`/branches/${b.id}/transactions`, {
          params: { from: from || undefined, to: to || undefined, limit: 200 },
        });
        const list = Array.isArray(d) ? d : d.items || d.transactions || [];
        list.filter((r) => String(r.txn_no || "").startsWith(prefix))
          .forEach((r) => all.push({ ...r, _code: codeOf[r.branch_id] || b.code }));
      } catch (e) { /* skip branch on error; surface below if all fail */ }
    }
    if (!all.length) {
      const body = wrap.querySelector(`#${fid}-body`);
      if (body) body.innerHTML = `<tr><td colspan="${showReverse ? 7 : 6}">${emptyState("Belum ada data", "Transaksi akan muncul di sini.")}</td></tr>`;
    }
    // wire filter inputs (debounced)
    let t;
    ["from", "to"].forEach((k) => {
      wrap.querySelector(`#${fid}-${k}`).addEventListener("change", () => { page = 1; fetchAll(); });
    });
    const q = wrap.querySelector(`#${fid}-q`);
    if (q) q.addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => { page = 1; draw(); }, 300); });
    page = 1;
    draw();
  }

  function filtered() {
    const { q } = readFilter(fid);
    let rows = all.slice().sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
    if (q) {
      rows = rows.filter((r) =>
        String(r.txn_no || "").toLowerCase().includes(q) ||
        String(r.customer || r.supplier || r.description || r.category || "").toLowerCase().includes(q));
    }
    return rows;
  }

  function draw() {
    const body = wrap.querySelector(`#${fid}-body`);
    const pagBox = wrap.querySelector(`#${fid}-pag`);
    if (!body) return;
    const rows = filtered();
    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="${showReverse && canReverse() ? 7 : 6}">${emptyState("Tidak ada hasil", "Ubah filter atau kata kunci pencarian.")}</td></tr>`;
      if (pagBox) pagBox.innerHTML = "";
      return;
    }
    const pg = paginate(rows, page, perPage, (p) => { page = p; draw(); });
    body.innerHTML = pg.pageItems.map((r) => {
      const desc = r.customer || r.supplier || r.description || txnTypeLabel(r.txn_no);
      const val = r.total ?? r.amount ?? r.subtotal ?? 0;
      return `<tr>
        <td class="font-mono text-xs font-semibold whitespace-nowrap">${esc(r.txn_no || "-")}</td>
        <td class="text-xs whitespace-nowrap">${fmtDate(r.expense_date || r.created_at)}</td>
        <td>${esc(r._code || "-")}</td>
        <td class="max-w-[12rem] truncate" title="${esc(desc)}">${esc(desc)}</td>
        <td class="num stat-num font-semibold">${fmtRp(val)}</td>
        <td>${statusBadge(r.status)}</td>
        ${showReverse && canReverse() ? `<td>${["posted", "received", "draft"].includes(r.status)
          ? `<button class="btn btn-ghost btn-sm" data-reverse="${esc(r.id)}" data-txn="${esc(r.txn_no || "")}">Batalkan</button>`
          : `<span class="text-xs text-slate-400">-</span>`}</td>` : ""}
      </tr>`;
    }).join("");
    if (pagBox) { pagBox.innerHTML = pg.html; pg.wire(pagBox); }
    body.querySelectorAll("[data-reverse]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const reason = await reasonDialog(`Batalkan transaksi ${btn.dataset.txn}?`, "Alasan pembatalan");
        if (!reason) return;
        btn.disabled = true;
        try {
          await api.post(`/transactions/${btn.dataset.reverse}/reverse`, { reason }, { allowForbidden: true });
          toast(`Transaksi ${btn.dataset.txn} dibatalkan & tercatat di audit.`, "success");
          fetchAll();
        } catch (err) {
          toast(err.code === 403 ? "Anda tidak memiliki izin koreksi transaksi." : err.message, "error");
          btn.disabled = false;
        }
      });
    });
  }

  await fetchAll();
  return { reload: fetchAll };
}

// ---------------- DETAIL CABANG ----------------
export async function renderCabangDetail(container, code) {
  const branch = await branchByCode(code || "");
  if (!branch) {
    container.innerHTML = errorAlert(`Cabang "${esc(code || "")}" tidak ditemukan atau di luar cakupan Anda.`) +
      `<a href="#/dashboard" class="btn btn-primary mt-4">Kembali ke Dashboard</a>`;
    return;
  }
  const products = await getProducts();
  container.innerHTML = `
    <div class="flex items-center gap-3 mb-4">
      <span class="badge badge-green text-base px-3 py-1">${esc(branch.code)}</span>
      <div>
        <h2 class="text-xl font-bold text-slate-800">${esc(branch.name || branch.code)}</h2>
        <p class="text-sm text-slate-500">${esc(branch.address || "")}</p>
      </div>
    </div>
    <div id="cd-kpis" class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">${""}</div>
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-5">
      <div class="card card-pad">
        <h3 class="font-bold text-slate-800 mb-3">Ringkasan Stok</h3>
        <div class="table-wrap"><table class="data-table">
          <thead><tr><th>Produk</th><th class="num">Stok (butir)</th></tr></thead>
          <tbody id="cd-inv">${skeletonRows(2, 4)}</tbody>
        </table></div>
        <a href="#/persediaan" class="btn btn-ghost btn-sm mt-3">Kelola persediaan →</a>
      </div>
      <div class="card card-pad">
        <h3 class="font-bold text-slate-800 mb-3">Stok Menipis</h3>
        <div id="cd-low"><div class="skeleton" style="height:5rem"></div></div>
      </div>
    </div>
    <div class="card card-pad">
      <div class="flex flex-col md:flex-row md:items-center gap-3 mb-3">
        <h3 class="font-bold text-slate-800 flex-1">Transaksi Cabang</h3>
        <select id="cd-type" class="field-select md:w-56 no-print">
          <option value="">Semua jenis</option>
          <option value="PJ-">Penjualan</option><option value="PB-">Pembelian</option>
          <option value="KK-">Pengeluaran</option><option value="RT-">Retur</option>
          <option value="SO-">Stok Opname</option><option value="TR-">Transfer</option>
        </select>
      </div>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>Nomor</th><th>Jenis</th><th>Tanggal</th><th class="num">Nilai</th><th>Status</th><th>Petugas</th><th>Waktu Catat</th>
        ${canReverse() ? "<th>Aksi</th>" : ""}</tr></thead>
        <tbody id="cd-body">${skeletonRows(canReverse() ? 8 : 7, 8)}</tbody>
      </table></div>
      <div id="cd-pag"></div>
    </div>`;

  let all = [];
  let page = 1;
  const perPage = 15;

  async function load() {
    const kpiBox = container.querySelector("#cd-kpis");
    try {
      const s = await api.get(`/branches/${branch.id}/summary`);
      const t = s.totals || {};
      const kpi = (l, v) => `<div class="card card-pad kpi-card">
        <p class="text-xs font-semibold text-slate-500 uppercase">${esc(l)}</p>
        <p class="text-lg font-bold text-pine-900 stat-num mt-1">${v}</p></div>`;
      kpiBox.innerHTML =
        kpi("Penjualan", fmtRp(t.sales ?? 0)) +
        kpi("Kas Masuk", fmtRp(t.cash_in ?? 0)) +
        kpi("Kas Keluar", fmtRp(t.cash_out ?? 0)) +
        kpi("Nilai Persediaan", fmtRp(t.inventory_value ?? t.stock_value ?? 0));
      const low = s.low_stock || [];
      container.querySelector("#cd-low").innerHTML = low.length
        ? `<ul class="divide-y divide-slate-100">` + low.slice(0, 8).map((l) => `
            <li class="py-2 flex justify-between text-sm">
              <span class="font-medium text-slate-700">${esc(l.product_name || l.name || l.sku || "-")}</span>
              <span class="badge badge-amber">${fmtNum(l.qty_base ?? l.qty ?? 0)} butir</span></li>`).join("") + `</ul>`
        : `<p class="text-sm text-slate-500">Stok aman.</p>`;
    } catch (err) {
      kpiBox.innerHTML = `<div class="col-span-full">${errorAlert(err.message)}</div>`;
    }
    try {
      const d = await api.get(`/branches/${branch.id}/inventory`);
      const items = Array.isArray(d) ? d : d.items || d.inventory || [];
      const body = container.querySelector("#cd-inv");
      body.innerHTML = items.length ? items.map((it) => `
        <tr><td class="font-medium">${esc(it.product_name || it.name || "-")}</td>
        <td class="num stat-num">${fmtNum(it.qty_base ?? it.qty ?? 0)}</td></tr>`).join("")
        : `<tr><td colspan="2">${emptyState("Stok kosong")}</td></tr>`;
    } catch (err) {
      container.querySelector("#cd-inv").innerHTML = `<tr><td colspan="2">${errorAlert(err.message)}</td></tr>`;
    }
    await loadTxns();
  }

  async function loadTxns() {
    const body = container.querySelector("#cd-body");
    body.innerHTML = skeletonRows(canReverse() ? 8 : 7, 8);
    try {
      const d = await api.get(`/branches/${branch.id}/transactions`, { params: { limit: 200 } });
      all = Array.isArray(d) ? d : d.items || d.transactions || [];
      page = 1;
      draw();
    } catch (err) {
      body.innerHTML = `<tr><td colspan="${canReverse() ? 8 : 7}">${errorAlert(err.message)}</td></tr>`;
    }
  }

  function draw() {
    const body = container.querySelector("#cd-body");
    const type = container.querySelector("#cd-type").value;
    let rows = all.slice().sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
    if (type) rows = rows.filter((r) => String(r.txn_no || "").startsWith(type));
    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="${canReverse() ? 8 : 7}">${emptyState("Belum ada transaksi")}</td></tr>`;
      container.querySelector("#cd-pag").innerHTML = "";
      return;
    }
    const pg = paginate(rows, page, perPage, (p) => { page = p; draw(); });
    body.innerHTML = pg.pageItems.map((r) => `
      <tr>
        <td class="font-mono text-xs font-semibold whitespace-nowrap">${esc(r.txn_no || "-")}</td>
        <td>${esc(txnTypeLabel(r.txn_no))}</td>
        <td class="text-xs whitespace-nowrap">${fmtDate(r.expense_date || r.created_at)}</td>
        <td class="num stat-num font-semibold">${fmtRp(r.total ?? r.amount ?? 0)}</td>
        <td>${statusBadge(r.status)}</td>
        <td class="text-xs">${esc(r.created_by_name || r.created_by || "-")}</td>
        <td class="text-xs text-slate-500 whitespace-nowrap">${fmtDateTime(r.created_at)}</td>
        ${canReverse() ? `<td>${["posted", "received", "draft"].includes(r.status)
          ? `<button class="btn btn-ghost btn-sm" data-crev="${esc(r.id)}" data-ctn="${esc(r.txn_no || "")}">Batalkan</button>`
          : `<span class="text-xs text-slate-400">-</span>`}</td>` : ""}
      </tr>`).join("");
    const pagBox = container.querySelector("#cd-pag");
    pagBox.innerHTML = pg.html; pg.wire(pagBox);
    body.querySelectorAll("[data-crev]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const reason = await reasonDialog(`Batalkan transaksi ${btn.dataset.ctn}?`, "Alasan pembatalan");
        if (!reason) return;
        btn.disabled = true;
        try {
          await api.post(`/transactions/${btn.dataset.crev}/reverse`, { reason }, { allowForbidden: true });
          toast("Transaksi dibatalkan & tercatat di audit.", "success");
          loadTxns();
        } catch (err) {
          toast(err.code === 403 ? "Anda tidak memiliki izin koreksi transaksi." : err.message, "error");
          btn.disabled = false;
        }
      });
    });
  }

  container.querySelector("#cd-type").addEventListener("change", () => { page = 1; draw(); });
  await load();
}
