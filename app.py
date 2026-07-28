"""Rotshild Portfolio Dashboard — HTTP application layer.

Serves the frontend pages and a JSON API with a normalized holdings model:
one instrument per row, persisted in SQLite, dynamically priced, and valued in
CHF for portfolio roll-ups.
"""

from __future__ import annotations

import json
import os
import webbrowser
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

import pfm
from data import fetch_latest_prices, fundamentals, load_news, load_prices
from i18n import TRANSLATIONS
from portfolio_calcs import (
    benchmark_comparison,
    position_values_chf,
    risk_free_aware_metrics,
    total_portfolio_value_chf,
)
from portfolio_store import (
    BUCKET_DIVERSIFY,
    BUCKET_RETURN,
    add_ticker_workflow,
    deactivate_holding,
    get_holding,
    init_db,
    list_holdings,
    sector_lookup,
    list_ticker_catalog,
    mark_price_updates,
    upsert_holding,
)
from quant import (
    asset_contributions,
    daily_returns,
    portfolio_returns,
    rebalance_trades,
    rolling_capm,
    simple_beta,
    summary_metrics,
)

ROOT = Path(__file__).resolve().parent
FRONTEND_ROOT = ROOT / "frontend"
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))

DEFAULT_BENCHMARK = "SPY"
DEFAULT_LOOKBACK = 252
DEFAULT_RISK_FREE = 0.02

PAGE_ROUTES = {
    "/": "index.html",
    "/login": "login.html",
    "/news": "news.html",
    "/allocation": "allocation.html",
    "/desk": "desk.html",
}


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# --------------------------------------------------------------------------- #
# Optional Firebase Admin (server-side token verification + Firestore)
# --------------------------------------------------------------------------- #
def _init_firebase_admin():
    try:
        import firebase_admin
        from firebase_admin import credentials

        key_path = os.environ.get(
            "GOOGLE_APPLICATION_CREDENTIALS", str(ROOT / "serviceAccount.json")
        )
        if not Path(key_path).exists():
            return None
        cred = credentials.Certificate(key_path)
        return firebase_admin.initialize_app(cred)
    except Exception:
        return None


FIREBASE_APP = _init_firebase_admin()


def _verify_bearer(header: str | None) -> str | None:
    if not FIREBASE_APP or not header or not header.startswith("Bearer "):
        return None
    from firebase_admin import auth

    try:
        return auth.verify_id_token(header.removeprefix("Bearer "))["uid"]
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Request parsing
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RequestParams:
    benchmark: str
    live: bool
    lookback: int
    risk_free: float
    bucket: str | None


def _parse_params(query: dict[str, list[str]]) -> RequestParams:
    def first(key: str, default: str) -> str:
        return (query.get(key, [default])[0] or default).strip()

    benchmark = first("benchmark", DEFAULT_BENCHMARK).upper()
    live = first("live", "1").lower() not in {"0", "false", "no", "off"}
    lookback = max(30, int(float(first("lookback", str(DEFAULT_LOOKBACK)))))
    risk_free = float(first("risk_free", str(DEFAULT_RISK_FREE * 100))) / 100.0

    raw_bucket = first("bucket", "")
    bucket = None
    if raw_bucket and raw_bucket.upper() != "ALL":
        if raw_bucket not in {BUCKET_RETURN, BUCKET_DIVERSIFY}:
            raise ValueError("bucket must be ALL, Return Assets, or Diversifying Assets")
        bucket = raw_bucket

    return RequestParams(benchmark=benchmark, live=live, lookback=lookback, risk_free=risk_free, bucket=bucket)


def _format_dates(index: pd.Index) -> list[str]:
    return [pd.Timestamp(value).strftime("%Y-%m-%d") for value in index]


def _clean(obj):
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, float) and (obj != obj or obj in (float("inf"), float("-inf"))):
        return None
    return obj


