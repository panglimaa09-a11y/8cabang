// Owner dashboard: 8 branch cards, KPIs, pure-canvas bar chart, low stock, recent txns.
import { api } from "./api.js";
import { myBranches, isOwner } from "./auth.js";
import {
  fmtRp, fmtRpShort, fmtNum, fmtDateTime, esc, skeletonCards, skeletonRows,
  emptyState, errorAlert, statusBadge,
} from "./ui.js";

let chartCleanup = null;

export async function renderDashboard(container) {
  const owner = isOwner();
  container.innerHTML = `
    <div class="flex flex-col md:flex-row md:items-center gap-3 mb-4 no-print">
      <div class="flex-1">
        <h2 class="text-xl font-bold text-slate-800">Dashboard ${owner ? "Owner" : ""}</h2>
        <p class="text-sm text-slate-500">Pantau operasional ${owner ? "8 cabang" : "cabang Anda"} secara real-time.</p>
      </div>
      <div class="flex flex-wrap gap-2 items-end">
        <div><label class="field-label" for="flt-from">Dari</label>
          <input type="date" id="flt-from" class="field-input"></div>
        <div><label class="field-label" for="flt-to">Sampai</label>
          <input type="date" id="flt-to" class="field-input"></div>
        ${owner ? `<div><label class="field-label" for="flt-branch">Cabang</label>
          <select id="flt-branch" class="field-select"><option value="">Semua cabang</option></select></div>` : ""}
        <button id="flt-apply" class="btn btn-primary">Terapkan</button>
      </div>
    </div>

    <div id="kpi-grid" class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">${skeletonCards(owner ? 8 : 4)}</div>

    <h3 class="font-bold text-slate-800 mb-3">Cabang</h3>
    <div id="branch-cards" class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 mb-5">${skeletonCards(8)}</div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-5">
      <div class="card card-pad">
        <h3 class="font-bold text-slate-800 mb-1">Performa Penjualan per Cabang</h3>
        <p class="text-xs text-slate-500 mb-3">Total penjualan pada periode filter.</p>
        <div class="chart-box"><canvas id="sales-chart"></canvas></div>
      </div>
      <div class="card card-pad">
        <h3 class="font-bold text-slate-800 mb-3">Stok Menipis</h3>
        <div id="low-stock"><div class="skeleton" style="height:8rem"></div></div>
      </div>
    </div>

    <div class="card card-pad">
      <h3 class="font-bold text-slate-800 mb-3">Transaksi Terbaru</h3>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>Nomor</th><th>Cabang</th><th>Jenis</th><th class="num">Nilai</th><th>Status</th><th>Waktu</th></tr></thead>
        <tbody id="recent-body">${skeletonRows(6, 5)}</tbody>
      </table></div>
    </div>`;

  const branches = await myBranches();
  if (owner) {
    const sel = container.querySelector("#flt-branch");
    branches.forEach((b) => {
      const o = document.createElement("option");
      o.value = b.code; o.textContent = `${b.code} — ${b.name || ""}`;
      sel.appendChild(o);
    });
  }

  async function load() {
    const from = container.querySelector("#flt-from").value;
    const to = container.querySelector("#flt-to").value;
    const branchCode = owner ? container.querySelector("#flt-branch").value : "";
    try {
      await loadData(container, { from, to, branchCode, branches, owner });
    } catch (err) {
      container.querySelector("#kpi-grid").innerHTML =
        `<div class="col-span-full">${errorAlert(err.message)}</div>`;
    }
  }

  container.querySelector("#flt-apply").addEventListener("click", load);
  await load();

  return () => { if (chartCleanup) chartCleanup(); };
}

async function loadData(container, { from, to, branchCode, branches, owner }) {
  const params = { from: from || undefined, to: to || undefined };
  const scoped = branchCode
    ? branches.filter((b) => b.code === branchCode)
    : branches;

  // Owner consolidated report: per-branch + combined totals (profit KPIs).
  let consolidated = null;
  if (owner) {
    try {
      consolidated = await api.get("/reports/consolidated", { params });
    } catch (e) {
      consolidated = null; // fall back to per-branch summaries
    }
  }

  // Per-branch summaries (sales, cash, inventory value, low stock, recent).
  const summaries = await Promise.all(
    scoped.map(async (b) => {
      try {
        const s = await api.get(`/branches/${b.id}/summary`, { params });
        return { branch: b, summary: s };
      } catch (e) {
        return { branch: b, summary: null, error: e.message };
      }
    })
  );

  renderKpis(container, { consolidated, summaries, owner });
  renderBranchCards(container, summaries, consolidated);
  renderLowStock(container, summaries);
  renderRecent(container, summaries);
  drawSalesChart(container, summaries, consolidated);
}

