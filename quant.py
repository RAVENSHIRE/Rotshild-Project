"""Quantitative analytics for the Rotshild portfolio dashboard.

Pure functions operating on pandas objects. No I/O, no Streamlit — this module
is deliberately importable and testable on its own.

Conventions
-----------
* ``prices``  : DataFrame of adjusted close prices, indexed by date, one column
  per instrument.
* ``returns`` : simple (arithmetic) daily returns, i.e. ``prices.pct_change()``.
* Annualisation assumes ``TRADING_DAYS`` observations per year.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252
ROLLING_WINDOW = 63  # ~one quarter of trading days


def daily_returns(prices: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    """Simple daily returns, with the leading NaN row dropped."""
    return prices.pct_change().dropna(how="all")


def cagr(prices: pd.Series) -> float:
    """Compound annual growth rate implied by the first and last price."""
    prices = prices.dropna()
    if len(prices) < 2:
        return float("nan")
    total_return = prices.iloc[-1] / prices.iloc[0]
    years = len(prices) / TRADING_DAYS
    if years <= 0 or total_return <= 0:
        return float("nan")
    return float(total_return ** (1 / years) - 1)


def max_drawdown(prices: pd.Series) -> float:
    """Largest peak-to-trough decline (a negative number, e.g. -0.23)."""
    prices = prices.dropna()
    if prices.empty:
        return float("nan")
    running_max = prices.cummax()
    drawdown = prices / running_max - 1.0
    return float(drawdown.min())


def _daily_rf(rf_annual: float) -> float:
    """Convert an annual risk-free rate to a per-trading-day rate."""
    return (1 + rf_annual) ** (1 / TRADING_DAYS) - 1


def sharpe_ratio(returns: pd.Series, rf_annual: float = 0.0) -> float:
    """Annualised Sharpe ratio of a daily return series."""
    returns = returns.dropna()
    if len(returns) < 2:
        return float("nan")
    excess = returns - _daily_rf(rf_annual)
    std = excess.std(ddof=1)
    if std == 0 or np.isnan(std):
        return float("nan")
    return float(excess.mean() / std * np.sqrt(TRADING_DAYS))


def sortino_ratio(returns: pd.Series, rf_annual: float = 0.0) -> float:
    """Annualised Sortino ratio (downside-deviation denominator)."""
    returns = returns.dropna()
    if len(returns) < 2:
        return float("nan")
    excess = returns - _daily_rf(rf_annual)
    downside = excess[excess < 0]
    if downside.empty:
        return float("inf")
    downside_dev = np.sqrt((downside ** 2).mean())
    if downside_dev == 0 or np.isnan(downside_dev):
        return float("nan")
    return float(excess.mean() / downside_dev * np.sqrt(TRADING_DAYS))


def portfolio_returns(returns: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Weighted daily returns of a portfolio.

    Weights are aligned to the columns of ``returns`` and renormalised so they
    sum to one over the instruments actually present.
    """
    cols = [c for c in returns.columns if c in weights]
    if not cols:
        return pd.Series(dtype=float)
    w = np.array([weights[c] for c in cols], dtype=float)
    total = w.sum()
    if total == 0:
        return pd.Series(0.0, index=returns.index)
    w = w / total
    return (returns[cols] * w).sum(axis=1)


def simple_beta(asset_returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """Full-sample CAPM beta: cov(asset, bench) / var(bench)."""
    joined = pd.concat([asset_returns, benchmark_returns], axis=1).dropna()
    if len(joined) < 2:
        return float("nan")
    var = joined.iloc[:, 1].var()
    if var == 0 or np.isnan(var):
        return float("nan")
    return float(joined.iloc[:, 0].cov(joined.iloc[:, 1]) / var)


def asset_contributions(
    returns: pd.DataFrame, weights: dict[str, float]
) -> dict[str, float]:
    """Approximate contribution of each asset to total portfolio return.

    Contribution_i = weight_i × cumulative return of asset i over the window
    (the standard buy-and-hold attribution approximation).
    """
    cols = [c for c in returns.columns if c in weights]
    if not cols:
        return {}
    w = np.array([weights[c] for c in cols], dtype=float)
    total = w.sum()
    if total == 0:
        return {c: 0.0 for c in cols}
    w = w / total
    cumulative = (1 + returns[cols].fillna(0)).prod() - 1
    return {c: float(w[i] * cumulative[c]) for i, c in enumerate(cols)}


def rolling_capm(
    asset_returns: pd.Series,
    benchmark_returns: pd.Series,
    window: int = ROLLING_WINDOW,
    rf_annual: float = 0.0,
) -> pd.DataFrame:
    """Rolling CAPM regression of an asset onto its benchmark.

    Returns a DataFrame with two columns:

    * ``beta``  : rolling cov(asset, bench) / var(bench).
    * ``alpha`` : rolling intercept, **annualised** (daily alpha × TRADING_DAYS).
    """
    rf = _daily_rf(rf_annual)
    a = (asset_returns - rf).rename("asset")
    b = (benchmark_returns - rf).rename("bench")
    joined = pd.concat([a, b], axis=1).dropna()
    if len(joined) < window:
        return pd.DataFrame(columns=["beta", "alpha"])

    cov = joined["asset"].rolling(window).cov(joined["bench"])
    var = joined["bench"].rolling(window).var()
    beta = cov / var
    mean_a = joined["asset"].rolling(window).mean()
    mean_b = joined["bench"].rolling(window).mean()
    alpha_daily = mean_a - beta * mean_b
    out = pd.DataFrame(
        {"beta": beta, "alpha": alpha_daily * TRADING_DAYS}
    ).dropna()
    return out


def summary_metrics(
    prices: pd.Series, rf_annual: float = 0.0
) -> dict[str, float]:
    """Headline performance metrics for a single price series."""
    rets = prices.pct_change().dropna()
    return {
        "cagr": cagr(prices),
        "max_drawdown": max_drawdown(prices),
        "sharpe": sharpe_ratio(rets, rf_annual),
        "sortino": sortino_ratio(rets, rf_annual),
    }


def rebalance_trades(
    current_weights: dict[str, float],
    target_weights: dict[str, float],
    portfolio_value: float,
) -> pd.DataFrame:
    """Trades needed to move current weights to target weights.

    Positive ``Trade Value`` = buy, negative = sell. Weights are renormalised
    within each set so rounding in the UI never breaks the arithmetic.
    """
    instruments = sorted(set(current_weights) | set(target_weights))

    def _norm(d: dict[str, float]) -> dict[str, float]:
        total = sum(d.get(i, 0.0) for i in instruments)
        if total == 0:
            return {i: 0.0 for i in instruments}
        return {i: d.get(i, 0.0) / total for i in instruments}

    cur = _norm(current_weights)
    tgt = _norm(target_weights)

    rows = []
    for i in instruments:
        drift = tgt[i] - cur[i]
        rows.append(
            {
                "Instrument": i,
                "Current Weight": cur[i],
                "Target Weight": tgt[i],
                "Drift": drift,
                "Trade Value": drift * portfolio_value,
            }
        )
    return pd.DataFrame(rows)
