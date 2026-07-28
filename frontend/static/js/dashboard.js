// ------------------------------------------------------------------
// Dashboard home: controls + holdings workflow + analytics roll-ups.
// ------------------------------------------------------------------
import {
  addTicker,
  deleteHolding,
  esc,
  fetchDashboard,
  fetchHoldings,
  fetchSectorMap,
  fmtMoney,
  fmtMoneySigned,
  fmtNum,
  fmtPct,
  fmtPctSigned,
  fmtPrice,
  loadState,
  refreshHoldingPrices,
  saveState,
  signClass,
  upsertHolding,
} from "./api.js";
import {
  divergingBar,
  lineChart,
  onThemeChange,
  palette,
  sparkChart,
  cssVar,
} from "./charts.js";
import { initShell } from "./shell.js";

let state = loadState();
let data = null;
let allHoldings = [];
let selected = null;
let sectorMap = {};

const $ = (id) => document.getElementById(id);

function fillForm() {
  $("benchmark-input").value = state.benchmark;
  $("risk-free-input").value = state.riskFree;
  $("lookback-input").value = state.lookback;
  $("live-input").checked = state.live;
  $("bucket-input").value = state.bucket || "ALL";
}

function readForm() {
  state = {
    ...state,
    benchmark: $("benchmark-input").value.trim().toUpperCase() || "SPY",
    riskFree: parseFloat($("risk-free-input").value) || 0,
    lookback: Math.max(30, parseInt($("lookback-input").value, 10) || 252),
    live: $("live-input").checked,
    bucket: $("bucket-input").value || "ALL",
  };
}

function setPill(text, mode) {
  const pill = $("data-source-pill");
  pill.textContent = text;
  pill.className = "status-pill " + (mode || "");
}

function showFormError(message) {
  $("holdings-form-error").textContent = message || "";
}

function populateSectorDropdown() {
  const sectorSelect = $("new-sector");
  const sectors = Object.keys(sectorMap);
  sectorSelect.innerHTML = sectors
    .map((sector) => `<option value="${esc(sector)}">${esc(sector)}</option>`)
    .join("");
  if (!sectors.length) {
    sectorSelect.innerHTML = '<option value="Unclassified">Unclassified</option>';
  }
  populateSubSectorDropdown();
}

function populateSubSectorDropdown() {
  const sector = $("new-sector").value || "Unclassified";
  const subSectors = sectorMap[sector] || ["Unclassified"];
  $("new-sub-sector").innerHTML = subSectors
    .map((sub) => `<option value="${esc(sub)}">${esc(sub)}</option>`)
    .join("");
}

function validateHoldingPayload(payload) {
  if (!/^[A-Z0-9.=\-]{1,20}$/.test(payload.ticker)) {
    return "Ticker is invalid. Example: AAPL, NESN.SW, BTC-USD.";
  }
  if (!payload.asset_name) {
    return "Asset name is required.";
  }
  if (!Number.isFinite(payload.quantity) || payload.quantity < 0) {
    return "Quantity must be a number greater than or equal to 0.";
  }
  if (!/^[A-Z]{3}$/.test(payload.currency)) {
    return "Currency must be a 3-letter ISO code, e.g. CHF or USD.";
  }
  if (!payload.sector || !payload.sub_sector) {
    return "Sector and sub-sector are required.";
  }
  return "";
}

function riskProfile(beta) {
  if (beta == null) return ["—", "Awaiting CAPM estimate"];
  if (beta < 0.75) return ["Defensive", `Portfolio β ${beta.toFixed(2)} — diversifiers dominate`];
  if (beta < 1.05) return ["Balanced", `Portfolio β ${beta.toFixed(2)} vs benchmark`];
  return ["Growth-tilted", `Portfolio β ${beta.toFixed(2)} — equity risk dominates`];
}

