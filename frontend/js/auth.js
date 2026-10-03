// Auth: login/logout/session, role + permission helpers, route guards.
import { api, apiRequest, setToken, clearSession, getToken } from "./api.js";

const PROFILE_KEY = "telur_profile";

export const PERMISSIONS = [
  "reports.view_profit",
  "reports.view_margin",
  "inventory.view_cost",
  "transactions.correct",
  "users.manage",
  "audit.view",
  "branches.manage",
  "settings.manage",
];

export const PERMISSION_LABELS = {
  "reports.view_profit": "Lihat Laba / Laporan Keuangan",
  "reports.view_margin": "Lihat Margin Keuntungan",
  "inventory.view_cost": "Lihat HPP / Nilai Persediaan",
  "transactions.correct": "Koreksi / Batalkan Transaksi",
  "users.manage": "Kelola Pengguna",
  "audit.view": "Lihat Audit Log",
  "branches.manage": "Kelola Cabang",
  "settings.manage": "Kelola Pengaturan",
};

export async function login(email, password) {
  const data = await apiRequest("POST", "/auth/login", { body: { email, password } });
  if (!data || !data.access_token) throw new Error("Respons login tidak valid dari server.");
  clearBranchCache();
  clearProductCache();
  setToken(data.access_token);
  const profile = data.profile || {};
  localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
  return profile;
}

export function logout() {
  clearSession();
  clearBranchCache();
  clearProductCache();
  window.location.hash = "#/login";
}

export function currentUser() {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

export function isLoggedIn() {
  return !!getToken() && !!currentUser();
}

export async function refreshMe() {
  const me = await api.get("/auth/me");
  const profile = me && me.profile ? me.profile : me;
  if (profile && profile.id) {
    const prev = currentUser() || {};
    localStorage.setItem(PROFILE_KEY, JSON.stringify({ ...prev, ...profile }));
  }
  return currentUser();
}

export function role() {
  const u = currentUser();
  return u ? u.role : null;
}

export function isOwner() {
  return role() === "owner";
}

export function isKaryawan() {
  return role() === "karyawan";
}

export function isAdmin() {
  return role() === "admin";
}

/** Owner has every permission. Others use permissions granted by the backend. */
export function hasPermission(key) {
  const u = currentUser();
  if (!u) return false;
  if (u.role === "owner") return true;
  const perms = Array.isArray(u.permissions) ? u.permissions : [];
  return perms.includes(key);
}

export function roleLabel(r) {
  return r === "owner" ? "Owner" : r === "admin" ? "Admin" : r === "karyawan" ? "Karyawan" : (r || "-");
}

// ---- Branch scope cache ----
let _branches = null;

export async function myBranches(force = false) {
  if (_branches && !force) return _branches;
  const data = await api.get("/branches");
  _branches = Array.isArray(data) ? data : data.branches || data.items || [];
  return _branches;
}

export function clearBranchCache() {
  _branches = null;
}

export async function branchIdByCode(code) {
  const branches = await myBranches();
  const b = branches.find((x) => String(x.code).toUpperCase() === String(code).toUpperCase());
  return b ? b.id : null;
}

export async function branchByCode(code) {
  const branches = await myBranches();
  return branches.find((x) => String(x.code).toUpperCase() === String(code).toUpperCase()) || null;
}

// ---- Product cache ----
let _products = null;

export async function getProducts(force = false) {
  if (_products && !force) return _products;
  const data = await api.get("/products");
  _products = Array.isArray(data) ? data : data.products || data.items || [];
  return _products;
}

export function clearProductCache() {
  _products = null;
}
