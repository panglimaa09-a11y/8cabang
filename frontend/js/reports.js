// Financial reports: cash, profit-loss, margin.
// Called only from explicit navigation; a 403 from the API redirects to #/ditolak
// (handled centrally in api.js) — never silently fetched or hidden with CSS.
import { api } from "./api.js";
import { myBranches } from "./auth.js";
import {
  fmtRp, fmtPct, fmtDate, esc, skeletonCards, emptyState, errorAlert, toast,
} from "./ui.js";

function reportFilters(id, branches, showBranch = true) {
  return `<div class="card card-pad mb-4 no-print">
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 items-end">
      <div><label class="field-label" for="${id}-from">Dari tanggal</label>
        <input type="date" id="${id}-from" class="field-input"></div>
      <div><label class="field-label" for="${id}-to">Sampai tanggal</label>
        <input type="date" id="${id}-to" class="field-input"></div>
      ${showBranch ? `<div><label class="field-label" for="${id}-branch">Cabang</label>
        <select id="${id}-branch" class="field-select"><option value="">Semua cabang</option>
        ${branches.map((b) => `<option value="${esc(b.id)}">${esc(b.code)} — ${esc(b.name || "")}</option>`).join("")}
        </select></div>` : ""}
      <div class="flex gap-2">
        <button id="${id}-apply" class="btn btn-primary">Tampilkan</button>
        <button id="${id}-print" class="btn btn-ghost">Cetak</button>
      </div>
    </div>
  </div>`;
}

function readParams(id) {
  const g = (s) => document.getElementById(`${id}-${s}`);
  return {
    from: g("from") ? g("from").value || undefined : undefined,
    to: g("to") ? g("to").value || undefined : undefined,
    branch_id: g("branch") && g("branch").value ? g("branch").value : undefined,
  };
}

function wireReport(id, onApply) {
  document.getElementById(`${id}-apply`).addEventListener("click", onApply);
  document.getElementById(`${id}-print`).addEventListener("click", () => window.print());
}

function kpi(label, value, tone = "") {
  const color = tone === "neg" ? "text-red-700" : tone === "pos" ? "text-green-700" : "text-pine-900";
  return `<div class="card card-pad kpi-card">
    <p class="text-xs font-semibold text-slate-500 uppercase tracking-wide">${esc(label)}</p>
    <p class="text-lg md:text-xl font-bold stat-num mt-1 ${color}">${value}</p></div>`;
}

// ---------------- LAPORAN KAS ----------------
export async function renderLaporanKas(container) {
  const branches = await myBranches();
  const fid = "rkas";
  container.innerHTML = `
    <h2 class="text-xl font-bold text-slate-800 mb-1">Laporan Kas</h2>
    <p class="text-sm text-slate-500 mb-4">Arus kas masuk vs keluar. Ini menunjukkan arus uang, bukan otomatis keuntungan.</p>
    ${reportFilters(fid, branches)}
    <div id="${fid}-out">${skeletonCards(3)}</div>`;

  async function load() {
    const out = container.querySelector(`#${fid}-out`);
    out.innerHTML = skeletonCards(3);
    try {
      const d = await api.get("/reports/cash", { params: readParams(fid) });
      const cashIn = Number(d.cash_in ?? d.total_in ?? 0);
      const cashOut = Number(d.cash_out ?? d.total_out ?? 0);
      const net = Number(d.net ?? d.net_cash ?? cashIn - cashOut);
      let perBranchRows = "";
      const perBranch = d.per_branch || d.branches || [];
      if (Array.isArray(perBranch) && perBranch.length) {
        perBranchRows = `<div class="card card-pad mt-4"><h3 class="font-bold text-slate-800 mb-3">Per Cabang</h3>
          <div class="table-wrap"><table class="data-table">
          <thead><tr><th>Cabang</th><th class="num">Kas Masuk</th><th class="num">Kas Keluar</th><th class="num">Kas Bersih</th></tr></thead>
          <tbody>${perBranch.map((r) => {
            const ci = Number(r.cash_in ?? 0), co = Number(r.cash_out ?? 0);
            return `<tr><td class="font-semibold">${esc(r.code || r.branch_code || "")} — ${esc(r.name || r.branch_name || "")}</td>
              <td class="num stat-num text-green-700">${fmtRp(ci)}</td>
              <td class="num stat-num text-red-700">${fmtRp(co)}</td>
              <td class="num stat-num font-bold">${fmtRp(ci - co)}</td></tr>`;
          }).join("")}</tbody></table></div></div>`;
      }
      const p = readParams(fid);
      out.innerHTML = `
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
          ${kpi("Total Kas Masuk", fmtRp(cashIn), "pos")}
          ${kpi("Total Kas Keluar", fmtRp(cashOut), "neg")}
          ${kpi("Kas Bersih", fmtRp(net), net < 0 ? "neg" : "pos")}
        </div>
        <p class="text-xs text-slate-500 mt-3">Periode: ${p.from ? fmtDate(p.from) : "awal"} — ${p.to ? fmtDate(p.to) : "sekarang"}</p>
        ${perBranchRows}`;
    } catch (err) {
      out.innerHTML = errorAlert(err.message);
    }
  }

  wireReport(fid, load);
  await load();
}

