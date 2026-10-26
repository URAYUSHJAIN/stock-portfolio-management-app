"""Virtual trade form and transaction history."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.theme import inr, setup_page
from src.config import STOCKS
from src.db import database_ready, latest_prices
from src.portfolio import brokerage_fee, place_order, portfolio_state, transactions

setup_page("Trade")
st.title("Virtual trading")
if "trade_notice" in st.session_state:
    st.success(st.session_state.pop("trade_notice"))
if not database_ready():
    st.error("Market data is unavailable. Run the data pipeline first.")
    st.stop()

state = portfolio_state()
quotes = latest_prices().set_index("ticker")
st.metric("Available virtual cash", inr(state["cash"]))
st.caption("Orders fill at the latest stored closing price. Brokerage: 0.1% of notional, minimum ₹20 per order.")

with st.form("virtual_order"):
    ticker = st.selectbox("Ticker", [ticker for ticker in STOCKS if ticker != "^NSEI"])
    side = st.radio("Side", ["BUY", "SELL"], horizontal=True)
    qty = int(st.number_input("Quantity", min_value=1, step=1, value=1))
    quote = quotes.loc[ticker] if ticker in quotes.index else None
    if quote is not None:
        quoted_price = float(quote["close"])
        st.write(f"Latest close: **{inr(quoted_price)}** on {quote['date']}")
        fee = brokerage_fee(qty, quoted_price)
        st.write(f"Estimated brokerage: **{inr(fee)}** · "
                 f"{'Total debit' if side == 'BUY' else 'Net credit'}: "
                 f"**{inr(qty * quoted_price + fee if side == 'BUY' else qty * quoted_price - fee)}**")
        if (date.today() - date.fromisoformat(quote["date"])).days > 7:
            st.warning("This cached quote is more than seven days old; the virtual fill will use that historical close.")
    submitted = st.form_submit_button("Place virtual order", type="primary", use_container_width=True)

if submitted:
    try:
        with st.spinner("Recording virtual order…"):
            result = place_order(1, ticker, side, qty)
        st.session_state["trade_notice"] = (
            f"Recorded {result['side']} {result['qty']} {result['ticker']} at "
            f"{inr(result['price'])}; brokerage {inr(result['fees'])}."
        )
        st.rerun()
    except ValueError as exc:
        st.error(str(exc))

st.subheader("Transaction history")
history = transactions()
if history.empty:
    st.info("No virtual trades yet. The portfolio currently holds cash.")
else:
    shown = history.copy()
    shown["price"] = shown["price"].map(inr)
    shown["fees"] = shown["fees"].map(inr)
    st.dataframe(shown.rename(columns={"date": "Date", "ticker": "Ticker", "side": "Side",
                                       "qty": "Qty", "price": "Price", "fees": "Brokerage"}),
                 use_container_width=True, hide_index=True)
    st.download_button("Download transactions CSV", data=history.to_csv(index=False).encode("utf-8"),
                       file_name="virtual_transactions.csv", mime="text/csv")
