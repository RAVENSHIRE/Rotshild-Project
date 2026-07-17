# Rotshild-Project
Qunat Dashboard

## Institutional Portfolio Terminal

- `app.py` — HTTP server: serves `/frontend` and the `/api/dashboard` endpoint
- `quant.py` — metrics layer: CAGR, max drawdown, Sharpe, Sortino, CAPM beta/alpha
- `data.py` — data layer: deterministic simulated prices (swap in yfinance for live data)
- `frontend/` — Dashboard, Asset Allocation, Market Intel, and Login pages (Chart.js vendored locally; Firebase auth optional — placeholder config runs in demo mode)

Run `python app.py` and open http://127.0.0.1:8000/

`index.html` at the repo root is a separate self-contained static dashboard (published as a Claude artifact).
