"""Entry point for the virtual portfolio Streamlit application."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.theme import setup_page  # noqa: E402
from src.db import database_ready  # noqa: E402

setup_page("Home")
st.title("Portfolio Lab")
st.write("Explore a virtual NSE portfolio, risk measures, trading signals, and cleaned price data.")
if database_ready():
    st.success("Market data and the ₹10,00,000 demo portfolio are ready. Choose a page in the sidebar.")
else:
    st.error("The database is not ready. Run `python -m src.data_pipeline` first.")
