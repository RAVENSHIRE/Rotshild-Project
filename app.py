import io

import numpy as np
import pandas as pd
import scipy.optimize as sco
import statsmodels.api as sm
import streamlit as st
import yfinance as yf

# ==========================================
# 1. QUANTITATIVE ENGINE (Quant Guild Logic)
# ==========================================


def fetch_data(tickers, start_date, end_date):
    """Fetches adjusted close prices from Yahoo Finance."""
    data = yf.download(tickers, start=start_date, end=end_date, auto_adjust=True)["Close"]
    if isinstance(data, pd.Series):
        data = data.to_frame(name=tickers[0] if len(tickers) == 1 else "Asset")
    # Calculate daily returns
    returns = data.pct_change().dropna()
    return returns


def calculate_portfolio_returns(returns_df, weights):
    """Calculates the weighted daily returns of the portfolio."""
    weights = np.array(weights)
    weights = weights / np.sum(weights)
    port_returns = returns_df.dot(weights)
    return port_returns


def calculate_performance_metrics(returns, risk_free_rate=0.02):
    """Calculates CAGR, Volatility, Max Drawdown, Sharpe, and Sortino."""
    # Volatility Drag & Geometric Return
    cumulative_returns = (1 + returns).cumprod()
    total_return = cumulative_returns.iloc[-1] - 1
    years = len(returns) / 252
    cagr = (1 + total_return) ** (1 / years) - 1

    # Volatility (Annualised Standard Deviation)
    volatility = returns.std() * np.sqrt(252)

    # Max Drawdown
    rolling_max = cumulative_returns.cummax()
    drawdown = cumulative_returns / rolling_max - 1
    max_drawdown = drawdown.min()

    # Sharpe Ratio
    sharpe = (cagr - risk_free_rate) / volatility

    # Sortino Ratio (downside deviation only)
    downside_returns = returns[returns < 0]
    downside_vol = downside_returns.std() * np.sqrt(252)
    sortino = (cagr - risk_free_rate) / downside_vol if downside_vol > 0 else np.nan

    return {
        "CAGR": cagr,
        "Volatility": volatility,
        "Max Drawdown": max_drawdown,
        "Sharpe Ratio": sharpe,
        "Sortino Ratio": sortino,
    }


def calculate_rolling_capm(port_returns, bench_returns, window=63):
    """
    Calculates rolling 63-day Alpha and Beta.
    Runs OLS regression: Portfolio_Return = Alpha + Beta * Benchmark_Return
    """
    df = pd.DataFrame({"Portfolio": port_returns, "Benchmark": bench_returns}).dropna()

    rolling_betas = []
    rolling_alphas = []
    dates = []

    for i in range(window, len(df)):
        y = df["Portfolio"].iloc[i - window : i]
        x = sm.add_constant(df["Benchmark"].iloc[i - window : i])

        model = sm.OLS(y, x).fit()

        alpha = model.params.iloc[0]
        beta = model.params.iloc[1]

        # Annualise alpha (daily data)
        annualized_alpha = (1 + alpha) ** 252 - 1

        rolling_alphas.append(annualized_alpha)
        rolling_betas.append(beta)
        dates.append(df.index[i - 1])

    return pd.DataFrame(
        {"Rolling Beta": rolling_betas, "Annualized Alpha": rolling_alphas},
        index=dates,
    )


# ==========================================
# 2. MEAN-VARIANCE OPTIMISATION ENGINE
# ==========================================


def mean_variance_optimise(returns_df, risk_free_rate=0.02, target="sharpe"):
    """
    Finds optimal portfolio weights using scipy.optimize.
    target: 'sharpe' (maximise Sharpe) | 'min_vol' (minimise volatility)
    Returns a dict with weights, expected CAGR, volatility, and Sharpe.
    """
    n = returns_df.shape[1]
    mean_returns = returns_df.mean() * 252
    cov_matrix = returns_df.cov() * 252

    def neg_sharpe(weights):
        port_ret = np.dot(weights, mean_returns)
        port_vol = np.sqrt(weights @ cov_matrix.values @ weights)
        return -(port_ret - risk_free_rate) / port_vol

    def portfolio_vol(weights):
        return np.sqrt(weights @ cov_matrix.values @ weights)

    constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1}
    bounds = tuple((0.0, 1.0) for _ in range(n))
    x0 = np.array([1.0 / n] * n)

    objective = neg_sharpe if target == "sharpe" else portfolio_vol
    result = sco.minimize(
        objective,
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-9, "maxiter": 1000},
    )

    if not result.success:
        return None

    weights = result.x
    port_ret = float(np.dot(weights, mean_returns))
    port_vol = float(np.sqrt(weights @ cov_matrix.values @ weights))
    sharpe = (port_ret - risk_free_rate) / port_vol if port_vol > 0 else np.nan

    return {
        "weights": weights,
        "Expected Return (Ann.)": port_ret,
        "Expected Volatility (Ann.)": port_vol,
        "Expected Sharpe": sharpe,
    }


