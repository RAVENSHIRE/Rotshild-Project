"""Quant layer: risk-adjusted performance metrics for the dashboard.

All functions take plain lists of floats so the layer has no third-party
dependencies. Return series are simple daily returns; annualization assumes
252 trading days.
"""

import math

TRADING_DAYS = 252


def daily_returns(prices):
    return [prices[i] / prices[i - 1] - 1 for i in range(1, len(prices))]


def total_return(prices):
    return prices[-1] / prices[0] - 1


def cagr(prices, periods_per_year=TRADING_DAYS):
    years = (len(prices) - 1) / periods_per_year
    if years <= 0:
        return 0.0
    return (prices[-1] / prices[0]) ** (1 / years) - 1


def max_drawdown(prices):
    peak = -math.inf
    worst = 0.0
    for p in prices:
        peak = max(peak, p)
        worst = min(worst, p / peak - 1)
    return worst


def _mean(xs):
    return sum(xs) / len(xs)


def _std(xs):
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def annualized_vol(returns, periods_per_year=TRADING_DAYS):
    return _std(returns) * math.sqrt(periods_per_year)


def sharpe(returns, risk_free_annual=0.0, periods_per_year=TRADING_DAYS):
    rf_daily = risk_free_annual / periods_per_year
    excess = [r - rf_daily for r in returns]
    sd = _std(excess)
    if sd == 0:
        return 0.0
    return _mean(excess) / sd * math.sqrt(periods_per_year)


def sortino(returns, risk_free_annual=0.0, periods_per_year=TRADING_DAYS):
    rf_daily = risk_free_annual / periods_per_year
    excess = [r - rf_daily for r in returns]
    downside = [min(0.0, r) for r in excess]
    dd = math.sqrt(sum(d * d for d in downside) / len(downside))
    if dd == 0:
        return 0.0
    return _mean(excess) / dd * math.sqrt(periods_per_year)


def capm(portfolio_returns, benchmark_returns, risk_free_annual=0.0,
         periods_per_year=TRADING_DAYS):
    """Beta, annualized alpha, and R² of the portfolio vs the benchmark."""
    n = min(len(portfolio_returns), len(benchmark_returns))
    rp, rb = portfolio_returns[-n:], benchmark_returns[-n:]
    mp, mb = _mean(rp), _mean(rb)
    cov = sum((a - mp) * (b - mb) for a, b in zip(rp, rb)) / (n - 1)
    var_b = sum((b - mb) ** 2 for b in rb) / (n - 1)
    beta = cov / var_b if var_b else 0.0
    rf_daily = risk_free_annual / periods_per_year
    alpha_daily = (mp - rf_daily) - beta * (mb - rf_daily)
    alpha_annual = alpha_daily * periods_per_year
    var_p = sum((a - mp) ** 2 for a in rp) / (n - 1)
    r_squared = (cov * cov) / (var_p * var_b) if var_p and var_b else 0.0
    return {"beta": beta, "alpha": alpha_annual, "r_squared": r_squared}


def portfolio_metrics(prices, benchmark_prices, risk_free_annual=0.0):
    rp = daily_returns(prices)
    rb = daily_returns(benchmark_prices)
    return {
        "total_return": total_return(prices),
        "cagr": cagr(prices),
        "max_drawdown": max_drawdown(prices),
        "volatility": annualized_vol(rp),
        "sharpe": sharpe(rp, risk_free_annual),
        "sortino": sortino(rp, risk_free_annual),
        "capm": capm(rp, rb, risk_free_annual),
    }
