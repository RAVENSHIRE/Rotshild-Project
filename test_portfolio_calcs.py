"""Sanity tests for portfolio calculation utilities."""

from __future__ import annotations

import pandas as pd

from portfolio_calcs import (
    benchmark_comparison,
    position_values_chf,
    risk_free_aware_metrics,
    total_portfolio_value_chf,
)


def approx(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) < tol


def test_position_and_total_value_chf():
    holdings = [
        {"ticker": "AAPL", "current_price": 200.0, "quantity": 10, "currency": "USD"},
        {"ticker": "NESN.SW", "current_price": 90.0, "quantity": 5, "currency": "CHF"},
    ]
    fx = {"USD": 0.88, "CHF": 1.0}
    pos = position_values_chf(holdings, fx)
    assert approx(pos["AAPL"], 1760.0)
    assert approx(pos["NESN.SW"], 450.0)
    assert approx(total_portfolio_value_chf(pos), 2210.0)


def test_benchmark_comparison():
    p = pd.Series([100.0, 110.0])
    b = pd.Series([100.0, 105.0])
    out = benchmark_comparison(p, b)
    assert approx(out["portfolio_total_return"], 0.10)
    assert approx(out["benchmark_total_return"], 0.05)
    assert approx(out["excess_return"], 0.05)


def test_risk_free_aware_metrics_shape():
    prices = pd.Series([100.0, 101.0, 103.0, 102.0, 104.0])
    m = risk_free_aware_metrics(prices, 0.02)
    for key in ["cagr", "max_drawdown", "sharpe", "sortino"]:
        assert key in m


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)} tests passed.")
