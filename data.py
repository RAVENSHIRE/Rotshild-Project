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

# Approximate "true" betas used only by the synthetic generator, so simulated
# series look plausible per asset class.
_SYNTHETIC_BETA = {"Equities": 1.1, "Fixed Income": -0.2, "Alternatives": 0.3}


@dataclass
class PriceData:
    """Container for a price panel and provenance metadata."""

    prices: pd.DataFrame          # date-indexed, one column per instrument
    is_synthetic: bool
    source: str                   # "Yahoo Finance (live)" or "Synthetic (offline)"


def asset_class(ticker: str) -> str:
    return ASSET_CLASSES.get(ticker.upper(), "Equities")


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
            missing = [t for t in ordered if t not in close.columns]
            if not missing and len(close) >= 30:
                return PriceData(close[ordered], False, "Yahoo Finance (live)")
        except Exception:
            pass  # fall through to synthetic

    synth = _synthetic(ordered, period_days)
    return PriceData(synth, True, "Synthetic (offline)")
