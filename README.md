# Rotshild Portfolio Dashboard

A four-page, institutional-grade **bottom-up portfolio management dashboard**:
security-level fundamentals and risk analytics roll up into a dual-mandate book
of **Return Assets** (growth) and **Diversifying Assets** (protection) — see
[`docs/investment-approach.md`](docs/investment-approach.md).

Zero-framework frontend (vanilla ES modules + Chart.js, self-hosted) on a
layered, dependency-light Python backend (stdlib HTTP server + pandas/numpy).
Firebase provides authentication and Firestore persistence, with a built-in
**demo mode** so everything works before any Firebase project exists.

## Pages

| Route | Page | What it does |
| --- | --- | --- |
| `/` | **Dashboard** | Hero KPIs (value, β, α, Sharpe), portfolio controls, the **security-level book** with per-holding fundamentals dossier, contribution-by-security and rolling-CAPM charts, portfolio-vs-benchmark roll-up. |
| `/allocation` | **Allocation** | Asset-by-asset target-weight editor with drift bars → **proposed trades** (buys/sells net to zero) → live roll-up donuts by asset class and by dual mandate. Targets can be applied to the dashboard and saved to the cloud. |
| `/news` | **News** | Curated institutional feed ordered bottom-up: stories touching held securities first; filters for holdings / company / rates & credit / macro. |
| `/login` | **Login** | Firebase email/password sign-in & sign-up (or simulated demo auth); on sign-in the user's saved portfolio state is pulled from Firestore. |
| `/desk` | **PFM Desk** | A conceptual clone of the **Avaloq Core Platform PFM** model: aggregated Business-Partner book (total AuM, discretionary share, open restriction flags), container drilldown with current-vs-target allocation, a **restriction engine** (asset-class ceilings, Retail suitability blocks, minimum-cash liquidity, single-position concentration → PASS/WARNING/BREACH), and a **model rebalancing engine** whose self-financing order proposals are pre-trade checked against every rule. |

## Architecture

```
frontend/                     ← served by app.py
  index.html · allocation.html · news.html · login.html
  static/styles.css           ← design tokens (light + dark), layout
  static/vendor/chart.umd.min.js  ← self-hosted Chart.js (no CDN dependency)
  static/js/
    firebase-config.js        ← paste your Firebase web config here
    firebase.js               ← auth + Firestore layer (demo-mode fallback)
    api.js                    ← state model, backend fetches, formatting
    charts.js                 ← Chart.js theme (CVD-validated palette), builders
    shell.js                  ← nav, auth button, EN/DE i18n
    dashboard.js · allocation.js · news.js · login.js

app.py      ← HTTP routing: pages + JSON API (+ optional firebase-admin endpoints)
data.py     ← market data (Yahoo live / synthetic fallback), fundamentals, news, mandates
portfolio_store.py ← SQLite persistence: normalized holdings + ticker onboarding catalog
quant.py    ← pure analytics: CAGR, drawdown, Sharpe/Sortino, CAPM, contributions, rebalancing
pfm.py      ← Avaloq-style PFM layer: BP/Container/Position object model,
              restriction engine, target models, compliance-checked rebalancing
i18n.py     ← EN/DE string table (served at /api/i18n)
test_quant.py  ← analytics sanity tests
test_pfm.py    ← restriction/rebalancing engine tests
test_portfolio_store.py ← holdings-schema and workflow persistence tests
test_portfolio_calcs.py ← CHF valuation / benchmark comparison utility tests
```

### API

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/dashboard` | GET | Full payload from normalized holdings rows. Params: `benchmark, lookback, risk_free, live, bucket` (`ALL`, `Return Assets`, `Diversifying Assets`). Portfolio value is computed automatically as `Σ(price × quantity × FX-to-CHF)`. |
| `/api/holdings` | GET/POST/DELETE | Holdings CRUD. One row per instrument with ticker, name, quantity, bucket, sector, sub-sector, currency, current price, update timestamp. |
| `/api/holdings/refresh-prices` | POST | Refreshes live prices for all active holdings (falls back to synthetic when live quotes fail). |
| `/api/tickers` | GET/POST | Ticker onboarding catalog + automated row creation workflow for new instruments with bucket/sector/sub-sector classification. |
| `/api/sector-map` | GET | Sector → sub-sector lookup map used by UI dropdowns and backend validation. |
| `/api/rebalance` | POST | `{current, target, portfolio_value}` → trade blotter (weights renormalised, trades net to zero). |
| `/api/news` | GET | Feed with `related` flags for held tickers. |
| `/api/i18n` | GET | EN/DE translation table. |
| `/api/portfolio` | GET/POST | Server-side Firestore read/write, verified via Firebase ID token (requires `firebase-admin`; otherwise 501 and the client SDK is used). |
| `/api/pfm/desk` | GET | Aggregated PFM-desk view: every Business Partner with AuM, drift, and compliance status. |
| `/api/pfm/portfolio` | GET | Container detail (`id=PF-2001`): positions, class weights vs target model, restriction report. |
| `/api/pfm/rebalance` | POST | `{portfolio_id}` → self-financing model-rebalancing orders + post-trade restriction check. |
| `/api/health` | GET | Liveness + firebase-admin status. |

## Quick start

```bash
pip install -r requirements.txt
python app.py            # serves http://127.0.0.1:8000/ and opens the browser
python test_quant.py     # analytics tests
python test_pfm.py       # restriction/rebalancing engine tests
python test_portfolio_store.py  # normalized holdings persistence tests
python test_portfolio_calcs.py  # portfolio CHF valuation utility tests
```

Live prices come from Yahoo Finance; without network the app transparently
switches to reproducible synthetic data with a realistic CAPM structure (the
status pill always states the active source).

## Firebase setup (optional — demo mode works without it)

1. Create a project at <https://console.firebase.google.com> → add a **Web app**.
2. Enable **Authentication → Sign-in method → Email/Password**.
3. Create a **Cloud Firestore** database, and restrict access to each user's own
   document:
   ```
   match /users/{uid} { allow read, write: if request.auth.uid == uid; }
   ```
4. Paste the web config into `frontend/static/js/firebase-config.js`.
5. *(Optional, server-side)* `pip install firebase-admin`, download a
   service-account key, and export
   `GOOGLE_APPLICATION_CREDENTIALS=/path/to/serviceAccount.json` before
   `python app.py` — this activates token-verified `/api/portfolio`.

Until step 4 the login page runs in clearly-labelled **demo mode**
(localStorage-simulated auth and cloud), so the full sign-in → persist →
reload flow is demonstrable offline.

## Methodology notes

- Annualisation uses 252 trading days; Sharpe/Sortino on daily excess returns.
- The risk-free input is annualized; the quant layer converts it to daily in `quant._daily_rf` for excess-return metrics (Sharpe, Sortino, CAPM alpha/beta).
- Rolling CAPM: β = cov/var over 63 days, α is the annualised intercept.
- Contribution ≈ weight × cumulative security return (buy-and-hold attribution).
- Portfolio valuation currency is CHF: each row is valued as `current_price × quantity × FX(currency→CHF)` and then aggregated.
- Rebalancing trades are `(target − current) × portfolio value`; net zero.
- Chart palette (light `#24558F/#B3862F/#BE5488/#12855F`, dark equivalents) is
  validated for colour-vision-deficiency separation and surface contrast.
