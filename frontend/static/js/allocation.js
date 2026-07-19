// ------------------------------------------------------------------
// Allocation page: security-level target editor → trade proposals →
// live class/mandate roll-ups. Targets persist locally and, when
// signed in, to Firestore.
// ------------------------------------------------------------------
import {
  fetchDashboard, postRebalance, loadState, saveState,
  esc, fmtMoney, fmtPct, fmtPctSigned, signClass,
} from "./api.js";
import { donutChart, divergingBar, classColor, mandateColor, onThemeChange } from "./charts.js";
import { initShell } from "./shell.js";

let state = loadState();
let holdings = [];           // from /api/dashboard
let targets = {};            // {TICKER: percent}
const $ = (id) => document.getElementById(id);

// ---- Editor ------------------------------------------------------- //
function driftOf(h) {
  return (targets[h.ticker] ?? h.weight) - h.weight;
}

function renderEditor() {
  const body = $("allocation-editor-body");
  body.innerHTML = "";
  for (const h of holdings) {
    const tr = document.createElement("tr");
    const mandateCls = h.mandate === "Return Assets" ? "return" : "divers";
    tr.innerHTML = `
      <td><span class="asset-name"><span class="ticker">${esc(h.ticker)}</span><span class="full">${esc(h.fundamentals.name)}</span></span></td>
      <td>${esc(h.asset_class)}</td>
      <td><span class="tag ${mandateCls}">${h.mandate === "Return Assets" ? "Return" : "Diversifying"}</span></td>
      <td class="num">${fmtPct(h.weight)}</td>
      <td class="num"><input class="target-input" type="number" min="0" max="100" step="0.5"
            value="${(targets[h.ticker] ?? h.weight).toFixed(1)}" data-ticker="${esc(h.ticker)}"></td>
      <td><span class="drift-cell">
            <span class="drift-track"><span class="drift-fill" data-ticker="${esc(h.ticker)}"></span></span>
            <small class="drift-label ${signClass(driftOf(h))}" data-ticker="${esc(h.ticker)}">${fmtPctSigned(driftOf(h))}</small>
          </span></td>`;
    body.appendChild(tr);
  }
  body.querySelectorAll(".target-input").forEach((input) =>
    input.addEventListener("input", () => {
      targets[input.dataset.ticker] = parseFloat(input.value) || 0;
      refreshDrift();
      renderRollups();
      renderTotal();
    })
  );
  refreshDrift();
  renderTotal();
}

function refreshDrift() {
  const maxDrift = Math.max(5, ...holdings.map((h) => Math.abs(driftOf(h))));
  const pos = getComputedStyle(document.documentElement).getPropertyValue("--pos").trim();
  const neg = getComputedStyle(document.documentElement).getPropertyValue("--neg").trim();
  for (const h of holdings) {
    const drift = driftOf(h);
    const fill = document.querySelector(`.drift-fill[data-ticker="${h.ticker}"]`);
    const label = document.querySelector(`.drift-label[data-ticker="${h.ticker}"]`);
    if (!fill || !label) continue;
    const half = Math.min(50, (Math.abs(drift) / maxDrift) * 50);
    fill.style.background = drift >= 0 ? pos : neg;
    fill.style.left = drift >= 0 ? "50%" : `${50 - half}%`;
    fill.style.width = `${half}%`;
    label.textContent = fmtPctSigned(drift);
    label.className = `drift-label ${signClass(drift)}`;
  }
}

function renderTotal() {
  const total = holdings.reduce((sum, h) => sum + (targets[h.ticker] ?? h.weight), 0);
  const el = $("target-total");
  el.textContent = fmtPct(total);
  el.style.color = Math.abs(total - 100) < 0.51 ? "" : "var(--neg)";
}

// ---- Roll-ups (consequence of the security-level targets) --------- //
function rollup(keyFn) {
  const out = {};
  const total = holdings.reduce((s, h) => s + (targets[h.ticker] ?? h.weight), 0) || 1;
  for (const h of holdings) {
    const key = keyFn(h);
    out[key] = (out[key] || 0) + ((targets[h.ticker] ?? h.weight) / total) * 100;
  }
  return out;
}

