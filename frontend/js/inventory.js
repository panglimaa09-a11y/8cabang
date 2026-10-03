// Inventory views: stock & HPP, stocktake (opname), returns & damage.
import { api } from "./api.js";
import { myBranches, getProducts, isOwner, hasPermission } from "./auth.js";
import {
  fmtRp, fmtNum, fmtDateTime, esc, skeletonRows, emptyState, errorAlert,
  statusBadge, convertQty, unitOptions, toast, confirmDialog, filterBar, readFilter,
} from "./ui.js";

function canSeeCost() {
  return isOwner() || hasPermission("inventory.view_cost");
}
function canCorrect() {
  return isOwner() || hasPermission("transactions.correct");
}

// ---------------- PERSEDIAAN & HPP ----------------
export async function renderPersediaan(container) {
  const branches = await myBranches();
  container.innerHTML = `
    <div class="flex flex-col md:flex-row md:items-center gap-3 mb-4">
      <div class="flex-1">
        <h2 class="text-xl font-bold text-slate-800">Persediaan & HPP</h2>
        <p class="text-sm text-slate-500">Stok per produk dengan konversi satuan. HPP metode rata-rata bergerak.</p>
      </div>
      <div class="flex gap-2 no-print">
        <div><label class="field-label" for="inv-branch">Cabang</label>
          <select id="inv-branch" class="field-select"></select></div>
        <div><label class="field-label" for="inv-unit">Tampilkan dalam</label>
          <select id="inv-unit" class="field-select">
            <option value="peti">peti</option><option value="rak">rak</option>
            <option value="kg">kg</option><option value="butir">butir</option>
          </select></div>
      </div>
    </div>
    ${canSeeCost() ? "" : `<div class="alert alert-info mb-4">Data HPP dan nilai persediaan disembunyikan sesuai izin peran Anda.</div>`}
    <div class="card card-pad mb-5">
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>Produk</th><th>SKU</th><th class="num">Stok</th><th class="num">Stok dasar</th>
        ${canSeeCost() ? `<th class="num">Rata-rata HPP</th><th class="num">Nilai Persediaan</th>` : ""}</tr></thead>
        <tbody id="inv-body">${skeletonRows(canSeeCost() ? 6 : 4, 6)}</tbody>
      </table></div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div class="card card-pad">
        <h3 class="font-bold text-slate-800 mb-3">Transfer Antar Cabang</h3>
        <form id="transfer-form" class="space-y-3">
          <div class="grid grid-cols-2 gap-3">
            <div><label class="field-label">Dari cabang</label><select id="tr-from" class="field-select" required></select></div>
            <div><label class="field-label">Ke cabang</label><select id="tr-to" class="field-select" required></select></div>
          </div>
          <div><label class="field-label">Produk</label><select id="tr-product" class="field-select" required></select></div>
          <div class="grid grid-cols-2 gap-3">
            <div><label class="field-label">Jumlah</label><input type="number" id="tr-qty" class="field-input" min="0.01" step="0.01" required></div>
            <div><label class="field-label">Satuan</label><select id="tr-unit" class="field-select"></select></div>
          </div>
          <div id="tr-error" class="alert alert-error hidden"></div>
          <button class="btn btn-primary w-full" type="submit">Kirim Transfer</button>
          <p class="text-xs text-slate-500">Stok berkurang di cabang asal, status <em>dalam perjalanan</em> hingga diterima cabang tujuan.</p>
        </form>
      </div>
      <div class="card card-pad">
        <h3 class="font-bold text-slate-800 mb-3">Transfer Perlu Diterima</h3>
        <div id="transfer-pending"><div class="skeleton" style="height:6rem"></div></div>
      </div>
    </div>`;

  const branchSel = container.querySelector("#inv-branch");
  const unitSel = container.querySelector("#inv-unit");
  branches.forEach((b) => {
    const o = document.createElement("option");
    o.value = b.id; o.textContent = `${b.code} — ${b.name || ""}`;
    branchSel.appendChild(o);
  });

  const products = await getProducts();
  const prodSel = container.querySelector("#tr-product");
  const unitSelTr = container.querySelector("#tr-unit");
  products.forEach((p) => {
    const o = document.createElement("option");
    o.value = p.id; o.textContent = `${p.name} (${p.sku})`;
    prodSel.appendChild(o);
  });
  const trFrom = container.querySelector("#tr-from");
  const trTo = container.querySelector("#tr-to");
  branches.forEach((b) => {
    const label = `${b.code} — ${b.name || ""}`;
    trFrom.add(new Option(label, b.id));
    trTo.add(new Option(label, b.id));
  });
  if (branches[1]) trTo.value = branches[1].id;

  function syncTrUnits() {
    const p = products.find((x) => x.id === prodSel.value);
    const units = (p && p.units) || { butir: 1 };
    unitSelTr.innerHTML = unitOptions(units).map((u) => `<option value="${esc(u)}">${esc(u)}</option>`).join("");
  }
  prodSel.addEventListener("change", syncTrUnits);
  syncTrUnits();

  async function loadInventory() {
    const body = container.querySelector("#inv-body");
    const unit = unitSel.value;
    body.innerHTML = skeletonRows(canSeeCost() ? 6 : 4, 6);
    try {
      const data = await api.get(`/branches/${branchSel.value}/inventory`);
      const items = Array.isArray(data) ? data : data.items || data.inventory || [];
      if (!items.length) {
        body.innerHTML = `<tr><td colspan="${canSeeCost() ? 6 : 4}">${emptyState("Stok kosong", "Belum ada persediaan tercatat di cabang ini.")}</td></tr>`;
        return;
      }
      body.innerHTML = items.map((it) => {
        const units = it.units || (products.find((p) => p.id === it.product_id) || {}).units || { butir: 1 };
        const qtyBase = Number(it.qty_base ?? it.qty ?? 0);
        const avg = it.avg_cost !== undefined && it.avg_cost !== null ? Number(it.avg_cost) : null;
        const val = avg !== null ? qtyBase * avg : null;
        return `<tr>
          <td class="font-semibold">${esc(it.product_name || it.name || "-")}</td>
          <td class="font-mono text-xs">${esc(it.sku || "-")}</td>
          <td class="num stat-num font-semibold text-pine-900">${fmtNum(convertQty(qtyBase, units, unit))} ${esc(unit)}</td>
          <td class="num stat-num text-slate-500">${fmtNum(qtyBase)} butir</td>
          ${canSeeCost() ? `<td class="num stat-num">${avg !== null ? fmtRp(avg) + " /butir" : "-"}</td>
          <td class="num stat-num font-semibold">${val !== null ? fmtRp(val) : "-"}</td>` : ""}
        </tr>`;
      }).join("");
    } catch (err) {
      body.innerHTML = `<tr><td colspan="${canSeeCost() ? 6 : 4}">${errorAlert(err.message)}</td></tr>`;
    }
  }

  async function loadPendingTransfers() {
    const box = container.querySelector("#transfer-pending");
    try {
      const rows = [];
      for (const b of branches) {
        try {
          const d = await api.get(`/branches/${b.id}/transactions`, { params: { limit: 50 } });
          const list = Array.isArray(d) ? d : d.items || d.transactions || [];
          list.filter((r) => String(r.txn_no || "").startsWith("TR-") && r.status === "in_transit")
            .forEach((r) => rows.push({ ...r, _code: b.code }));
        } catch (e) { /* skip branch on error */ }
      }
      if (!rows.length) {
        box.innerHTML = `<p class="text-sm text-slate-500">Tidak ada transfer yang menunggu penerimaan.</p>`;
        return;
      }
      box.innerHTML = `<ul class="divide-y divide-slate-100">` + rows.map((r, i) => `
        <li class="py-2 flex items-center justify-between gap-2">
          <div class="min-w-0">
            <p class="text-sm font-mono font-semibold">${esc(r.txn_no)}</p>
            <p class="text-xs text-slate-500">${esc(r._code)} → ${esc(r.branch_to_code || r.branch_id_to || "tujuan")} · ${fmtNum(r.qty_base ?? r.qty ?? 0)} butir</p>
          </div>
          <button class="btn btn-accent btn-sm" data-tr-receive="${i}">Terima</button>
        </li>`).join("") + `</ul>`;
      box.querySelectorAll("[data-tr-receive]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const r = rows[Number(btn.dataset.trReceive)];
          if (!await confirmDialog(`Terima transfer ${r.txn_no}? Stok akan bertambah di cabang tujuan.`)) return;
          btn.disabled = true;
          try {
            await api.post(`/transfers/${r.id}/receive`, {});
            toast(`Transfer ${r.txn_no} diterima.`, "success");
            loadPendingTransfers(); loadInventory();
          } catch (err) {
            toast(err.message, "error"); btn.disabled = false;
          }
        });
      });
    } catch (err) {
      box.innerHTML = errorAlert(err.message);
    }
  }

  container.querySelector("#transfer-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errBox = container.querySelector("#tr-error");
    errBox.classList.add("hidden");
    const btn = e.target.querySelector('button[type="submit"]');
    btn.disabled = true;
    try {
      const data = await api.post("/transfers", {
        branch_id_from: trFrom.value,
        branch_id_to: trTo.value,
        product_id: prodSel.value,
        qty: Number(container.querySelector("#tr-qty").value),
        unit: unitSelTr.value,
      });
      toast(`Transfer tercatat: ${data.txn_no || "berhasil"}. Menunggu penerimaan.`, "success");
      e.target.reset(); syncTrUnits();
      loadPendingTransfers();
    } catch (err) {
      errBox.textContent = err.message;
      errBox.classList.remove("hidden");
    } finally { btn.disabled = false; }
  });

  branchSel.addEventListener("change", loadInventory);
  unitSel.addEventListener("change", loadInventory);
  await loadInventory();
  await loadPendingTransfers();
}

