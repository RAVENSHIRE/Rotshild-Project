// ------------------------------------------------------------------
// Shared page shell: nav highlighting, mobile menu, auth button state,
// EN/DE localisation via the backend /api/i18n table.
// ------------------------------------------------------------------
import { onAuthChange, signOutUser, authReady } from "./firebase.js";
import { syncFromCloud } from "./api.js";

const LANG_KEY = "rotshild-lang";
let translations = null;

export function currentLang() {
  return localStorage.getItem(LANG_KEY) || "EN";
}

async function applyLang(lang) {
  localStorage.setItem(LANG_KEY, lang);
  document.querySelectorAll(".lang-toggle button").forEach((b) =>
    b.classList.toggle("active", b.dataset.lang === lang)
  );
  if (!translations) {
    try {
      translations = (await (await fetch("/api/i18n")).json()).translations;
    } catch {
      return;
    }
  }
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const entry = translations[el.dataset.i18n];
    if (entry) el.textContent = entry[lang] || entry.EN;
  });
}

export function initShell({ onUserReady } = {}) {
  // Active nav link
  const path = location.pathname.replace(/\/$/, "") || "/";
  document.querySelectorAll(".site-nav a[data-route]").forEach((a) => {
    a.classList.toggle("active", a.dataset.route === path);
  });

  // Mobile menu
  const menuBtn = document.getElementById("menu-btn");
  const nav = document.getElementById("site-nav");
  menuBtn?.addEventListener("click", () => nav?.classList.toggle("open"));

  // Language toggle
  document.querySelectorAll(".lang-toggle button").forEach((b) =>
    b.addEventListener("click", () => applyLang(b.dataset.lang))
  );
  applyLang(currentLang());

  // Auth-aware login button
  const loginBtn = document.getElementById("login-btn");
  authReady.then(() => {
    onAuthChange(async (user) => {
      if (!loginBtn) return;
      if (user) {
        loginBtn.dataset.i18n = "sign_out";
        loginBtn.textContent = translations?.sign_out?.[currentLang()] || "Sign out";
        loginBtn.title = user.email + (user.demo ? " (demo)" : "");
        loginBtn.onclick = async () => {
          await signOutUser();
          location.href = "/login";
        };
        const remote = await syncFromCloud().catch(() => null);
        onUserReady?.(user, remote);
      } else {
        loginBtn.dataset.i18n = "sign_in";
        loginBtn.textContent = translations?.sign_in?.[currentLang()] || "Sign in";
        loginBtn.title = "";
        loginBtn.onclick = () => (location.href = "/login");
      }
    });
  });
}
