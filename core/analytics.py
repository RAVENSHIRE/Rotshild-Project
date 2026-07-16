"""Return and risk analytics over a wide price DataFrame (index=date, cols=tickers)."""

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.pct_change().dropna(how="all")


def cumulative_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return prices / prices.iloc[0] - 1.0


def portfolio_series(prices: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Daily-rebalanced weighted portfolio return series, compounded to an index (start=1)."""
    rets = daily_returns(prices[list(weights)])
    port = (rets * pd.Series(weights)).sum(axis=1)
    return (1.0 + port).cumprod()


def annualized_return(prices: pd.DataFrame) -> pd.Series:
    n_days = len(prices)
    total = prices.iloc[-1] / prices.iloc[0]
    return total ** (TRADING_DAYS / max(n_days, 1)) - 1.0


def annualized_volatility(prices: pd.DataFrame) -> pd.Series:
    return daily_returns(prices).std() * np.sqrt(TRADING_DAYS)


def max_drawdown(prices: pd.DataFrame) -> pd.Series:
    cummax = prices.cummax()
    return ((prices - cummax) / cummax).min()


def correlation_matrix(prices: pd.DataFrame) -> pd.DataFrame:
    return daily_returns(prices).corr()


def cagr(series: pd.Series) -> float:
    """Compound annual growth rate of a price/index series."""
    n_days = len(series)
    if n_days < 2:
        return 0.0
    return float((series.iloc[-1] / series.iloc[0]) ** (TRADING_DAYS / n_days) - 1.0)


def sharpe_ratio(series: pd.Series, risk_free: float = 0.0) -> float:
    """Annualized Sharpe ratio of a price/index series."""
    rets = series.pct_change().dropna()
    excess = rets - risk_free / TRADING_DAYS
    std = excess.std()
    if std == 0:
        return 0.0
    return float(excess.mean() / std * np.sqrt(TRADING_DAYS))


def sortino_ratio(series: pd.Series, risk_free: float = 0.0) -> float:
    """Annualized Sortino ratio (downside deviation only)."""
    rets = series.pct_change().dropna()
    excess = rets - risk_free / TRADING_DAYS
    downside = excess[excess < 0].std()
    if downside == 0 or np.isnan(downside):
        return 0.0
    return float(excess.mean() / downside * np.sqrt(TRADING_DAYS))


def rolling_beta(asset: pd.Series, benchmark: pd.Series, window: int = 63) -> pd.Series:
    """Rolling CAPM beta of an asset/portfolio index vs a benchmark index."""
    a, b = asset.pct_change().dropna(), benchmark.pct_change().dropna()
    a, b = a.align(b, join="inner")
    cov = a.rolling(window).cov(b)
    var = b.rolling(window).var()
    return (cov / var).dropna()


def rolling_alpha(asset: pd.Series, benchmark: pd.Series, window: int = 63) -> pd.Series:
    """Rolling annualized CAPM alpha (Jensen's alpha, rf=0) vs a benchmark index."""
    a, b = asset.pct_change().dropna(), benchmark.pct_change().dropna()
    a, b = a.align(b, join="inner")
    beta = rolling_beta(asset, benchmark, window)
    alpha_daily = a.rolling(window).mean() - beta * b.rolling(window).mean()
    return (alpha_daily * TRADING_DAYS).dropna()
