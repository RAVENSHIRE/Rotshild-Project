// script.js — dashboard logic engine: fetches /api/dashboard and binds the DOM.

let performanceChart = null;

document.addEventListener("DOMContentLoaded", () => {
    fetchDashboardData();
});

async function fetchDashboardData() {
    try {
        // Relative URL: the frontend is served by app.py itself, so the call
        // is same-origin and CORS never comes into play.
        const response = await fetch("/api/dashboard?tickers=AAPL,MSFT,NVDA&benchmark=SPY&portfolio_value=1250000");
        if (!response.ok) throw new Error("API responded " + response.status);
        const data = await response.json();

        document.getElementById("benchmark-label").textContent = "BENCHMARK: " + data.benchmark;
        updateMetrics(data.metrics);
        renderChart(data.charts.performance, data.benchmark);
        populateHoldingsTable(data.holdings);
    } catch (error) {
        console.error("Error fetching portfolio data:", error);
        document.getElementById("total-value").textContent = "API offline";
    }
}

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const usdCents = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const pct = new Intl.NumberFormat("en-US", { style: "percent", minimumFractionDigits: 2, signDisplay: "exceptZero" });

function updateMetrics(metrics) {
    const p = metrics.portfolio;
    document.getElementById("total-value").textContent = usd.format(p.value);

    const returnEl = document.getElementById("total-return");
    returnEl.textContent = pct.format(p.total_return);
    returnEl.className = p.total_return >= 0 ? "pnl positive" : "pnl negative";

    document.getElementById("metric-cagr").textContent = pct.format(p.cagr);
    document.getElementById("metric-dd").textContent = pct.format(p.max_drawdown);
    document.getElementById("metric-sharpe").textContent = p.sharpe.toFixed(2);
    document.getElementById("metric-sortino").textContent = p.sortino.toFixed(2);
    document.getElementById("metric-beta").textContent = metrics.capm.beta.toFixed(2);

    const alphaEl = document.getElementById("metric-alpha");
    alphaEl.textContent = pct.format(metrics.capm.alpha);
    alphaEl.className = metrics.capm.alpha >= 0 ? "positive" : "negative";
}

function renderChart(chartData, benchmarkName) {
    const ctx = document.getElementById("performanceChart").getContext("2d");
    if (performanceChart) performanceChart.destroy();

    performanceChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: chartData.labels,
            datasets: [
                {
                    label: "Portfolio Value",
                    data: chartData.portfolio,
                    borderColor: "#5B8CFF",
                    backgroundColor: "rgba(91,140,255,0.1)",
                    borderWidth: 2,
                    fill: true,
                    pointRadius: 0,
                    tension: 0.15
                },
                {
                    label: "Benchmark (" + benchmarkName + ")",
                    data: chartData.benchmark,
                    borderColor: "#8A94A7",
                    borderDash: [5, 5],
                    borderWidth: 2,
                    fill: false,
                    pointRadius: 0,
                    tension: 0.15
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
                legend: { labels: { color: "#eef2f9", usePointStyle: true, pointStyle: "line" } },
                tooltip: {
                    callbacks: {
                        label: (item) => item.dataset.label + ": " + usd.format(item.parsed.y)
                    }
                }
            },
            scales: {
                x: { display: false },
                y: {
                    grid: { color: "rgba(255,255,255,0.05)" },
                    ticks: {
                        color: "#8A94A7",
                        callback: (v) => usd.format(v)
                    }
                }
            }
        }
    });
}

function populateHoldingsTable(holdings) {
    const tbody = document.getElementById("holdings-table-body");
    tbody.replaceChildren();

    const cell = (text, className) => {
        const td = document.createElement("td");
        td.textContent = text;
        if (className) td.className = className;
        return td;
    };

    holdings.forEach((asset) => {
        const tr = document.createElement("tr");
        tr.appendChild(cell(asset.ticker, "strong"));
        tr.appendChild(cell(asset.asset_class));
        tr.appendChild(cell(usdCents.format(asset.price)));
        tr.appendChild(cell(
            (asset.change_24h > 0 ? "+" : "") + asset.change_24h.toFixed(2) + "%",
            asset.change_24h >= 0 ? "positive" : "negative"
        ));
        tr.appendChild(cell(usd.format(asset.value)));
        tr.appendChild(cell(asset.current_weight.toFixed(2) + "%"));
        tr.appendChild(cell(asset.target_weight.toFixed(2) + "%"));
        tr.appendChild(cell(
            (asset.drift > 0 ? "+" : "") + asset.drift.toFixed(2) + "%",
            Math.abs(asset.drift) > 2 ? "negative" : ""
        ));

        const tdAction = document.createElement("td");
        const btn = document.createElement("button");
        btn.className = "btn";
        btn.type = "button";
        btn.textContent = "Analyze";
        btn.addEventListener("click", () => {
            window.location.href = "allocation.html#" + encodeURIComponent(asset.ticker);
        });
        tdAction.appendChild(btn);
        tr.appendChild(tdAction);

        tbody.appendChild(tr);
    });
}
