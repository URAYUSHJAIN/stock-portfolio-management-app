"""Portfolio valuation and holdings dashboard."""

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

from app.theme import INDIGO, LOSS, PROFIT, TEAL, chart_layout, inr, percent, setup_page, signed_inr
from src.db import database_ready, latest_prices
from src.portfolio import portfolio_state, valuation_history

setup_page("Dashboard")
st.title("Dashboard")
if not database_ready():
    st.error("Market data is unavailable. Run the data pipeline first.")
    st.stop()

with st.spinner("Valuing your virtual portfolio…"):
    state = portfolio_state()
    history = valuation_history()
    quotes = latest_prices()

source = quotes["source"].iloc[0] if not quotes.empty else "unknown"
latest_date = quotes["date"].max() if not quotes.empty else "unknown"
st.caption(f"Latest available close: {latest_date} · Source: {source}. Quotes are cached and may be stale.")
if source == "supplied_synthetic":
    st.warning("The current fallback is a 63-day synthetic dataset, including weekends. Portfolio results are for demonstration only.")

first, second, third, fourth = st.columns(4)
first.metric("Portfolio value", inr(state["total_value"]))
second.metric("Total P&L", signed_inr(state["total_pnl"]),
              delta=percent(state["total_pnl"] / state["initial_cash"], arrow=True))
third.metric("Day P&L", signed_inr(state["day_pnl"]))
fourth.metric("Cash available", inr(state["cash"]))

st.subheader("Portfolio value over time")
if history.empty:
    st.info("No price history is available yet.")
else:
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=history["date"], y=history["value"], mode="lines",
                                name="Portfolio value", line=dict(color=TEAL, width=3),
                                fill="tozeroy", fillcolor="rgba(20,184,166,.08)"))
    figure.update_yaxes(title="Virtual portfolio value (₹)")
    st.plotly_chart(chart_layout(figure), use_container_width=True)

st.subheader("Holdings")
holdings = state["holdings"]
if holdings.empty:
    st.info("The demo portfolio holds only cash. Use Trade to place a virtual order.")
else:
    shown = holdings.copy()
    shown["avg_cost"] = shown["avg_cost"].map(inr)
    shown["close"] = shown["close"].map(inr)
    shown["market_value"] = shown["market_value"].map(inr)
    shown["unrealised_pnl"] = shown["unrealised_pnl"].map(signed_inr)
    shown["pnl_pct"] = shown["pnl_pct"].map(lambda value: percent(value / 100, arrow=True))
    shown["weight"] = shown["weight"].map(percent)
    shown = shown.rename(columns={"ticker": "Ticker", "qty": "Qty", "avg_cost": "Avg cost",
                                  "close": "LTP", "market_value": "Value", "unrealised_pnl": "P&L",
                                  "pnl_pct": "P&L %", "weight": "Weight"})
    st.dataframe(shown[["Ticker", "Qty", "Avg cost", "LTP", "Value", "P&L", "P&L %", "Weight"]],
                 use_container_width=True, hide_index=True)

    left, right = st.columns(2)
    with left:
        st.subheader("Allocation")
        allocation = holdings[["ticker", "market_value"]].rename(columns={"ticker": "Asset", "market_value": "Value"})
        allocation.loc[len(allocation)] = ["Cash", state["cash"]]
        fig = px.pie(allocation, names="Asset", values="Value", hole=.65,
                     color_discrete_sequence=[TEAL, INDIGO, PROFIT, LOSS])
        st.plotly_chart(chart_layout(fig, height=330), use_container_width=True)
    with right:
        st.subheader("Holding P&L")
        ranked = holdings.sort_values("unrealised_pnl", ascending=False)
        fig = px.bar(ranked, x="ticker", y="unrealised_pnl", color="unrealised_pnl",
                     color_continuous_scale=[LOSS, "#334155", PROFIT], color_continuous_midpoint=0)
        fig.update_layout(showlegend=False, coloraxis_showscale=False)
        st.plotly_chart(chart_layout(fig, height=330), use_container_width=True)

st.subheader("Market movers")
if not quotes.empty:
    movers = quotes.loc[quotes["ticker"] != "^NSEI"].copy()
    movers["change_pct"] = (movers["close"] / movers["previous_close"] - 1) * 100
    movers = movers.dropna(subset=["change_pct"])
    gainers, losers = st.columns(2)
    gainers.write("**Top gainers**")
    gainers.dataframe(movers.nlargest(3, "change_pct").assign(
        Change=lambda d: d["change_pct"].map(lambda value: percent(value / 100, arrow=True))
    )[["ticker", "Change"]].rename(columns={"ticker": "Ticker"}), hide_index=True, use_container_width=True)
    losers.write("**Top losers**")
    losers.dataframe(movers.nsmallest(3, "change_pct").assign(
        Change=lambda d: d["change_pct"].map(lambda value: percent(value / 100, arrow=True))
    )[["ticker", "Change"]].rename(columns={"ticker": "Ticker"}), hide_index=True, use_container_width=True)
