"""App layer: serves the frontend and the /api/dashboard endpoint.

Run `python app.py` and open http://127.0.0.1:8000/ — the frontend is served
from ./frontend by the same server, so fetch('/api/dashboard') is same-origin
and no CORS setup is needed.
"""

import json
import os
import webbrowser
from datetime import date, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import data
import quant

HOST, PORT = "127.0.0.1", 8000
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
HISTORY_DAYS = 504  # ~2 trading years


def month_labels(n):
    """n daily labels ending today (weekdays only), ISO formatted."""
    labels = []
    d = date.today()
    while len(labels) < n:
        if d.weekday() < 5:
            labels.append(d.isoformat())
        d -= timedelta(days=1)
    return list(reversed(labels))


def build_dashboard(tickers, benchmark, portfolio_value, target_weights=None):
    prices = data.get_price_history(tickers + [benchmark], days=HISTORY_DAYS)
    bench = prices[benchmark]

    if not target_weights:
        target_weights = {t: 1.0 / len(tickers) for t in tickers}

    # Buy at target weights at the start of the window, hold the share count;
    # current weights then drift with each name's performance.
    start_value = portfolio_value
    shares = {t: start_value * target_weights[t] / prices[t][0] for t in tickers}
    curve = [sum(shares[t] * prices[t][i] for t in tickers)
             for i in range(HISTORY_DAYS)]
    scale = portfolio_value / curve[0]
    bench_curve = [portfolio_value * p / bench[0] for p in bench]

    m = quant.portfolio_metrics(curve, bench)
    current_total = curve[-1]

    holdings = []
    for t in tickers:
        value = shares[t] * prices[t][-1]
        cur_w = value / current_total
        tgt_w = target_weights[t]
        holdings.append({
            "ticker": t,
            "asset_class": data.get_asset_class(t),
            "price": round(prices[t][-1], 2),
            "change_24h": round((prices[t][-1] / prices[t][-2] - 1) * 100, 2),
            "value": round(value, 2),
            "current_weight": round(cur_w * 100, 2),
            "target_weight": round(tgt_w * 100, 2),
            "drift": round((cur_w - tgt_w) * 100, 2),
            "rebalance_usd": round(current_total * tgt_w - value, 2),
        })

    step = max(1, HISTORY_DAYS // 260)  # thin the chart payload
    labels = month_labels(HISTORY_DAYS)
    return {
        "as_of": labels[-1],
        "benchmark": benchmark,
        "metrics": {
            "portfolio": {
                "value": round(current_total, 2),
                "total_return": m["total_return"],
                "cagr": m["cagr"],
                "max_drawdown": m["max_drawdown"],
                "volatility": m["volatility"],
                "sharpe": round(m["sharpe"], 2),
                "sortino": round(m["sortino"], 2),
            },
            "capm": {k: round(v, 4) for k, v in m["capm"].items()},
            "benchmark": {
                "total_return": quant.total_return(bench),
                "cagr": quant.cagr(bench),
            },
        },
        "charts": {
            "performance": {
                "labels": labels[::step],
                "portfolio": [round(v, 2) for v in curve[::step]],
                "benchmark": [round(v, 2) for v in bench_curve[::step]],
            }
        },
        "holdings": holdings,
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/dashboard":
            q = parse_qs(parsed.query)
            tickers = [t.strip().upper() for t in
                       q.get("tickers", ["AAPL,MSFT,NVDA"])[0].split(",") if t.strip()]
            benchmark = q.get("benchmark", ["SPY"])[0].strip().upper()
            try:
                portfolio_value = float(q.get("portfolio_value", ["1250000"])[0])
            except ValueError:
                portfolio_value = 1_250_000.0
            payload = json.dumps(build_dashboard(tickers, benchmark, portfolio_value))
            body = payload.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}/"
    print(f"Serving dashboard at {url}  (Ctrl+C to stop)")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    server.serve_forever()


if __name__ == "__main__":
    main()