function totalsOf(s) {
  const t = (s && (s.totals || s.summary || {})) || {};
  return {
    sales: Number(t.sales ?? t.total_sales ?? 0),
    cash_in: Number(t.cash_in ?? 0),
    cash_out: Number(t.cash_out ?? 0),
    inventory_value: Number(t.inventory_value ?? t.stock_value ?? 0),
    cogs: Number(t.cogs ?? t.hpp ?? 0),
  };
}

function renderKpis(container, { consolidated, summaries, owner }) {
  const grid = container.querySelector("#kpi-grid");
  const agg = { sales: 0, cash_in: 0, cash_out: 0, inventory_value: 0, cogs: 0 };
  summaries.forEach(({ summary }) => {
    const t = totalsOf(summary);
    agg.sales += t.sales; agg.cash_in += t.cash_in; agg.cash_out += t.cash_out;
    agg.inventory_value += t.inventory_value; agg.cogs += t.cogs;
  });

  const ct = (consolidated && (consolidated.totals || consolidated.total)) || null;
  const kpi = (label, value, sub = "") => `
    <div class="card card-pad kpi-card">
      <p class="text-xs font-semibold text-slate-500 uppercase tracking-wide">${esc(label)}</p>
      <p class="text-lg md:text-xl font-bold text-pine-900 stat-num mt-1">${value}</p>
      ${sub ? `<p class="text-xs text-slate-500 mt-1">${sub}</p>` : ""}
    </div>`;

  let html = kpi("Total Penjualan", fmtRp(agg.sales));
  html += kpi("Kas Masuk", fmtRp(agg.cash_in));
  html += kpi("Kas Keluar", fmtRp(agg.cash_out));
  html += kpi("Nilai Persediaan", fmtRp(agg.inventory_value));

  // Profit KPIs: owner only, from consolidated report (never fetched for karyawan).
  if (owner && ct) {
    const revenue = Number(ct.revenue_net ?? ct.sales ?? agg.sales);
    const cogs = Number(ct.cogs ?? agg.cogs);
    const net = Number(ct.net_profit ?? ct.net ?? (revenue - cogs));
    const margin = revenue > 0 ? (net / revenue) * 100 : null;
    html += kpi("HPP Penjualan", fmtRp(cogs));
    html += kpi("Laba Bersih", fmtRp(net));
    html += kpi("Margin Bersih", margin === null ? "-" : margin.toLocaleString("id-ID", { maximumFractionDigits: 2 }) + "%",
      "Dari total gabungan");
    html += kpi("Kas Bersih", fmtRp(agg.cash_in - agg.cash_out), "Arus kas, bukan laba");
  }
  grid.innerHTML = html;
}

function renderBranchCards(container, summaries, consolidated) {
  const box = container.querySelector("#branch-cards");
  const perBranch = {};
  const arr = (consolidated && (consolidated.branches || consolidated.per_branch)) || [];
  arr.forEach((r) => {
    const code = r.code || r.branch_code;
    if (code) perBranch[String(code).toUpperCase()] = r;
  });

  box.innerHTML = summaries.map(({ branch, summary, error }) => {
    const t = totalsOf(summary);
    const pb = perBranch[String(branch.code).toUpperCase()] || {};
    const sales = Number(pb.sales ?? pb.total_sales ?? t.sales);
    const lowCount = summary && Array.isArray(summary.low_stock) ? summary.low_stock.length : 0;
    return `<a href="#/cabang/${esc(branch.code)}" class="card card-pad hover:shadow-md transition block">
      <div class="flex items-center justify-between mb-2">
        <span class="badge ${summary ? "badge-green" : "badge-red"}">${esc(branch.code)}</span>
        ${lowCount > 0 ? `<span class="badge badge-amber">${lowCount} stok menipis</span>` : ""}
      </div>
      <p class="font-bold text-slate-800 truncate">${esc(branch.name || branch.code)}</p>
      ${error
        ? `<p class="text-xs text-red-600 mt-2">Gagal memuat: ${esc(error)}</p>`
        : `<p class="text-lg font-bold text-pine-900 stat-num mt-1">${fmtRp(sales)}</p>
           <p class="text-xs text-slate-500 mt-1">Kas bersih: ${fmtRp(t.cash_in - t.cash_out)}</p>`}
    </a>`;
  }).join("") || emptyState("Tidak ada cabang", "Akun Anda belum ditugaskan ke cabang mana pun.");
}

