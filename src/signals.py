"""Technical signals and next-open virtual backtesting."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DB_PATH, STOCKS
from .db import price_history, transaction
from .portfolio import brokerage_fee
from .risk import calculate_risk, drawdown_curve

LOG = logging.getLogger(__name__)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder-smoothed relative strength index, using only current and past closes."""
    changes = close.diff()
    gains = changes.clip(lower=0)
    losses = -changes.clip(upper=0)
    avg_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    relative = avg_gain / avg_loss.replace(0, np.nan)
    output = 100 - 100 / (1 + relative)
    output = output.mask((avg_loss == 0) & (avg_gain > 0), 100)
    output = output.mask((avg_loss == 0) & (avg_gain == 0), 50)
    return output


def generate_signals(prices: pd.DataFrame) -> pd.DataFrame:
    """Mark SMA 20/50 crosses and RSI 14 oversold/overbought conditions at close."""
    frame = prices.sort_values("date").copy().reset_index(drop=True)
    if frame.empty:
        return frame
    frame["sma20"] = frame["close"].rolling(20, min_periods=20).mean()
    frame["sma50"] = frame["close"].rolling(50, min_periods=50).mean()
    frame["rsi14"] = rsi(frame["close"])
    bullish = frame["sma20"] > frame["sma50"]
    previous = bullish.shift(1, fill_value=False)
    ready = frame["sma50"].notna()
    frame["sma_signal"] = np.select(
        [ready & bullish & ~previous, ready & ~bullish & previous], ["BUY", "SELL"], default="HOLD"
    )
    frame["rsi_signal"] = np.select(
        [frame["rsi14"] < 30, frame["rsi14"] > 70], ["BUY", "SELL"], default="HOLD"
    )
    return frame


def _buy_capacity(cash: float, price: float) -> int:
    """Find the largest whole-share order affordable after brokerage."""
    qty = max(0, int(cash // price))
    while qty and qty * price + brokerage_fee(qty, price) > cash + 1e-9:
        qty -= 1
    return qty


def backtest_signals(
    prices: pd.DataFrame, signal_column: str = "sma_signal", initial_cash: float = 100_000.0,
) -> dict:
    """Execute yesterday's close signal at today's open; stay long or in cash."""
    if signal_column not in prices:
        raise ValueError(f"Missing signal column: {signal_column}")
    frame = prices.sort_values("date").reset_index(drop=True)
    required = {"date", "open", "close"}
    if not required.issubset(frame):
        raise ValueError("Backtest requires date, open and close")
    if frame.empty or initial_cash <= 0:
        raise ValueError("Backtest requires prices and positive starting cash")
    cash, shares, entry_cost = float(initial_cash), 0, 0.0
    trades: list[dict] = []
    wins = exits = 0
    curve = []
    for index, row in frame.iterrows():
        prior_signal = frame.iloc[index - 1][signal_column] if index else "HOLD"
        open_price = float(row["open"])
        if prior_signal == "BUY" and shares == 0:
            qty = _buy_capacity(cash, open_price)
            if qty:
                fee = brokerage_fee(qty, open_price)
                cash -= qty * open_price + fee
                shares = qty
                entry_cost = qty * open_price + fee
                trades.append({"date": row["date"], "side": "BUY", "qty": qty,
                               "price": open_price, "fees": fee, "realised_pnl": None})
        elif prior_signal == "SELL" and shares:
            fee = brokerage_fee(shares, open_price)
            proceeds = shares * open_price - fee
            pnl = proceeds - entry_cost
            cash += proceeds
            trades.append({"date": row["date"], "side": "SELL", "qty": shares,
                           "price": open_price, "fees": fee, "realised_pnl": pnl})
            wins += int(pnl > 0)
            exits += 1
            shares, entry_cost = 0, 0.0
        curve.append({"date": row["date"], "strategy": cash + shares * float(row["close"])})
    equity = pd.DataFrame(curve)
    first_open = float(frame.iloc[0]["open"])
    hold_shares = _buy_capacity(initial_cash, first_open)
    hold_cash = initial_cash - hold_shares * first_open - (brokerage_fee(hold_shares, first_open) if hold_shares else 0)
    equity["buy_hold"] = hold_cash + hold_shares * frame["close"].to_numpy(dtype=float)
    strategy_returns = equity["strategy"].pct_change(fill_method=None).dropna()
    risk = calculate_risk(strategy_returns)
    return {
        "equity": equity, "trades": pd.DataFrame(trades),
        "strategy_return": float(equity["strategy"].iloc[-1] / initial_cash - 1),
        "buy_hold_return": float(equity["buy_hold"].iloc[-1] / initial_cash - 1),
        "sharpe": risk["sharpe"],
        "max_drawdown": float(drawdown_curve(strategy_returns).min()) if not strategy_returns.empty else 0.0,
        "win_rate": wins / exits if exits else None,
        "completed_trades": exits,
    }


def persist_signals(db_path: Path | str = DB_PATH) -> int:
    """Save all available technical signals without changing portfolio orders."""
    prices = price_history(path=db_path)
    if prices.empty:
        return 0
    records = []
    for ticker, group in prices.loc[prices["ticker"] != "^NSEI"].groupby("ticker"):
        generated = generate_signals(group)
        for row in generated.itertuples(index=False):
            for strategy, signal in (("SMA20_50", row.sma_signal), ("RSI14", row.rsi_signal)):
                records.append((row.date.strftime("%Y-%m-%d"), ticker, strategy, signal))
    with transaction(db_path) as connection:
        connection.execute("DELETE FROM signals")
        connection.executemany("""
            INSERT INTO signals(date,ticker,strategy,signal) VALUES (?,?,?,?)
            ON CONFLICT(date,ticker,strategy) DO UPDATE SET signal = excluded.signal
        """, records)
    LOG.info("Saved %s signals", len(records))
    return len(records)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(f"Saved {persist_signals()} signals")
