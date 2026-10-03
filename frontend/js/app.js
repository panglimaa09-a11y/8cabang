// App shell: hash router, layout (sidebar drawer on mobile, topbar), role-based nav.
import { isLoggedIn, currentUser, logout, role, isOwner, isAdmin, isKaryawan, myBranches, roleLabel } from "./auth.js";
import { esc, toast } from "./ui.js";
import { renderLogin } from "./views-login.js";
import { renderDashboard } from "./dashboard.js";
import { renderCabangDetail } from "./transactions.js";
import {
  renderPemasukan, renderPengeluaran, renderPenjualan, renderPembelian,
} from "./transactions.js";
import { renderPersediaan, renderOpname, renderRetur } from "./inventory.js";
import { renderLaporanKas, renderLaporanLabaRugi, renderLaporanMargin } from "./reports.js";
import { renderPengguna, renderIzin, renderAudit } from "./admin.js";

const ICON = (n) => `frontend/assets/icons/${n}.svg`;

// name -> { title, render(container, param), guard() -> true | redirectHash }
const ROUTES = {
  "login":          { title: "Masuk", public: true, render: renderLogin },
  "dashboard":      { title: "Dashboard", render: renderDashboard },
  "cabang":         { title: "Detail Cabang", render: renderCabangDetail },
  "pemasukan":      { title: "Pemasukan", render: renderPemasukan },
  "pengeluaran":    { title: "Pengeluaran", render: renderPengeluaran },
  "penjualan":      { title: "Penjualan Telur", render: renderPenjualan },
  "pembelian":      { title: "Pembelian Stok", render: renderPembelian },
  "persediaan":     { title: "Persediaan & HPP", render: renderPersediaan },
  "opname":         { title: "Stok Opname", render: renderOpname },
  "retur":          { title: "Retur & Kerusakan", render: renderRetur },
  "laporan-kas":    { title: "Laporan Kas", render: renderLaporanKas },
  "laporan-labarugi": { title: "Laporan Laba-Rugi", render: renderLaporanLabaRugi, guard: () => !isKaryawan() },
  "laporan-margin": { title: "Laporan Margin", render: renderLaporanMargin, guard: () => !isKaryawan() },
  "pengguna":       { title: "Manajemen Pengguna", render: renderPengguna, guard: () => isOwner() || isAdmin() },
  "izin":           { title: "Pengaturan Izin", render: renderIzin, guard: () => isOwner() },
  "audit":          { title: "Audit Log", render: renderAudit, guard: () => isOwner() || isAdmin() },
  "ditolak":        { title: "Akses Ditolak", render: renderForbidden, auth: true },
};

