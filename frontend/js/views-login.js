// Login view (public).
import { login } from "./auth.js";
import { toast } from "./ui.js";

export async function renderLogin(container) {
  container.innerHTML = `
  <div class="min-h-screen login-bg flex items-center justify-center p-4">
    <div class="w-full max-w-md">
      <div class="text-center mb-6">
        <img src="frontend/assets/pictures/hero.svg" alt="Ilustrasi telur" class="w-40 h-40 mx-auto drop-shadow-xl">
        <h1 class="text-white text-2xl font-bold mt-4">Manajemen Penjualan Telur</h1>
        <p class="text-pine-200 text-sm mt-1">8 Cabang — Masuk untuk mengelola operasional</p>
      </div>
      <div class="card card-pad">
        <div class="flex items-center gap-3 mb-5">
          <img src="frontend/assets/logo.svg" alt="Logo" class="w-11 h-11">
          <div>
            <p class="font-bold text-slate-800">Selamat datang</p>
            <p class="text-xs text-slate-500">Masuk dengan akun Anda</p>
          </div>
        </div>
        <form id="login-form" class="space-y-4" autocomplete="on">
          <div>
            <label class="field-label" for="login-email">Email</label>
            <input type="email" id="login-email" class="field-input" required
              placeholder="nama@contoh.com" autocomplete="username">
          </div>
          <div>
            <label class="field-label" for="login-password">Kata sandi</label>
            <input type="password" id="login-password" class="field-input" required
              placeholder="••••••••" autocomplete="current-password">
          </div>
          <div id="login-error" class="alert alert-error hidden"></div>
          <button type="submit" id="login-btn" class="btn btn-primary w-full">Masuk</button>
        </form>
      </div>
      <p class="text-center text-pine-300 text-xs mt-6">Data tersimpan terpusat & tersinkron online.</p>
    </div>
  </div>`;

  const form = container.querySelector("#login-form");
  const errBox = container.querySelector("#login-error");
  const btn = container.querySelector("#login-btn");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errBox.classList.add("hidden");
    btn.disabled = true;
    btn.textContent = "Memeriksa...";
    try {
      const email = container.querySelector("#login-email").value.trim();
      const password = container.querySelector("#login-password").value;
      await login(email, password);
      toast("Selamat datang!", "success");
      window.location.hash = "#/dashboard";
    } catch (err) {
      errBox.textContent = err.code === 401 || /invalid|password|email/i.test(err.message)
        ? "Email atau kata sandi salah. Coba lagi."
        : err.message;
      errBox.classList.remove("hidden");
    } finally {
      btn.disabled = false;
      btn.textContent = "Masuk";
    }
  });
}