function renderLowStock(container, summaries) {
  const box = container.querySelector("#low-stock");
  const items = [];
  summaries.forEach(({ branch, summary }) => {
    const low = (summary && summary.low_stock) || [];
    low.forEach((l) => items.push({ branch, ...l }));
  });
  if (!items.length) {
    box.innerHTML = `<p class="text-sm text-slate-500">Semua stok aman. Tidak ada produk di bawah batas minimum.</p>`;
    return;
  }
  box.innerHTML = `<ul class="divide-y divide-slate-100">` + items.slice(0, 12).map((it) => `
    <li class="py-2 flex items-center justify-between gap-2">
      <div class="min-w-0">
        <p class="text-sm font-semibold text-slate-700 truncate">${esc(it.product_name || it.name || it.sku || "Produk")}</p>
        <p class="text-xs text-slate-500">${esc(it.branch.code)} — ${esc(it.branch.name || "")}</p>
      </div>
      <span class="badge badge-amber whitespace-nowrap">${esc(fmtNum(it.qty_base ?? it.qty ?? 0))} butir</span>
    </li>`).join("") + `</ul>
    ${items.length > 12 ? `<p class="text-xs text-slate-500 mt-2">+ ${items.length - 12} lainnya</p>` : ""}`;
}

function renderRecent(container, summaries) {
  const body = container.querySelector("#recent-body");
  const all = [];
  const codeOf = {};
  summaries.forEach(({ branch }) => { codeOf[branch.id] = branch.code; });
  summaries.forEach(({ branch, summary }) => {
    const rec = (summary && summary.recent) || [];
    rec.forEach((r) => all.push({ ...r, _code: codeOf[r.branch_id] || branch.code }));
  });
  all.sort((a, b) => new Date(b.created_at || b.txn_date || 0) - new Date(a.created_at || a.txn_date || 0));
  const top = all.slice(0, 10);
  if (!top.length) {
    body.innerHTML = `<tr><td colspan="6">${emptyState("Belum ada transaksi", "Transaksi terbaru akan tampil di sini.")}</td></tr>`;
    return;
  }
  body.innerHTML = top.map((r) => `
    <tr>
      <td class="font-mono text-xs font-semibold">${esc(r.txn_no || "-")}</td>
      <td>${esc(r._code || "-")}</td>
      <td>${esc(r.txn_type || r.type || "-")}</td>
      <td class="num stat-num">${fmtRp(r.total ?? r.amount ?? r.value ?? 0)}</td>
      <td>${statusBadge(r.status)}</td>
      <td class="text-xs text-slate-500 whitespace-nowrap">${fmtDateTime(r.created_at || r.txn_date)}</td>
    </tr>`).join("");
}

function drawSalesChart(container, summaries, consolidated) {
  const canvas = container.querySelector("#sales-chart");
  if (!canvas) return;
  const perBranch = {};
  const arr = (consolidated && (consolidated.branches || consolidated.per_branch)) || [];
  arr.forEach((r) => {
    const code = r.code || r.branch_code;
    if (code) perBranch[String(code).toUpperCase()] = Number(r.sales ?? r.total_sales ?? 0);
  });
  const labels = summaries.map(({ branch }) => branch.code);
  const values = summaries.map(({ branch, summary }) => {
    const hit = perBranch[String(branch.code).toUpperCase()];
    return hit !== undefined ? hit : totalsOf(summary).sales;
  });

  const render = () => {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    canvas.width = w * dpr; canvas.height = h * dpr;
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    const padL = 56, padB = 34, padT = 16, padR = 8;
    const cw = w - padL - padR, ch = h - padT - padB;
    const max = Math.max(...values, 1);
    const n = labels.length;
    const slot = cw / Math.max(n, 1);
    const barW = Math.min(44, slot * 0.55);

    ctx.font = "10px system-ui"; ctx.fillStyle = "#64748b"; ctx.textAlign = "right";
    for (let i = 0; i <= 4; i++) {
      const v = (max * i) / 4;
      const y = padT + ch - (ch * i) / 4;
      ctx.fillText(fmtRpShort(v), padL - 6, y + 3);
      ctx.strokeStyle = "#e2e8f0"; ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
    }

    labels.forEach((label, i) => {
      const v = values[i];
      const bh = (ch * v) / max;
      const x = padL + slot * i + (slot - barW) / 2;
      const y = padT + ch - bh;
      const grad = ctx.createLinearGradient(0, y, 0, y + bh);
      grad.addColorStop(0, "#2b875c"); grad.addColorStop(1, "#0b3d2e");
      ctx.fillStyle = grad;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(x, y, barW, Math.max(bh, 2), 4); else ctx.rect(x, y, barW, Math.max(bh, 2));
      ctx.fill();
      ctx.fillStyle = "#0b3d2e"; ctx.textAlign = "center";
      ctx.fillText(label, x + barW / 2, padT + ch + 14);
      if (bh > 18) { ctx.fillStyle = "#fff"; ctx.fillText(fmtRpShort(v), x + barW / 2, y + 12); }
    });
  };

  render();
  const onResize = () => render();
  window.addEventListener("resize", onResize);
  chartCleanup = () => window.removeEventListener("resize", onResize);
}