def _refresh_holdings_prices(holdings: list[dict], use_live: bool, tickers: list[str] | None = None) -> dict:
    if tickers:
        ticker_set = {t.strip().upper() for t in tickers if t.strip()}
        pool = [h["ticker"] for h in holdings if h.get("is_active") and h["ticker"] in ticker_set]
    else:
        pool = [h["ticker"] for h in holdings if h.get("is_active")]

    if not pool:
        return {"source": "None", "synthetic": False, "missing": []}

    result = fetch_latest_prices(pool, use_live=use_live)
    mark_price_updates(result.prices, updated_at=_now_iso())
    return {
        "source": result.source,
        "synthetic": result.synthetic,
        "missing": result.missing,
    }


def _load_fx_to_chf(currencies: set[str], use_live: bool) -> tuple[dict[str, float], list[str]]:
    rates: dict[str, float] = {"CHF": 1.0}
    unresolved: list[str] = []

    needed = sorted(c for c in currencies if c != "CHF")
    if not needed:
        return rates, unresolved

    fx_tickers = [f"{c}CHF=X" for c in needed]
    fx_result = fetch_latest_prices(fx_tickers, use_live=use_live)
    for currency in needed:
        fx_ticker = f"{currency}CHF=X"
        value = fx_result.prices.get(fx_ticker)
        if value is None or value <= 0:
            unresolved.append(currency)
            continue
        rates[currency] = float(value)

    return rates, unresolved


