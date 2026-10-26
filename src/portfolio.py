"""Virtual orders, holdings, cost basis and portfolio valuation."""

from __future__ import annotations

import sqlite3
import math
from contextlib import closing
from datetime import date
from pathlib import Path

import pandas as pd

from .config import DB_PATH, STOCKS
from .db import connect, latest_prices, price_history

FEE_RATE = 0.001
MIN_FEE = 20.0


def brokerage_fee(qty: int, price: float) -> float:
    """Charge 0.1% of notional, with a ₹20 minimum per order."""
    return round(max(MIN_FEE, qty * price * FEE_RATE), 2)


def _ledger(rows: list[sqlite3.Row]) -> tuple[pd.DataFrame, float]:
    """Apply transactions in order using a moving weighted average cost basis."""
    positions: dict[str, dict[str, float]] = {}
    realised_total = 0.0
    for row in rows:
        ticker = row["ticker"]
        position = positions.setdefault(ticker, {"qty": 0, "cost": 0.0, "realised_pnl": 0.0})
        qty, gross, fees = int(row["qty"]), float(row["qty"] * row["price"]), float(row["fees"])
        if row["side"] == "BUY":
            position["qty"] += qty
            position["cost"] += gross + fees
        else:
            if qty > position["qty"]:
                raise ValueError(f"Transaction ledger has an uncovered sell for {ticker}")
            avg = position["cost"] / position["qty"]
            pnl = gross - fees - qty * avg
            position["qty"] -= qty
            position["cost"] -= qty * avg
            if position["qty"] == 0:
                position["cost"] = 0.0
            position["realised_pnl"] += pnl
            realised_total += pnl
    records = [
        {"ticker": ticker, "qty": int(p["qty"]), "avg_cost": p["cost"] / p["qty"],
         "cost_basis": p["cost"], "realised_pnl": p["realised_pnl"]}
        for ticker, p in positions.items() if p["qty"] > 0
    ]
    return pd.DataFrame(records, columns=["ticker", "qty", "avg_cost", "cost_basis", "realised_pnl"]), realised_total


def _transaction_rows(connection: sqlite3.Connection, portfolio_id: int) -> list[sqlite3.Row]:
    return connection.execute("""
        SELECT * FROM transactions WHERE portfolio_id = ? ORDER BY date, id
    """, (portfolio_id,)).fetchall()