function legend(containerId, entries, colorFn) {
  $(containerId).innerHTML =
    (containerId === "allocation-list" ? "<h3>By asset class</h3>" : "") +
    Object.entries(entries)
      .map(
        ([label, value]) => `
        <div class="allocation-item">
          <span><i class="dot" style="background:${esc(colorFn(label))}"></i>${esc(label)}</span>
          <strong>${fmtPct(value)}</strong>
        </div>`
      )
      .join("");
}

function renderRollups() {
  const byClass = rollup((h) => h.asset_class);
  const byMandate = rollup((h) => h.mandate);
  donutChart("allocationChart", Object.keys(byClass), Object.values(byClass),
    Object.keys(byClass).map(classColor));
  donutChart("mandateChart", Object.keys(byMandate), Object.values(byMandate),
    Object.keys(byMandate).map(mandateColor));
  legend("allocation-list", byClass, classColor);
  legend("mandate-list", byMandate, mandateColor);
}

// ---- Trades ------------------------------------------------------- //
async function computeTrades() {
  const current = Object.fromEntries(holdings.map((h) => [h.ticker, h.weight]));
  const target = Object.fromEntries(holdings.map((h) => [h.ticker, targets[h.ticker] ?? h.weight]));
  const result = await postRebalance(current, target, state.portfolioValue);
  const body = $("trades-table-body");
  body.innerHTML = "";
  for (const t of result.trades) {
    const sideCls = t.side === "BUY" ? "positive" : t.side === "SELL" ? "negative" : "";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span class="asset-name"><span class="ticker">${esc(t.instrument)}</span><span class="full">${esc(t.asset_class)} · ${esc(t.mandate)}</span></span></td>
      <td class="${sideCls}" style="font-weight:600;">${esc(t.side)}</td>
      <td class="num">${fmtPct(t.current_weight)}</td>
      <td class="num">${fmtPct(t.target_weight)}</td>
      <td class="num ${signClass(t.drift)}">${fmtPctSigned(t.drift)}</td>
      <td class="num ${signClass(t.trade_value)}">${fmtMoney(Math.abs(t.trade_value))}</td>`;
    body.appendChild(tr);
  }
  $("trades-section").hidden = false;
  $("trades-section").scrollIntoView({ behavior: "smooth", block: "start" });
}

function flash(text) {
  const el = $("save-flash");
  el.textContent = text;
  setTimeout(() => (el.textContent = ""), 3200);
}

// ---- Load --------------------------------------------------------- //
async function load() {
  const pill = $("data-source-pill");
  try {
    const data = await fetchDashboard(state);
    holdings = data.holdings;
    targets = { ...(state.targets || {}) };
    for (const h of holdings) if (targets[h.ticker] == null) targets[h.ticker] = h.weight;
    pill.textContent = data.source.label;
    pill.className = "status-pill " + (data.source.synthetic ? "synthetic" : "live");
    renderEditor();
    renderRollups();
  } catch (err) {
    pill.textContent = `Error: ${err.message}`;
    pill.className = "status-pill error";
  }
}

$("compute-trades-btn").addEventListener("click", () =>
  computeTrades().catch((err) => flash("Trade computation failed: " + err.message))
);
$("apply-targets-btn").addEventListener("click", async () => {
  state.targets = { ...targets };
  await saveState(state);
  flash("Targets applied — dashboard now weights the book accordingly.");
});
$("save-cloud-btn").addEventListener("click", async () => {
  state.targets = { ...targets };
  await saveState(state, { cloud: true });
  flash("Allocation saved" + (localStorage.getItem("rotshild-demo-user") ? " (demo store)" : "") + ".");
});

initShell({
  onUserReady(_user, remoteState) {
    if (remoteState) {
      state = remoteState;
      load();
    }
  },
});
onThemeChange(() => holdings.length && renderRollups());
load();