// ---------------- LAPORAN LABA-RUGI ----------------
export async function renderLaporanLabaRugi(container) {
  const branches = await myBranches();
  const fid = "rlr";
  container.innerHTML = `
    <h2 class="text-xl font-bold text-slate-800 mb-1">Laporan Laba-Rugi</h2>
    <p class="text-sm text-slate-500 mb-4">Pendapatan bersih − HPP − beban operasional.</p>
    ${reportFilters(fid, branches)}
    <div id="${fid}-out">${skeletonCards(4)}</div>`;

  async function load() {
    const out = container.querySelector(`#${fid}-out`);
    out.innerHTML = skeletonCards(4);
    try {
      const d = await api.get("/reports/profit-loss", { params: readParams(fid) });
      const revenue = Number(d.revenue_net ?? d.revenue ?? 0);
      const cogs = Number(d.cogs ?? d.hpp ?? 0);
      const gross = Number(d.gross_profit ?? revenue - cogs);
      const opex = Number(d.opex ?? d.operating_expenses ?? 0);
      const other = Number(d.other_income ?? 0);
      const net = Number(d.net_profit ?? gross - opex + other);
      const row = (label, value, bold = false, tone = "") => `
        <tr class="${bold ? "font-bold bg-pine-50" : ""}">
          <td>${esc(label)}</td>
          <td class="num stat-num ${tone === "neg" ? "text-red-700" : tone === "pos" ? "text-green-700" : ""}">${fmtRp(value)}</td>
        </tr>`;
      const p = readParams(fid);
      out.innerHTML = `
        <div class="card card-pad">
          <div class="flex items-center justify-between mb-3">
            <h3 class="font-bold text-slate-800">Laporan Laba-Rugi</h3>
            <span class="text-xs text-slate-500">Periode: ${p.from ? fmtDate(p.from) : "awal"} — ${p.to ? fmtDate(p.to) : "sekarang"}</span>
          </div>
          <div class="table-wrap"><table class="data-table">
            <tbody>
              ${row("Pendapatan penjualan bersih", revenue)}
              ${row("HPP penjualan", cogs, false, "neg")}
              ${row("Laba kotor", gross, true, gross < 0 ? "neg" : "pos")}
              ${row("Beban operasional", opex, false, "neg")}
              ${row("Pendapatan lain", other, false, "pos")}
              ${row("Laba bersih", net, true, net < 0 ? "neg" : "pos")}
            </tbody>
          </table></div>
          <p class="text-xs text-slate-500 mt-3">HPP dihitung otomatis dengan metode rata-rata bergerak dan tersimpan historis per penjualan.</p>
        </div>`;
    } catch (err) {
      out.innerHTML = errorAlert(err.message);
    }
  }

  wireReport(fid, load);
  await load();
}

// ---------------- LAPORAN MARGIN ----------------
export async function renderLaporanMargin(container) {
  const branches = await myBranches();
  const fid = "rmg";
  container.innerHTML = `
    <h2 class="text-xl font-bold text-slate-800 mb-1">Laporan Margin</h2>
    <p class="text-sm text-slate-500 mb-4">Margin bersih = laba bersih ÷ pendapatan bersih. Margin gabungan dihitung dari total gabungan.</p>
    ${reportFilters(fid, branches)}
    <div id="${fid}-out">${skeletonCards(3)}</div>`;

  async function load() {
    const out = container.querySelector(`#${fid}-out`);
    out.innerHTML = skeletonCards(3);
    try {
      const d = await api.get("/reports/profit-margin", { params: readParams(fid) });
      const revenue = Number(d.revenue_net ?? d.revenue ?? 0);
      const net = Number(d.net_profit ?? d.net ?? 0);
      const margin = d.margin_pct !== undefined && d.margin_pct !== null ? Number(d.margin_pct) : null;
      const p = readParams(fid);
      out.innerHTML = `
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
          ${kpi("Pendapatan Bersih", fmtRp(revenue))}
          ${kpi("Laba Bersih", fmtRp(net), net < 0 ? "neg" : "pos")}
          ${kpi("Margin Bersih", margin === null ? "-" : fmtPct(margin), margin !== null && margin < 0 ? "neg" : "pos")}
        </div>
        <div class="card card-pad mt-4">
          <h3 class="font-bold text-slate-800 mb-2">Ringkasan</h3>
          <p class="text-sm text-slate-600">Periode: <strong>${p.from ? fmtDate(p.from) : "awal"} — ${p.to ? fmtDate(p.to) : "sekarang"}</strong></p>
          <p class="text-sm text-slate-600 mt-1">Dari setiap <strong>${fmtRp(100000)}</strong> pendapatan,
            laba bersih yang dihasilkan adalah <strong>${margin === null ? "-" : fmtRp((margin / 100) * 100000)}</strong>.</p>
          ${margin === null ? `<p class="text-xs text-amber-700 mt-2">Margin tidak dihitung karena pendapatan nol (menghindari pembagian nol).</p>` : ""}
        </div>`;
    } catch (err) {
      out.innerHTML = errorAlert(err.message);
    }
  }

  wireReport(fid, load);
  await load();
}