def place_order(
    portfolio_id: int, ticker: str, side: str, qty: int, *,
    price: float | None = None, db_path: Path | str = DB_PATH,
) -> dict:
    """Execute one validated virtual trade atomically at the latest close by default."""
    ticker = ticker.upper().strip()
    side = side.upper().strip()
    if ticker not in STOCKS or ticker == "^NSEI":
        raise ValueError("Select a supported tradable NSE ticker")
    if side not in {"BUY", "SELL"}:
        raise ValueError("Side must be BUY or SELL")
    if not isinstance(qty, int) or isinstance(qty, bool) or qty <= 0:
        raise ValueError("Quantity must be a positive whole number")
    connection = connect(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        portfolio = connection.execute("SELECT cash FROM portfolio WHERE id = ?", (portfolio_id,)).fetchone()
        if portfolio is None:
            raise ValueError("Portfolio does not exist")
        if price is None:
            quote = connection.execute(
                "SELECT close FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 1", (ticker,)
            ).fetchone()
            if quote is None:
                raise ValueError("No price available for this ticker")
            price = float(quote["close"])
        if not math.isfinite(price) or price <= 0:
            raise ValueError("Price must be positive")
        fee = brokerage_fee(qty, price)
        gross = qty * price
        if side == "BUY":
            cash_delta = -(gross + fee)
            if float(portfolio["cash"]) + cash_delta < -1e-8:
                raise ValueError("Insufficient virtual cash")
        else:
            holdings, _ = _ledger(_transaction_rows(connection, portfolio_id))
            owned = int(holdings.loc[holdings["ticker"] == ticker, "qty"].sum()) if not holdings.empty else 0
            if qty > owned:
                raise ValueError(f"Insufficient shares: own {owned}")
            cash_delta = gross - fee
            if float(portfolio["cash"]) + cash_delta < -1e-8:
                raise ValueError("Insufficient virtual cash to cover brokerage")
        cursor = connection.execute("""
            INSERT INTO transactions(portfolio_id,ticker,side,qty,price,fees)
            VALUES (?,?,?,?,?,?)
        """, (portfolio_id, ticker, side, qty, price, fee))
        connection.execute("UPDATE portfolio SET cash = cash + ? WHERE id = ?", (cash_delta, portfolio_id))
        connection.commit()
        return {"id": cursor.lastrowid, "ticker": ticker, "side": side, "qty": qty,
                "price": price, "fees": fee, "cash_delta": cash_delta}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def transactions(portfolio_id: int = 1, db_path: Path | str = DB_PATH) -> pd.DataFrame:
    """List a portfolio's trades for display or CSV export."""
    with closing(connect(db_path)) as connection:
        return pd.read_sql_query("""
            SELECT date,ticker,side,qty,price,fees FROM transactions
            WHERE portfolio_id = ? ORDER BY date DESC, id DESC
        """, connection, params=(portfolio_id,))


def portfolio_state(portfolio_id: int = 1, db_path: Path | str = DB_PATH) -> dict:
    """Value cash and current positions using each ticker's latest close."""
    with closing(connect(db_path)) as connection:
        portfolio = connection.execute(
            "SELECT id,name,cash,initial_cash FROM portfolio WHERE id = ?", (portfolio_id,)
        ).fetchone()
        if portfolio is None:
            raise ValueError("Portfolio does not exist")
        holdings, realised = _ledger(_transaction_rows(connection, portfolio_id))
    quotes = latest_prices(db_path)
    if not holdings.empty:
        holdings = holdings.merge(quotes, on="ticker", how="left")
        holdings["market_value"] = holdings["qty"] * holdings["close"]
        holdings["unrealised_pnl"] = holdings["market_value"] - holdings["cost_basis"]
        holdings["pnl_pct"] = 100 * holdings["unrealised_pnl"] / holdings["cost_basis"]
        holdings["day_pnl"] = holdings["qty"] * (holdings["close"] - holdings["previous_close"])
        holdings["day_pnl"] = holdings["day_pnl"].fillna(0)
    market_value = float(holdings["market_value"].sum()) if not holdings.empty else 0.0
    cash = float(portfolio["cash"])
    total = cash + market_value
    if not holdings.empty:
        holdings["weight"] = holdings["market_value"] / total if total else 0.0
    initial = float(portfolio["initial_cash"])
    return {"id": portfolio_id, "name": portfolio["name"], "cash": cash,
            "initial_cash": initial, "total_value": total, "total_pnl": total - initial,
            "day_pnl": float(holdings["day_pnl"].sum()) if not holdings.empty else 0.0,
            "realised_pnl": realised,
            "unrealised_pnl": float(holdings["unrealised_pnl"].sum()) if not holdings.empty else 0.0,
            "cumulative_return_pct": 100 * (total / initial - 1), "holdings": holdings}


def valuation_history(portfolio_id: int = 1, db_path: Path | str = DB_PATH) -> pd.DataFrame:
    """Revalue actual holdings and cash on each available price date."""
    prices = price_history(path=db_path)
    if prices.empty:
        return pd.DataFrame(columns=["date", "value", "cumulative_return_pct"])
    with closing(connect(db_path)) as connection:
        initial = float(connection.execute(
            "SELECT initial_cash FROM portfolio WHERE id = ?", (portfolio_id,)
        ).fetchone()["initial_cash"])
        ledger = pd.read_sql_query("""
            SELECT date,ticker,side,qty,price,fees FROM transactions
            WHERE portfolio_id = ? ORDER BY date,id
        """, connection, params=(portfolio_id,))
    close = prices.pivot(index="date", columns="ticker", values="close").sort_index().ffill()
    tickers = [ticker for ticker in close if ticker != "^NSEI"]
    cash, qty = initial, {ticker: 0 for ticker in tickers}
    events = ledger.to_dict("records")
    index = 0
    dates = list(close.index)
    today = pd.Timestamp(date.today())
    if events and today > dates[-1]:
        dates.append(today)
    values = []
    for day in dates:
        while index < len(events) and pd.Timestamp(events[index]["date"]).normalize() <= day:
            event = events[index]
            signed = 1 if event["side"] == "BUY" else -1
            qty[event["ticker"]] += signed * int(event["qty"])
            cash -= signed * int(event["qty"]) * float(event["price"]) + float(event["fees"])
            index += 1
        quoted = close.loc[day] if day in close.index else close.iloc[-1]
        value = cash + sum(qty[ticker] * float(quoted[ticker]) for ticker in tickers if pd.notna(quoted[ticker]))
        values.append({"date": day, "value": value,
                       "cumulative_return_pct": 100 * (value / initial - 1)})
    return pd.DataFrame(values)
