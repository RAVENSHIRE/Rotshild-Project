// ------------------------------------------------------------------
// Firebase Authentication + Firestore persistence layer.
//
// Real mode  : modular Firebase v10 SDK loaded from the gstatic CDN.
//              Auth = email/password; portfolio state lives in
//              Firestore at users/{uid}.
// Demo mode  : active while firebase-config.js still holds
//              placeholders (or the CDN is unreachable). Auth and the
//              "cloud" document are simulated in localStorage so the
//              full login → persist → reload flow can be demonstrated
//              offline.
// ------------------------------------------------------------------
import { firebaseConfig } from "./firebase-config.js";

const DEMO_USER_KEY = "rotshild-demo-user";
const DEMO_CLOUD_KEY = "rotshild-demo-cloud";

const configured =
  firebaseConfig.apiKey && !firebaseConfig.apiKey.startsWith("YOUR_");

let fb = null; // { auth, db, fns } when real Firebase is active
const authListeners = [];
let demoUser = null;

function notify(user) {
  authListeners.forEach((cb) => cb(user));
}

async function initReal() {
  const [{ initializeApp }, authMod, fsMod] = await Promise.all([
    import("https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js"),
    import("https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js"),
    import("https://www.gstatic.com/firebasejs/10.12.2/firebase-firestore.js"),
  ]);
  const app = initializeApp(firebaseConfig);
  const auth = authMod.getAuth(app);
  const db = fsMod.getFirestore(app);
  authMod.onAuthStateChanged(auth, (user) =>
    notify(user ? { uid: user.uid, email: user.email, demo: false } : null)
  );
  fb = { auth, db, authMod, fsMod };
}

export const authReady = (async () => {
  if (configured) {
    try {
      await initReal();
      return { mode: "firebase" };
    } catch (err) {
      console.warn("Firebase unavailable, falling back to demo mode:", err);
    }
  }
  demoUser = JSON.parse(localStorage.getItem(DEMO_USER_KEY) || "null");
  queueMicrotask(() => notify(demoUser));
  return { mode: "demo" };
})();

export function isDemo() {
  return fb === null;
}

export function onAuthChange(cb) {
  authListeners.push(cb);
  // Fire immediately with the demo state; real Firebase fires on its own.
  if (fb === null) cb(demoUser);
}

export async function signIn(email, password) {
  await authReady;
  if (fb) {
    const cred = await fb.authMod.signInWithEmailAndPassword(fb.auth, email, password);
    return { uid: cred.user.uid, email: cred.user.email, demo: false };
  }
  if (!email || password.length < 6) {
    throw new Error("Enter your email and a password of at least 6 characters.");
  }
  demoUser = { uid: "demo-" + btoa(email).replace(/=/g, ""), email, demo: true };
  localStorage.setItem(DEMO_USER_KEY, JSON.stringify(demoUser));
  notify(demoUser);
  return demoUser;
}

export async function signUp(email, password) {
  await authReady;
  if (fb) {
    const cred = await fb.authMod.createUserWithEmailAndPassword(fb.auth, email, password);
    return { uid: cred.user.uid, email: cred.user.email, demo: false };
  }
  return signIn(email, password); // demo mode: sign-up == sign-in
}

export async function signOutUser() {
  await authReady;
  if (fb) return fb.authMod.signOut(fb.auth);
  demoUser = null;
  localStorage.removeItem(DEMO_USER_KEY);
  notify(null);
}

export function currentUser() {
  if (fb) {
    const u = fb.auth.currentUser;
    return u ? { uid: u.uid, email: u.email, demo: false } : null;
  }
  return demoUser;
}

// ---- Portfolio state persistence (Firestore users/{uid}) ---------- //
export async function saveCloudState(state) {
  await authReady;
  const user = currentUser();
  if (!user) return false;
  if (fb) {
    const { doc, setDoc } = fb.fsMod;
    await setDoc(
      doc(fb.db, "users", user.uid),
      { ...state, updatedAt: new Date().toISOString() },
      { merge: true }
    );
    return true;
  }
  localStorage.setItem(
    DEMO_CLOUD_KEY + ":" + user.uid,
    JSON.stringify({ ...state, updatedAt: new Date().toISOString() })
  );
  return true;
}

export async function loadCloudState() {
  await authReady;
  const user = currentUser();
  if (!user) return null;
  if (fb) {
    const { doc, getDoc } = fb.fsMod;
    const snap = await getDoc(doc(fb.db, "users", user.uid));
    return snap.exists() ? snap.data() : null;
  }
  return JSON.parse(localStorage.getItem(DEMO_CLOUD_KEY + ":" + user.uid) || "null");
}
