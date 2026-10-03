// Shared UI helpers: Indonesian formatting, skeletons, toasts, tables, pagination.
const EMPTY_IMG = "frontend/assets/pictures/empty.svg";

const rpFmt = new Intl.NumberFormat("id-ID", {
  style: "currency",
  currency: "IDR",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});
const numFmt = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 });
const dateFmt = new Intl.DateTimeFormat("id-ID", { day: "numeric", month: "short", year: "numeric" });
const dateTimeFmt = new Intl.DateTimeFormat("id-ID", {
  day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
});

export function fmtRp(n) {
  if (n === null || n === undefined || n === "") return "Rp0";
  const v = Number(n);
  if (Number.isNaN(v)) return "Rp0";
  return rpFmt.format(v);
}

/** Compact rupiah for chart labels: 1,5 jt / 250 rb */
export function fmtRpShort(n) {
  const v = Number(n) || 0;
  const abs = Math.abs(v);
  if (abs >= 1e9) return "Rp" + (v / 1e9).toLocaleString("id-ID", { maximumFractionDigits: 1 }) + " M";
  if (abs >= 1e6) return "Rp" + (v / 1e6).toLocaleString("id-ID", { maximumFractionDigits: 1 }) + " jt";
  if (abs >= 1e3) return "Rp" + (v / 1e3).toLocaleString("id-ID", { maximumFractionDigits: 1 }) + " rb";
  return "Rp" + v.toLocaleString("id-ID");
}

export function fmtNum(n, decimals = 2) {
  if (n === null || n === undefined || n === "") return "0";
  const v = Number(n);
  if (Number.isNaN(v)) return "0";
  return v.toLocaleString("id-ID", { maximumFractionDigits: decimals, minimumFractionDigits: 0 });
}

export function fmtDate(v) {
  if (!v) return "-";
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? "-" : dateFmt.format(d);
}

export function fmtDateTime(v) {
  if (!v) return "-";
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? "-" : dateTimeFmt.format(d);
}

export function fmtPct(n) {
  if (n === null || n === undefined || n === "") return "-";
  const v = Number(n);
  if (Number.isNaN(v)) return "-";
  return v.toLocaleString("id-ID", { maximumFractionDigits: 2 }) + "%";
}

export function esc(s) {
  return String(s === null || s === undefined ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Convert base qty (butir) into a display unit using product.units map. */
export function convertQty(qtyBase, units, unit) {
  const map = units || { butir: 1 };
  const factor = Number(map[unit] || 1);
  return Number(qtyBase) / factor;
}

export function unitOptions(units) {
  const map = units || { butir: 1 };
  return Object.keys(map);
}

/** "12,5 peti" style, plus exact base qty handled by caller. */
export function fmtQtyDisplay(qtyBase, units, unit) {
  return fmtNum(convertQty(qtyBase, units, unit)) + " " + unit;
}

const STATUS_BADGE = {
  posted: ["badge-green", "Tercatat"],
  received: ["badge-green", "Diterima"],
  draft: ["badge-amber", "Draft"],
  pending: ["badge-amber", "Menunggu"],
  in_transit: ["badge-blue", "Dalam Perjalanan"],
  voided: ["badge-red", "Dibatalkan"],
  cancelled: ["badge-red", "Dibatalkan"],
  approved: ["badge-green", "Disetujui"],
  rejected: ["badge-red", "Ditolak"],
};

export function statusBadge(status) {
  const [cls, label] = STATUS_BADGE[String(status)] || ["badge-slate", String(status || "-")];
  return `<span class="badge ${cls}">${esc(label)}</span>`;
}

export function txnTypeLabel(txnNo) {
  const p = String(txnNo || "").split("-")[0];
  return (
    { PJ: "Penjualan", PB: "Pembelian", KK: "Pengeluaran", RT: "Retur", SO: "Stok Opname", TR: "Transfer" }[p] ||
    "Transaksi"
  );
}

/** Skeleton rows for tables while loading. */
export function skeletonRows(cols = 5, rows = 6) {
  let h = "";
  for (let i = 0; i < rows; i++) {
    h += `<tr>${"<td><div class='skeleton' style='height:0.9rem'></div></td>".repeat(cols)}</tr>`;
  }
  return h;
}

export function skeletonCards(n = 4) {
  let h = "";
  for (let i = 0; i < n; i++) {
    h += `<div class="card card-pad"><div class="skeleton" style="height:1rem;width:55%"></div>
      <div class="skeleton mt-3" style="height:1.8rem;width:80%"></div>
      <div class="skeleton mt-2" style="height:0.8rem;width:40%"></div></div>`;
  }
  return h;
}

export function emptyState(title = "Belum ada data", subtitle = "Data akan muncul di sini setelah tersedia.") {
  return `<div class="flex flex-col items-center justify-center py-10 text-center">
    <img src="${EMPTY_IMG}" alt="Tidak ada data" class="w-28 h-28 opacity-80">
    <p class="mt-3 font-semibold text-slate-700">${esc(title)}</p>
    <p class="text-sm text-slate-500 mt-1">${esc(subtitle)}</p>
  </div>`;
}

export function errorAlert(msg) {
  return `<div class="alert alert-error" role="alert"><strong>Gagal memuat data.</strong><br>${esc(msg)}</div>`;
}

export function toast(msg, type = "info") {
  const root = document.getElementById("toast-root");
  if (!root) return;
  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  root.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transition = "opacity 0.3s";
    setTimeout(() => el.remove(), 350);
  }, 4200);
}

