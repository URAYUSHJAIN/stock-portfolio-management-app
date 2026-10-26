"""Filtered OHLCV table and transparent data quality report."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if (ROOT / ".deps").exists():
    sys.path.append(str(ROOT / ".deps"))

import plotly.express as px
import streamlit as st

from app.theme import chart_layout, setup_page
from src.config import QUALITY_REPORT
from src.db import database_ready, price_history

setup_page("Data Explorer")
st.title("Data explorer")
if not database_ready():
    st.error("Market data is unavailable. Run the data pipeline first.")
    st.stop()

with st.spinner("Loading cleaned market data…"):
    prices = price_history()
if prices.empty:
    st.info("There are no price rows to explore.")
    st.stop()

tickers = sorted(prices["ticker"].unique())
selection = st.multiselect("Tickers", tickers, default=tickers[:2])
range_value = st.date_input("Date range", value=(prices["date"].min().date(), prices["date"].max().date()),
                            min_value=prices["date"].min().date(), max_value=prices["date"].max().date())
if len(range_value) == 2:
    start, end = range_value
else:
    st.info("Select a start and end date.")
    st.stop()
filtered = prices.loc[(prices["ticker"].isin(selection)) &
                      (prices["date"].dt.date >= start) & (prices["date"].dt.date <= end)].copy()
st.caption(f"{len(filtered):,} of {len(prices):,} rows · Active source: {prices['source'].iloc[0]}")
if filtered.empty:
    st.info("No observations match these filters.")
else:
    fig = px.line(filtered, x="date", y="close", color="ticker", title="Closing prices")
    st.plotly_chart(chart_layout(fig), use_container_width=True)
    st.dataframe(filtered, hide_index=True, use_container_width=True)
    st.download_button("Download filtered CSV", filtered.to_csv(index=False).encode("utf-8"),
                       file_name="filtered_prices.csv", mime="text/csv")

st.subheader("Data quality")
if QUALITY_REPORT.exists():
    report = json.loads(QUALITY_REPORT.read_text(encoding="utf-8"))
    cols = st.columns(4)
    cols[0].metric("Supplied rows", report["input_rows"])
    cols[1].metric("High bounds fixed", report["high_bounds_fixed"])
    cols[2].metric("Low bounds fixed", report["low_bounds_fixed"])
    cols[3].metric("Weekend rows", report["weekend_rows"])
    st.write(report["notes"])
    st.caption(f"Invalid rows dropped: {report['invalid_rows_dropped']} · Duplicate keys dropped: {report['duplicate_keys_dropped']} · Active rows: {report['active_rows']:,}")
    if report.get("risk_limitation"):
        st.warning(report["risk_limitation"])
    with st.expander("Full quality report"):
        st.json(report)
else:
    st.info("The quality report has not been generated yet.")
