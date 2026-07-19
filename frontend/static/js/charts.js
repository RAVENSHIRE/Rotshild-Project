// ------------------------------------------------------------------
// Chart.js theming + builders. Colors are read from the CSS custom
// properties in styles.css, so charts follow light/dark automatically;
// on a scheme change every chart is destroyed and rebuilt.
// ------------------------------------------------------------------

const instances = new Map(); // canvasId -> Chart
const rebuilders = [];       // page-level re-render callbacks

export const cssVar = (name) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim();

export const palette = () => ({
  s1: cssVar("--s1"),
  s2: cssVar("--s2"),
  s3: cssVar("--s3"),
  s4: cssVar("--s4"),
  pos: cssVar("--pos"),
  neg: cssVar("--neg"),
  grid: cssVar("--grid"),
  muted: cssVar("--muted"),
  ink2: cssVar("--ink-2"),
  surface: cssVar("--surface"),
});

export const classColor = (cls) => {
  const p = palette();
  return { Equities: p.s1, "Fixed Income": p.s4, Alternatives: p.s2 }[cls] || p.s3;
};
export const mandateColor = (m) => {
  const p = palette();
  return m === "Return Assets" ? p.s1 : p.s4;
};

function applyDefaults() {
  const p = palette();
  const C = window.Chart;
  C.defaults.font.family =
    '"Inter", system-ui, -apple-system, "Segoe UI", sans-serif';
  C.defaults.font.size = 11;
  C.defaults.color = p.muted;
  C.defaults.borderColor = p.grid;
  C.defaults.animation = { duration: 350 };
  C.defaults.plugins.legend.labels.boxWidth = 9;
  C.defaults.plugins.legend.labels.boxHeight = 9;
  C.defaults.plugins.legend.labels.usePointStyle = true;
  C.defaults.plugins.legend.labels.pointStyle = "rectRounded";
  C.defaults.plugins.tooltip.backgroundColor = cssVar("--navy") || "#14203a";
  C.defaults.plugins.tooltip.titleColor = "#f5f2ea";
  C.defaults.plugins.tooltip.bodyColor = "#d5dae4";
  C.defaults.plugins.tooltip.cornerRadius = 6;
  C.defaults.plugins.tooltip.padding = 10;
  C.defaults.plugins.tooltip.displayColors = true;
  C.defaults.plugins.tooltip.boxWidth = 8;
  C.defaults.plugins.tooltip.boxHeight = 8;
}

function mount(canvasId, config) {
  const el = document.getElementById(canvasId);
  if (!el) return null;
  applyDefaults();
  instances.get(canvasId)?.destroy();
  const chart = new window.Chart(el.getContext("2d"), config);
  instances.set(canvasId, chart);
  return chart;
}

const monthTicks = {
  maxRotation: 0,
  autoSkip: true,
  maxTicksLimit: 6,
  callback(value) {
    const label = this.getLabelForValue(value); // YYYY-MM-DD
    return label ? label.slice(0, 7) : "";
  },
};

/** Multi-series time line (portfolio vs benchmark, beta, …). */
export function lineChart(canvasId, labels, series, { yFormat, legend } = {}) {
  const p = palette();
  return mount(canvasId, {
    type: "line",
    data: {
      labels,
      datasets: series.map((s) => ({
        label: s.label,
        data: s.data,
        borderColor: s.color,
        borderWidth: 2,
        borderDash: s.dashed ? [5, 4] : undefined,
        pointRadius: 0,
        pointHoverRadius: 4,
        pointHoverBackgroundColor: s.color,
        fill: s.fill ? { target: "origin", above: s.color + "1f", below: s.color + "1f" } : false,
        tension: 0.15,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: legend !== false && series.length > 1, position: "top", align: "start" },
        tooltip: {
          callbacks: yFormat
            ? { label: (c) => ` ${c.dataset.label}: ${yFormat(c.parsed.y)}` }
            : {},
        },
      },
      scales: {
        x: { grid: { display: false }, border: { color: p.grid }, ticks: monthTicks },
        y: {
          grid: { color: p.grid },
          border: { display: false },
          ticks: yFormat ? { callback: (v) => yFormat(v), maxTicksLimit: 6 } : { maxTicksLimit: 6 },
        },
      },
    },
  });
}

/** Minimal sparkline for the hero panel — no axes, no legend. */
export function sparkChart(canvasId, labels, data, color) {
  return mount(canvasId, {
    type: "line",
    data: {
      labels,
      datasets: [{
        data,
        borderColor: color,
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 3,
        fill: { target: "origin", above: color + "24" },
        tension: 0.2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: { x: { display: false }, y: { display: false } },
    },
  });
}

/** Doughnut with 2px surface spacers; legend rendered by the caller. */
export function donutChart(canvasId, labels, values, colors, { format } = {}) {
  const p = palette();
  return mount(canvasId, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: colors,
        borderColor: p.surface,
        borderWidth: 2,
        hoverOffset: 5,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "68%",
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => ` ${c.label}: ${(format || ((v) => v.toFixed(1) + "%"))(c.parsed)}`,
          },
        },
      },
    },
  });
}

/** Horizontal diverging bar (per-security contribution, drift). */
export function divergingBar(canvasId, labels, values, { format } = {}) {
  const p = palette();
  return mount(canvasId, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: values.map((v) => (v >= 0 ? p.pos : p.neg)),
        borderRadius: 4,
        borderSkipped: false,
        barThickness: 16,
        maxBarThickness: 18,
      }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => ` ${(format || ((v) => v.toFixed(2) + "%"))(c.parsed.x)}`,
          },
        },
      },
      scales: {
        x: {
          grid: { color: p.grid },
          border: { display: false },
          ticks: format ? { callback: (v) => format(v), maxTicksLimit: 7 } : { maxTicksLimit: 7 },
        },
        y: { grid: { display: false }, border: { color: p.grid }, ticks: { color: p.ink2 } },
      },
    },
  });
}

/** Re-render all charts when the OS/color-scheme flips. */
export function onThemeChange(rebuild) {
  rebuilders.push(rebuild);
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  rebuilders.forEach((fn) => fn());
});
