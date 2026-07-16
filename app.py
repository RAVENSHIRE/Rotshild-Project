"""Rotshild Quant Dashboard — Streamlit application.

A Swiss private-banking style portfolio analytics tool for quantitative
portfolio managers. Run with:

    streamlit run app.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import quant
from data import asset_class, load_prices
from i18n import tr

# --------------------------------------------------------------------------- #
# Theme
# --------------------------------------------------------------------------- #
NAVY = "#0B1F3A"
NAVY_2 = "#12294A"
CHARCOAL = "#2A2F3A"
GOLD = "#C5A25A"
GOLD_SOFT = "#D8B36A"
SILVER = "#C0C4CC"
SLATE = "#4F6D9A"
TEAL = "#4C8C8C"
GREEN = "#1E8E5A"
RED = "#C0392B"
INK = "#1C2430"

CLASS_COLORS = {"Equities": SLATE, "Fixed Income": TEAL, "Alternatives": GOLD_SOFT}

st.set_page_config(
    page_title="Rotshild Quant Dashboard",
    page_icon="⚜️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    f"""
    <style>
      .stApp {{ background: #F4F6F9; }}
      section[data-testid="stSidebar"] {{
          background: linear-gradient(180deg, {NAVY} 0%, {NAVY_2} 100%);
      }}
      section[data-testid="stSidebar"] * {{ color: #E8ECF3 !important; }}
      section[data-testid="stSidebar"] input,
      section[data-testid="stSidebar"] textarea {{
          background: rgba(255,255,255,0.06) !important;
          color: #FFFFFF !important;
          border: 1px solid rgba(197,162,90,0.35) !important;
      }}
      .app-header {{
          display:flex; align-items:baseline; gap:14px;
          border-bottom: 2px solid {GOLD}; padding-bottom: 8px; margin-bottom: 6px;
      }}
      .app-header h1 {{ color:{NAVY}; font-size:1.7rem; margin:0; letter-spacing:.5px; }}
      .app-header span {{ color:{CHARCOAL}; font-size:.95rem; }}
      .kpi {{
          background:#FFFFFF; border:1px solid #E3E7ED; border-left:4px solid {GOLD};
          border-radius:10px; padding:16px 18px;
          box-shadow:0 2px 10px rgba(11,31,58,0.06);
      }}
      .kpi .label {{ color:{CHARCOAL}; font-size:.78rem; text-transform:uppercase;
                     letter-spacing:.06em; }}
      .kpi .value {{ color:{NAVY}; font-size:1.9rem; font-weight:700; line-height:1.1; }}
      .kpi .delta {{ font-size:.82rem; font-weight:600; }}
      .up {{ color:{GREEN}; }} .down {{ color:{RED}; }}
      .stButton>button {{
          background: linear-gradient(90deg, {GOLD} 0%, {GOLD_SOFT} 100%);
          color:{NAVY}; font-weight:700; border:none; border-radius:8px;
          padding:.55rem 1.1rem;
      }}
      div[data-baseweb="tag"] {{ background:{SLATE} !important; }}
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def kpi_card(label: str, value: str, delta: str | None, positive: bool | None) -> str:
    if delta is None:
        delta_html = ""
    else:
        cls = "up" if positive else "down"
        arrow = "▲" if positive else "▼"
        delta_html = f'<div class="delta {cls}">{arrow} {delta}</div>'
    return (
        f'<div class="kpi"><div class="label">{label}</div>'
        f'<div class="value">{value}</div>{delta_html}</div>'
    )


def fmt_pct(x: float, digits: int = 1) -> str:
    if x is None or np.isnan(x):
        return "—"
    if np.isinf(x):
        return "∞"
    return f"{x * 100:.{digits}f}%"


def fmt_num(x: float, digits: int = 2) -> str:
    if x is None or np.isnan(x):
        return "—"
    if np.isinf(x):
        return "∞"
    return f"{x:.{digits}f}"


@st.cache_data(show_spinner=False)
def get_prices(tickers: tuple[str, ...], benchmark: str, days: int, live: bool):
    pd_obj = load_prices(list(tickers), benchmark, days, live)
    return pd_obj.prices, pd_obj.is_synthetic, pd_obj.source


def chart_header(text: str) -> None:
    """Consistent chart title rendered above the plot (avoids legend overlap)."""
    st.markdown(
        f'<div style="color:{NAVY};font-weight:700;font-size:1.02rem;'
        f'margin:2px 0 -6px 4px;">{text}</div>',
        unsafe_allow_html=True,
    )


def base_chart_layout(height: int = 320, legend: bool = True) -> dict:
    return dict(
        height=height,
        margin=dict(l=10, r=10, t=24, b=10),
        paper_bgcolor="white",
        plot_bgcolor="white",
        showlegend=legend,
        font=dict(color=INK, family="Inter, Roboto, sans-serif"),
        xaxis=dict(gridcolor="#EEF1F5", zeroline=False),
        yaxis=dict(gridcolor="#EEF1F5", zeroline=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
    )


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
lang = st.sidebar.radio("🌐 EN / DE", ["EN", "DE"], horizontal=True, index=0)

st.sidebar.markdown(f"### {tr('config', lang)}")
tickers_raw = st.sidebar.text_input(
    tr("tickers", lang), value="AAPL, MSFT, TLT, GLD", help=tr("tickers_help", lang)
)
benchmark = st.sidebar.text_input(tr("benchmark", lang), value="SPY").strip().upper()
rf_annual = st.sidebar.number_input(
    tr("risk_free", lang), min_value=0.0, max_value=0.10, value=0.02, step=0.005,
    format="%.3f",
)
lookback = st.sidebar.slider(tr("lookback", lang), 126, 756, 504, step=21)
use_live = st.sidebar.checkbox(tr("use_live", lang), value=True)

st.sidebar.markdown(f"### {tr('nav', lang)}")
sections = ["market_overview", "quant_risk", "rebalancing", "export"]
section = st.sidebar.radio(
    "nav", sections, format_func=lambda s: tr(s, lang), label_visibility="collapsed"
)

tickers = [t.strip().upper() for t in tickers_raw.split(",") if t.strip()]
if not tickers:
    st.warning("Enter at least one ticker symbol.")
    st.stop()

prices, is_synthetic, source = get_prices(tuple(tickers), benchmark, lookback, use_live)
returns = prices.pct_change().dropna(how="all")

# Equal-weight portfolio across the entered tickers (benchmark excluded).
port_tickers = [t for t in tickers if t in prices.columns]
equal_w = {t: 1.0 / len(port_tickers) for t in port_tickers}
port_ret = quant.portfolio_returns(returns, equal_w)
port_prices = 100 * (1 + port_ret).cumprod()

# --------------------------------------------------------------------------- #
# Header + data-source banner
# --------------------------------------------------------------------------- #
st.markdown(
    f'<div class="app-header"><h1>⚜️ {tr("app_title", lang)}</h1>'
    f'<span>{tr("app_subtitle", lang)}</span></div>',
    unsafe_allow_html=True,
)
if is_synthetic:
    st.info("⚙️ " + tr("synthetic_banner", lang))
else:
    st.success("🟢 " + tr("live_banner", lang))

period_txt = f"{prices.index[0].date()} → {prices.index[-1].date()}"
st.caption(f"{tr('data_source', lang)}: **{source}**  ·  {tr('period_covered', lang)}: {period_txt}")


# =========================================================================== #
# Section 1 — Market Overview
# =========================================================================== #
if section == "market_overview":
    pm = quant.summary_metrics(port_prices, rf_annual)
    bm = quant.summary_metrics(prices[benchmark], rf_annual) if benchmark in prices else {}

    cols = st.columns(4)
    specs = [
        ("cagr", pm["cagr"], bm.get("cagr"), fmt_pct, True),
        ("max_drawdown", pm["max_drawdown"], bm.get("max_drawdown"), fmt_pct, False),
        ("sharpe", pm["sharpe"], bm.get("sharpe"), fmt_num, True),
        ("sortino", pm["sortino"], bm.get("sortino"), fmt_num, True),
    ]
    for col, (key, val, bench_val, fmt, higher_better) in zip(cols, specs):
        delta_txt, positive = None, None
        if bench_val is not None and not np.isnan(bench_val) and not np.isnan(val):
            diff = val - bench_val
            positive = (diff >= 0) if higher_better else (diff <= 0)
            delta_txt = f"{fmt(abs(diff))} {tr('vs_benchmark', lang)}"
        col.markdown(
            kpi_card(tr(key, lang), fmt(val), delta_txt, positive),
            unsafe_allow_html=True,
        )

    st.markdown("####")
    chart_header(tr("cumulative_perf", lang))
    fig = go.Figure()
    rebased = prices / prices.iloc[0] * 100
    for t in port_tickers:
        fig.add_trace(go.Scatter(
            x=rebased.index, y=rebased[t], name=t, mode="lines",
            line=dict(width=1.6, color=CLASS_COLORS.get(asset_class(t), SLATE)),
            opacity=0.55,
        ))
    fig.add_trace(go.Scatter(
        x=port_prices.index, y=port_prices, name=tr("portfolio", lang),
        line=dict(width=3.2, color=NAVY),
    ))
    if benchmark in rebased:
        fig.add_trace(go.Scatter(
            x=rebased.index, y=rebased[benchmark], name=benchmark,
            line=dict(width=2, color=GOLD, dash="dash"),
        ))
    fig.update_layout(**base_chart_layout(height=420))
    st.plotly_chart(fig, use_container_width=True)


# =========================================================================== #
# Section 2 — Quant Risk & CAPM
# =========================================================================== #
elif section == "quant_risk":
    if benchmark not in returns.columns:
        st.error(f"Benchmark {benchmark} not available in the data.")
        st.stop()

    asset = st.selectbox(
        tr("select_asset", lang), [tr("portfolio", lang), *port_tickers]
    )
    asset_ret = port_ret if asset == tr("portfolio", lang) else returns[asset]
    capm = quant.rolling_capm(
        asset_ret, returns[benchmark], quant.ROLLING_WINDOW, rf_annual
    )

    if capm.empty:
        st.warning("Not enough observations for a rolling regression.")
        st.stop()

    c1, c2 = st.columns(2)
    c1.markdown(
        kpi_card(tr("current_beta", lang), fmt_num(capm["beta"].iloc[-1]), None, None),
        unsafe_allow_html=True,
    )
    c2.markdown(
        kpi_card(tr("current_alpha", lang), fmt_pct(capm["alpha"].iloc[-1], 2), None, None),
        unsafe_allow_html=True,
    )

    st.markdown("####")
    left, right = st.columns(2)
    with left:
        chart_header(tr("rolling_beta", lang))
        fig_b = go.Figure()
        fig_b.add_trace(go.Scatter(
            x=capm.index, y=capm["beta"], line=dict(width=2.4, color=SLATE), name="β"
        ))
        fig_b.add_hline(y=1.0, line=dict(color=SILVER, dash="dot"))
        fig_b.update_layout(**base_chart_layout(legend=False))
        st.plotly_chart(fig_b, use_container_width=True)
    with right:
        chart_header(tr("annualized_alpha", lang))
        fig_a = go.Figure()
        fig_a.add_trace(go.Scatter(
            x=capm.index, y=capm["alpha"], line=dict(width=2.4, color=GOLD),
            fill="tozeroy", fillcolor="rgba(197,162,90,0.12)", name="α",
        ))
        fig_a.add_hline(y=0.0, line=dict(color=SILVER, dash="dot"))
        fig_a.update_layout(**base_chart_layout(legend=False))
        fig_a.update_yaxes(tickformat=".0%")
        st.plotly_chart(fig_a, use_container_width=True)


# =========================================================================== #
# Section 3 — Rebalancing Engine
# =========================================================================== #
elif section == "rebalancing":
    left, right = st.columns([1, 1.2])

    # Allocation donut aggregated by asset class (equal-weight current book).
    with left:
        chart_header(tr("allocation", lang))
        alloc = {}
        for t in port_tickers:
            alloc[asset_class(t)] = alloc.get(asset_class(t), 0) + equal_w[t]
        donut = go.Figure(go.Pie(
            labels=list(alloc), values=list(alloc.values()), hole=0.62,
            marker=dict(colors=[CLASS_COLORS[k] for k in alloc]),
            textinfo="label+percent",
        ))
        donut.update_layout(**base_chart_layout(height=340, legend=False))
        st.plotly_chart(donut, use_container_width=True)

    with right:
        pv = st.number_input(
            tr("portfolio_value", lang), min_value=0.0, value=5_000_000.0,
            step=100_000.0, format="%.0f",
        )
        st.markdown(f"**{tr('weights_editor', lang)}**")
        editor_df = pd.DataFrame({
            "Instrument": port_tickers,
            "Class": [asset_class(t) for t in port_tickers],
            "Current %": [round(equal_w[t] * 100, 1) for t in port_tickers],
            "Target %": [round(equal_w[t] * 100, 1) for t in port_tickers],
        })
        edited = st.data_editor(
            editor_df, hide_index=True, use_container_width=True,
            disabled=["Instrument", "Class", "Current %"],
            column_config={
                "Target %": st.column_config.NumberColumn(
                    min_value=0.0, max_value=100.0, step=0.5, format="%.1f"
                )
            },
            key="weights_editor",
        )
        if st.button("🧮 " + tr("calculate_trades", lang)):
            cur = dict(zip(edited["Instrument"], edited["Current %"]))
            tgt = dict(zip(edited["Instrument"], edited["Target %"]))
            st.session_state["trades"] = quant.rebalance_trades(cur, tgt, pv)

    if "trades" in st.session_state:
        st.markdown(f"#### {tr('proposed_trades', lang)}")
        trades = st.session_state["trades"].copy()

        def action(v: float) -> str:
            if abs(v) < 1e-6 * max(1.0, abs(trades["Trade Value"]).max()):
                return tr("hold", lang)
            return tr("buy", lang) if v > 0 else tr("sell", lang)

        display = pd.DataFrame({
            "Instrument": trades["Instrument"],
            "Current Weight": (trades["Current Weight"] * 100).map(lambda x: f"{x:.1f}%"),
            "Target Weight": (trades["Target Weight"] * 100).map(lambda x: f"{x:.1f}%"),
            "Drift": (trades["Drift"] * 100).map(lambda x: f"{x:+.1f}%"),
            "Action": trades["Trade Value"].map(action),
            "Trade Value (CHF)": trades["Trade Value"].map(lambda x: f"{x:+,.0f}"),
        })
        st.dataframe(display, hide_index=True, use_container_width=True)


# =========================================================================== #
# Section 4 — Avaloq / VBA Export
# =========================================================================== #
elif section == "export":
    st.markdown(f"#### {tr('export', lang)}")
    st.caption(tr("export_intro", lang))

    if "trades" not in st.session_state:
        st.warning(tr("run_rebalance_first", lang))
        st.stop()

    trades = st.session_state["trades"].copy()
    active = trades[trades["Trade Value"].abs() > 1.0].copy()
    active["Side"] = np.where(active["Trade Value"] > 0, "BUY", "SELL")
    export_df = active[["Instrument", "Side", "Trade Value"]].rename(
        columns={"Trade Value": "Amount_CHF"}
    )
    export_df["Amount_CHF"] = export_df["Amount_CHF"].round(2)

    if export_df.empty:
        st.info(
            "No trades required — the portfolio is already at its target weights."
            if lang == "EN" else
            "Keine Trades erforderlich — das Portfolio entspricht bereits den "
            "Zielgewichten."
        )
        st.stop()

    st.dataframe(export_df, hide_index=True, use_container_width=True)

    csv = export_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ " + tr("download_csv", lang), data=csv,
        file_name="rotshild_trades_avaloq.csv", mime="text/csv",
    )

    # A small VBA snippet that reconstructs the trade blotter as an array.
    lines = ["Sub LoadTrades()", "    Dim trades As Variant", "    trades = Array( _"]
    rows = [
        f'        Array("{r.Instrument}", "{r.Side}", {r.Amount_CHF:.2f})'
        for r in export_df.itertuples()
    ]
    lines.append(", _\n".join(rows) + " _")
    lines += ["    )", "    ' TODO: route to Avaloq order interface", "End Sub"]
    st.markdown(f"**{tr('copy_vba', lang)}**")
    st.code("\n".join(lines), language="vb")
