// ------------------------------------------------------------------
// PFM Desk: aggregated Business Partner book, container drilldown,
// restriction engine report, and compliance-checked model rebalancing.
// ------------------------------------------------------------------
import { esc, fmtMoney, fmtPct, fmtPctSigned, signClass } from "./api.js";
import { divergingBar, onThemeChange } from "./charts.js";
import { initShell } from "./shell.js";

const $ = (id) => document.getElementById(id);
let selected = null;   // portfolio_id
let detail = null;     // last portfolio_detail payload

async function getJSON(url, options) {
  const res = await fetch(url, options);
  const body = await res.json();
  if (!res.ok || body.error) throw new Error(body.error || `HTTP ${res.status}`);
  return body;
}

const complianceBadge = (status) => {
  const cls = status === "BREACH" ? "negative" : status === "WARNING" ? "warn" : "positive";
  const icon = status === "BREACH" ? "✕" : status === "WARNING" ? "▲" : "✓";
  return `<span class="badge ${cls}">${icon} ${esc(status)}</span>`;
};

// ---- Desk overview ------------------------------------------------ //
async function loadDesk() {
  const desk = await getJSON("/api/pfm/desk");
  const t = desk.totals;
  $("desk-aum").textContent = fmtMoney(t.aum);
  $("desk-aum-note").textContent = "across all containers";
  $("desk-clients").textContent = t.clients;
  $("desk-discretionary").textContent = fmtPct(t.discretionary_share);
  $("desk-flags").textContent = `${t.breaches} / ${t.warnings}`;
  $("desk-flags-note").textContent = "breaches / warnings";
  $("desk-flags").className = t.breaches > 0 ? "negative" : t.warnings > 0 ? "warn" : "positive";

  const body = $("desk-table-body");
  body.innerHTML = "";
  for (const c of desk.clients) {
    const tr = document.createElement("tr");
    tr.className = "selectable" + (c.portfolio_id === selected ? " selected" : "");
    const svcCls = c.service_type === "Discretionary" ? "return" : "divers";
    tr.innerHTML = `
      <td><span class="asset-name"><span class="ticker">${esc(c.client)}</span><span class="full">${esc(c.bp_id)} · ${esc(c.portfolio)}</span></span></td>
      <td>${esc(c.segment)}</td>
      <td><span class="tag ${svcCls}">${esc(c.service_type)}</span></td>
      <td>${esc(c.model)}</td>
      <td class="num">${fmtMoney(c.aum)}</td>
      <td class="num">${fmtPct(c.max_drift)}</td>
      <td>${complianceBadge(c.compliance)}</td>`;
    tr.addEventListener("click", () => openPortfolio(c.portfolio_id));
    body.appendChild(tr);
  }
}

// ---- Container drilldown ------------------------------------------ //
function restrictionRows(containerId, results) {
  $(containerId).innerHTML = results
    .map(
      (r) => `
      <div class="restriction-item">
        <div class="r-head">
          <span class="r-rule">${esc(r.rule_id)} · ${esc(r.description)}</span>
          ${complianceBadge(r.status)}
        </div>
        <div class="r-body">Measured <strong>${esc(r.measured)}</strong> · limit <strong>${esc(r.limit)}</strong></div>
      </div>`
    )
    .join("");
}

async function openPortfolio(portfolioId) {
  selected = portfolioId;
  detail = await getJSON(`/api/pfm/portfolio?id=${encodeURIComponent(portfolioId)}`);
  $("orders-section").hidden = true;

  $("detail-eyebrow").textContent =
    `${detail.bp_id} · ${detail.segment} · ${detail.service_type} · ${detail.model}`;
  $("detail-title").textContent = `${detail.client} — ${detail.portfolio}`;

  $("detail-classes-body").innerHTML = detail.classes
    .map(
      (c) => `
      <tr>
        <td>${esc(c.asset_class)}</td>
        <td class="num">${fmtPct(c.current)}</td>
        <td class="num">${fmtPct(c.target)}</td>
        <td class="num ${signClass(c.drift)}">${fmtPctSigned(c.drift)}</td>
      </tr>`
    )
    .join("");

  $("detail-positions-body").innerHTML = detail.positions
    .map(
      (p) => `
      <tr>
        <td><span class="asset-name"><span class="ticker">${esc(p.instrument)}</span></span></td>
        <td>${esc(p.asset_class)}</td>
        <td><span class="tag ${p.mandate === "Return Assets" ? "return" : "divers"}">${p.mandate === "Return Assets" ? "Return" : "Diversifying"}</span></td>
        <td class="num">${fmtMoney(p.value)}</td>
        <td class="num">${fmtPct(p.weight)}</td>
      </tr>`
    )
    .join("");

  restrictionRows("restriction-list", detail.restrictions);
  renderDriftChart();

  $("portfolio-detail-section").hidden = false;
  loadDesk(); // refresh row highlight
  $("portfolio-detail-section").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderDriftChart() {
  if (!detail) return;
  divergingBar(
    "deskDriftChart",
    detail.classes.map((c) => c.asset_class),
    detail.classes.map((c) => c.drift),
    { format: (v) => fmtPctSigned(v, 1) }
  );
}

// ---- Rebalancing -------------------------------------------------- //
async function runRebalance() {
  if (!selected) return;
  const btn = $("run-rebalance-btn");
  btn.disabled = true;
  try {
    const result = await getJSON("/api/pfm/rebalance", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ portfolio_id: selected }),
    });
    $("orders-table-body").innerHTML = result.orders.length
      ? result.orders
          .map(
            (o) => `
            <tr>
              <td><span class="asset-name"><span class="ticker">${esc(o.instrument)}</span></span></td>
              <td>${esc(o.asset_class)}</td>
              <td class="${o.side === "BUY" ? "positive" : "negative"}" style="font-weight:600;">${esc(o.side)}</td>
              <td class="num ${signClass(o.amount)}">${fmtMoney(Math.abs(o.amount))}</td>
            </tr>`
          )
          .join("")
      : '<tr><td colspan="4">Portfolio is already on model — no orders required.</td></tr>';
    restrictionRows("pretrade-list", result.pre_trade_check);
    $("orders-verdict").innerHTML =
      `Pre-trade verdict: ${complianceBadge(result.verdict)} — orders are self-financing (net ≈ 0).`;
    $("orders-section").hidden = false;
    $("orders-section").scrollIntoView({ behavior: "smooth", block: "start" });
  } finally {
    btn.disabled = false;
  }
}

$("run-rebalance-btn").addEventListener("click", () =>
  runRebalance().catch((err) => {
    $("orders-verdict").textContent = `Rebalancing failed: ${err.message}`;
    $("orders-section").hidden = false;
  })
);

initShell({});
onThemeChange(() => renderDriftChart());
loadDesk().catch((err) => {
  $("desk-table-body").innerHTML =
    `<tr><td colspan="7">Could not load the client book: ${esc(err.message)}</td></tr>`;
});
