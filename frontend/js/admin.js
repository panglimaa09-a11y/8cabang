// Admin views: user management, permission settings (owner only), audit log.
import { api } from "./api.js";
import { myBranches, isOwner, hasPermission, roleLabel, PERMISSIONS, PERMISSION_LABELS } from "./auth.js";
import {
  fmtDateTime, esc, skeletonRows, emptyState, errorAlert, statusBadge,
  toast, confirmDialog, filterBar, readFilter, paginate,
} from "./ui.js";

// ---------------- MANAJEMEN PENGGUNA ----------------
export async function renderPengguna(container) {
  const canManage = isOwner() || hasPermission("users.manage");
  const branches = await myBranches();
  container.innerHTML = `
    <div class="flex flex-col md:flex-row md:items-center gap-3 mb-4">
      <div class="flex-1">
        <h2 class="text-xl font-bold text-slate-800">Manajemen Pengguna</h2>
        <p class="text-sm text-slate-500">Kelola akun, peran, dan penugasan cabang.</p>
      </div>
      ${canManage ? `<button id="usr-add" class="btn btn-primary no-print">+ Tambah Pengguna</button>` : ""}
    </div>
    ${canManage ? "" : `<div class="alert alert-info mb-4">Anda hanya dapat melihat daftar pengguna (tanpa izin kelola).</div>`}
    <div class="card card-pad">
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>Nama</th><th>Email</th><th>Peran</th><th>Cabang</th><th>Status</th>${canManage ? "<th>Aksi</th>" : ""}</tr></thead>
        <tbody id="usr-body">${skeletonRows(canManage ? 6 : 5, 6)}</tbody>
      </table></div>
    </div>
    <div id="usr-modal"></div>`;

  async function load() {
    const body = container.querySelector("#usr-body");
    body.innerHTML = skeletonRows(canManage ? 6 : 5, 6);
    try {
      const d = await api.get("/users");
      const users = Array.isArray(d) ? d : d.items || d.users || [];
      if (!users.length) {
        body.innerHTML = `<tr><td colspan="${canManage ? 6 : 5}">${emptyState("Belum ada pengguna")}</td></tr>`;
        return;
      }
      body.innerHTML = users.map((u) => {
        const br = (u.branch_codes || u.branches || []).map((b) => (typeof b === "string" ? b : b.code)).join(", ");
        return `<tr>
          <td class="font-semibold">${esc(u.full_name || "-")}</td>
          <td class="text-sm">${esc(u.email || "-")}</td>
          <td><span class="badge ${u.role === "owner" ? "badge-amber" : u.role === "admin" ? "badge-blue" : "badge-slate"}">${esc(roleLabel(u.role))}</span></td>
          <td class="text-sm">${esc(br || "-")}</td>
          <td>${u.is_active === false ? `<span class="badge badge-red">Nonaktif</span>` : `<span class="badge badge-green">Aktif</span>`}</td>
          ${canManage ? `<td class="whitespace-nowrap">
            ${u.role !== "owner" || isOwner() ? `
              <button class="btn btn-ghost btn-sm" data-usr-edit="${esc(u.id)}">Ubah</button>
              <button class="btn btn-ghost btn-sm" data-usr-toggle="${esc(u.id)}" data-active="${u.is_active === false ? "1" : "0"}">
                ${u.is_active === false ? "Aktifkan" : "Nonaktifkan"}</button>` : `<span class="text-xs text-slate-400">-</span>`}
          </td>` : ""}
        </tr>`;
      }).join("");

      body.querySelectorAll("[data-usr-toggle]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const activate = btn.dataset.active === "1";
          if (!await confirmDialog(`${activate ? "Aktifkan" : "Nonaktifkan"} pengguna ini?`)) return;
          try {
            await api.patch(`/users/${btn.dataset.usrToggle}`, { is_active: activate });
            toast("Status pengguna diperbarui.", "success");
            load();
          } catch (err) { toast(err.message, "error"); }
        });
      });
      body.querySelectorAll("[data-usr-edit]").forEach((btn) => {
        btn.addEventListener("click", () => openUserModal(users.find((u) => String(u.id) === btn.dataset.usrEdit)));
      });
    } catch (err) {
      body.innerHTML = `<tr><td colspan="${canManage ? 6 : 5}">${errorAlert(err.message)}</td></tr>`;
    }
  }

  function openUserModal(user) {
    const modal = container.querySelector("#usr-modal");
    const isNew = !user;
    const uBranchIds = new Set((user && (user.branch_ids || (user.branches || []).map((b) => b.id))) || []);
    modal.innerHTML = `<div class="fixed inset-0 z-[110] flex items-center justify-center bg-black/50 p-4">
      <div class="card card-pad w-full max-w-md max-h-[90vh] overflow-y-auto">
        <h3 class="font-bold text-slate-800 mb-4">${isNew ? "Tambah Pengguna" : "Ubah Pengguna"}</h3>
        <form id="usr-form" class="space-y-3">
          <div><label class="field-label">Nama lengkap</label>
            <input id="uf-name" class="field-input" required value="${esc(user?.full_name || "")}"></div>
          <div><label class="field-label">Email</label>
            <input id="uf-email" type="email" class="field-input" required ${isNew ? "" : "disabled"}
              value="${esc(user?.email || "")}"></div>
          ${isNew ? `<div><label class="field-label">Kata sandi awal</label>
            <input id="uf-pass" type="password" class="field-input" required minlength="6" placeholder="min. 6 karakter"></div>` : ""}
          <div><label class="field-label">Peran</label>
            <select id="uf-role" class="field-select" required>
              ${["karyawan", "admin", "owner"].map((r) =>
                `<option value="${r}" ${(user?.role || "karyawan") === r ? "selected" : ""}>${roleLabel(r)}</option>`).join("")}
            </select></div>
          <div><label class="field-label">Cabang ditugaskan</label>
            <div class="grid grid-cols-2 gap-1 max-h-32 overflow-y-auto border rounded p-2">
              ${branches.map((b) => `<label class="text-sm flex items-center gap-2">
                <input type="checkbox" value="${esc(b.id)}" ${uBranchIds.has(b.id) ? "checked" : ""} class="uf-branch">
                ${esc(b.code)}</label>`).join("")}
            </div></div>
          <div id="uf-error" class="alert alert-error hidden"></div>
          <div class="flex justify-end gap-2 pt-2">
            <button type="button" class="btn btn-ghost" id="uf-cancel">Batal</button>
            <button type="submit" class="btn btn-primary">Simpan</button>
          </div>
        </form>
      </div></div>`;
    modal.querySelector("#uf-cancel").addEventListener("click", () => { modal.innerHTML = ""; });
    modal.querySelector("#usr-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const errBox = modal.querySelector("#uf-error");
      errBox.classList.add("hidden");
      const branch_ids = [...modal.querySelectorAll(".uf-branch:checked")].map((c) => c.value);
      const btn = e.target.querySelector('button[type="submit"]');
      btn.disabled = true;
      try {
        if (isNew) {
          await api.post("/users", {
            email: modal.querySelector("#uf-email").value.trim(),
            password: modal.querySelector("#uf-pass").value,
            full_name: modal.querySelector("#uf-name").value.trim(),
            role: modal.querySelector("#uf-role").value,
            branch_ids,
          });
          toast("Pengguna baru dibuat.", "success");
        } else {
          await api.patch(`/users/${user.id}`, {
            full_name: modal.querySelector("#uf-name").value.trim(),
            role: modal.querySelector("#uf-role").value,
            branch_ids,
          });
          toast("Pengguna diperbarui.", "success");
        }
        modal.innerHTML = "";
        load();
      } catch (err) {
        errBox.textContent = err.message;
        errBox.classList.remove("hidden");
      } finally { btn.disabled = false; }
    });
  }

  const addBtn = container.querySelector("#usr-add");
  if (addBtn) addBtn.addEventListener("click", () => openUserModal(null));
  await load();
}

