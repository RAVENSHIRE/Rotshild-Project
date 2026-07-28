// ------------------------------------------------------------------
// Login page: Firebase email/password auth (or demo fallback), then
// pull the user's cloud portfolio state and return to the dashboard.
// ------------------------------------------------------------------
import { authReady, isDemo, signIn, signUp, signOutUser, onAuthChange } from "./firebase.js";
import { syncFromCloud } from "./api.js";
import { initShell } from "./shell.js";

const $ = (id) => document.getElementById(id);
let mode = "signin";
let redirectOnAuth = false;

function setMode(next) {
  mode = next;
  $("tab-signin").classList.toggle("active", mode === "signin");
  $("tab-signup").classList.toggle("active", mode === "signup");
  $("auth-submit").textContent = mode === "signin" ? "Sign in" : "Create account";
  $("auth-password").autocomplete = mode === "signin" ? "current-password" : "new-password";
  $("auth-error").textContent = "";
}

$("tab-signin").addEventListener("click", () => setMode("signin"));
$("tab-signup").addEventListener("click", () => setMode("signup"));

$("auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = $("auth-submit");
  submit.disabled = true;
  $("auth-error").textContent = "";
  redirectOnAuth = true;
  try {
    const action = mode === "signin" ? signIn : signUp;
    await action($("auth-email").value.trim(), $("auth-password").value);
    await syncFromCloud().catch(() => null);
    location.href = "/";
  } catch (err) {
    redirectOnAuth = false;
    $("auth-error").textContent = (err.message || String(err))
      .replace("Firebase: ", "")
      .replace(/\(auth\/([a-z-]+)\)\.?/, (_, code) => `(${code.replace(/-/g, " ")})`);
  } finally {
    submit.disabled = false;
  }
});

$("signout-btn").addEventListener("click", async () => {
  await signOutUser();
  $("auth-session").hidden = true;
  $("auth-forms").hidden = false;
});

authReady.then(() => {
  $("auth-mode-note").style.display = isDemo() ? "" : "none";
  onAuthChange((user) => {
    if (user && !redirectOnAuth) {
      $("auth-forms").hidden = true;
      $("auth-session").hidden = false;
      $("session-email").textContent = user.email + (user.demo ? " (demo)" : "");
    }
  });
});

initShell({});
