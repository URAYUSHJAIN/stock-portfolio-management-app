"""Technical signals, next-open backtest, and ML evaluation."""

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

from app.theme import INDIGO, LOSS, PROFIT, TEAL, chart_layout, percent, setup_page
from src.config import STOCKS
from src.db import database_ready, price_history
from src.ml_model import train_direction_model
from src.signals import backtest_signals, generate_signals

setup_page("Signals")
st.title("Signals and backtesting")
if not database_ready():
    st.error("Market data is unavailable. Run the data pipeline first.")
    st.stop()

ticker = st.selectbox("Ticker", [ticker for ticker in STOCKS if ticker != "^NSEI"])
strategy = st.radio("Strategy", ["SMA 20/50 crossover", "RSI 14 thresholds"], horizontal=True)
signal_column = "sma_signal" if strategy.startswith("SMA") else "rsi_signal"
with st.spinner("Calculating signals and evaluating the historical simulation…"):
    prices = price_history(ticker)
    if prices.empty:
        st.info("No prices are available for this ticker.")
        st.stop()
    marked = generate_signals(prices)
    backtest = backtest_signals(marked, signal_column)

st.caption(f"Source: {prices['source'].iloc[0]} · {len(prices)} observations. Signal is known at the close; a virtual order fills at the following day's open.")
if prices["source"].iloc[0] == "supplied_synthetic":
    st.warning("The supplied history is synthetic, includes weekends, and spans only 63 dates. Treat signal and backtest results as a demonstration.")

st.subheader("Price and signal markers")
fig = go.Figure()
fig.add_trace(go.Scatter(x=marked["date"], y=marked["close"], name="Close",
                         mode="lines", line=dict(color=TEAL, width=2)))
if signal_column == "sma_signal":
    fig.add_trace(go.Scatter(x=marked["date"], y=marked["sma20"], name="SMA 20",
                             mode="lines", line=dict(color=INDIGO, width=1.5)))
    fig.add_trace(go.Scatter(x=marked["date"], y=marked["sma50"], name="SMA 50",
                             mode="lines", line=dict(color="#F59E0B", width=1.5)))
for signal, colour, symbol in (("BUY", PROFIT, "triangle-up"), ("SELL", LOSS, "triangle-down")):
    selected = marked.loc[marked[signal_column] == signal]
    fig.add_trace(go.Scatter(x=selected["date"], y=selected["close"], mode="markers",
                             name=f"{signal} signal", marker=dict(color=colour, size=12, symbol=symbol)))
fig.update_yaxes(title="Close (₹)")
st.plotly_chart(chart_layout(fig), use_container_width=True)
if signal_column == "rsi_signal":
    rsi_fig = go.Figure(go.Scatter(x=marked["date"], y=marked["rsi14"],
                                   name="RSI 14", line=dict(color=INDIGO)))
    rsi_fig.add_hline(y=30, line_dash="dash", line_color=PROFIT)
    rsi_fig.add_hline(y=70, line_dash="dash", line_color=LOSS)
    rsi_fig.update_yaxes(title="RSI", range=[0, 100])
    st.plotly_chart(chart_layout(rsi_fig, height=260), use_container_width=True)

st.subheader("Backtest versus buy-and-hold")
st.caption("Long or cash only; starts with ₹1,00,000, whole shares, the same 0.1% / ₹20 brokerage, no slippage or taxes. Buy-and-hold enters at the first open.")
cols = st.columns(5)
cols[0].metric("Strategy return", percent(backtest["strategy_return"], arrow=True))
cols[1].metric("Buy-and-hold return", percent(backtest["buy_hold_return"], arrow=True))
cols[2].metric("Sharpe", f"{backtest['sharpe']:.2f}" if backtest["sharpe"] is not None else "—")
cols[3].metric("Max drawdown", percent(backtest["max_drawdown"]))
cols[4].metric("Win rate", percent(backtest["win_rate"]) if backtest["win_rate"] is not None else "—")
if backtest["sharpe"] is None:
    st.caption("Sharpe is withheld until at least 252 daily returns are available. Win rate counts completed round trips only.")
equity = backtest["equity"]
equity_fig = go.Figure()
equity_fig.add_trace(go.Scatter(x=equity["date"], y=equity["strategy"],
                                name="Strategy", line=dict(color=TEAL, width=2)))
equity_fig.add_trace(go.Scatter(x=equity["date"], y=equity["buy_hold"],
                                name="Buy-and-hold", line=dict(color=INDIGO, width=2)))
equity_fig.update_yaxes(title="Virtual equity (₹)")
st.plotly_chart(chart_layout(equity_fig), use_container_width=True)
if backtest["trades"].empty:
    st.info("No orders were triggered by this strategy in the selected history.")
else:
    with st.expander("Executed virtual orders"):
        st.dataframe(backtest["trades"], hide_index=True, use_container_width=True)

st.subheader("Next-day direction model")
model = train_direction_model(prices)
if not model["available"]:
    st.info(model["reason"])
else:
    st.caption(f"Logistic regression; {model['train_rows']} earlier training rows, {model['test_rows']} later test rows. Training ended {model['train_end']}; test began {model['test_start']}.")
    cols = st.columns(5)
    for col, (label, key) in zip(cols, (("Accuracy", "accuracy"), ("Precision", "precision"),
                                         ("Recall", "recall"), ("F1", "f1"),
                                         ("Majority baseline", "majority_baseline_accuracy"))):
        col.metric(label, percent(model[key]))
    matrix = px.imshow(model["confusion_matrix"], x=["Predicted down", "Predicted up"],
                       y=["Actual down", "Actual up"], text_auto=True,
                       color_continuous_scale="Teal", title="Out-of-sample confusion matrix")
    st.plotly_chart(chart_layout(matrix, height=330), use_container_width=True)
    st.caption("Historical classification scores are not trading returns or evidence of future performance.")
