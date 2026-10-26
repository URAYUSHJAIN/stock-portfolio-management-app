"""Focused checks for cleaning and durable price constraints."""

from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from src.data_pipeline import clean_prices
from src.db import create_schema


def test_clean_prices_repairs_bounds_and_returns() -> None:
    raw = pd.DataFrame([
        {"date": "2024-01-01", "ticker": "TCS", "open": 100, "high": 99,
         "low": 101, "close": 102, "volume": 1000, "daily_return_pct": 88},
        {"date": "2024-01-02", "ticker": "TCS", "open": 102, "high": 106,
         "low": 101, "close": 104, "volume": 1100, "daily_return_pct": 88},
    ])
    cleaned, report = clean_prices(raw)
    assert report["high_bounds_fixed"] == 1
    assert report["low_bounds_fixed"] == 1
    assert cleaned.iloc[0]["high"] == 102
    assert cleaned.iloc[0]["low"] == 100
    assert pd.isna(cleaned.iloc[0]["daily_return_pct"])
    assert cleaned.iloc[1]["daily_return_pct"] == pytest.approx(100 * (104 / 102 - 1))


def test_schema_rejects_bad_candle_and_negative_cash() -> None:
    with sqlite3.connect(":memory:") as connection:
        create_schema(connection)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("""
                INSERT INTO prices(date,ticker,open,high,low,close,volume,source)
                VALUES (?,?,?,?,?,?,?,?)
            """, ("2024-01-01", "TCS", 100, 99, 98, 101, 100, "supplied_synthetic"))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE portfolio SET cash = ? WHERE id = ?", (-1, 1))
