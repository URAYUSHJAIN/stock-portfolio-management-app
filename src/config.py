"""Paths and application configuration."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("HCL_DATA_DIR", str(ROOT / "data"))).resolve()
DB_PATH = Path(os.getenv("HCL_DB_PATH", str(DATA_DIR / "portfolio.db"))).resolve()
ORIGINAL_CSV = DATA_DIR / "dataset.csv"
CLEANED_CSV = DATA_DIR / "cleaned_dataset.csv"
MARKET_CACHE = DATA_DIR / "market_cache.csv"
QUALITY_REPORT = DATA_DIR / "quality_report.json"
INITIAL_CASH = 1_000_000.0
RISK_FREE_RATE = 0.065
TRADING_DAYS = 252
DISCLAIMER = "Simulation only. NOT investment advice. Virtual money, no real brokerage connection."

STOCKS = {
    "RELIANCE": ("Reliance Industries", "Energy"),
    "TCS": ("Tata Consultancy Services", "Technology"),
    "INFY": ("Infosys", "Technology"),
    "HDFCBANK": ("HDFC Bank", "Banking"),
    "ICICIBANK": ("ICICI Bank", "Banking"),
    "WIPRO": ("Wipro", "Technology"),
    "LT": ("Larsen & Toubro", "Industrials"),
    "AXISBANK": ("Axis Bank", "Banking"),
    "^NSEI": ("NIFTY 50", "Index"),
}
