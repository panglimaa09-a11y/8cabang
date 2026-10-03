// API client: fetch wrapper with JWT, idempotency keys, and auth error routing.
// baseURL = current origin + "/api" (same-origin; served by FastAPI).

const TOKEN_KEY = "telur_jwt";
const PROFILE_KEY = "telur_profile";
const API_BASE = window.location.origin + "/api";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(PROFILE_KEY);
}

function authHeaders(extra = {}) {
  const headers = { "Content-Type": "application/json", ...extra };
  const token = getToken();
  if (token) headers["Authorization"] = "Bearer " + token;
  return headers;
}

/**
 * Core request.
 * options: { params, body, idempotency, allowForbidden }
 * - 401: session cleared, redirect to #/login, throws.
 * - 403: redirects to #/ditolak unless options.allowForbidden (then throws with err.code=403).
 * - Other errors: throws Error with server message; never reports fake success.
 */
export async function apiRequest(method, path, options = {}) {
  const { params, body, idempotency = false, allowForbidden = false } = options;
  const url = new URL(API_BASE + path, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
    }
  }

  const headers = authHeaders();
  let payload = body;
  if (idempotency && (method === "POST" || method === "PUT" || method === "PATCH")) {
    const key = (payload && payload.idempotency_key) || crypto.randomUUID();
    headers["Idempotency-Key"] = key;
    if (payload && typeof payload === "object" && !payload.idempotency_key) {
      payload = { ...payload, idempotency_key: key };
    }
  }

  let res;
  try {
    res = await fetch(url.toString(), {
      method,
      headers,
      body: payload !== undefined ? JSON.stringify(payload) : undefined,
    });
  } catch (e) {
    throw new Error("Tidak dapat terhubung ke server. Periksa koneksi internet Anda lalu coba lagi.");
  }

  if (res.status === 401) {
    clearSession();
    if (!window.location.hash.startsWith("#/login")) window.location.hash = "#/login";
    const err = new Error("Sesi berakhir. Silakan login kembali.");
    err.code = 401;
    throw err;
  }

  if (res.status === 403) {
    const err = new Error("Akses ditolak untuk peran Anda.");
    err.code = 403;
    if (!allowForbidden && !window.location.hash.startsWith("#/ditolak")) {
      window.location.hash = "#/ditolak";
    }
    throw err;
  }

  let data = null;
  try {
    data = await res.json();
  } catch (e) {
    data = null;
  }

  if (!res.ok) {
    const msg =
      (data && (data.detail || data.message || data.error)) ||
      `Kesalahan server (kode ${res.status}).`;
    const err = new Error(Array.isArray(msg) ? msg.join("; ") : String(msg));
    err.code = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

export const api = {
  get: (path, options) => apiRequest("GET", path, options),
  post: (path, body, options) => apiRequest("POST", path, { ...options, body, idempotency: true }),
  patch: (path, body, options) => apiRequest("PATCH", path, { ...options, body }),
  del: (path, options) => apiRequest("DELETE", path, options),
};
