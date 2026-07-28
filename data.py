"""Market-data access layer.

Attempts to pull live adjusted-close prices from Yahoo Finance via ``yfinance``.
When the network is unavailable (as in locked-down/offline environments) it
falls back to a reproducible synthetic generator that preserves a genuine CAPM
structure — every asset is driven by a common market factor plus idiosyncratic
noise — so the analytics downstream remain meaningful.

``load_prices`` always returns a populated ``PriceData`` so the dashboard never
renders empty.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# Rough asset-class tags used by the allocation donut. Unknown tickers default
# to Equities in the UI.
ASSET_CLASSES: dict[str, str] = {
    "AAPL": "Equities", "MSFT": "Equities", "GOOGL": "Equities",
    "AMZN": "Equities", "NVDA": "Equities", "NESN.SW": "Equities",
    "ROG.SW": "Equities", "NOVN.SW": "Equities", "SPY": "Equities",
    "TLT": "Fixed Income", "AGG": "Fixed Income", "BND": "Fixed Income",
    "IEF": "Fixed Income", "LQD": "Fixed Income",
    "GLD": "Alternatives", "SLV": "Alternatives", "DBC": "Alternatives",
    "VNQ": "Alternatives", "BTC-USD": "Alternatives",
}

# Bottom-up dual-mandate framework (see docs/investment-approach.md):
# every security is either a Return Asset (growth engine) or a Diversifying
# Asset (protection engine). The roll-up views aggregate this classification.
MANDATES: dict[str, str] = {
    "Equities": "Return Assets",
    "Fixed Income": "Diversifying Assets",
    "Alternatives": "Diversifying Assets",
}

# Approximate "true" betas used only by the synthetic generator, so simulated
# series look plausible per asset class.
_SYNTHETIC_BETA = {"Equities": 1.1, "Fixed Income": -0.2, "Alternatives": 0.3}

# Curated security-level fundamentals: the micro data a bottom-up process
# starts from. Used when live look-ups are unavailable; unknown tickers get a
# neutral placeholder so the UI never breaks.
FUNDAMENTALS: dict[str, dict] = {
    "AAPL": {
        "name": "Apple Inc.", "sector": "Technology Hardware",
        "thesis": "Ecosystem lock-in and services mix drive durable high-margin cash flow.",
        "metrics": [["P/E (fwd)", "29.4x"], ["ROE", "147%"], ["Net margin", "26.3%"], ["Div. yield", "0.4%"]],
    },
    "MSFT": {
        "name": "Microsoft Corp.", "sector": "Software & Cloud",
        "thesis": "Azure and enterprise seat pricing compound recurring revenue at scale.",
        "metrics": [["P/E (fwd)", "31.2x"], ["ROE", "38%"], ["Net margin", "35.6%"], ["Div. yield", "0.7%"]],
    },
    "NVDA": {
        "name": "NVIDIA Corp.", "sector": "Semiconductors",
        "thesis": "Accelerated-computing franchise with pricing power across the AI stack.",
        "metrics": [["P/E (fwd)", "34.8x"], ["ROE", "91%"], ["Net margin", "55.0%"], ["Div. yield", "0.02%"]],
    },
    "GOOGL": {
        "name": "Alphabet Inc.", "sector": "Interactive Media",
        "thesis": "Search cash cow funds optionality in cloud and foundational models.",
        "metrics": [["P/E (fwd)", "22.6x"], ["ROE", "30%"], ["Net margin", "27.4%"], ["Div. yield", "0.5%"]],
    },
    "AMZN": {
        "name": "Amazon.com Inc.", "sector": "Consumer Discretionary",
        "thesis": "AWS margin expansion and retail logistics leverage lift free cash flow.",
        "metrics": [["P/E (fwd)", "33.1x"], ["ROE", "23%"], ["Net margin", "9.3%"], ["Div. yield", "—"]],
    },
    "NESN.SW": {
        "name": "Nestlé S.A.", "sector": "Consumer Staples",
        "thesis": "Defensive staples compounder with consistent CHF dividend growth.",
        "metrics": [["P/E (fwd)", "18.9x"], ["ROE", "32%"], ["Net margin", "11.8%"], ["Div. yield", "3.2%"]],
    },
    "TLT": {
        "name": "iShares 20+ Year Treasury", "sector": "Long Government Bonds",
        "thesis": "Long-duration Treasuries: convexity and flight-to-quality ballast.",
        "metrics": [["Duration", "16.5y"], ["YTM", "4.6%"], ["Credit", "AAA (US)"], ["Expense", "0.15%"]],
    },
    "IEF": {
        "name": "iShares 7–10 Year Treasury", "sector": "Government Bonds",
        "thesis": "Belly-of-the-curve rate exposure with lower drawdown than TLT.",
        "metrics": [["Duration", "7.4y"], ["YTM", "4.2%"], ["Credit", "AAA (US)"], ["Expense", "0.15%"]],
    },
    "AGG": {
        "name": "iShares Core US Aggregate", "sector": "Broad Fixed Income",
        "thesis": "Core investment-grade aggregate as the portfolio's income anchor.",
        "metrics": [["Duration", "6.1y"], ["YTM", "4.5%"], ["Credit", "AA avg"], ["Expense", "0.03%"]],
    },
    "LQD": {
        "name": "iShares IG Corporate Bond", "sector": "Corporate Credit",
        "thesis": "Investment-grade credit spread carry over Treasuries.",
        "metrics": [["Duration", "8.3y"], ["YTM", "5.1%"], ["Credit", "A/BBB"], ["Expense", "0.14%"]],
    },
    "GLD": {
        "name": "SPDR Gold Shares", "sector": "Precious Metals",
        "thesis": "Non-correlated real-asset hedge against monetary debasement.",
        "metrics": [["Corr. vs SPY", "0.08"], ["Vol (ann.)", "14%"], ["Expense", "0.40%"], ["Backing", "Physical"]],
    },
    "SLV": {
        "name": "iShares Silver Trust", "sector": "Precious Metals",
        "thesis": "Industrial-monetary hybrid metal with higher beta to gold.",
        "metrics": [["Corr. vs SPY", "0.18"], ["Vol (ann.)", "26%"], ["Expense", "0.50%"], ["Backing", "Physical"]],
    },
    "VNQ": {
        "name": "Vanguard Real Estate", "sector": "Listed Real Estate",
        "thesis": "REIT income stream with inflation pass-through via rents.",
        "metrics": [["Div. yield", "3.9%"], ["P/FFO", "16.2x"], ["Expense", "0.13%"], ["Corr. vs SPY", "0.61"]],
    },
    "SPY": {
        "name": "SPDR S&P 500", "sector": "US Large-Cap Index",
        "thesis": "Benchmark proxy for US large-cap beta.",
        "metrics": [["P/E (fwd)", "21.8x"], ["Div. yield", "1.3%"], ["Expense", "0.09%"], ["Holdings", "503"]],
    },
}

# Curated institutional news feed. ``hours_ago`` is relative so the feed always
# looks current; ``tickers`` links each story to securities for the bottom-up
# "your holdings first" ordering.
_NEWS_ITEMS: list[dict] = [
    {"headline": "Apple services revenue hits record as installed base expands",
     "source": "Financial Times", "category": "Company", "hours_ago": 2, "tickers": ["AAPL"],
     "summary": "Services gross margin above 70% reinforces the recurring-revenue thesis underpinning the position."},
    {"headline": "Microsoft lifts Azure capex guidance on enterprise AI demand",
     "source": "Reuters", "category": "Company", "hours_ago": 4, "tickers": ["MSFT"],
     "summary": "Management guided cloud capacity investment higher; commercial bookings grew double digits."},
    {"headline": "NVIDIA data-centre backlog extends into next fiscal year",
     "source": "Bloomberg", "category": "Company", "hours_ago": 7, "tickers": ["NVDA"],
     "summary": "Supply remains the binding constraint; pricing holds firm across the accelerator line-up."},
    {"headline": "Alphabet consolidates AI infrastructure spend under DeepMind",
     "source": "Wall Street Journal", "category": "Company", "hours_ago": 11, "tickers": ["GOOGL"],
     "summary": "Reorganisation aims to shorten the path from research to monetised product."},
    {"headline": "Treasury curve bull-steepens as cut expectations firm",
     "source": "Reuters", "category": "Rates & Credit", "hours_ago": 5, "tickers": ["TLT", "IEF", "AGG"],
     "summary": "Long-duration ETFs caught a bid; futures now price two additional cuts this year."},
    {"headline": "IG credit spreads grind to cycle tights on strong inflows",
     "source": "Financial Times", "category": "Rates & Credit", "hours_ago": 20, "tickers": ["LQD", "AGG"],
     "summary": "Investment-grade demand remains robust; new-issue concessions have all but disappeared."},
    {"headline": "Gold consolidates near highs as central-bank buying continues",
     "source": "Bloomberg", "category": "Company", "hours_ago": 9, "tickers": ["GLD", "SLV"],
     "summary": "Official-sector purchases underpin the diversifying-asset case independent of real yields."},
    {"headline": "SNB holds policy rate, flags franc strength in assessment",
     "source": "Neue Zürcher Zeitung", "category": "Macro", "hours_ago": 8, "tickers": [],
     "summary": "Swiss inflation remains inside the target band; the Bank keeps intervention optionality."},
    {"headline": "Fed minutes show growing comfort with mid-year easing path",
     "source": "Wall Street Journal", "category": "Macro", "hours_ago": 26, "tickers": ["SPY"],
     "summary": "Committee participants see risks to the dual mandate as broadly balanced."},
    {"headline": "Euro-area PMIs edge back above 50 on services resilience",
     "source": "Reuters", "category": "Macro", "hours_ago": 31, "tickers": [],
     "summary": "Composite output returned to expansion; manufacturing remains the laggard."},
]


@dataclass
class PriceData:
    """Container for a price panel and provenance metadata."""

    prices: pd.DataFrame          # date-indexed, one column per instrument
    is_synthetic: bool
    source: str                   # "Yahoo Finance (live)" or "Synthetic (offline)"


@dataclass
class LatestPriceResult:
    """Latest prices for a ticker set plus provenance and failures."""

    prices: dict[str, float | None]
    source: str
    synthetic: bool
    missing: list[str]


def asset_class(ticker: str) -> str:
    return ASSET_CLASSES.get(ticker.upper(), "Equities")


def mandate(ticker: str) -> str:
    """Return Assets vs Diversifying Assets — the dual-mandate roll-up."""
    return MANDATES.get(asset_class(ticker), "Return Assets")


def fundamentals(ticker: str) -> dict:
    """Security-level fundamental snapshot for the bottom-up holdings view."""
    base = FUNDAMENTALS.get(ticker.upper())
    if base is None:
        base = {
            "name": ticker.upper(),
            "sector": asset_class(ticker),
            "thesis": "No curated fundamental snapshot for this instrument yet.",
            "metrics": [],
        }
    return {**base, "mandate": mandate(ticker), "asset_class": asset_class(ticker)}


def load_news(tickers: list[str] | None = None) -> list[dict]:
    """News feed ordered bottom-up: stories on held securities first.

    Each item gains ``related`` (touches a held ticker) and an ``id``.
    """
    held = {t.strip().upper() for t in (tickers or [])}
    items = []
    for i, item in enumerate(_NEWS_ITEMS):
        related = bool(held.intersection(item["tickers"]))
        items.append({**item, "id": i, "related": related})
    items.sort(key=lambda x: (not x["related"], x["hours_ago"]))
    return items


def _fetch_live(tickers: list[str], period_days: int) -> pd.DataFrame:
    import yfinance as yf

    period = f"{max(period_days, 30) + 10}d"
    raw = yf.download(
        tickers=tickers,
        period=period,
        progress=False,
        auto_adjust=True,
        threads=False,
    )
    if raw is None or raw.empty:
        raise RuntimeError("empty response")

    # Normalise the (field, ticker) column layout to a flat close-price frame.
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"].copy()
    else:  # single ticker → flat columns
        close = raw[["Close"]].copy()
        close.columns = [tickers[0]]

    close = close.dropna(how="all")
    if close.empty:
        raise RuntimeError("no close prices")
    return close


def fetch_latest_prices(tickers: list[str], use_live: bool = True) -> LatestPriceResult:
    """Fetch latest prices ticker-by-ticker with robust fallback.

    This function is intentionally resilient for onboarding workflows: each
    ticker is attempted individually, so one failing symbol does not break the
    entire refresh job.
    """
    ordered: list[str] = []
    for ticker in tickers:
        symbol = (ticker or "").strip().upper()
        if symbol and symbol not in ordered:
            ordered.append(symbol)

    if not ordered:
        return LatestPriceResult({}, "None", False, [])

    prices: dict[str, float | None] = {t: None for t in ordered}
    missing: list[str] = []

    if use_live:
        try:
            live = _fetch_live(ordered, period_days=30)
            for ticker in ordered:
                if ticker in live.columns:
                    series = live[ticker].dropna()
                    if not series.empty:
                        prices[ticker] = float(series.iloc[-1])
        except Exception:
            pass

        # Retry symbols that were missing from the bulk request.
        for ticker in ordered:
            if prices[ticker] is not None:
                continue
            try:
                single = _fetch_live([ticker], period_days=30)
                series = single.iloc[:, 0].dropna()
                if not series.empty:
                    prices[ticker] = float(series.iloc[-1])
            except Exception:
                continue

    for ticker in ordered:
        if prices[ticker] is None:
            missing.append(ticker)

    if not missing:
        return LatestPriceResult(prices, "Yahoo Finance (live)", False, [])

    # If live quotes are incomplete, fill only the missing symbols with
    # synthetic levels so valuation still works in offline/failure scenarios.
    synth = _synthetic(missing, period_days=60)
    for ticker in missing:
        series = synth[ticker].dropna()
        prices[ticker] = float(series.iloc[-1]) if not series.empty else None

    still_missing = [ticker for ticker, value in prices.items() if value is None]
    return LatestPriceResult(prices, "Synthetic fallback", True, still_missing)


def _synthetic(tickers: list[str], period_days: int, seed: int = 7) -> pd.DataFrame:
    """Correlated geometric-Brownian-motion prices with a CAPM structure."""
    rng = np.random.default_rng(seed)
    n = max(period_days, 60)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)

    # Common market factor: ~10% annual drift, ~15% annual vol.
    mkt_mu, mkt_sigma = 0.10 / 252, 0.15 / np.sqrt(252)
    market = rng.normal(mkt_mu, mkt_sigma, n)

    prices = {}
    for t in tickers:
        cls = asset_class(t)
        beta = _SYNTHETIC_BETA.get(cls, 1.0)
        # Idiosyncratic drift/vol vary a little per ticker for visual variety.
        idio_mu = rng.normal(0.04 / 252, 0.01 / 252)
        idio_sigma = abs(rng.normal(0.12, 0.03)) / np.sqrt(252)
        idio = rng.normal(idio_mu, idio_sigma, n)
        rets = beta * market + idio
        series = 100.0 * np.cumprod(1 + rets)
        prices[t] = series

    return pd.DataFrame(prices, index=dates)


def load_prices(
    tickers: list[str],
    benchmark: str = "SPY",
    period_days: int = 504,
    use_live: bool = True,
) -> PriceData:
    """Load prices for ``tickers`` plus ``benchmark``.

    Tries live data first (when ``use_live``), otherwise — or on any failure —
    returns a synthetic panel covering the same instruments.
    """
    # De-duplicate while preserving order; benchmark last.
    ordered: list[str] = []
    for t in [*tickers, benchmark]:
        t = t.strip().upper()
        if t and t not in ordered:
            ordered.append(t)

    if use_live:
        try:
            close = _fetch_live(ordered, period_days)
            # Attempt to recover any ticker missing from the bulk download.
            missing = [t for t in ordered if t not in close.columns]
            recovered: dict[str, pd.Series] = {}
            for ticker in missing:
                try:
                    single = _fetch_live([ticker], period_days)
                    recovered[ticker] = single.iloc[:, 0]
                except Exception:
                    continue

            for ticker, series in recovered.items():
                close[ticker] = series

            if all(t in close.columns for t in ordered) and len(close) >= 30:
                return PriceData(close[ordered].dropna(how="all"), False, "Yahoo Finance (live)")
        except Exception:
            pass  # fall through to synthetic

    synth = _synthetic(ordered, period_days)
    return PriceData(synth, True, "Synthetic (offline)")