// ---------------- STOK OPNAME ----------------
export async function renderOpname(container) {
  const branches = await myBranches();
  const products = await getProducts();
  container.innerHTML = `
    <h2 class="text-xl font-bold text-slate-800 mb-1">Stok Opname</h2>
    <p class="text-sm text-slate-500 mb-4">Hitung fisik lalu ajukan penyesuaian. Penyesuaian berlaku setelah disetujui.</p>
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div class="card card-pad">
        <h3 class="font-bold text-slate-800 mb-3">Form Opname Baru</h3>
        <form id="so-form" class="space-y-3">
          <div><label class="field-label">Cabang</label><select id="so-branch" class="field-select" required></select></div>
          <div><label class="field-label">Produk</label><select id="so-product" class="field-select" required></select></div>
          <div class="grid grid-cols-2 gap-3">
            <div><label class="field-label">Hasil hitung</label>
              <input type="number" id="so-qty" class="field-input" min="0" step="0.01" required></div>
            <div><label class="field-label">Satuan</label><select id="so-unit" class="field-select"></select></div>
          </div>
          <div id="so-sys" class="text-sm text-slate-500"></div>
          <div id="so-error" class="alert alert-error hidden"></div>
          <button class="btn btn-primary w-full" type="submit">Ajukan Opname</button>
        </form>
      </div>
      <div class="card card-pad">
        <h3 class="font-bold text-slate-800 mb-3">Riwayat Opname</h3>
        <div class="table-wrap"><table class="data-table">
          <thead><tr><th>Nomor</th><th>Produk</th><th class="num">Selisih</th><th>Status</th><th>Aksi</th></tr></thead>
          <tbody id="so-body">${skeletonRows(5, 5)}</tbody>
        </table></div>
        ${canCorrect() ? "" : `<p class="text-xs text-slate-500 mt-3">Persetujuan opname memerlukan izin koreksi transaksi.</p>`}
      </div>
    </div>`;

  const brSel = container.querySelector("#so-branch");
  const prSel = container.querySelector("#so-product");
  const unSel = container.querySelector("#so-unit");
  branches.forEach((b) => brSel.add(new Option(`${b.code} — ${b.name || ""}`, b.id)));
  products.forEach((p) => prSel.add(new Option(`${p.name} (${p.sku})`, p.id)));
  const syncUnits = () => {
    const p = products.find((x) => x.id === prSel.value);
    const units = (p && p.units) || { butir: 1 };
    unSel.innerHTML = unitOptions(units).map((u) => `<option value="${esc(u)}">${esc(u)}</option>`).join("");
  };
  prSel.addEventListener("change", syncUnits); syncUnits();

  async function refreshSystemQty() {
    const box = container.querySelector("#so-sys");
    try {
      const data = await api.get(`/branches/${brSel.value}/inventory`);
      const items = Array.isArray(data) ? data : data.items || data.inventory || [];
      const it = items.find((x) => x.product_id === prSel.value);
      const p = products.find((x) => x.id === prSel.value);
      const units = (p && p.units) || { butir: 1 };
      box.textContent = it
        ? `Stok sistem saat ini: ${fmtNum(convertQty(Number(it.qty_base || 0), units, unSel.value))} ${unSel.value}`
        : "Produk belum memiliki stok di cabang ini.";
    } catch (e) { box.textContent = ""; }
  }
  brSel.addEventListener("change", () => { refreshSystemQty(); loadHistory(); });
  prSel.addEventListener("change", () => { syncUnits(); refreshSystemQty(); });
  unSel.addEventListener("change", refreshSystemQty);

  async function loadHistory() {
    const body = container.querySelector("#so-body");
    body.innerHTML = skeletonRows(5, 5);
    try {
      const rows = [];
      for (const b of branches) {
        try {
          const d = await api.get(`/branches/${b.id}/transactions`, { params: { limit: 50 } });
          const list = Array.isArray(d) ? d : d.items || d.transactions || [];
          list.filter((r) => String(r.txn_no || "").startsWith("SO-")).forEach((r) => rows.push(r));
        } catch (e) { /* skip */ }
      }
      rows.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
      const top = rows.slice(0, 20);
      if (!top.length) {
        body.innerHTML = `<tr><td colspan="5">${emptyState("Belum ada opname")}</td></tr>`;
        return;
      }
      body.innerHTML = top.map((r) => `
        <tr>
          <td class="font-mono text-xs font-semibold">${esc(r.txn_no)}</td>
          <td>${esc(r.product_name || r.product_id || "-")}</td>
          <td class="num stat-num ${Number(r.variance || 0) < 0 ? "text-red-600" : "text-green-700"}">
            ${Number(r.variance || 0) > 0 ? "+" : ""}${fmtNum(r.variance ?? 0)} butir</td>
          <td>${statusBadge(r.status)}</td>
          <td class="whitespace-nowrap">
            ${r.status === "pending" && canCorrect()
              ? `<button class="btn btn-accent btn-sm" data-so-approve="${esc(r.id)}">Setujui</button>`
              : `<span class="text-xs text-slate-400">-</span>`}
          </td>
        </tr>`).join("");
      body.querySelectorAll("[data-so-approve]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          if (!await confirmDialog("Setujui opname ini? Stok akan disesuaikan dengan hasil hitung.")) return;
          btn.disabled = true;
          try {
            await api.post(`/stocktakes/${btn.dataset.soApprove}/approve`, {});
            toast("Opname disetujui, stok disesuaikan.", "success");
            loadHistory(); refreshSystemQty();
          } catch (err) { toast(err.message, "error"); btn.disabled = false; }
        });
      });
    } catch (err) {
      body.innerHTML = `<tr><td colspan="5">${errorAlert(err.message)}</td></tr>`;
    }
  }

  container.querySelector("#so-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errBox = container.querySelector("#so-error");
    errBox.classList.add("hidden");
    const btn = e.target.querySelector('button[type="submit"]');
    btn.disabled = true;
    try {
      const data = await api.post("/stocktakes", {
        branch_id: brSel.value,
        product_id: prSel.value,
        counted_qty: Number(container.querySelector("#so-qty").value),
        unit: unSel.value,
      });
      toast(`Opname ${data.txn_no || "tercatat"} diajukan, menunggu persetujuan.`, "success");
      e.target.reset(); syncUnits();
      loadHistory(); refreshSystemQty();
    } catch (err) {
      errBox.textContent = err.message;
      errBox.classList.remove("hidden");
    } finally { btn.disabled = false; }
  });

  await refreshSystemQty();
  await loadHistory();
}