// ---------------- PENGATURAN IZIN (owner only) ----------------
export async function renderIzin(container) {
  container.innerHTML = `
    <h2 class="text-xl font-bold text-slate-800 mb-1">Pengaturan Izin</h2>
    <p class="text-sm text-slate-500 mb-4">Berikan atau cabut izin khusus per pengguna. Hanya Owner.</p>
    <div class="card card-pad mb-4 no-print">
      <label class="field-label" for="perm-user">Pilih pengguna</label>
      <select id="perm-user" class="field-select md:w-96"><option value="">— pilih —</option></select>
    </div>
    <div id="perm-out"></div>`;

  const sel = container.querySelector("#perm-user");
  const out = container.querySelector("#perm-out");
  let users = [];
  try {
    const d = await api.get("/users");
    users = (Array.isArray(d) ? d : d.items || d.users || []).filter((u) => u.role !== "owner");
    users.forEach((u) => sel.add(new Option(`${u.full_name || u.email} (${roleLabel(u.role)})`, u.id)));
  } catch (err) {
    out.innerHTML = errorAlert(err.message);
    return;
  }

  sel.addEventListener("change", () => {
    const u = users.find((x) => String(x.id) === sel.value);
    if (!u) { out.innerHTML = ""; return; }
    const granted = new Set(u.permissions || []);
    out.innerHTML = `<div class="card card-pad">
      <h3 class="font-bold text-slate-800 mb-1">${esc(u.full_name || u.email)}</h3>
      <p class="text-xs text-slate-500 mb-4">Peran: ${esc(roleLabel(u.role))} — izin khusus di bawah ini menimpa bawaan peran.</p>
      <ul class="divide-y divide-slate-100">` +
      PERMISSIONS.map((key) => {
        const has = granted.has(key);
        return `<li class="py-3 flex flex-col sm:flex-row sm:items-center gap-2">
          <div class="flex-1">
            <p class="text-sm font-semibold text-slate-700">${esc(PERMISSION_LABELS[key] || key)}</p>
            <p class="text-xs font-mono text-slate-400">${esc(key)}</p>
          </div>
          <div class="flex items-center gap-2">
            <span class="badge ${has ? "badge-green" : "badge-slate"}">${has ? "Diberikan" : "Tidak"}</span>
            ${has
              ? `<button class="btn btn-ghost btn-sm" data-revoke="${esc(key)}">Cabut</button>`
              : `<button class="btn btn-primary btn-sm" data-grant="${esc(key)}">Berikan</button>`}
          </div></li>`;
      }).join("") + `</ul></div>`;

    out.querySelectorAll("[data-grant]").forEach((b) => b.addEventListener("click", () => changePerm(u, b.dataset.grant, "grant")));
    out.querySelectorAll("[data-revoke]").forEach((b) => b.addEventListener("click", () => changePerm(u, b.dataset.revoke, "revoke")));
  });

  async function changePerm(u, key, action) {
    const verb = action === "grant" ? "Berikan" : "Cabut";
    if (!await confirmDialog(`${verb} izin "${PERMISSION_LABELS[key] || key}" untuk ${u.full_name || u.email}?`)) return;
    try {
      await api.post(`/permissions/${action}`, { profile_id: u.id, permission_key: key });
      toast(`Izin ${action === "grant" ? "diberikan" : "dicabut"}.`, "success");
      // refresh user permissions
      const d = await api.get("/users");
      const fresh = (Array.isArray(d) ? d : d.items || d.users || []).find((x) => String(x.id) === String(u.id));
      if (fresh) {
        const idx = users.findIndex((x) => String(x.id) === String(u.id));
        users[idx] = fresh;
        sel.dispatchEvent(new Event("change"));
      }
    } catch (err) {
      toast(err.message, "error");
    }
  }
}

