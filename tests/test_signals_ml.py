"""Signal timing, benchmark and model split checks."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.ml_model import train_direction_model
from src.signals import backtest_signals, generate_signals


def test_backtest_executes_only_at_next_open() -> None:
    prices = pd.DataFrame([
        {"date": "2024-01-01", "open": 100, "close": 100, "sma_signal": "BUY"},
        {"date": "2024-01-02", "open": 200, "close": 200, "sma_signal": "HOLD"},
    ])
    result = backtest_signals(prices, initial_cash=1000)
    assert result["trades"].iloc[0]["date"] == "2024-01-02"
    assert result["trades"].iloc[0]["price"] == 200
    assert result["trades"].iloc[0]["qty"] == 4
    assert result["strategy_return"] == pytest.approx(-0.02)
    assert result["buy_hold_return"] > result["strategy_return"]


def test_sma_has_no_signal_before_fifty_closes() -> None:
    prices = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=60),
                           "close": np.arange(100, 160, dtype=float)})
    generated = generate_signals(prices)
    assert (generated.loc[:48, "sma_signal"] == "HOLD").all()
    assert generated.loc[49, "sma_signal"] == "BUY"


def test_model_requires_adequate_history() -> None:
    close = np.linspace(100, 120, 63)
    prices = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=63),
                           "open": close, "high": close + 1, "low": close - 1,
                           "close": close, "volume": 1000})
    result = train_direction_model(prices)
    assert not result["available"]
    assert "252" in result["reason"]


def test_model_uses_chronological_holdout_and_past_only_features() -> None:
    rng = np.random.default_rng(42)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.012, 310)))
    prices = pd.DataFrame({"date": pd.date_range("2023-01-01", periods=310),
                           "open": close * 0.999, "high": close * 1.01,
                           "low": close * 0.99, "close": close,
                           "volume": rng.integers(1000, 3000, 310)})
    result = train_direction_model(prices)
    assert result["available"]
    assert result["train_rows"] > result["test_rows"] > 0
    assert pd.Timestamp(result["train_end"]) < pd.Timestamp(result["test_start"])
    assert pd.Timestamp(result["train_label_end"]) < pd.Timestamp(result["test_start"])
    assert sum(sum(row) for row in result["confusion_matrix"]) == result["test_rows"]
