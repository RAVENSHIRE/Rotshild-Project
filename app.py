"""Rotshild Portfolio Dashboard — HTTP application layer.

Serves the four-page frontend (Dashboard, Login, News, Allocation) and a JSON
API on top of the layered backend:

    app.py    routing / HTTP           (this file)
    data.py   market data, fundamentals, news
    quant.py  pure analytics (CAGR, Sharpe, CAPM, rebalancing)
    i18n.py   EN/DE string table

Run with:  python app.py   →  http://127.0.0.1:8000/

Firebase Authentication and Firestore persistence are handled client-side by
the frontend SDK. If ``firebase-admin`` is installed and a service-account
key is available (GOOGLE_APPLICATION_CREDENTIALS or ./serviceAccount.json),
the server additionally exposes token-verified /api/portfolio endpoints so
portfolio state can be read/written server-side.
"""

from __future__ import annotations

import json
import os
import webbrowser
from dataclasses import asdict, dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

import pfm
from data import asset_class, fundamentals, load_news, load_prices, mandate
from i18n import TRANSLATIONS
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

DEFAULT_TICKERS = ["AAPL", "MSFT", "NVDA", "TLT", "GLD"]
DEFAULT_BENCHMARK = "SPY"
DEFAULT_PORTFOLIO_VALUE = 5_000_000.0
DEFAULT_LOOKBACK = 252
DEFAULT_RISK_FREE = 0.02

# Pretty URLs → files inside frontend/.
PAGE_ROUTES = {
    "/": "index.html",
    "/login": "login.html",
    "/news": "news.html",
    "/allocation": "allocation.html",
    "/desk": "desk.html",
}


# --------------------------------------------------------------------------- #
# Optional Firebase Admin (server-side token verification + Firestore)
# --------------------------------------------------------------------------- #
def _init_firebase_admin():
    """Initialise firebase-admin when credentials are available, else None."""
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
    """Return the Firebase uid for a ``Bearer <idToken>`` header, else None."""
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
    tickers: list[str]
    benchmark: str
    live: bool
    lookback: int
    risk_free: float
    portfolio_value: float
    weights: dict[str, float] | None  # optional target weights (fractions)


def _parse_tickers(value: str | None) -> list[str]:
    raw = value or ",".join(DEFAULT_TICKERS)
    tickers: list[str] = []
    for item in raw.split(","):
        symbol = item.strip().upper()
        if symbol and symbol not in tickers:
            tickers.append(symbol)
    return tickers or DEFAULT_TICKERS.copy()


def _parse_weights(value: str | None) -> dict[str, float] | None:
    """Parse ``AAPL:30,MSFT:25`` into normalised weight fractions.

    Values are *relative* weights on any scale — percent (``30,25``) and
    fractions (``0.3,0.25``) normalise to the identical allocation, since
    each weight is divided by the total.
    """
    if not value:
        return None
    weights: dict[str, float] = {}
    for pair in value.split(","):
        if ":" not in pair:
            continue
        symbol, _, pct = pair.partition(":")
        try:
            weights[symbol.strip().upper()] = max(0.0, float(pct))
        except ValueError:
            continue
    total = sum(weights.values())
    if total <= 0:
        return None
    return {k: v / total for k, v in weights.items()}


def _parse_params(query: dict[str, list[str]]) -> RequestParams:
    def first(key: str, default: str) -> str:
        return (query.get(key, [default])[0] or default).strip()

    tickers = _parse_tickers(query.get("tickers", [None])[0])
    benchmark = first("benchmark", DEFAULT_BENCHMARK).upper()
    live = first("live", "1").lower() not in {"0", "false", "no", "off"}
    lookback = max(30, int(float(first("lookback", str(DEFAULT_LOOKBACK)))))
    risk_free = float(first("risk_free", str(DEFAULT_RISK_FREE * 100))) / 100.0
    portfolio_value = float(first("portfolio_value", str(DEFAULT_PORTFOLIO_VALUE)))
    weights = _parse_weights(query.get("weights", [None])[0])
    return RequestParams(tickers, benchmark, live, lookback, risk_free, portfolio_value, weights)


