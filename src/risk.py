"""Historical risk measures for virtual portfolios and benchmark comparisons."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import DB_PATH, RISK_FREE_RATE, TRADING_DAYS
from .db import price_history
from .portfolio import portfolio_state


def drawdown_curve(returns: pd.Series) -> pd.Series:
    """Return drawdown from the prior compounded-wealth peak."""
    wealth = (1 + returns.dropna()).cumprod()
    return wealth / wealth.cummax() - 1


def calculate_risk(
    returns: pd.Series, benchmark: pd.Series | None = None, *,
    min_observations: int = 252, risk_free_rate: float = RISK_FREE_RATE,
) -> dict:
    """Calculate sample risk statistics only when the history is adequate."""
    series = pd.to_numeric(returns, errors="coerce").dropna()
    result = {"observations": len(series), "sufficient_history": len(series) >= min_observations,
              "volatility": None, "sharpe": None, "beta": None, "max_drawdown": None,
              "var_95": None}
    if len(series) >= 20:
        result["max_drawdown"] = float(drawdown_curve(series).min())
        result["var_95"] = max(0.0, -float(series.quantile(0.05)))
    if len(series) < min_observations:
        return result
    std = float(series.std(ddof=1))
    result["volatility"] = std * np.sqrt(TRADING_DAYS)
    result["sharpe"] = ((float(series.mean()) - risk_free_rate / TRADING_DAYS)
                        / std * np.sqrt(TRADING_DAYS)) if std > 0 else None
    if benchmark is not None:
        paired = pd.concat([series.rename("asset"), benchmark.rename("benchmark")], axis=1).dropna()
        if len(paired) >= min_observations:
            variance = float(paired["benchmark"].var(ddof=1))
            result["beta"] = (float(paired["asset"].cov(paired["benchmark"])) / variance
                              if variance > 0 else None)
    return result


def close_and_returns(db_path: Path | str = DB_PATH) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create aligned close and daily-return matrices."""
    prices = price_history(path=db_path)
    if prices.empty:
        return pd.DataFrame(), pd.DataFrame()
    close = prices.pivot(index="date", columns="ticker", values="close").sort_index()
    returns = close.pct_change(fill_method=None)
    return close, returns


def portfolio_returns(portfolio_id: int = 1, db_path: Path | str = DB_PATH) -> pd.Series:
    """Compute close-to-close returns of today's holdings plus fixed cash."""
    state = portfolio_state(portfolio_id, db_path)
    close, _ = close_and_returns(db_path)
    holdings = state["holdings"]
    if close.empty or holdings.empty:
        return pd.Series(dtype=float, name="portfolio")
    shares = holdings.set_index("ticker")["qty"]
    available = [ticker for ticker in shares.index if ticker in close]
    values = close[available].ffill().mul(shares[available], axis=1).sum(axis=1) + state["cash"]
    return values.pct_change(fill_method=None).dropna().rename("portfolio")


def correlation_matrix(returns: pd.DataFrame) -> pd.DataFrame:
    """Pairwise Pearson correlations of daily returns."""
    return returns.corr(min_periods=30)
