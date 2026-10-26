"""SQLite schema and parameterised database access."""

from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Iterator

import pandas as pd

from .config import DB_PATH, INITIAL_CASH, STOCKS


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys enabled."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


@contextmanager
def transaction(path: Path | str = DB_PATH) -> Iterator[sqlite3.Connection]:
    """Commit or roll back a unit of work."""
    connection = connect(path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def create_schema(connection: sqlite3.Connection) -> None:
    """Create durable virtual portfolio tables and indexes."""
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS stocks (
            ticker TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            sector TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS prices (
            date TEXT NOT NULL,
            ticker TEXT NOT NULL REFERENCES stocks(ticker),
            open REAL NOT NULL CHECK (open > 0),
            high REAL NOT NULL CHECK (high >= open AND high >= close AND high >= low),
            low REAL NOT NULL CHECK (low > 0 AND low <= open AND low <= close),
            close REAL NOT NULL CHECK (close > 0),
            volume INTEGER NOT NULL CHECK (volume >= 0),
            daily_return_pct REAL,
            source TEXT NOT NULL CHECK (source IN ('supplied_synthetic', 'yfinance')),
            PRIMARY KEY (date, ticker)
        );
        CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON prices(ticker, date);
        CREATE TABLE IF NOT EXISTS portfolio (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            cash REAL NOT NULL CHECK (cash >= 0),
            initial_cash REAL NOT NULL CHECK (initial_cash > 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY,
            portfolio_id INTEGER NOT NULL REFERENCES portfolio(id),
            date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ticker TEXT NOT NULL REFERENCES stocks(ticker),
            side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
            qty INTEGER NOT NULL CHECK (qty > 0),
            price REAL NOT NULL CHECK (price > 0),
            fees REAL NOT NULL CHECK (fees >= 0)
        );
        CREATE INDEX IF NOT EXISTS idx_transactions_portfolio_date
            ON transactions(portfolio_id, date);
        CREATE TABLE IF NOT EXISTS signals (
            date TEXT NOT NULL,
            ticker TEXT NOT NULL REFERENCES stocks(ticker),
            strategy TEXT NOT NULL,
            signal TEXT NOT NULL CHECK (signal IN ('BUY', 'SELL', 'HOLD')),
            PRIMARY KEY (date, ticker, strategy)
        );
        CREATE VIEW IF NOT EXISTS holdings AS
        SELECT portfolio_id, ticker,
            SUM(CASE WHEN side = 'BUY' THEN qty ELSE -qty END) AS qty
        FROM transactions GROUP BY portfolio_id, ticker
        HAVING SUM(CASE WHEN side = 'BUY' THEN qty ELSE -qty END) > 0;
    """)
    connection.executemany(
        "INSERT OR IGNORE INTO stocks(ticker, name, sector) VALUES (?, ?, ?)",
        ((ticker, *details) for ticker, details in STOCKS.items()),
    )
    connection.execute(
        "INSERT OR IGNORE INTO portfolio(id, name, cash, initial_cash) VALUES (1, ?, ?, ?)",
        ("Demo portfolio", INITIAL_CASH, INITIAL_CASH),
    )


def database_ready(path: Path | str = DB_PATH) -> bool:
    """Check whether the database has at least one price observation."""
    if not Path(path).exists():
        return False
    try:
        with closing(connect(path)) as connection:
            row = connection.execute("SELECT EXISTS(SELECT 1 FROM prices) AS ready").fetchone()
            return bool(row["ready"])
    except sqlite3.Error:
        return False


def price_history(ticker: str | None = None, path: Path | str = DB_PATH) -> pd.DataFrame:
    """Return dated OHLCV observations sorted in ascending order."""
    with closing(connect(path)) as connection:
        if ticker is None:
            frame = pd.read_sql_query("SELECT * FROM prices ORDER BY date, ticker", connection)
        else:
            frame = pd.read_sql_query(
                "SELECT * FROM prices WHERE ticker = ? ORDER BY date", connection, params=(ticker,)
            )
    if not frame.empty:
        frame["date"] = pd.to_datetime(frame["date"])
    return frame


def latest_prices(path: Path | str = DB_PATH) -> pd.DataFrame:
    """Read the latest available close and its previous close for each ticker."""
    with closing(connect(path)) as connection:
        frame = pd.read_sql_query("""
            SELECT ticker, date, close, source,
                   LAG(close) OVER (PARTITION BY ticker ORDER BY date) AS previous_close,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS newest
            FROM prices
        """, connection)
    return frame.loc[frame["newest"] == 1].drop(columns="newest")