# --------------------------------------------------------------------------- #
# Dashboard payload — bottom-up holdings first, then roll-ups
# --------------------------------------------------------------------------- #
def _build_dashboard_payload(params: RequestParams) -> dict:
    all_holdings = list_holdings(include_inactive=False)
    if not all_holdings:
        raise RuntimeError("No holdings found. Add a ticker row first.")

    price_meta = _refresh_holdings_prices(all_holdings, use_live=params.live)
    holdings = list_holdings(include_inactive=False)
    holdings = [h for h in holdings if h.get("quantity", 0) > 0]
    if params.bucket:
        holdings = [h for h in holdings if h.get("portfolio_bucket") == params.bucket]
    if not holdings:
        scope = params.bucket or "all buckets"
        raise RuntimeError(f"No non-zero holdings available for {scope}.")

    fx_rates, unresolved_fx = _load_fx_to_chf({h["currency"] for h in holdings}, use_live=params.live)
    if unresolved_fx:
        raise RuntimeError(
            "Missing FX conversion to CHF for currencies: " + ", ".join(sorted(unresolved_fx))
        )

    missing_prices = [h["ticker"] for h in holdings if h.get("current_price") in (None, 0)]
    if missing_prices:
        raise RuntimeError("Missing current price for: " + ", ".join(sorted(missing_prices)))

    position_values = position_values_chf(holdings, fx_rates)
    total_value = total_portfolio_value_chf(position_values)
    if total_value <= 0:
        raise RuntimeError("Portfolio value is zero. Increase at least one holding quantity.")

    tickers = [h["ticker"] for h in holdings]
    period_days = max(params.lookback + 90, 360)
    price_data = load_prices(
        tickers,
        benchmark=params.benchmark,
        period_days=period_days,
        use_live=params.live,
    )

    prices = price_data.prices
    benchmark = params.benchmark if params.benchmark in prices.columns else prices.columns[-1]
    portfolio_tickers = [t for t in tickers if t in prices.columns and t != benchmark]
    if not portfolio_tickers:
        raise RuntimeError("No valid ticker history available for the selected holdings.")

    returns = daily_returns(prices).tail(params.lookback)
    if returns.empty:
        raise RuntimeError("Not enough price history to compute metrics.")

    weights = {t: position_values[t] / total_value for t in portfolio_tickers}
    port_ret = portfolio_returns(returns[portfolio_tickers], weights)
    if port_ret.empty:
        raise RuntimeError("Could not compute portfolio returns from the current holdings.")

    bench_ret = returns[benchmark]
    portfolio_values = total_value * (1 + port_ret).cumprod()
    bench_series = prices[benchmark].reindex(portfolio_values.index).ffill().dropna()
    if bench_series.empty:
        bench_series = pd.Series(total_value, index=portfolio_values.index)
    else:
        bench_series = bench_series / bench_series.iloc[0] * total_value

    portfolio_metrics = risk_free_aware_metrics(portfolio_values, params.risk_free)
    benchmark_metrics = risk_free_aware_metrics(bench_series, params.risk_free)
    comparison = benchmark_comparison(portfolio_values, bench_series)
    capm = rolling_capm(
        port_ret, bench_ret, window=min(63, max(2, len(port_ret) - 1)), rf_annual=params.risk_free
    )
    contributions = asset_contributions(returns[portfolio_tickers], weights)

    current_value = float(portfolio_values.iloc[-1])
    previous_value = float(portfolio_values.iloc[-2]) if len(portfolio_values) > 1 else current_value
    week_value = float(portfolio_values.iloc[-6]) if len(portfolio_values) > 5 else float(portfolio_values.iloc[0])
    first_value = float(portfolio_values.iloc[0])

    holdings_by_ticker = {h["ticker"]: h for h in holdings}
    allocation_by_sector: dict[str, float] = {}
    allocation_by_bucket: dict[str, float] = {}
    payload_holdings: list[dict] = []

    for ticker in portfolio_tickers:
        h = holdings_by_ticker[ticker]
        series = prices[ticker].reindex(portfolio_values.index).ffill().dropna()
        if series.empty:
            continue

        fx = fx_rates[h["currency"]]
        native_price = float(h["current_price"])
        price_chf = native_price * fx
        value_chf = position_values[ticker]
        weight = weights[ticker]
        total_ret = float(series.iloc[-1] / series.iloc[0] - 1)
        day_change = float(series.pct_change().iloc[-1] * 100) if len(series) > 1 else 0.0

        allocation_by_sector[h["sector"]] = allocation_by_sector.get(h["sector"], 0.0) + weight
        allocation_by_bucket[h["portfolio_bucket"]] = allocation_by_bucket.get(h["portfolio_bucket"], 0.0) + weight

        payload_holdings.append(
            {
                "ticker": ticker,
                "asset_name": h["asset_name"],
                "portfolio_bucket": h["portfolio_bucket"],
                "asset_class": h["sector"],
                "mandate": h["portfolio_bucket"],
                "sector": h["sector"],
                "sub_sector": h["sub_sector"],
                "currency": h["currency"],
                "fx_to_chf": fx,
                "price": native_price,
                "price_chf": price_chf,
                "change_24h": day_change,
                "total_return": total_ret * 100,
                "beta": simple_beta(returns[ticker], bench_ret),
                "sharpe": summary_metrics(series, params.risk_free)["sharpe"],
                "contribution": contributions.get(ticker, 0.0) * 100,
                "quantity": float(h["quantity"]),
                "value": value_chf,
                "weight": weight * 100,
                "last_updated": h["last_updated"],
                "fundamentals": {
                    **fundamentals(ticker),
                    "name": h["asset_name"],
                    "sector": h["sector"],
                    "sub_sector": h["sub_sector"],
                    "mandate": h["portfolio_bucket"],
                    "asset_class": h["sector"],
                },
            }
        )

    current_beta = float(capm["beta"].iloc[-1]) if not capm.empty else float("nan")
    current_alpha = float(capm["alpha"].iloc[-1]) if not capm.empty else float("nan")

    payload = {
        "config": {
            "benchmark": benchmark,
            "risk_free": params.risk_free,
            "lookback": params.lookback,
            "live": params.live,
            "bucket": params.bucket or "ALL",
        },
        "source": {
            "label": price_data.source,
            "synthetic": price_data.is_synthetic,
            "holding_prices": price_meta,
        },
        "warnings": {
            "missing_live_prices": price_meta["missing"],
            "risk_free_note": (
                "Risk-free input is annualized and converted to a daily rate in quant._daily_rf "
                "for Sharpe/Sortino and excess-return CAPM calculations."
            ),
        },
        "metrics": {
            "portfolio": {
                "value": current_value,
                "daily_change": current_value - previous_value,
                "weekly_change": current_value - week_value,
                "total_change": current_value - first_value,
                "total_return": current_value / first_value - 1,
                "excess_return_vs_benchmark": comparison["excess_return"],
                **portfolio_metrics,
            },
            "benchmark": {
                "value": float(bench_series.iloc[-1]),
                "total_return": comparison["benchmark_total_return"],
                **benchmark_metrics,
            },
            "capm": {"beta": current_beta, "alpha": current_alpha},
        },
        "charts": {
            "performance": {
                "labels": _format_dates(portfolio_values.index),
                "portfolio": [float(v) for v in portfolio_values],
                "benchmark": [float(v) for v in bench_series.reindex(portfolio_values.index).ffill()],
            },
            "capm": {
                "labels": _format_dates(capm.index),
                "beta": [float(v) for v in capm["beta"]],
                "alpha": [float(v) for v in capm["alpha"]],
            },
            "contribution": {
                "labels": [h["ticker"] for h in payload_holdings],
                "values": [h["contribution"] for h in payload_holdings],
            },
            "allocation": {
                "labels": list(allocation_by_sector),
                "values": [v * 100 for v in allocation_by_sector.values()],
            },
            "mandate": {
                "labels": list(allocation_by_bucket),
                "values": [v * 100 for v in allocation_by_bucket.values()],
            },
        },
        "holdings": payload_holdings,
    }
    return _clean(payload)


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #
class PortfolioHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_ROOT), **kwargs)

    def log_message(self, format: str, *args) -> None:
        return

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/api/dashboard":
            self._guarded(lambda: self._send_json(_build_dashboard_payload(_parse_params(query))))
            return
        if parsed.path == "/api/holdings":
            self._guarded(lambda: self._send_json({"holdings": list_holdings(include_inactive=False)}))
            return
        if parsed.path == "/api/tickers":
            self._guarded(lambda: self._send_json({"tickers": list_ticker_catalog()}))
            return
        if parsed.path == "/api/sector-map":
            self._guarded(lambda: self._send_json({"sectors": sector_lookup()}))
            return
        if parsed.path == "/api/news":
            tickers = query.get("tickers", [""])[0].strip()
            if tickers:
                held = [t.strip().upper() for t in tickers.split(",") if t.strip()]
            else:
                held = [h["ticker"] for h in list_holdings(include_inactive=False) if h.get("quantity", 0) > 0]
            self._guarded(lambda: self._send_json({"items": load_news(held)}))
            return
        if parsed.path == "/api/i18n":
            self._send_json({"translations": TRANSLATIONS})
            return
        if parsed.path == "/api/pfm/desk":
            self._guarded(lambda: self._send_json(pfm.desk_overview()))
            return
        if parsed.path == "/api/pfm/portfolio":
            pid = (query.get("id", [""])[0] or "").strip().upper()
            self._guarded(lambda: self._send_json(pfm.portfolio_detail(pid)))
            return
        if parsed.path == "/api/health":
            self._send_json({"ok": True, "firebase_admin": FIREBASE_APP is not None})
            return
        if parsed.path == "/api/portfolio":
            self._portfolio_get()
            return
        if parsed.path in PAGE_ROUTES:
            self.path = "/" + PAGE_ROUTES[parsed.path]
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/rebalance":
            self._guarded(self._rebalance)
            return
        if parsed.path == "/api/holdings":
            self._guarded(self._upsert_holding)
            return
        if parsed.path == "/api/holdings/refresh-prices":
            self._guarded(self._refresh_prices)
            return
        if parsed.path == "/api/tickers":
            self._guarded(self._add_ticker)
            return
        if parsed.path == "/api/pfm/rebalance":
            self._guarded(
                lambda: self._send_json(
                    pfm.rebalance_portfolio(
                        str(self._read_body().get("portfolio_id", "")).strip().upper()
                    )
                )
            )
            return
        if parsed.path == "/api/portfolio":
            self._portfolio_post()
            return

        self.send_error(404, "Unknown endpoint")

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/api/holdings":
            ticker = (query.get("ticker", [""])[0] or "").strip().upper()
            self._guarded(lambda: self._delete_holding(ticker))
            return
        self.send_error(404, "Unknown endpoint")

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

    def _upsert_holding(self) -> None:
        body = self._read_body()
        holding = body.get("holding") or body
        row = upsert_holding(holding)
        refresh = fetch_latest_prices([row["ticker"]], use_live=True)
        mark_price_updates(refresh.prices, updated_at=_now_iso())
        self._send_json({"holding": get_holding(row["ticker"]), "price_source": refresh.source})

    def _refresh_prices(self) -> None:
        body = self._read_body()
        use_live = bool(body.get("live", True))
        ticker = str(body.get("ticker", "")).strip().upper()
        holdings = list_holdings(include_inactive=False)
        meta = _refresh_holdings_prices(holdings, use_live, tickers=[ticker] if ticker else None)
        self._send_json({"ok": True, "meta": meta, "holdings": list_holdings(include_inactive=False)})

    def _delete_holding(self, ticker: str) -> None:
        if not ticker:
            raise ValueError("ticker is required")
        deactivate_holding(ticker)
        self._send_json({"ok": True})

    def _add_ticker(self) -> None:
        payload = self._read_body()
        row = add_ticker_workflow(payload)
        refresh = fetch_latest_prices([row["ticker"]], use_live=True)
        mark_price_updates(refresh.prices, updated_at=_now_iso())
        self._send_json({
            "ticker": get_holding(row["ticker"]),
            "price_source": refresh.source,
            "missing": refresh.missing,
        })

    def _rebalance(self) -> None:
        body = self._read_body()
        current = {str(k).upper(): float(v) for k, v in (body.get("current") or {}).items()}
        target = {str(k).upper(): float(v) for k, v in (body.get("target") or {}).items()}
        value = float(body.get("portfolio_value", 0.0))
        trades = rebalance_trades(current, target, value)
        self._send_json(
            {
                "portfolio_value": value,
                "trades": [
                    {
                        "instrument": row["Instrument"],
                        "current_weight": row["Current Weight"] * 100,
                        "target_weight": row["Target Weight"] * 100,
                        "drift": row["Drift"] * 100,
                        "trade_value": row["Trade Value"],
                        "side": "BUY"
                        if row["Trade Value"] > 0.5
                        else ("SELL" if row["Trade Value"] < -0.5 else "HOLD"),
                    }
                    for row in trades.to_dict("records")
                ],
            }
        )

    def _portfolio_get(self) -> None:
        uid = _verify_bearer(self.headers.get("Authorization"))
        if not FIREBASE_APP:
            self._send_json({"configured": False}, status=501)
            return
        if not uid:
            self._send_json({"error": "Invalid or missing ID token"}, status=401)
            return

        from firebase_admin import firestore

        doc = firestore.client().collection("users").document(uid).get()
        self._send_json({"configured": True, "state": doc.to_dict() or None})

    def _portfolio_post(self) -> None:
        uid = _verify_bearer(self.headers.get("Authorization"))
        if not FIREBASE_APP:
            self._send_json({"configured": False}, status=501)
            return
        if not uid:
            self._send_json({"error": "Invalid or missing ID token"}, status=401)
            return

        from firebase_admin import firestore

        state = self._read_body().get("state") or {}
        firestore.client().collection("users").document(uid).set(state, merge=True)
        self._send_json({"ok": True})

    def _guarded(self, fn) -> None:
        try:
            fn()
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(_clean(payload)).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), PortfolioHandler)
    url = f"http://{HOST}:{PORT}/"
    print(f"Serving Rotshild Portfolio Dashboard at {url}")
    print(f"Database: {ROOT / 'portfolio.db'}")
    print(
        f"Firebase Admin: {'active' if FIREBASE_APP else 'not configured (client-side SDK only)'}"
    )

    if os.environ.get("NO_BROWSER") != "1":
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