function renderHoldingsAdmin() {
  const body = $("holdings-admin-body");
  body.innerHTML = "";
  for (const h of allHoldings) {
    const tr = document.createElement("tr");
    const bucketCls = h.portfolio_bucket === "Return Assets" ? "return" : "divers";
    tr.innerHTML = `
      <td><strong>${esc(h.ticker)}</strong></td>
      <td>${esc(h.asset_name)}</td>
      <td><span class="tag ${bucketCls}">${h.portfolio_bucket === "Return Assets" ? "Return" : "Diversifying"}</span></td>
      <td>${esc(h.sector)}</td>
      <td>${esc(h.sub_sector)}</td>
      <td>${esc(h.currency)}</td>
      <td class="num">${fmtPrice(h.current_price)}</td>
      <td class="num"><input class="qty-input" data-ticker="${esc(h.ticker)}" type="number" min="0" step="any" value="${Number(h.quantity || 0)}"></td>
      <td class="num">${h.last_updated ? esc(h.last_updated.slice(0, 19).replace("T", " ")) : "—"}</td>
      <td class="num">
        <button class="btn btn-outline mini-btn" data-refresh="${esc(h.ticker)}" type="button">Refresh</button>
        <button class="btn btn-outline mini-btn" data-delete="${esc(h.ticker)}" type="button">Remove</button>
      </td>
    `;
    body.appendChild(tr);
  }

  body.querySelectorAll(".qty-input").forEach((input) =>
    input.addEventListener("change", async () => {
      const ticker = input.dataset.ticker;
      const row = allHoldings.find((x) => x.ticker === ticker);
      if (!row) return;
      try {
        showFormError("");
        await upsertHolding({ ...row, quantity: parseFloat(input.value) || 0 });
        await load();
      } catch (err) {
        showFormError(`Quantity update failed: ${err.message}`);
        setPill(`Quantity update failed: ${err.message}`, "error");
      }
    })
  );

  body.querySelectorAll("button[data-refresh]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      try {
        showFormError("");
        await refreshHoldingPrices(state.live, btn.dataset.refresh);
        await load();
      } catch (err) {
        showFormError(`Price refresh failed: ${err.message}`);
        setPill(`Price refresh failed: ${err.message}`, "error");
      }
    })
  );

  body.querySelectorAll("button[data-delete]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      try {
        showFormError("");
        await deleteHolding(btn.dataset.delete);
        await load();
      } catch (err) {
        showFormError(`Delete failed: ${err.message}`);
        setPill(`Delete failed: ${err.message}`, "error");
      }
    })
  );
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
    const bucketCls = h.portfolio_bucket === "Return Assets" ? "return" : "divers";
    tr.innerHTML = `
      <td><span class="asset-name"><span class="ticker">${esc(h.ticker)}</span><span class="full">${esc(h.asset_name)} · ${esc(h.sector)} / ${esc(h.sub_sector)}</span></span></td>
      <td><span class="tag ${bucketCls}">${h.portfolio_bucket === "Return Assets" ? "Return" : "Diversifying"}</span></td>
      <td class="num">${fmtNum(h.quantity, 2)}</td>
      <td class="num">${fmtPrice(h.price_chf)}</td>
      <td class="num">${fmtMoney(h.value)}</td>
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
    ["Last price (native)", `${fmtPrice(h.price)} ${h.currency}`],
    ["FX to CHF", fmtNum(h.fx_to_chf, 4)],
    ["Last price (CHF)", fmtPrice(h.price_chf)],
    ["Quantity", fmtNum(h.quantity, 2)],
    ["Position value", fmtMoney(h.value)],
    ["1-day move", fmtPctSigned(h.change_24h, 2)],
    ["Beta vs " + data.config.benchmark, fmtNum(h.beta)],
    ["Sharpe (period)", fmtNum(h.sharpe)],
    ["Return contribution", fmtPctSigned(h.contribution, 2)],
  ];
  $("security-detail").innerHTML = `
    <h3>Security dossier</h3>
    <div class="d-name">${esc(f.name)}</div>
    <div class="d-sector">${esc(h.ticker)} · ${esc(h.sector)} · ${esc(h.sub_sector)} · ${esc(h.portfolio_bucket)}</div>
    <p class="d-thesis">${esc(f.thesis)}</p>
    <div class="metric-rows">
      ${rows.map(([k, v]) => `<div><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join("")}
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

async function load() {
  setPill("Loading portfolio data…", "");
  try {
    const [dashboard, holdingsRes, sectorRes] = await Promise.all([
      fetchDashboard(state),
      fetchHoldings(),
      fetchSectorMap(),
    ]);
    data = dashboard;
    allHoldings = holdingsRes.holdings || [];
    sectorMap = sectorRes.sectors || {};
    populateSectorDropdown();

    renderHoldingsAdmin();
    renderHero();
    renderHoldings();
    renderStats();
    renderCharts();

    const src = data.source;
    const scope = data.config.bucket === "ALL" ? "all buckets" : data.config.bucket;
    setPill(
      `${src.label} · ${data.holdings.length} holdings · ${scope} · ${data.config.lookback}-day window`,
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

$("refresh-prices-btn").addEventListener("click", async () => {
  try {
    await refreshHoldingPrices(state.live);
    await load();
  } catch (err) {
    setPill(`Price refresh failed: ${err.message}`, "error");
  }
});

$("add-ticker-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    ticker: $("new-ticker").value.trim().toUpperCase(),
    asset_name: $("new-asset-name").value.trim(),
    quantity: parseFloat($("new-quantity").value) || 0,
    portfolio_bucket: $("new-bucket").value,
    sector: $("new-sector").value.trim(),
    sub_sector: $("new-sub-sector").value.trim(),
    currency: $("new-currency").value.trim().toUpperCase() || "CHF",
  };
  const validationError = validateHoldingPayload(payload);
  if (validationError) {
    showFormError(validationError);
    return;
  }
  try {
    showFormError("");
    await addTicker(payload);
    event.target.reset();
    $("new-bucket").value = "Return Assets";
    $("new-currency").value = "USD";
    populateSectorDropdown();
    await load();
  } catch (err) {
    showFormError(`Ticker onboarding failed: ${err.message}`);
    setPill(`Ticker onboarding failed: ${err.message}`, "error");
  }
});

$("new-sector").addEventListener("change", () => {
  populateSubSectorDropdown();
  showFormError("");
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
