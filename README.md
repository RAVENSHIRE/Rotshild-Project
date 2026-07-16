# Rotshild Quant Dashboard

A Swiss private-banking style **portfolio analytics dashboard** for quantitative
portfolio managers, built with [Streamlit](https://streamlit.io). It computes
real quant metrics from market data and presents them in an institutional
navy/gold interface.

![sections](https://img.shields.io/badge/sections-4-0B1F3A) ![lang](https://img.shields.io/badge/i18n-EN%20%2F%20DE-C5A25A)

## Features

The app is organised into four sections (left-hand navigation):

| Section | What it does |
| --- | --- |
| **Market Overview** | KPI cards for **CAGR**, **Max Drawdown**, **Sharpe** and **Sortino**, each compared against the benchmark, plus a rebased cumulative-performance chart. |
| **Quant Risk & CAPM** | **Rolling 63-day Beta** and **Annualized Alpha** from a rolling CAPM regression of any instrument (or the portfolio) onto the benchmark. |
| **Rebalancing Engine** | Asset-allocation **donut** by class, an editable **current vs target** weights table, and a one-click **optimal-trade** calculation. |
| **Avaloq/VBA Export** | Exports the proposed trades as **CSV** (Avaloq-style) and as a ready-to-paste **VBA array** for Excel macros. |

Other niceties:

- **Bilingual** interface — English / German toggle in the sidebar.
- Configurable **tickers**, **benchmark**, **risk-free rate**, and **look-back**.
- **Live data** via Yahoo Finance when the network allows, with an automatic,
  clearly-labelled fallback to **reproducible synthetic data** that preserves a
  realistic CAPM structure, so the dashboard works fully offline.

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the URL Streamlit prints (default <http://localhost:8501>).

## Project layout

| File | Purpose |
| --- | --- |
| `app.py` | Streamlit UI, theming, and section rendering. |
| `quant.py` | Pure analytics — CAGR, drawdown, Sharpe/Sortino, rolling CAPM, rebalancing. No I/O. |
| `data.py` | Market-data layer: live Yahoo Finance fetch with synthetic fallback. |
| `i18n.py` | EN/DE string table. |
| `test_quant.py` | Sanity tests for the analytics (`python test_quant.py`). |

## Methodology notes

- **Annualisation** uses 252 trading days.
- **Sharpe / Sortino** are computed on daily excess returns over the (daily-ised)
  risk-free rate and annualised by √252; Sortino uses downside deviation only.
- **Rolling CAPM** estimates β as `cov(asset, bench) / var(bench)` over a 63-day
  window and reports the regression intercept (α) annualised.
- **Rebalancing** trades are `(target − current) weight × portfolio value`, so
  proposed buys and sells net to zero.

## Data availability

Yahoo Finance is reached through `yfinance`. In restricted network
environments the request is blocked, and the app transparently switches to
synthetic data — a banner and the "Data source" caption always tell you which
mode you are in.
