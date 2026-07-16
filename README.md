# Rotshild-Project — Quant Dashboard

A Streamlit dashboard for a **bottom-up, two-pillar investment approach**:

- **Return assets** — produce long-term capital growth
- **Diversifying assets** — provide protection and diversification

The dashboard has three tabs plus a benchmark-relative KPI row
(CAGR, max drawdown, Sharpe, Sortino — each vs the benchmark, default SPY):

- **Market Overview** — cumulative returns, per-asset risk/return, correlations
- **Quant Risk & CAPM** — rolling 63-day beta and annualized alpha (window adjustable)
- **Rebalancing Engine** — allocation donut, current vs target weights, trade list + CSV export

Prices come from Yahoo Finance (with a synthetic offline fallback), web
research via [Firecrawl](https://firecrawl.dev). Styled with an
institutional navy/gold theme (`.streamlit/config.toml`).

## Quick start

### Option A — GitHub Codespaces (recommended)

1. Open <https://codespaces.new/RAVENSHIRE/Rotshild-Project> (or the green
   **Code ▸ Codespaces ▸ Create codespace** button on the repo).
2. Wait for the container build — it auto-installs Python deps and the
   Firecrawl CLI (`.devcontainer/devcontainer.json`).
3. Add your Firecrawl key as a Codespaces secret named `FIRECRAWL_API_KEY`
   (repo **Settings ▸ Secrets and variables ▸ Codespaces**), or create a
   local `.env` from `.env.example`.
4. Run the dashboard:

   ```bash
   streamlit run app/main.py
   ```

   Port 8501 is auto-forwarded and opens in a preview tab.

### Option B — Local

```bash
git clone https://github.com/RAVENSHIRE/Rotshild-Project.git
cd Rotshild-Project
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then paste your Firecrawl key
streamlit run app/main.py
```

## Project structure

```
app/main.py          Streamlit dashboard (UI only)
core/portfolio.py    Two-pillar portfolio model (Asset, Pillar, Portfolio)
core/analytics.py    Returns, volatility, drawdown, correlation
core/data/market.py  Prices via yfinance (+ offline demo fallback)
core/data/web.py     Firecrawl scrape/search for news & research
core/config.py       .env loading, API keys
.devcontainer/       Codespaces / Dev Container setup
ARCHITECTURE.md      Precise architecture, contracts, and roadmap
FIRECRAWL.md         Firecrawl setup, usage, and proxy notes
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the module contracts and the
development roadmap, and [FIRECRAWL.md](FIRECRAWL.md) for web-data setup.

## Development notes

- **No live data? No problem.** If Yahoo Finance is unreachable the app
  renders with clearly-flagged synthetic demo data, so you can develop
  anywhere (including restricted networks).
- **Secrets** live only in `.env` (gitignored) or Codespaces secrets.
- **Editing holdings:** replace `demo_portfolio()` in `core/portfolio.py`
  with your real allocations; weights must sum to 1.0.
