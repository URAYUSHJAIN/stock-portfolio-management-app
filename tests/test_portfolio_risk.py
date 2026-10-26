"""Accounting and risk checks with known expected values."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from src.db import create_schema, transaction
from src.portfolio import place_order, portfolio_state
from src.risk import calculate_risk, drawdown_curve


@pytest.fixture
def portfolio_db():
    path = Path(__file__).resolve().parents[1] / "data" / f"_test_{uuid4().hex}.db"
    try:
        with transaction(path) as connection:
            create_schema(connection)
            connection.executemany("""
                INSERT INTO prices(date,ticker,open,high,low,close,volume,source)
                VALUES (?,?,?,?,?,?,?,?)
            """, [
                ("2024-01-01", "TCS", 100, 100, 100, 100, 1000, "supplied_synthetic"),
                ("2024-01-02", "TCS", 120, 120, 120, 120, 1000, "supplied_synthetic"),
            ])
        yield path
    finally:
        path.unlink(missing_ok=True)


def test_weighted_cost_realised_and_unrealised_pnl(portfolio_db: Path) -> None:
    place_order(1, "TCS", "BUY", 10, price=100, db_path=portfolio_db)
    place_order(1, "TCS", "SELL", 4, price=120, db_path=portfolio_db)
    state = portfolio_state(1, portfolio_db)
    holding = state["holdings"].iloc[0]
    assert state["cash"] == pytest.approx(999_440)
    assert holding["qty"] == 6
    assert holding["avg_cost"] == pytest.approx(102)
    assert state["realised_pnl"] == pytest.approx(52)
    assert state["unrealised_pnl"] == pytest.approx(108)
    assert state["total_pnl"] == pytest.approx(160)
    assert holding["weight"] == pytest.approx(720 / 1_000_160)


def test_order_guards_preserve_cash_and_holdings(portfolio_db: Path) -> None:
    with pytest.raises(ValueError, match="Insufficient virtual cash"):
        place_order(1, "TCS", "BUY", 100_000, db_path=portfolio_db)
    with pytest.raises(ValueError, match="Insufficient shares"):
        place_order(1, "TCS", "SELL", 1, db_path=portfolio_db)
    with pytest.raises(ValueError, match="positive whole number"):
        place_order(1, "TCS", "BUY", 0, db_path=portfolio_db)
    state = portfolio_state(1, portfolio_db)
    assert state["cash"] == 1_000_000
    assert state["holdings"].empty


def test_order_defaults_to_latest_stored_close(portfolio_db: Path) -> None:
    order = place_order(1, "TCS", "BUY", 1, db_path=portfolio_db)
    state = portfolio_state(1, portfolio_db)
    assert order["price"] == 120
    assert order["fees"] == 20
    assert state["cash"] == pytest.approx(1_000_000 - 120 - 20)


def test_risk_beta_drawdown_and_insufficient_history() -> None:
    benchmark = pd.Series(np.tile([0.01, -0.005, 0.002], 100))
    asset = benchmark * 2
    result = calculate_risk(asset, benchmark)
    assert result["sufficient_history"]
    assert result["beta"] == pytest.approx(2)
    assert result["volatility"] > 0
    assert result["var_95"] == pytest.approx(0.01)
    assert calculate_risk(asset.iloc[:63], benchmark.iloc[:63])["sharpe"] is None
    curve = drawdown_curve(pd.Series([0.1, -0.2]))
    assert curve.iloc[-1] == pytest.approx(-0.2)