def _format_dates(index: pd.Index) -> list[str]:
    return [pd.Timestamp(value).strftime("%Y-%m-%d") for value in index]


# --------------------------------------------------------------------------- #
# Dashboard payload — bottom-up: per-security analytics first, then roll-ups
# --------------------------------------------------------------------------- #
def _build_dashboard_payload(params: RequestParams) -> dict:
    period_days = max(params.lookback + 90, 360)
    price_data = load_prices(
        params.tickers,
        benchmark=params.benchmark,
        period_days=period_days,
        use_live=params.live,
    )

    prices = price_data.prices
    benchmark = params.benchmark if params.benchmark in prices.columns else prices.columns[-1]
    portfolio_tickers = [t for t in params.tickers if t in prices.columns and t != benchmark]
    if not portfolio_tickers:
        portfolio_tickers = [c for c in prices.columns if c != benchmark][:3] or [benchmark]

    returns = daily_returns(prices).tail(params.lookback)
    if returns.empty:
        raise RuntimeError("Not enough price data to build the dashboard")

    # Weights: caller-supplied targets when present, equal-weight otherwise.
    if params.weights:
        weights = {t: params.weights.get(t, 0.0) for t in portfolio_tickers}
        if sum(weights.values()) <= 0:
            weights = {t: 1.0 / len(portfolio_tickers) for t in portfolio_tickers}
        else:
            total = sum(weights.values())
            weights = {t: w / total for t, w in weights.items()}
    else:
        weights = {t: 1.0 / len(portfolio_tickers) for t in portfolio_tickers}

    port_ret = portfolio_returns(returns[portfolio_tickers], weights)
    bench_ret = returns[benchmark]

    portfolio_values = params.portfolio_value * (1 + port_ret).cumprod()
    bench_series = prices[benchmark].reindex(portfolio_values.index).ffill().dropna()
    if bench_series.empty:
        bench_series = pd.Series(params.portfolio_value, index=portfolio_values.index)
    else:
        bench_series = bench_series / bench_series.iloc[0] * params.portfolio_value

    portfolio_metrics = summary_metrics(portfolio_values, params.risk_free)
    benchmark_metrics = summary_metrics(bench_series, params.risk_free)
    capm = rolling_capm(
        port_ret, bench_ret, window=min(63, max(2, len(port_ret) - 1)), rf_annual=params.risk_free
    )
    contributions = asset_contributions(returns[portfolio_tickers], weights)

    current_value = float(portfolio_values.iloc[-1])
    previous_value = float(portfolio_values.iloc[-2]) if len(portfolio_values) > 1 else current_value
    week_value = float(portfolio_values.iloc[-6]) if len(portfolio_values) > 5 else float(portfolio_values.iloc[0])
    first_value = float(portfolio_values.iloc[0])

    # ---- Security level (the bottom-up core) ------------------------------ #
    holdings: list[dict] = []
    allocation_by_class: dict[str, float] = {}
    allocation_by_mandate: dict[str, float] = {}
    allocation_rows: list[dict] = []

    for ticker in portfolio_tickers:
        series = prices[ticker].reindex(portfolio_values.index).ffill().dropna()
        if series.empty:
            continue
        latest_price = float(series.iloc[-1])
        day_change = float(series.pct_change().iloc[-1] * 100) if len(series) > 1 else 0.0
        total_ret = float(series.iloc[-1] / series.iloc[0] - 1)
        weight = weights[ticker]
        value = params.portfolio_value * weight
        cls = asset_class(ticker)
        role = mandate(ticker)
        allocation_by_class[cls] = allocation_by_class.get(cls, 0.0) + weight
        allocation_by_mandate[role] = allocation_by_mandate.get(role, 0.0) + weight
        allocation_rows.append(
            {"label": ticker, "weight": weight * 100, "class": cls, "mandate": role}
        )
        holdings.append(
            {
                "ticker": ticker,
                "asset_class": cls,
                "mandate": role,
                "price": latest_price,
                "change_24h": day_change,
                "total_return": total_ret * 100,
                "beta": simple_beta(returns[ticker], bench_ret),
                "sharpe": summary_metrics(series, params.risk_free)["sharpe"],
                "contribution": contributions.get(ticker, 0.0) * 100,
                "quantity": value / latest_price if latest_price else 0.0,
                "value": value,
                "weight": weight * 100,
                "fundamentals": fundamentals(ticker),
            }
        )

    current_beta = float(capm["beta"].iloc[-1]) if not capm.empty else float("nan")
    current_alpha = float(capm["alpha"].iloc[-1]) if not capm.empty else float("nan")

    def _clean(obj):
        """JSON-safe: NaN/inf → None, recursively."""
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_clean(v) for v in obj]
        if isinstance(obj, float) and (obj != obj or obj in (float("inf"), float("-inf"))):
            return None
        return obj

    payload = {
        "config": asdict(params),
        "source": {"label": price_data.source, "synthetic": price_data.is_synthetic},
        "metrics": {
            "portfolio": {
                "value": current_value,
                "daily_change": current_value - previous_value,
                "weekly_change": current_value - week_value,
                "total_change": current_value - first_value,
                "total_return": current_value / first_value - 1,
                **portfolio_metrics,
            },
            "benchmark": {
                "value": float(bench_series.iloc[-1]),
                "total_return": float(bench_series.iloc[-1] / bench_series.iloc[0] - 1),
                **benchmark_metrics,
            },
            "capm": {"beta": current_beta, "alpha": current_alpha},
        },
        "charts": {
            "performance": {
                "labels": _format_dates(portfolio_values.index),
                "portfolio": [float(v) for v in portfolio_values],
                "benchmark": [
                    float(v) for v in bench_series.reindex(portfolio_values.index).ffill()
                ],
            },
            "capm": {
                "labels": _format_dates(capm.index),
                "beta": [float(v) for v in capm["beta"]],
                "alpha": [float(v) for v in capm["alpha"]],
            },
            "contribution": {
                "labels": [h["ticker"] for h in holdings],
                "values": [h["contribution"] for h in holdings],
            },
            "allocation": {
                "labels": list(allocation_by_class),
                "values": [v * 100 for v in allocation_by_class.values()],
            },
            "mandate": {
                "labels": list(allocation_by_mandate),
                "values": [v * 100 for v in allocation_by_mandate.values()],
            },
        },
        "holdings": holdings,
        "allocation": allocation_rows,
    }
    return _clean(payload)


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #
class PortfolioHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_ROOT), **kwargs)

    def log_message(self, format: str, *args) -> None:  # keep the console quiet
        return

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    # ---- GET -------------------------------------------------------------- #
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/api/dashboard":
            self._guarded(lambda: self._send_json(_build_dashboard_payload(_parse_params(query))))
            return
        if parsed.path == "/api/news":
            tickers = _parse_tickers(query.get("tickers", [None])[0])
            self._guarded(lambda: self._send_json({"items": load_news(tickers)}))
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

    # ---- POST ------------------------------------------------------------- #
    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/rebalance":
            self._guarded(self._rebalance)
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

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

    def _rebalance(self) -> None:
        body = self._read_body()
        current = {str(k).upper(): float(v) for k, v in (body.get("current") or {}).items()}
        target = {str(k).upper(): float(v) for k, v in (body.get("target") or {}).items()}
        value = float(body.get("portfolio_value", DEFAULT_PORTFOLIO_VALUE))
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
                        "side": "BUY" if row["Trade Value"] > 0.5 else ("SELL" if row["Trade Value"] < -0.5 else "HOLD"),
                        "asset_class": asset_class(row["Instrument"]),
                        "mandate": mandate(row["Instrument"]),
                    }
                    for row in trades.to_dict("records")
                ],
            }
        )

    # ---- Server-side portfolio persistence (requires firebase-admin) ------ #
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

    # ---- Helpers ----------------------------------------------------------- #
    def _guarded(self, fn) -> None:
        try:
            fn()
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), PortfolioHandler)
    url = f"http://{HOST}:{PORT}/"
    print(f"Serving Rotshild Portfolio Dashboard at {url}")
    print(f"Firebase Admin: {'active' if FIREBASE_APP else 'not configured (client-side SDK only)'}")
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