/** Simple client-side pagination over an array. Returns {pageItems, html}. */
export function paginate(items, page, perPage, onPage) {
  const total = items.length;
  const pages = Math.max(1, Math.ceil(total / perPage));
  const p = Math.min(Math.max(1, page), pages);
  const start = (p - 1) * perPage;
  const pageItems = items.slice(start, start + perPage);
  const btn = (label, target, disabled) =>
    `<button class="btn btn-ghost btn-sm" ${disabled ? "disabled" : ""} data-page="${target}">${label}</button>`;
  const html = `<div class="flex items-center justify-between mt-4 no-print">
      <span class="text-sm text-slate-500">Menampilkan ${total === 0 ? 0 : start + 1}-${Math.min(start + perPage, total)} dari ${total}</span>
      <div class="flex gap-1">
        ${btn("‹", p - 1, p <= 1)}
        <span class="text-sm px-2 py-1 font-semibold">${p} / ${pages}</span>
        ${btn("›", p + 1, p >= pages)}
      </div>
    </div>`;
  return { pageItems, html, wire: (root) => {
    root.querySelectorAll("[data-page]").forEach((b) =>
      b.addEventListener("click", () => onPage(Number(b.dataset.page)))
    );
  }};
}

/** Filter bar: date range + search. Returns HTML; caller wires events. */
export function filterBar(id, { showSearch = true, searchPlaceholder = "Cari nomor / keterangan..." } = {}) {
  return `<div class="card card-pad mb-4 no-print" id="${id}">
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
      <div><label class="field-label" for="${id}-from">Dari tanggal</label>
        <input type="date" id="${id}-from" class="field-input"></div>
      <div><label class="field-label" for="${id}-to">Sampai tanggal</label>
        <input type="date" id="${id}-to" class="field-input"></div>
      ${showSearch ? `<div class="col-span-2"><label class="field-label" for="${id}-q">Pencarian</label>
        <input type="search" id="${id}-q" class="field-input" placeholder="${esc(searchPlaceholder)}"></div>` : ""}
    </div>
  </div>`;
}

export function readFilter(id) {
  const g = (s) => document.getElementById(`${id}-${s}`);
  return {
    from: g("from") ? g("from").value : "",
    to: g("to") ? g("to").value : "",
    q: g("q") ? g("q").value.trim().toLowerCase() : "",
  };
}

/** Promise-based confirm dialog. */
export function confirmDialog(message, confirmLabel = "Ya, lanjutkan") {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "fixed inset-0 z-[110] flex items-center justify-center bg-black/50 p-4";
    overlay.innerHTML = `<div class="card card-pad max-w-sm w-full">
      <p class="font-semibold text-slate-800">${esc(message)}</p>
      <div class="flex justify-end gap-2 mt-5">
        <button class="btn btn-ghost" data-x="cancel">Batal</button>
        <button class="btn btn-danger" data-x="ok">${esc(confirmLabel)}</button>
      </div></div>`;
    const done = (v) => { overlay.remove(); resolve(v); };
    overlay.querySelector('[data-x="cancel"]').addEventListener("click", () => done(false));
    overlay.querySelector('[data-x="ok"]').addEventListener("click", () => done(true));
    overlay.addEventListener("click", (e) => { if (e.target === overlay) done(false); });
    document.body.appendChild(overlay);
  });
}

/** Prompt dialog with textarea (used for reverse reason). */
export function reasonDialog(title, label = "Alasan") {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "fixed inset-0 z-[110] flex items-center justify-center bg-black/50 p-4";
    overlay.innerHTML = `<div class="card card-pad max-w-md w-full">
      <p class="font-semibold text-slate-800 mb-3">${esc(title)}</p>
      <label class="field-label">${esc(label)} (wajib)</label>
      <textarea id="reason-text" class="field-input" rows="3" placeholder="Tulis alasan koreksi..."></textarea>
      <div class="flex justify-end gap-2 mt-4">
        <button class="btn btn-ghost" data-x="cancel">Batal</button>
        <button class="btn btn-primary" data-x="ok">Kirim</button>
      </div></div>`;
    const done = (v) => { overlay.remove(); resolve(v); };
    overlay.querySelector('[data-x="cancel"]').addEventListener("click", () => done(null));
    overlay.querySelector('[data-x="ok"]').addEventListener("click", () => {
      const v = overlay.querySelector("#reason-text").value.trim();
      if (!v) { toast("Alasan wajib diisi.", "error"); return; }
      done(v);
    });
    document.body.appendChild(overlay);
    setTimeout(() => overlay.querySelector("#reason-text").focus(), 50);
  });
}
