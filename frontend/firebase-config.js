// firebase-config.js — centralized auth state for all pages.
//
// Fill in firebaseConfig with your project's real values (Firebase console →
// Project settings → Your apps). Until you do, the app runs in DEMO MODE:
// auth is skipped entirely so the dashboard stays usable — a route guard that
// fires with placeholder keys would otherwise trap every page in a redirect
// loop to login.html.

const firebaseConfig = {
    apiKey: "YOUR_API_KEY",
    authDomain: "YOUR_PROJECT.firebaseapp.com",
    projectId: "YOUR_PROJECT_ID",
    storageBucket: "YOUR_PROJECT.appspot.com",
    messagingSenderId: "YOUR_MESSAGING_ID",
    appId: "YOUR_APP_ID"
};

const configured = !firebaseConfig.apiKey.startsWith("YOUR_");
const isLoginPage = window.location.pathname.endsWith("login.html");

export let auth = null;
export let db = null;

function wireLogout(handler) {
    const btn = document.getElementById("logout-btn");
    if (btn) {
        btn.addEventListener("click", handler);
        btn.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") { handler(); e.preventDefault(); }
        });
    }
}

if (configured) {
    const { initializeApp } = await import("https://www.gstatic.com/firebasejs/10.8.0/firebase-app.js");
    const { getAuth, onAuthStateChanged, signOut } = await import("https://www.gstatic.com/firebasejs/10.8.0/firebase-auth.js");
    const { getFirestore } = await import("https://www.gstatic.com/firebasejs/10.8.0/firebase-firestore.js");

    const app = initializeApp(firebaseConfig);
    auth = getAuth(app);
    db = getFirestore(app);

    // Global route guard
    onAuthStateChanged(auth, (user) => {
        if (!user && !isLoginPage) {
            window.location.href = "login.html";
        } else if (user && isLoginPage) {
            window.location.href = "index.html";
        }
    });

    document.addEventListener("DOMContentLoaded", () => {
        wireLogout(() => signOut(auth));
    });
} else {
    console.info("Firebase not configured — running in demo mode, auth disabled.");
    document.addEventListener("DOMContentLoaded", () => {
        wireLogout(() => { window.location.href = "login.html"; });
    });
}
