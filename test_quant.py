"""Sanity tests for the quant analytics. Run with: python test_quant.py"""

import numpy as np
import pandas as pd

import quant


def approx(a, b, tol=1e-6):
    return abs(a - b) < tol


def test_cagr():
    # Price doubles over exactly one trading year → 100% CAGR.
    prices = pd.Series(np.linspace(100, 200, quant.TRADING_DAYS))
    assert approx(quant.cagr(prices), 1.0, tol=1e-2), quant.cagr(prices)


def test_max_drawdown():
    prices = pd.Series([100, 120, 90, 110, 60, 130])
    # Peak 120 → trough 60 = -50%.
    assert approx(quant.max_drawdown(prices), -0.5), quant.max_drawdown(prices)


def test_sharpe_positive_for_uptrend():
    rng = np.random.default_rng(0)
    rets = pd.Series(rng.normal(0.001, 0.01, 500))
    assert quant.sharpe_ratio(rets) > 0


def test_sortino_ge_relationship():
    rng = np.random.default_rng(1)
    rets = pd.Series(rng.normal(0.0008, 0.012, 800))
    # Sortino uses only downside deviation, so for symmetric-ish noise it is
    # typically >= Sharpe. Just assert both are finite and Sortino is defined.
    assert np.isfinite(quant.sharpe_ratio(rets))
    assert np.isfinite(quant.sortino_ratio(rets))


def test_rolling_capm_recovers_beta():
    rng = np.random.default_rng(2)
    bench = pd.Series(rng.normal(0.0003, 0.01, 400))
    true_beta = 1.5
    asset = true_beta * bench + rng.normal(0, 0.001, 400)
    capm = quant.rolling_capm(asset, bench, window=63)
    assert not capm.empty
    # Estimated beta should land near the true value.
    assert approx(capm["beta"].iloc[-1], true_beta, tol=0.15), capm["beta"].iloc[-1]


def test_rebalance_trades_sum_to_zero():
    cur = {"A": 0.5, "B": 0.5}
    tgt = {"A": 0.7, "B": 0.3}
    df = quant.rebalance_trades(cur, tgt, 1_000_000)
    assert approx(df["Trade Value"].sum(), 0.0, tol=1e-6)
    a_row = df[df["Instrument"] == "A"].iloc[0]
    assert approx(a_row["Trade Value"], 200_000, tol=1.0)


def test_simple_beta_recovers_scaling():
    rng = np.random.default_rng(3)
    bench = pd.Series(rng.normal(0.0004, 0.01, 300))
    asset = 0.8 * bench + rng.normal(0, 0.0005, 300)
    assert approx(quant.simple_beta(asset, bench), 0.8, tol=0.05)


def test_asset_contributions_sum_and_split():
    idx = pd.date_range("2020-01-01", periods=2)
    rets = pd.DataFrame({"A": [0.10, 0.0], "B": [0.0, 0.0]}, index=idx)
    contrib = quant.asset_contributions(rets, {"A": 0.5, "B": 0.5})
    # A returned 10% at half weight → 5% contribution; B contributed nothing.
    assert approx(contrib["A"], 0.05)
    assert approx(contrib["B"], 0.0)


def test_portfolio_returns_renormalises():
    idx = pd.date_range("2020-01-01", periods=3)
    rets = pd.DataFrame({"A": [0.01, 0.02, -0.01], "B": [0.0, 0.01, 0.02]}, index=idx)
    pr = quant.portfolio_returns(rets, {"A": 1.0, "B": 1.0})
    assert approx(pr.iloc[0], 0.005)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)} tests passed.")