def build_efficient_frontier(returns_df, n_points=200):
    """Builds the efficient frontier by iterating over target return levels."""
    n = returns_df.shape[1]
    mean_returns = returns_df.mean() * 252
    cov_matrix = returns_df.cov() * 252

    min_ret = float(mean_returns.min())
    max_ret = float(mean_returns.max())
    target_returns = np.linspace(min_ret, max_ret, n_points)

    frontier_vols = []
    frontier_rets = []

    for target_ret in target_returns:
        constraints = [
            {"type": "eq", "fun": lambda w: np.sum(w) - 1},
            {"type": "eq", "fun": lambda w, t=target_ret: np.dot(w, mean_returns) - t},
        ]
        bounds = tuple((0.0, 1.0) for _ in range(n))
        x0 = np.array([1.0 / n] * n)

        result = sco.minimize(
            lambda w: np.sqrt(w @ cov_matrix.values @ w),
            x0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"ftol": 1e-9, "maxiter": 1000},
        )

        if result.success:
            frontier_vols.append(float(np.sqrt(result.x @ cov_matrix.values @ result.x)))
            frontier_rets.append(target_ret)

    return pd.DataFrame({"Volatility": frontier_vols, "Return": frontier_rets})


# ==========================================
# 3. STREAMLIT FRONTEND / UI DASHBOARD
# ==========================================

st.set_page_config(page_title="Rothschild Analytics Dashboard", layout="wide")

st.title("Portfolio Management Analytics Engine")
st.markdown("Inspired by Quant Guild | Built for Rothschild & Co. Portfolio Management")

# ---- Sidebar ----
st.sidebar.header("Portfolio Parameters")
tickers_input = st.sidebar.text_input(
    "Enter Tickers (comma separated)", "AAPL, MSFT, NVDA"
)
benchmark_input = st.sidebar.text_input("Benchmark", "SPY")
start_date = st.sidebar.date_input("Start Date", pd.to_datetime("2020-01-01"))
end_date = st.sidebar.date_input("End Date", pd.to_datetime("today"))
risk_free_rate = st.sidebar.number_input(
    "Risk-Free Rate (%)", min_value=0.0, max_value=20.0, value=2.0, step=0.25
) / 100

# Parse inputs
tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
benchmark = benchmark_input.strip().upper()
all_tickers = tickers + ([benchmark] if benchmark not in tickers else [])

# ---- App Tabs ----
tab1, tab2, tab3 = st.tabs(
    ["Quant Risk & CAPM (Alpha/Beta)", "Portfolio Rebalancing", "Data Export (Excel)"]
)

