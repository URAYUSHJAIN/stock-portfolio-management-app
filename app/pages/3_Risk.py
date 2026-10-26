"""Historical portfolio risk measures and benchmark comparison."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if (ROOT / ".deps").exists():
    sys.path.append(str(ROOT / ".deps"))

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.theme import LOSS, TEAL, chart_layout, percent, setup_page
from src.db import database_ready, latest_prices
from src.portfolio import portfolio_state
from src.risk import calculate_risk, close_and_returns, correlation_matrix, drawdown_curve, portfolio_returns

setup_page("Risk")
st.title("Risk analytics")
if not database_ready():
    st.error("Market data is unavailable. Run the data pipeline first.")
    st.stop()

close, returns = close_and_returns()
state = portfolio_state()
quotes = latest_prices()
source = quotes["source"].iloc[0] if not quotes.empty else "unknown"
if returns.empty:
    st.info("Risk measures need price history.")
    st.stop()

if not state["holdings"].empty:
    chosen = "Current portfolio"
    series = portfolio_returns()
    st.caption("Portfolio risk applies today's shares and cash balance to historical closing prices; it is a current-exposure scenario, not the realised account history.")
else:
    st.info("The portfolio is all cash. Choose a ticker for an exploratory risk view.")
    chosen = st.selectbox("Ticker", [ticker for ticker in returns if ticker != "^NSEI"])
    series = returns[chosen].dropna()
benchmark = returns["^NSEI"].dropna() if "^NSEI" in returns else None
risk = calculate_risk(series, benchmark)
st.caption(f"Analysing {chosen} · {risk['observations']} return observations · Source: {source}")
if not risk["sufficient_history"]:
    st.warning("Fewer than 252 return observations. Annualised volatility, Sharpe and beta are withheld. Short-window drawdown and VaR are exploratory only.")
if benchmark is None:
    st.warning("NIFTY 50 history is unavailable, so beta cannot be calculated.")

cols = st.columns(5)
cols[0].metric("Volatility, annualised", percent(risk["volatility"]) if risk["volatility"] is not None else "—")
cols[1].metric("Sharpe", f"{risk['sharpe']:.2f}" if risk["sharpe"] is not None else "—")
cols[2].metric("Beta vs NIFTY 50", f"{risk['beta']:.2f}" if risk["beta"] is not None else "—")
cols[3].metric("Max drawdown", percent(risk["max_drawdown"]) if risk["max_drawdown"] is not None else "—")
cols[4].metric("Historical VaR 95%", percent(risk["var_95"]) if risk["var_95"] is not None else "—")

st.subheader("Drawdown")
if len(series.dropna()) >= 2:
    drawdown = drawdown_curve(series)
    fig = go.Figure(go.Scatter(x=drawdown.index, y=drawdown * 100, mode="lines",
                               line=dict(color=LOSS, width=2), fill="tozeroy",
                               fillcolor="rgba(239,68,68,.13)", name="Drawdown"))
    fig.update_yaxes(title="Drawdown (%)")
    st.plotly_chart(chart_layout(fig), use_container_width=True)
else:
    st.info("At least two returns are needed for a drawdown chart.")

st.subheader("Return correlation")
correlation = correlation_matrix(returns)
if correlation.empty or correlation.isna().all().all():
    st.info("At least 30 overlapping returns are needed for the correlation heatmap.")
else:
    fig = px.imshow(correlation, zmin=-1, zmax=1, color_continuous_scale="RdBu",
                    title="Pairwise daily-return correlation")
    st.plotly_chart(chart_layout(fig, height=470), use_container_width=True)

with st.expander("How these measures are calculated"):
    st.markdown("""
    - **Annualised volatility:** sample standard deviation of daily returns × √252.
    - **Sharpe ratio:** (mean daily return − 6.5% ÷ 252) ÷ daily return standard deviation × √252.
    - **Beta:** covariance(asset, NIFTY 50) ÷ variance(NIFTY 50), on overlapping days.
    - **Maximum drawdown:** lowest value of compounded wealth ÷ its previous peak − 1.
    - **Historical VaR 95%:** negative fifth percentile of daily returns, floored at zero; it is not a guaranteed loss limit.
    - **Correlation:** Pearson correlation of overlapping daily returns.

    Annualised measures require 252 observations. All historical estimates depend on the selected sample and source.
    """)
