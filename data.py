"""Data layer: daily price history per ticker.

This environment has no market-data access, so prices are simulated with a
geometric random walk seeded per ticker — the same ticker always produces the
same series, so metrics are stable across requests. To go live, replace
`get_price_history` with a real source, e.g.:

    import yfinance as yf
    def get_price_history(tickers, days=504):
        px = yf.download(tickers, period=f"{days}d")["Close"]
        return {t: px[t].dropna().tolist() for t in tickers}

Everything downstream (quant.py, app.py, the frontend) only sees
{ticker: [closes...]} and does not care where the numbers came from.
"""

import hashlib
import math
import random

# One-factor model: every ticker loads on a common market factor plus its own
# idiosyncratic noise, so portfolio-vs-benchmark betas and alphas come out
# economically sensible instead of ~0.
MARKET = {"drift": 0.00032, "vol": 0.0080}
PROFILES = {
    "AAPL": {"start": 254.31, "beta": 1.10, "alpha": 0.00005, "idio": 0.0100},
    "MSFT": {"start": 512.44, "beta": 1.05, "alpha": 0.00012, "idio": 0.0090},
    "NVDA": {"start": 1487.20, "beta": 1.60, "alpha": 0.00040, "idio": 0.0180},
    "SPY":  {"start": 428.72, "beta": 1.00, "alpha": 0.0, "idio": 0.0},
}
DEFAULT_PROFILE = {"start": 100.0, "beta": 1.00, "alpha": 0.0, "idio": 0.0120}

ASSET_CLASSES = {
    "AAPL": "US Equity — Info Tech",
    "MSFT": "US Equity — Info Tech",
    "NVDA": "US Equity — Semis",
    "SPY": "ETF — Broad Market",
}


def _rng_for(ticker):
    seed = int(hashlib.sha256(ticker.upper().encode()).hexdigest()[:12], 16)
    return random.Random(seed)


def get_price_history(tickers, days=504):
    """Return {ticker: [daily closes, oldest first]} of length `days`."""
    mkt_rng = _rng_for("__MARKET__")
    market = [MARKET["drift"] + MARKET["vol"] * mkt_rng.gauss(0, 1)
              for _ in range(days - 1)]

    out = {}
    for t in tickers:
        t = t.upper()
        prof = PROFILES.get(t, DEFAULT_PROFILE)
        rng = _rng_for(t)
        rets = [prof["alpha"] + prof["beta"] * m + prof["idio"] * rng.gauss(0, 1)
                for m in market]
        # Walk backwards from today's quoted level so the last close matches
        # the profile's headline price.
        level = prof["start"] / math.exp(sum(rets))
        series = [level]
        for r in rets:
            level *= math.exp(r)
            series.append(level)
        out[t] = series
    return out


def get_asset_class(ticker):
    return ASSET_CLASSES.get(ticker.upper(), "US Equity")
