// ------------------------------------------------------------------
// API layer: persisted dashboard controls + backend fetch helpers.
// Holdings are normalized rows on the backend (one ticker per row).
// ------------------------------------------------------------------
import { currentUser, loadCloudState, saveCloudState } from "./firebase.js";

const STATE_KEY = "rotshild-portfolio-state";

export const DEFAULT_STATE = {
  benchmark: "SPY",
  riskFree: 2.0, // annual percent
  lookback: 252,
  live: true,
  bucket: "ALL", // ALL | Return Assets | Diversifying Assets
  targets: null, // {TICKER: percent}
};

export function loadState() {
  try {
    const saved = JSON.parse(localStorage.getItem(STATE_KEY) || "null");
    return saved ? { ...DEFAULT_STATE, ...saved } : { ...DEFAULT_STATE };
  } catch {
    return { ...DEFAULT_STATE };
  }
}

export async function saveState(state, { cloud = true } = {}) {
  localStorage.setItem(STATE_KEY, JSON.stringify(state));
  if (cloud && currentUser()) {
    try {
      await saveCloudState(state);
    } catch (err) {
      console.warn("Cloud sync failed:", err);
    }
  }
}

export async function syncFromCloud() {
  const remote = await loadCloudState();
  if (!remote) return null;
  const state = { ...DEFAULT_STATE, ...remote };
  delete state.updatedAt;
  localStorage.setItem(STATE_KEY, JSON.stringify(state));
  return state;
}

function query(state) {
  const params = new URLSearchParams({
    benchmark: state.benchmark,
    risk_free: String(state.riskFree),
    lookback: String(state.lookback),
    live: state.live ? "1" : "0",
    bucket: state.bucket || "ALL",
  });
  return params.toString();
}

async function getJSON(url, options) {
  const res = await fetch(url, options);
  const body = await res.json();
  if (!res.ok || body.error) throw new Error(body.error || `HTTP ${res.status}`);
  return body;
}

export const fetchDashboard = (state) => getJSON(`/api/dashboard?${query(state)}`);
export const fetchHoldings = () => getJSON("/api/holdings");
export const refreshHoldingPrices = (live = true, ticker = null) =>
  getJSON("/api/holdings/refresh-prices", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ live, ...(ticker ? { ticker } : {}) }),
  });
export const upsertHolding = (holding) =>
  getJSON("/api/holdings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ holding }),
  });
export const deleteHolding = (ticker) =>
  getJSON(`/api/holdings?ticker=${encodeURIComponent(ticker)}`, {
    method: "DELETE",
  });
export const addTicker = (payload) =>
  getJSON("/api/tickers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
export const fetchSectorMap = () => getJSON("/api/sector-map");

export const fetchNews = (tickers = []) => {
  const q = tickers.length
    ? `?tickers=${encodeURIComponent(tickers.join(","))}`
    : "";
  return getJSON(`/api/news${q}`);
};

export const postRebalance = (current, target, portfolioValue) =>
  getJSON("/api/rebalance", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current, target, portfolio_value: portfolioValue }),
  });

// ---- Formatting --------------------------------------------------- //
export const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );

const money = new Intl.NumberFormat("en-CH", {
  style: "currency", currency: "CHF", maximumFractionDigits: 0,
});
const money2 = new Intl.NumberFormat("en-CH", {
  style: "currency", currency: "CHF", maximumFractionDigits: 2,
});

export const fmtMoney = (v) => (v == null ? "—" : money.format(v));
export const fmtPrice = (v) => (v == null ? "—" : money2.format(v));
export const fmtMoneySigned = (v) =>
  v == null ? "—" : (v >= 0 ? "+" : "−") + money.format(Math.abs(v));
export const fmtPct = (v, d = 1) => (v == null ? "—" : `${v.toFixed(d)}%`);
export const fmtPctSigned = (v, d = 1) =>
  v == null ? "—" : `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(d)}%`;
export const fmtNum = (v, d = 2) => (v == null ? "—" : v.toFixed(d));
export const timeAgo = (hours) =>
  hours < 24 ? `${hours}h ago` : `${Math.round(hours / 24)}d ago`;
export const signClass = (v) => (v == null ? "" : v >= 0 ? "positive" : "negative");
