// ------------------------------------------------------------------
// News page: /api/news feed, holdings-first ordering, filter chips.
// ------------------------------------------------------------------
import { esc, fetchHoldings, fetchNews, timeAgo } from "./api.js";
import { initShell } from "./shell.js";
let items = [];
let filter = "all";

function render() {
  const grid = document.getElementById("news-grid");
  const visible = items.filter((item) => {
    if (filter === "all") return true;
    if (filter === "holdings") return item.related;
    return item.category === filter;
  });
  if (!visible.length) {
    grid.innerHTML = '<article class="news-card"><p>No stories match this filter.</p></article>';
    return;
  }
  grid.innerHTML = visible
    .map(
      (item) => `
      <article class="news-card${item.related ? " related" : ""}">
        <div class="news-meta">
          <span class="source">${esc(item.source)}</span>
          <span>·</span>
          <span>${esc(timeAgo(item.hours_ago))}</span>
          <span>·</span>
          <span>${esc(item.category)}</span>
          ${item.related ? '<span class="held-badge">Held position</span>' : ""}
        </div>
        <h3>${esc(item.headline)}</h3>
        <p>${esc(item.summary)}</p>
        <div class="news-tags">
          ${item.tickers.map((t) => `<span class="tag">${esc(t)}</span>`).join("")}
        </div>
      </article>`
    )
    .join("");
}

document.querySelectorAll("#news-filters .chip").forEach((chip) =>
  chip.addEventListener("click", () => {
    filter = chip.dataset.filter;
    document.querySelectorAll("#news-filters .chip").forEach((c) =>
      c.classList.toggle("active", c === chip)
    );
    render();
  })
);

initShell({});
Promise.all([fetchHoldings(), fetchNews()])
  .then(([holdingsRes, fallbackNews]) => {
    const heldTickers = (holdingsRes.holdings || [])
      .filter((h) => (h.quantity || 0) > 0)
      .map((h) => h.ticker);
    if (!heldTickers.length) {
      items = fallbackNews.items;
      render();
      return;
    }
    return fetchNews(heldTickers).then((res) => {
      items = res.items;
      render();
    });
  })
  .catch((err) => {
    document.getElementById("news-grid").innerHTML =
      `<article class="news-card"><p>Could not load the news feed: ${esc(err.message)}</p></article>`;
  });
