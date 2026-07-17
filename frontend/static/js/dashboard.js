// ------------------------------------------------------------------
// Dashboard home: hero, controls, security-level book (bottom-up),
// contribution + CAPM charts, portfolio roll-up.
// ------------------------------------------------------------------
import {
  fetchDashboard, loadState, saveState,
  fmtMoney, fmtPrice, fmtMoneySigned, fmtPct, fmtPctSigned, fmtNum, signClass,
} from "./api.js";
import {
  lineChart, sparkChart, divergingBar, palette, cssVar, onThemeChange,
} from "./charts.js";
import { initShell } from "./shell.js";

let state = loadState();
let data = null;      // last dashboard payload
let selected = null;  // selected ticker in the holdings table

const $ = (id) => document.getElementById(id);

// ---- Controls ----------------------------------------------------- //
function fillForm() {
  $("tickers-input").value = state.tickers.join(", ");
  $("benchmark-input").value = state.benchmark;
  $("risk-free-input").value = state.riskFree;
  $("lookback-input").value = state.lookback;
  $("live-input").checked = state.live;
  $("portfolio-value-input").value = state.portfolioValue;
}

function readForm() {
  const tickers = $("tickers-input").value.split(",").map((t) => t.trim().toUpperCase()).filter(Boolean);
  // Saved targets only stay valid while the instrument list is unchanged.
  const sameBook =
    state.targets && tickers.length === state.tickers.length &&
    tickers.every((t) => state.tickers.includes(t));
  state = {
    ...state,
    targets: sameBook ? state.targets : null,
    tickers,
    benchmark: $("benchmark-input").value.trim().toUpperCase() || "SPY",
    riskFree: parseFloat($("risk-free-input").value) || 0,
    lookback: Math.max(30, parseInt($("lookback-input").value, 10) || 252),
    live: $("live-input").checked,
    portfolioValue: parseFloat($("portfolio-value-input").value) || 1,
  };
}

// ---- Rendering ---------------------------------------------------- //
function setPill(text, mode) {
  const pill = $("data-source-pill");
  pill.textContent = text;
  pill.className = "status-pill " + (mode || "");
}

function riskProfile(beta) {
  if (beta == null) return ["—", "Awaiting CAPM estimate"];
  if (beta < 0.75) return ["Defensive", `Portfolio β ${beta.toFixed(2)} — diversifiers dominate`];
  if (beta < 1.05) return ["Balanced", `Portfolio β ${beta.toFixed(2)} vs benchmark`];
  return ["Growth-tilted", `Portfolio β ${beta.toFixed(2)} — equity risk dominates`];
}

function renderHero() {
  const m = data.metrics.portfolio;
  const capm = data.metrics.capm;
  const dailyPct = m.value - m.daily_change !== 0 ? (m.daily_change / (m.value - m.daily_change)) * 100 : 0;

  $("hero-portfolio-value").textContent = fmtMoney(m.value);
  const change = $("hero-portfolio-change");
  change.textContent = `${fmtPctSigned(dailyPct, 2)} today · ${fmtMoneySigned(m.daily_change)}`;
  change.className = signClass(m.daily_change);

  $("hero-beta").textContent = fmtNum(capm.beta);
  $("hero-alpha").textContent = capm.alpha == null ? "—" : fmtPctSigned(capm.alpha * 100);
  $("hero-sharpe").textContent = fmtNum(m.sharpe);

  const [score, note] = riskProfile(capm.beta);
  $("hero-risk-score").textContent = score;
  $("hero-risk-note").textContent = note;
}

function renderHoldings() {
  const body = $("holdings-table-body");
  body.innerHTML = "";
  for (const h of data.holdings) {
    const tr = document.createElement("tr");
    tr.className = "selectable" + (h.ticker === selected ? " selected" : "");
    const mandateCls = h.mandate === "Return Assets" ? "return" : "divers";
    tr.innerHTML = `
      <td><span class="asset-name"><span class="ticker">${h.ticker}</span><span class="full">${h.fundamentals.name} · ${h.fundamentals.sector}</span></span></td>
      <td><span class="tag ${mandateCls}">${h.mandate === "Return Assets" ? "Return" : "Diversifying"}</span></td>
      <td class="num ${signClass(h.total_return)}">${fmtPctSigned(h.total_return)}</td>
      <td class="num">${fmtNum(h.beta)}</td>
      <td class="num ${signClass(h.contribution)}">${fmtPctSigned(h.contribution, 2)}</td>
      <td class="num">${fmtPct(h.weight)}</td>`;
    tr.addEventListener("click", () => {
      selected = h.ticker;
      renderHoldings();
      renderDetail(h);
    });
    body.appendChild(tr);
  }
  const current = data.holdings.find((h) => h.ticker === selected) || data.holdings[0];
  if (current) {
    selected = current.ticker;
    renderDetail(current);
  }
}

