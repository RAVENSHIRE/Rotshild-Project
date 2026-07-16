"""Rotshild Quant Dashboard — Streamlit entry point.

Run with:  streamlit run app/main.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import analytics
from core.data.market import fetch_prices
from core.portfolio import Pillar, demo_portfolio, rebalancing_trades

# Institutional palette: navy, slate blue, muted teal, soft gold, silver
PALETTE = ["#1B2A4A", "#5B7DB1", "#3E7C7B", "#C9A227", "#8B90A0"]
GOLD = "#C9A227"

st.set_page_config(page_title="Rotshild Quant Dashboard", page_icon="📈", layout="wide")

st.title("Rotshild Quant Dashboard")
st.caption(
    "Bottom-up, two-pillar approach: **Return assets** for growth, "
    "**Diversifying assets** for protection."
)

portfolio = demo_portfolio()
portfolio.validate()

with st.sidebar:
    st.header("Settings")
    benchmark = st.text_input("Benchmark", value="SPY").strip().upper()
    period = st.selectbox("History", ["1y", "2y", "5y"], index=1)
    st.subheader("Holdings")
    for pillar, label in [
        (Pillar.RETURN, "Return assets"),
        (Pillar.DIVERSIFYING, "Diversifying assets"),
    ]:
        st.markdown(f"**{label}** ({portfolio.pillar_weight(pillar):.0%})")
        for a in portfolio.by_pillar(pillar):
            st.write(f"- {a.ticker} · {a.name} · {a.weight:.0%}")


@st.cache_data(ttl=3600)
def load_prices(tickers: tuple[str, ...], period: str):
    return fetch_prices(list(tickers), period)


all_tickers = tuple(dict.fromkeys(portfolio.tickers + [benchmark]))
prices, is_live = load_prices(all_tickers, period)
if not is_live:
    st.warning("Live market data unavailable — showing synthetic demo data.")

holdings_prices = prices[portfolio.tickers]
port_index = analytics.portfolio_series(prices, portfolio.weights())
bench_index = prices[benchmark] / prices[benchmark].iloc[0]

# ---- KPI row: portfolio vs benchmark -------------------------------------
kpis = {
    "CAGR": (analytics.cagr(port_index), analytics.cagr(bench_index), "{:.1%}"),
    "Max Drawdown": (
        float(analytics.max_drawdown(port_index.to_frame("p"))["p"]),
        float(analytics.max_drawdown(bench_index.to_frame("b"))["b"]),
        "{:.1%}",
    ),
    "Sharpe Ratio": (
        analytics.sharpe_ratio(port_index),
        analytics.sharpe_ratio(bench_index),
        "{:.2f}",
    ),
    "Sortino Ratio": (
        analytics.sortino_ratio(port_index),
        analytics.sortino_ratio(bench_index),
        "{:.2f}",
    ),
}
cols = st.columns(len(kpis))
for col, (name, (val, bench_val, fmt)) in zip(cols, kpis.items()):
    col.metric(name, fmt.format(val), delta=f"{fmt.format(val - bench_val)} vs {benchmark}")

tab_market, tab_capm, tab_rebal = st.tabs(
    ["Market Overview", "Quant Risk & CAPM", "Rebalancing Engine"]
)

# ---- Tab 1: Market Overview -----------------------------------------------
with tab_market:
    st.subheader("Cumulative returns")
    cum = analytics.cumulative_returns(holdings_prices)
    cum["PORTFOLIO"] = port_index - 1.0
    cum[benchmark] = bench_index - 1.0
    fig = px.line(
        cum,
        labels={"value": "Return", "index": "Date", "variable": "Asset"},
        color_discrete_sequence=PALETTE + [GOLD, "#22262B"],
    )
    fig.update_layout(yaxis_tickformat=".0%", legend_title=None)
    st.plotly_chart(fig, use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.subheader("Risk / return by asset")
        stats = pd.DataFrame(
            {
                "Ann. return": analytics.annualized_return(holdings_prices),
                "Ann. volatility": analytics.annualized_volatility(holdings_prices),
                "Max drawdown": analytics.max_drawdown(holdings_prices),
            }
        )
        st.dataframe(stats.style.format("{:.1%}"), use_container_width=True)
    with right:
        st.subheader("Correlation (daily returns)")
        corr = analytics.correlation_matrix(holdings_prices)
        st.plotly_chart(
            px.imshow(corr, zmin=-1, zmax=1, color_continuous_scale="RdBu_r", text_auto=".2f"),
            use_container_width=True,
        )

# ---- Tab 2: Quant Risk & CAPM ----------------------------------------------
with tab_capm:
    window = st.slider("Rolling window (trading days)", 21, 252, 63, step=21)
    beta = analytics.rolling_beta(port_index, bench_index, window)
    alpha = analytics.rolling_alpha(port_index, bench_index, window)

    left, right = st.columns(2)
    with left:
        st.subheader(f"Rolling {window}-Day Beta vs {benchmark}")
        fig_b = px.line(beta, color_discrete_sequence=["#5B7DB1"])
        fig_b.add_hline(y=1.0, line_dash="dot", line_color=GOLD)
        fig_b.update_layout(showlegend=False, yaxis_title="Beta", xaxis_title="Date")
        st.plotly_chart(fig_b, use_container_width=True)
    with right:
        st.subheader("Annualized Alpha")
        fig_a = px.line(alpha, color_discrete_sequence=["#3E7C7B"])
        fig_a.add_hline(y=0.0, line_dash="dot", line_color=GOLD)
        fig_a.update_layout(
            showlegend=False, yaxis_title="Alpha (ann.)", yaxis_tickformat=".1%", xaxis_title="Date"
        )
        st.plotly_chart(fig_a, use_container_width=True)

# ---- Tab 3: Rebalancing Engine ----------------------------------------------
with tab_rebal:
    trades = rebalancing_trades(portfolio, holdings_prices)

    left, right = st.columns([1, 1.4])
    with left:
        st.subheader("Allocation by pillar")
        pillar_df = trades.groupby("Pillar", as_index=False)["Current Weight"].sum()
        donut = go.Figure(
            go.Pie(
                labels=pillar_df["Pillar"].str.title(),
                values=pillar_df["Current Weight"],
                hole=0.55,
                marker={"colors": ["#3E7C7B", "#1B2A4A"]},
            )
        )
        donut.update_layout(showlegend=True, margin=dict(t=10, b=10))
        st.plotly_chart(donut, use_container_width=True)
    with right:
        st.subheader("Current vs target weights")
        st.dataframe(
            trades.style.format(
                {"Current Weight": "{:.1%}", "Target Weight": "{:.1%}", "Trade": "{:+.1%}"}
            ),
            use_container_width=True,
            hide_index=True,
        )
        if st.button("Calculate Optimal Trades", type="primary"):
            buys = trades[trades["Trade"] > 0.0005]
            sells = trades[trades["Trade"] < -0.0005]
            if buys.empty and sells.empty:
                st.success("Portfolio is within 0.05% of target — no trades needed.")
            else:
                for _, r in sells.iterrows():
                    st.write(f"🔻 Sell {abs(r['Trade']):.1%} of portfolio in **{r['Ticker']}**")
                for _, r in buys.iterrows():
                    st.write(f"🔺 Buy {r['Trade']:.1%} of portfolio in **{r['Ticker']}**")
        st.download_button(
            "Export trades (CSV)",
            trades.to_csv(index=False).encode(),
            file_name="rebalancing_trades.csv",
            mime="text/csv",
        )
