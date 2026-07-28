"""Portfolio calculation utilities used by the dashboard workflow."""

from __future__ import annotations

import pandas as pd

from quant import summary_metrics


def position_values_chf(holdings: list[dict], fx_rates: dict[str, float]) -> dict[str, float]:
    """Return CHF market value per ticker: price * quantity * FX-to-CHF."""
    values: dict[str, float] = {}
    for holding in holdings:
        ticker = str(holding["ticker"])
        currency = str(holding["currency"])
        fx = float(fx_rates[currency])
        price = float(holding["current_price"])
        quantity = float(holding["quantity"])
        values[ticker] = price * quantity * fx
    return values


def total_portfolio_value_chf(position_values: dict[str, float]) -> float:
    return float(sum(position_values.values()))


def benchmark_comparison(portfolio_values: pd.Series, benchmark_values: pd.Series) -> dict[str, float]:
    """Comparable total-return deltas for portfolio vs benchmark curves."""
    if portfolio_values.empty or benchmark_values.empty:
        return {"portfolio_total_return": 0.0, "benchmark_total_return": 0.0, "excess_return": 0.0}

    p_ret = float(portfolio_values.iloc[-1] / portfolio_values.iloc[0] - 1)
    b_ret = float(benchmark_values.iloc[-1] / benchmark_values.iloc[0] - 1)
    return {
        "portfolio_total_return": p_ret,
        "benchmark_total_return": b_ret,
        "excess_return": p_ret - b_ret,
    }


def risk_free_aware_metrics(prices: pd.Series, risk_free_annual: float) -> dict[str, float]:
    """Risk-aware headline metrics using annual risk-free input."""
    return summary_metrics(prices, risk_free_annual)