function renderDetail(h) {
  const f = h.fundamentals;
  const rows = [
    ...f.metrics,
    ["Last price", fmtPrice(h.price)],
    ["1-day move", fmtPctSigned(h.change_24h, 2)],
    ["Beta vs " + data.config.benchmark, fmtNum(h.beta)],
    ["Sharpe (period)", fmtNum(h.sharpe)],
    ["Return contribution", fmtPctSigned(h.contribution, 2)],
    ["Position value", fmtMoney(h.value)],
    ["Quantity", fmtNum(h.quantity, 0)],
  ];
  $("security-detail").innerHTML = `
    <h3>Security dossier</h3>
    <div class="d-name">${f.name}</div>
    <div class="d-sector">${h.ticker} · ${f.sector} · ${f.asset_class}</div>
    <p class="d-thesis">${f.thesis}</p>
    <div class="metric-rows">
      ${rows.map(([k, v]) => `<div><span>${k}</span><strong>${v}</strong></div>`).join("")}
    </div>`;
}

function renderStats() {
  const m = data.metrics.portfolio;
  const b = data.metrics.benchmark;
  const set = (id, text, cls) => {
    const el = $(id);
    el.textContent = text;
    if (cls !== undefined) el.className = cls;
  };
  set("metric-total-value", fmtMoney(m.value));
  set("metric-total-delta", `${fmtPctSigned(m.total_return * 100)} over period`, signClass(m.total_return));
  set("metric-24h-change", fmtMoneySigned(m.daily_change), signClass(m.daily_change));
  set("metric-24h-note", m.daily_change >= 0 ? "Net positive session" : "Net negative session", signClass(m.daily_change));
  set("metric-7d-change", fmtMoneySigned(m.weekly_change), signClass(m.weekly_change));
  set("metric-7d-note", "Trailing five sessions", signClass(m.weekly_change));
  set("metric-alltime-return", fmtMoneySigned(m.total_change), signClass(m.total_change));
  set(
    "metric-alltime-note",
    `vs ${data.config.benchmark} ${fmtPctSigned((m.total_return - b.total_return) * 100)}`,
    signClass(m.total_return - b.total_return)
  );
}

function renderCharts() {
  const p = palette();
  const perf = data.charts.performance;

  // Hero sparkline sits on the navy panel in both themes → fixed gold.
  sparkChart("performanceChart", perf.labels, perf.portfolio, cssVar("--gold-soft") || "#c9a558");

  lineChart("overviewChart", perf.labels, [
    { label: "Portfolio", data: perf.portfolio, color: p.s1 },
    { label: data.config.benchmark, data: perf.benchmark, color: p.s2, dashed: true },
  ], { yFormat: (v) => fmtMoney(v) });

  const contrib = data.charts.contribution;
  divergingBar("contributionChart", contrib.labels, contrib.values, {
    format: (v) => fmtPctSigned(v, 2),
  });

  const capm = data.charts.capm;
  lineChart("betaChart", capm.labels, [
    { label: "β", data: capm.beta, color: p.s1, fill: true },
  ], { yFormat: (v) => fmtNum(v), legend: false });
}

// ---- Load cycle --------------------------------------------------- //
async function load() {
  setPill("Loading portfolio data…", "");
  try {
    data = await fetchDashboard(state);
    renderHero();
    renderHoldings();
    renderStats();
    renderCharts();
    const src = data.source;
    setPill(
      `${src.label} · ${data.config.tickers.length} instruments · ${data.config.lookback}-day window` +
        (state.targets ? " · custom target weights applied" : " · equal-weight book"),
      src.synthetic ? "synthetic" : "live"
    );
  } catch (err) {
    setPill(`Could not load dashboard: ${err.message}`, "error");
  }
}

$("dashboard-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  readForm();
  await saveState(state);
  load();
});

initShell({
  onUserReady(_user, remoteState) {
    if (remoteState) {
      state = remoteState;
      fillForm();
      load();
    }
  },
});
onThemeChange(() => data && renderCharts());
fillForm();
load();
