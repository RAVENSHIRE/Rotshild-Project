"""Market price data via yfinance, with a deterministic offline fallback.

The fallback keeps the dashboard fully renderable in restricted-network
environments (CI, remote sandboxes) — swap in real data by simply having
network access; no code change needed.
"""

import numpy as np
import pandas as pd

# Seeded GBM parameters per demo ticker: (annual drift, annual vol)
_DEMO_PARAMS: dict[str, tuple[float, float]] = {
    "VTI": (0.09, 0.16),
    "VXUS": (0.06, 0.17),
    "BND": (0.03, 0.05),
    "GLD": (0.05, 0.14),
    "BIL": (0.045, 0.003),
    "SPY": (0.10, 0.15),
}


def fetch_prices(tickers: list[str], period: str = "2y") -> tuple[pd.DataFrame, bool]:
    """Return (adjusted close prices, is_live).

    Tries yfinance first; on any failure returns synthetic demo data so the
    UI always renders. `is_live` tells the caller which one it got.
    """
    try:
        import yfinance as yf

        raw = yf.download(tickers, period=period, progress=False, auto_adjust=True)
        prices = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
        if isinstance(prices, pd.Series):
            prices = prices.to_frame(tickers[0])
        prices = prices.dropna(how="all")
        if prices.empty:
            raise ValueError("yfinance returned no data")
        return prices, True
    except Exception:
        return _demo_prices(tickers, period), False


def _demo_prices(tickers: list[str], period: str) -> pd.DataFrame:
    years = {"1y": 1, "2y": 2, "5y": 5}.get(period, 2)
    n = 252 * years
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    out = {}
    for i, t in enumerate(tickers):
        mu, sigma = _DEMO_PARAMS.get(t, (0.06, 0.15))
        rng = np.random.default_rng(seed=hash(t) % (2**32))
        dt = 1 / 252
        shocks = rng.normal((mu - 0.5 * sigma**2) * dt, sigma * np.sqrt(dt), n)
        out[t] = 100.0 * np.exp(np.cumsum(shocks))
    return pd.DataFrame(out, index=dates)