if st.sidebar.button("Run Analytics"):
    with st.spinner("Fetching data and running quantitative models…"):
        # ---- Fetch data ----
        try:
            returns_df = fetch_data(all_tickers, start_date, end_date)
        except Exception as e:
            st.error(f"Data fetch failed: {e}")
            st.stop()

        if returns_df.empty or len(returns_df) < 65:
            st.error("Not enough data returned. Extend the date range or check tickers.")
            st.stop()

        # Separate portfolio assets and benchmark
        available_tickers = [t for t in tickers if t in returns_df.columns]
        if not available_tickers:
            st.error("None of the provided tickers returned data.")
            st.stop()

        port_assets = returns_df[available_tickers]
        benchmark_returns = returns_df[benchmark] if benchmark in returns_df.columns else None

        # Equal weight as default
        weights = [1.0 / len(available_tickers)] * len(available_tickers)
        port_returns = calculate_portfolio_returns(port_assets, weights)

        # Performance metrics
        metrics = calculate_performance_metrics(port_returns, risk_free_rate)
        bench_metrics = (
            calculate_performance_metrics(benchmark_returns, risk_free_rate)
            if benchmark_returns is not None
            else None
        )

        # Rolling CAPM
        capm_df = None
        if benchmark_returns is not None:
            capm_df = calculate_rolling_capm(port_returns, benchmark_returns, window=63)

        # ============================================================
        # TAB 1 – QUANT RISK & CAPM
        # ============================================================
        with tab1:
            st.subheader("Performance Metrics vs. Benchmark")
            col1, col2, col3, col4, col5 = st.columns(5)

            cagr_delta = (
                f"{(metrics['CAGR'] - bench_metrics['CAGR']):.2%} vs Bench"
                if bench_metrics
                else None
            )
            col1.metric("CAGR", f"{metrics['CAGR']:.2%}", cagr_delta)
            col2.metric("Max Drawdown", f"{metrics['Max Drawdown']:.2%}")
            col3.metric("Sharpe Ratio", f"{metrics['Sharpe Ratio']:.2f}")
            col4.metric("Sortino Ratio", f"{metrics['Sortino Ratio']:.2f}")
            col5.metric("Volatility", f"{metrics['Volatility']:.2%}")

            if capm_df is not None and not capm_df.empty:
                st.subheader("Rolling 63-Day Alpha & Beta (CAPM)")
                st.markdown(
                    "Tracking undiversifiable risk exposure and idiosyncratic "
                    "outperformance over time."
                )
                col_b, col_a = st.columns(2)
                with col_b:
                    st.caption("Rolling Beta")
                    st.line_chart(capm_df["Rolling Beta"])
                with col_a:
                    st.caption("Annualised Alpha")
                    st.line_chart(capm_df["Annualized Alpha"])
            else:
                st.info("Rolling CAPM requires a benchmark with overlapping data.")

            st.subheader("Cumulative Returns")
            cum_port = (1 + port_returns).cumprod()
            chart_df = pd.DataFrame({"Portfolio (Equal-Weight)": cum_port})
            if benchmark_returns is not None:
                chart_df[benchmark] = (1 + benchmark_returns).cumprod()
            st.line_chart(chart_df)

        # ============================================================
        # TAB 2 – PORTFOLIO REBALANCING
        # ============================================================
        with tab2:
            st.subheader("Mean-Variance Optimisation Engine")
            st.markdown(
                "Uses **scipy.optimize (SLSQP)** to find optimal portfolio weights "
                "on the efficient frontier."
            )

            opt_target = st.radio(
                "Optimisation Target",
                ["Maximum Sharpe Ratio", "Minimum Volatility"],
                horizontal=True,
            )
            target_key = "sharpe" if opt_target == "Maximum Sharpe Ratio" else "min_vol"

            if len(available_tickers) < 2:
                st.warning("Need at least 2 assets for optimisation.")
            else:
                with st.spinner("Running optimiser…"):
                    opt_result = mean_variance_optimise(
                        port_assets, risk_free_rate=risk_free_rate, target=target_key
                    )

                if opt_result is None:
                    st.error("Optimisation did not converge. Try a different date range.")
                else:
                    opt_weights = opt_result["weights"]

                    st.subheader("Optimal Weights")
                    weights_df = pd.DataFrame(
                        {
                            "Ticker": available_tickers,
                            "Equal-Weight": [
                                f"{w:.2%}" for w in weights
                            ],
                            "Optimal Weight": [f"{w:.2%}" for w in opt_weights],
                            "Δ Weight": [
                                f"{(o - e):.2%}"
                                for o, e in zip(
                                    opt_weights,
                                    [1.0 / len(available_tickers)] * len(available_tickers),
                                )
                            ],
                        }
                    )
                    st.dataframe(weights_df, use_container_width=True)

                    col_r, col_v, col_s = st.columns(3)
                    col_r.metric(
                        "Expected Return (Ann.)",
                        f"{opt_result['Expected Return (Ann.)']:.2%}",
                    )
                    col_v.metric(
                        "Expected Volatility (Ann.)",
                        f"{opt_result['Expected Volatility (Ann.)']:.2%}",
                    )
                    col_s.metric(
                        "Expected Sharpe",
                        f"{opt_result['Expected Sharpe']:.2f}",
                    )

                    # Efficient Frontier
                    with st.spinner("Building efficient frontier…"):
                        frontier_df = build_efficient_frontier(port_assets)

                    if not frontier_df.empty:
                        st.subheader("Efficient Frontier")
                        st.line_chart(
                            frontier_df.set_index("Volatility")["Return"],
                        )

                    # Required trades from equal-weight to optimal
                    st.subheader("Required Rebalancing Trades")
                    st.markdown(
                        "Assuming a **\\$1,000,000** portfolio starting at equal weights."
                    )
                    portfolio_value = 1_000_000
                    trades = []
                    for ticker, eq_w, opt_w in zip(
                        available_tickers,
                        [1.0 / len(available_tickers)] * len(available_tickers),
                        opt_weights,
                    ):
                        delta = (opt_w - eq_w) * portfolio_value
                        action = "BUY" if delta > 0 else "SELL"
                        trades.append(
                            {
                                "Ticker": ticker,
                                "Current Weight": f"{eq_w:.2%}",
                                "Target Weight": f"{opt_w:.2%}",
                                "Trade ($)": f"${abs(delta):,.2f}",
                                "Action": action,
                            }
                        )
                    st.dataframe(pd.DataFrame(trades), use_container_width=True)

        # ============================================================
        # TAB 3 – DATA EXPORT
        # ============================================================
        with tab3:
            st.subheader("Avaloq / VBA Compatible Data Export")

            # Preview
            st.markdown("**Daily Returns (last 10 rows)**")
            st.dataframe(returns_df.tail(10), use_container_width=True)

            # Build Excel workbook in memory
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                returns_df.to_excel(writer, sheet_name="Daily Returns")
                cum_returns = (1 + returns_df).cumprod()
                cum_returns.to_excel(writer, sheet_name="Cumulative Returns")

                # Performance summary sheet
                summary_data = {
                    "Metric": list(metrics.keys()),
                    "Portfolio": [f"{v:.4f}" for v in metrics.values()],
                }
                if bench_metrics:
                    summary_data[benchmark] = [
                        f"{v:.4f}" for v in bench_metrics.values()
                    ]
                pd.DataFrame(summary_data).to_excel(
                    writer, sheet_name="Performance Summary", index=False
                )

                # CAPM sheet
                if capm_df is not None and not capm_df.empty:
                    capm_df.to_excel(writer, sheet_name="Rolling CAPM")

            output.seek(0)
            st.download_button(
                label="⬇ Download Portfolio Data (.xlsx)",
                data=output,
                file_name="rothschild_portfolio_analytics.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
