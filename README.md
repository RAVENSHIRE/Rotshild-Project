# Rothschild & Co — Portfolio Management Analytics Dashboard

A quantitative web application built to demonstrate wealth management analytical skills relevant to Rothschild & Co's Portfolio Management Internship (September 2026). The dashboard covers live market tracking, portfolio rebalancing, risk metrics, and investment proposal generation — all in a single, deployable Python application.

---

## Live Demo

> **Dashboard:** `https://yourname-portfolio-analytics.streamlit.app`
> **Walkthrough Video:** `https://loom.com/share/your-video-id`

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend / Backend | Python · [Streamlit](https://streamlit.io) |
| Market Data | [yfinance](https://github.com/ranaroussi/yfinance) (Yahoo Finance API) |
| Quantitative Analytics | pandas · NumPy · SciPy (`scipy.optimize`) |
| Visualisation | Plotly |
| Exports | openpyxl (Excel) · ReportLab / WeasyPrint (PDF) |
| Deployment | Streamlit Community Cloud |

Excel and VBA compatibility is built into the export layer so that output files slot directly into standard banking workflows.

---

## Dashboard Architecture

The application is structured around a sidebar navigator with four tabs, each mapped to a core responsibility listed in the internship description.

### Tab 1 — Market Overview & Asset Allocation
*"Conduct market and portfolio analyses"*

- Live price tracking for major global indices with Swiss market emphasis:
  - SMI · S&P 500 · Euro Stoxx 50 · US 10-Year Treasury Yield · Gold (XAU/USD)
- Dynamic donut chart showing a model Wealth Management allocation across Equities, Fixed Income, Cash, and Alternatives
- One-click data refresh via `yfinance`

### Tab 2 — Rebalancing Engine *(Core Feature)*
*"Support portfolio reviews and rebalancing activities"*

- User inputs a **Current Portfolio** (ticker symbols + current weights) and a **Target Portfolio**
- Engine calculates the exact buy / sell amounts (in currency and percentage terms) required to rebalance
- Output table is exportable directly to Excel for downstream PM review
- **Language toggle (EN / DE)** — all labels and UI strings switch between English and German, demonstrating bilingual proficiency

### Tab 3 — Quantitative Risk Metrics
*Quant Guild–inspired analytical layer*

| Metric | Description |
|---|---|
| Annualised Return | Geometric mean return over the selected period |
| Annualised Volatility | Rolling standard deviation (252-day basis) |
| Sharpe Ratio | `(Rp − Rf) / σp` using current risk-free rate |
| Maximum Drawdown | Peak-to-trough decline over the period |
| Correlation Matrix | Heatmap of pairwise asset correlations for diversification analysis |

### Tab 4 — Investment Proposal Generator
*"Prepare standard investment proposals and client presentation materials"*

- Compiles data from all three tabs into a downloadable **Tear Sheet**
- Two export formats:
  - **Excel** — structured workbook with separate sheets per tab, compatible with Avaloq-based workflows (`Avaloq-Compatible Data Export`)
  - **PDF** — clean single-page client-facing tear sheet
- Filenames are timestamped for version control

---

## Project Structure

```
rothschild-dashboard/
├── app.py                  # Streamlit entry point & sidebar navigation
├── tabs/
│   ├── market_overview.py  # Tab 1: live indices + asset allocation chart
│   ├── rebalancing.py      # Tab 2: rebalancing engine + EN/DE toggle
│   ├── risk_metrics.py     # Tab 3: Sharpe, drawdown, correlation heatmap
│   └── proposal.py         # Tab 4: Excel & PDF export
├── utils/
│   ├── data.py             # yfinance data fetching & caching
│   ├── analytics.py        # Return, volatility, Sharpe, drawdown calculations
│   └── export.py           # openpyxl workbook builder & PDF generator
├── requirements.txt
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- pip

### Installation

```bash
git clone https://github.com/RAVENSHIRE/Rotshild-Project.git
cd Rotshild-Project
pip install -r requirements.txt
```

### Run locally

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501` by default.

### Deploy to Streamlit Community Cloud

1. Push the repository to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) and connect the repo.
3. Set `app.py` as the entry point.
4. The app is live in under two minutes.

---

## Key Dependencies

```
streamlit
yfinance
pandas
numpy
scipy
plotly
openpyxl
reportlab
```

Install all at once:

```bash
pip install -r requirements.txt
```

---

## Presenting to Rothschild

1. **Live URL** — place the clean dashboard URL at the very top of your CV and Cover Letter.
2. **Loom Video** — record a 2-minute walkthrough:
   > *"Hi Rothschild Portfolio Management Team. I'm applying for the Internship starting September 2026. Instead of just sending a CV, I built this analytics engine to demonstrate my ability to conduct market analysis, automate rebalancing, and generate investment proposals. Here is how it works..."*
3. **LinkedIn Outreach** — send the video link to a Portfolio Manager or Investment Specialist at Rothschild & Co in Zürich with a brief, professional note.

---

## Inspiration

Quantitative rigour inspired by the analytical frameworks of **Roman Paolucci** and **Quant Guild**, adapted specifically for a **Wealth Management** context and aligned with the tooling and workflows used at Rothschild & Co.

---

## License

MIT