// ---------------- AUDIT LOG ----------------
export async function renderAudit(container) {
  container.innerHTML = `
    <h2 class="text-xl font-bold text-slate-800 mb-1">Audit Log</h2>
    <p class="text-sm text-slate-500 mb-4">Jejak tindakan penting: koreksi, perubahan izin, persetujuan opname.</p>
    <div id="audit-wrap"></div>`;
  const wrap = container.querySelector("#audit-wrap");
  const fid = "auditflt";
  const branches = await myBranches();

  let all = [];
  let page = 1;
  const perPage = 15;

  async function fetchAll() {
    wrap.innerHTML = `
      <div class="card card-pad mb-4 no-print">
        <div class="grid grid-cols-2 md:grid-cols-5 gap-3 items-end">
          <div><label class="field-label">Dari</label><input type="date" id="${fid}-from" class="field-input"></div>
          <div><label class="field-label">Sampai</label><input type="date" id="${fid}-to" class="field-input"></div>
          <div><label class="field-label">Cabang</label>
            <select id="${fid}-branch" class="field-select"><option value="">Semua</option>
            ${branches.map((b) => `<option value="${esc(b.id)}">${esc(b.code)}</option>`).join("")}</select></div>
          <div class="col-span-2"><label class="field-label">Pencarian</label>
            <input type="search" id="${fid}-q" class="field-input" placeholder="Cari aksi / entitas / alasan..."></div>
        </div>
      </div>
      <div class="card card-pad"><div class="table-wrap"><table class="data-table">
        <thead><tr><th>Waktu</th><th>Pelaku</th><th>Cabang</th><th>Aksi</th><th>Entitas</th><th>Alasan</th></tr></thead>
        <tbody id="${fid}-body">${skeletonRows(6, 8)}</tbody>
      </table></div><div id="${fid}-pag"></div></div>`;

    const { from, to } = readFilter(fid);
    const branchId = wrap.querySelector(`#${fid}-branch`).value;
    try {
      const d = await api.get("/audit-logs", {
        params: { from: from || undefined, to: to || undefined, branch_id: branchId || undefined, limit: 200 },
      });
      all = Array.isArray(d) ? d : d.items || d.logs || [];
    } catch (err) {
      wrap.querySelector(`#${fid}-body`).innerHTML = `<tr><td colspan="6">${errorAlert(err.message)}</td></tr>`;
      return;
    }
    let t;
    ["from", "to", "branch"].forEach((k) => {
      wrap.querySelector(`#${fid}-${k}`).addEventListener("change", () => { page = 1; fetchAll(); });
    });
    wrap.querySelector(`#${fid}-q`).addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => { page = 1; draw(); }, 300); });
    page = 1;
    draw();
  }

  function draw() {
    const body = wrap.querySelector(`#${fid}-body`);
    const pagBox = wrap.querySelector(`#${fid}-pag`);
    if (!body) return;
    const q = (wrap.querySelector(`#${fid}-q`).value || "").trim().toLowerCase();
    let rows = all.slice().sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
    if (q) {
      rows = rows.filter((r) =>
        String(r.action || "").toLowerCase().includes(q) ||
        String(r.entity_type || "").toLowerCase().includes(q) ||
        String(r.reason || "").toLowerCase().includes(q) ||
        String(r.actor_name || r.actor_email || "").toLowerCase().includes(q));
    }
    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="6">${emptyState("Tidak ada log", "Belum ada aktivitas tercatat pada filter ini.")}</td></tr>`;
      if (pagBox) pagBox.innerHTML = "";
      return;
    }
    const codeOf = {};
    branches.forEach((b) => { codeOf[b.id] = b.code; });
    const pg = paginate(rows, page, perPage, (p) => { page = p; draw(); });
    body.innerHTML = pg.pageItems.map((r) => `
      <tr>
        <td class="text-xs whitespace-nowrap">${fmtDateTime(r.created_at)}</td>
        <td class="text-sm">${esc(r.actor_name || r.actor_email || r.actor_id || "-")}</td>
        <td>${esc(codeOf[r.branch_id] || r.branch_code || "-")}</td>
        <td><span class="badge badge-slate">${esc(r.action || "-")}</span></td>
        <td class="text-xs">${esc(r.entity_type || "-")}${r.entity_id ? `<br><span class="font-mono text-slate-400">${esc(String(r.entity_id).slice(0, 8))}…</span>` : ""}</td>
        <td class="text-sm max-w-[16rem] truncate" title="${esc(r.reason || "")}">${esc(r.reason || "-")}</td>
      </tr>`).join("");
    if (pagBox) { pagBox.innerHTML = pg.html; pg.wire(pagBox); }
  }

  await fetchAll();
}