// ---------------- RETUR & KERUSAKAN ----------------
export async function renderRetur(container) {
  const branches = await myBranches();
  const products = await getProducts();
  container.innerHTML = `
    <h2 class="text-xl font-bold text-slate-800 mb-1">Retur & Kerusakan</h2>
    <p class="text-sm text-slate-500 mb-4">Retur penjualan menambah stok, retur pembelian & kerusakan mengurangi stok.</p>
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div class="card card-pad">
        <h3 class="font-bold text-slate-800 mb-3">Catat Retur / Kerusakan</h3>
        <form id="rt-form" class="space-y-3">
          <div><label class="field-label">Cabang</label><select id="rt-branch" class="field-select" required></select></div>
          <div><label class="field-label">Jenis</label>
            <select id="rt-type" class="field-select" required>
              <option value="sales_return">Retur penjualan (stok +)</option>
              <option value="purchase_return">Retur pembelian (stok -)</option>
              <option value="damage">Telur rusak / pecah (stok -)</option>
            </select></div>
          <div><label class="field-label">ID transaksi acuan <span class="font-normal text-slate-400">(UUID, opsional)</span></label>
            <input type="text" id="rt-ref" class="field-input" placeholder="cth: 550e8400-e29b-41d4-a716-446655440000"></div>
          <div><label class="field-label">Produk</label><select id="rt-product" class="field-select" required></select></div>
          <div class="grid grid-cols-2 gap-3">
            <div><label class="field-label">Jumlah</label>
              <input type="number" id="rt-qty" class="field-input" min="0.01" step="0.01" required></div>
            <div><label class="field-label">Satuan</label><select id="rt-unit" class="field-select"></select></div>
          </div>
          <div><label class="field-label">Alasan</label>
            <textarea id="rt-reason" class="field-input" rows="2" placeholder="cth: pecah saat pengiriman" required></textarea></div>
          <div id="rt-error" class="alert alert-error hidden"></div>
          <button class="btn btn-primary w-full" type="submit">Catat</button>
        </form>
      </div>
      <div class="card card-pad">
        <h3 class="font-bold text-slate-800 mb-3">Riwayat Retur</h3>
        <div class="table-wrap"><table class="data-table">
          <thead><tr><th>Nomor</th><th>Jenis</th><th class="num">Jumlah</th><th>Waktu</th></tr></thead>
          <tbody id="rt-body">${skeletonRows(4, 6)}</tbody>
        </table></div>
      </div>
    </div>`;

  const brSel = container.querySelector("#rt-branch");
  const prSel = container.querySelector("#rt-product");
  const unSel = container.querySelector("#rt-unit");
  branches.forEach((b) => brSel.add(new Option(`${b.code} — ${b.name || ""}`, b.id)));
  products.forEach((p) => prSel.add(new Option(`${p.name} (${p.sku})`, p.id)));
  const syncUnits = () => {
    const p = products.find((x) => x.id === prSel.value);
    const units = (p && p.units) || { butir: 1 };
    unSel.innerHTML = unitOptions(units).map((u) => `<option value="${esc(u)}">${esc(u)}</option>`).join("");
  };
  prSel.addEventListener("change", syncUnits); syncUnits();

  async function loadHistory() {
    const body = container.querySelector("#rt-body");
    body.innerHTML = skeletonRows(4, 6);
    try {
      const rows = [];
      for (const b of branches) {
        try {
          const d = await api.get(`/branches/${b.id}/transactions`, { params: { limit: 50 } });
          const list = Array.isArray(d) ? d : d.items || d.transactions || [];
          list.filter((r) => String(r.txn_no || "").startsWith("RT-")).forEach((r) => rows.push(r));
        } catch (e) { /* skip */ }
      }
      rows.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
      const top = rows.slice(0, 20);
      if (!top.length) { body.innerHTML = `<tr><td colspan="4">${emptyState("Belum ada retur")}</td></tr>`; return; }
      const typeLabel = { sales_return: "Retur jual", purchase_return: "Retur beli", damage: "Rusak" };
      body.innerHTML = top.map((r) => `
        <tr>
          <td class="font-mono text-xs font-semibold">${esc(r.txn_no)}</td>
          <td>${esc(typeLabel[r.return_type] || r.return_type || "-")}</td>
          <td class="num stat-num">${fmtNum(r.qty_base ?? r.qty ?? 0)} butir</td>
          <td class="text-xs text-slate-500 whitespace-nowrap">${fmtDateTime(r.created_at)}</td>
        </tr>`).join("");
    } catch (err) {
      body.innerHTML = `<tr><td colspan="4">${errorAlert(err.message)}</td></tr>`;
    }
  }

  container.querySelector("#rt-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errBox = container.querySelector("#rt-error");
    errBox.classList.add("hidden");
    const btn = e.target.querySelector('button[type="submit"]');
    btn.disabled = true;
    try {
      const type = container.querySelector("#rt-type").value;
      const payload = {
        branch_id: brSel.value,
        product_id: prSel.value,
        qty: Number(container.querySelector("#rt-qty").value),
        unit: unSel.value,
        reason: container.querySelector("#rt-reason").value.trim(),
      };
      // Contract return_type is sales_return|purchase_return; damage reduces stock
      // the same way as a purchase return, distinguished by the reason text.
      payload.return_type = type === "damage" ? "purchase_return" : type;
      const ref = container.querySelector("#rt-ref").value.trim();
      if (ref) {
        if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(ref)) {
          errBox.textContent = "ID transaksi acuan harus berupa UUID yang valid, atau kosongkan.";
          errBox.classList.remove("hidden");
          btn.disabled = false;
          return;
        }
        payload.ref_txn_id = ref;
      }
      const data = await api.post("/returns", payload);
      toast(`Tercatat: ${data.txn_no || "retur berhasil"}.`, "success");
      e.target.reset(); syncUnits();
      loadHistory();
    } catch (err) {
      errBox.textContent = err.message;
      errBox.classList.remove("hidden");
    } finally { btn.disabled = false; }
  });

  await loadHistory();
}