function parseHash() {
  const raw = (window.location.hash || "#/dashboard").replace(/^#\/?/, "");
  const [name, param] = raw.split("/");
  return { name: name || "dashboard", param: param ? decodeURIComponent(param) : "" };
}

function navItems() {
  const items = [
    { section: "Utama" },
    { hash: "#/dashboard", label: "Dashboard", icon: ICON("dashboard") },
    { section: "Transaksi" },
    { hash: "#/penjualan", label: "Penjualan Telur", icon: ICON("cart") },
    { hash: "#/pembelian", label: "Pembelian Stok", icon: ICON("truck") },
    { hash: "#/persediaan", label: "Persediaan & HPP", icon: ICON("box") },
    { hash: "#/opname", label: "Stok Opname", icon: ICON("clipboard") },
    { hash: "#/retur", label: "Retur & Kerusakan", icon: ICON("return") },
    { hash: "#/pemasukan", label: "Pemasukan", icon: ICON("cash-in") },
    { hash: "#/pengeluaran", label: "Pengeluaran", icon: ICON("cash") },
    { section: "Cabang" },
    { hash: "#/laporan-kas", label: "Laporan Kas", icon: ICON("cash") },
  ];
  // Profit reports: hidden from karyawan entirely (never call the endpoints).
  if (!isKaryawan()) {
    items.push({ hash: "#/laporan-labarugi", label: "Laporan Laba-Rugi", icon: ICON("chart") });
    items.push({ hash: "#/laporan-margin", label: "Laporan Margin", icon: ICON("chart") });
  }
  if (isOwner() || isAdmin()) {
    items.push({ section: "Administrasi" });
    items.push({ hash: "#/pengguna", label: "Pengguna", icon: ICON("users") });
    if (isOwner()) items.push({ hash: "#/izin", label: "Pengaturan Izin", icon: ICON("shield") });
    items.push({ hash: "#/audit", label: "Audit Log", icon: ICON("shield") });
  }
  return items;
}

function sidebarHTML(activeHash) {
  const links = navItems()
    .map((it) => {
      if (it.section) return `<div class="nav-section">${esc(it.section)}</div>`;
      const active = activeHash === it.hash || (it.hash.startsWith("#/cabang") && activeHash.startsWith("#/cabang"));
      return `<a href="${it.hash}" class="nav-link ${active ? "active" : ""}" data-nav>
        <img src="${it.icon}" class="nav-icon" alt="" aria-hidden="true"><span>${esc(it.label)}</span></a>`;
    })
    .join("");
  return `
    <div class="flex items-center gap-3 px-4 py-5 border-b border-white/10">
      <img src="frontend/assets/logo.svg" alt="Logo" class="w-10 h-10 rounded-lg bg-white p-1">
      <div>
        <p class="text-white font-bold leading-tight">Telur 8 Cabang</p>
        <p class="text-pine-300 text-xs">Manajemen Penjualan</p>
      </div>
    </div>
    <nav class="flex-1 overflow-y-auto px-3 pb-4" id="branch-nav">
      ${links}
      <div class="nav-section">Cabang Saya</div>
      <div id="nav-branches"><div class="skeleton mx-3" style="height:2rem"></div></div>
    </nav>
    <div class="px-4 py-4 border-t border-white/10">
      <button id="btn-logout" class="nav-link w-full text-left">
        <img src="${ICON("logout")}" class="nav-icon" alt="" aria-hidden="true"><span>Keluar</span>
      </button>
    </div>`;
}

function shellHTML(title) {
  return `
  <div class="min-h-screen md:flex">
    <div id="drawer-overlay" class="fixed inset-0 bg-black/50 z-30 hidden md:hidden"></div>
    <aside id="sidebar" class="fixed md:static z-40 inset-y-0 left-0 w-64 bg-pine-900 flex flex-col
        -translate-x-full md:translate-x-0 min-h-screen max-h-screen">
      ${sidebarHTML(window.location.hash)}
    </aside>
    <div class="flex-1 min-w-0 flex flex-col min-h-screen">
      <header id="topbar" class="sticky top-0 z-20 bg-pine-900 text-white shadow">
        <div class="flex items-center gap-3 px-4 py-3">
          <button id="btn-menu" class="md:hidden p-2 -ml-2 rounded hover:bg-white/10" aria-label="Menu">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M4 6h16M4 12h16M4 18h16"/></svg>
          </button>
          <h1 class="font-bold text-base md:text-lg truncate flex-1">${esc(title)}</h1>
          <div class="hidden sm:flex items-center gap-2 text-sm">
            <span class="badge badge-amber" id="user-role"></span>
            <span id="user-name" class="text-pine-100 font-medium max-w-[10rem] truncate"></span>
          </div>
        </div>
      </header>
      <main id="view" class="flex-1 p-4 md:p-6 w-full max-w-7xl mx-auto"></main>
      <footer class="text-center text-xs text-slate-400 py-4 no-print">Sistem Manajemen Penjualan Telur — 8 Cabang</footer>
    </div>
  </div>`;
}

function wireShell() {
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("drawer-overlay");
  const open = () => { sidebar.classList.remove("-translate-x-full"); overlay.classList.remove("hidden"); };
  const close = () => { if (window.innerWidth < 768) { sidebar.classList.add("-translate-x-full"); overlay.classList.add("hidden"); } };
  document.getElementById("btn-menu").addEventListener("click", open);
  overlay.addEventListener("click", close);
  document.querySelectorAll("[data-nav]").forEach((a) => a.addEventListener("click", close));
  document.getElementById("btn-logout").addEventListener("click", () => { toast("Anda telah keluar.", "info"); logout(); });

  const u = currentUser();
  if (u) {
    document.getElementById("user-name").textContent = u.full_name || u.email || "";
    document.getElementById("user-role").textContent = roleLabel(u.role);
  }
  // Branch quick links in sidebar (scoped to user)
  myBranches().then((branches) => {
    const box = document.getElementById("nav-branches");
    if (!box) return;
    if (!branches.length) { box.innerHTML = `<p class="text-pine-300 text-xs px-3">Tidak ada cabang.</p>`; return; }
    box.innerHTML = branches
      .map((b) => `<a href="#/cabang/${esc(b.code)}" data-nav
          class="flex items-center gap-2 px-3 py-2 rounded text-sm text-pine-100 hover:bg-white/10">
        <img src="${ICON("store")}" class="w-4 h-4" alt="" aria-hidden="true">
        <span class="truncate">${esc(b.code)} — ${esc(b.name || "")}</span></a>`)
      .join("");
    box.querySelectorAll("[data-nav]").forEach((a) => a.addEventListener("click", close));
  }).catch(() => {});
}

export function renderForbidden(container) {
  container.innerHTML = `<div class="card card-pad max-w-lg mx-auto text-center py-12">
    <img src="frontend/assets/icons/shield.svg" alt="" class="w-16 h-16 mx-auto opacity-60">
    <h2 class="text-xl font-bold text-slate-800 mt-4">Akses Ditolak (403)</h2>
    <p class="text-slate-500 mt-2 text-sm">Peran Anda tidak memiliki izin untuk membuka halaman ini.
    Jika Anda merasa ini keliru, hubungi Owner.</p>
    <a href="#/dashboard" class="btn btn-primary mt-6">Kembali ke Dashboard</a>
  </div>`;
}

let currentViewCleanup = null;

async function renderRoute() {
  const { name, param } = parseHash();
  const route = ROUTES[name];
  const app = document.getElementById("app");

  if (currentViewCleanup) { try { currentViewCleanup(); } catch (e) {} currentViewCleanup = null; }

  // Public route
  if (route && route.public) {
    if (isLoggedIn()) { window.location.hash = "#/dashboard"; return; }
    app.innerHTML = `<div id="view"></div>`;
    await route.render(document.getElementById("view"), param);
    return;
  }

  // Auth required
  if (!isLoggedIn()) { window.location.hash = "#/login"; return; }

  const target = route || ROUTES["dashboard"];
  if (target.guard && !target.guard()) { window.location.hash = "#/ditolak"; return; }

  app.innerHTML = shellHTML(target.title);
  wireShell();
  const view = document.getElementById("view");
  try {
    const maybeCleanup = await target.render(view, param);
    if (typeof maybeCleanup === "function") currentViewCleanup = maybeCleanup;
  } catch (err) {
    if (err && err.code === 403) { window.location.hash = "#/ditolak"; return; }
    const { errorAlert } = await import("./ui.js");
    view.innerHTML = errorAlert(err.message || "Terjadi kesalahan.");
  }
}

window.addEventListener("hashchange", renderRoute);

document.addEventListener("DOMContentLoaded", () => {
  if (!window.location.hash) window.location.hash = isLoggedIn() ? "#/dashboard" : "#/login";
  renderRoute();
});
