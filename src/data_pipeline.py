"""Clean supplied synthetic OHLCV data and optionally cache real market history."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .config import CLEANED_CSV, DATA_DIR, DB_PATH, MARKET_CACHE, ORIGINAL_CSV, QUALITY_REPORT, STOCKS
from .db import create_schema, transaction

LOG = logging.getLogger(__name__)
PRICE_COLUMNS = ["date", "ticker", "open", "high", "low", "close", "volume", "daily_return_pct"]


def clean_prices(frame: pd.DataFrame, source: str = "supplied_synthetic") -> tuple[pd.DataFrame, dict]:
    """Validate prices, repair candle bounds, and recalculate close-to-close returns."""
    missing = set(PRICE_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
    cleaned = frame[PRICE_COLUMNS].copy()
    original_count = len(cleaned)
    cleaned["date"] = pd.to_datetime(cleaned["date"], errors="coerce").dt.normalize()
    cleaned["ticker"] = cleaned["ticker"].astype("string").str.strip().str.upper()
    numeric = ["open", "high", "low", "close", "volume", "daily_return_pct"]
    for column in numeric:
        cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")
    required = ["date", "ticker", "open", "high", "low", "close", "volume"]
    invalid = cleaned[required].isna().any(axis=1)
    invalid |= (cleaned[["open", "high", "low", "close"]] <= 0).any(axis=1)
    invalid |= cleaned["volume"] < 0
    invalid |= cleaned["volume"] % 1 != 0
    invalid |= ~cleaned["ticker"].isin(STOCKS)
    dropped_invalid = int(invalid.sum())
    cleaned = cleaned.loc[~invalid].copy()
    duplicates = int(cleaned.duplicated(["date", "ticker"]).sum())
    cleaned = cleaned.drop_duplicates(["date", "ticker"], keep="last")
    bad_high = int((cleaned["high"] < cleaned[["open", "close"]].max(axis=1)).sum())
    bad_low = int((cleaned["low"] > cleaned[["open", "close"]].min(axis=1)).sum())
    cleaned["high"] = cleaned[["high", "open", "close"]].max(axis=1)
    cleaned["low"] = cleaned[["low", "open", "close"]].min(axis=1)
    cleaned = cleaned.sort_values(["ticker", "date"]).reset_index(drop=True)
    cleaned["daily_return_pct"] = cleaned.groupby("ticker")["close"].pct_change(fill_method=None) * 100
    cleaned["volume"] = cleaned["volume"].astype("int64")
    weekend_rows = int((cleaned["date"].dt.dayofweek >= 5).sum())
    cleaned["date"] = cleaned["date"].dt.strftime("%Y-%m-%d")
    cleaned["source"] = source
    report = {
        "source": source,
        "input_rows": original_count,
        "output_rows": len(cleaned),
        "invalid_rows_dropped": dropped_invalid,
        "duplicate_keys_dropped": duplicates,
        "high_bounds_fixed": bad_high,
        "low_bounds_fixed": bad_low,
        "weekend_rows": weekend_rows,
        "first_return_unavailable_per_ticker": True,
        "notes": (
            "Supplied rows are synthetic and include calendar weekends. OHLC bounds were repaired; "
            "close-to-close returns were recalculated."
            if source == "supplied_synthetic" else
            "Downloaded market candles were validated and close-to-close returns were recalculated. "
            "Any weekend rows are retained as published by the provider."
        ),
    }
    return cleaned, report


def _normalise_yfinance(frame: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Flatten a single yfinance download into the project schema."""
    if frame.empty:
        return pd.DataFrame(columns=PRICE_COLUMNS)
    result = frame.copy()
    if isinstance(result.columns, pd.MultiIndex):
        result.columns = result.columns.get_level_values(0)
    result = result.reset_index()
    result.columns = [str(column).lower().replace(" ", "_") for column in result.columns]
    result = result.rename(columns={"datetime": "date"})
    result["ticker"] = ticker
    result["daily_return_pct"] = np.nan
    return result[PRICE_COLUMNS]


def download_market_history(years: int = 5) -> pd.DataFrame:
    """Download NSE stocks and NIFTY 50; return an empty frame on failure."""
    local_deps = Path(__file__).resolve().parents[1] / ".deps"
    if local_deps.exists() and str(local_deps) not in sys.path:
        sys.path.append(str(local_deps))
    try:
        import yfinance as yf
    except ImportError:
        LOG.warning("yfinance is unavailable; using the supplied dataset")
        return pd.DataFrame(columns=PRICE_COLUMNS)
    start = (pd.Timestamp(date.today()) - pd.DateOffset(years=years)).date()
    end = date.today() + timedelta(days=1)
    pieces = []
    for ticker in STOCKS:
        symbol = ticker if ticker == "^NSEI" else f"{ticker}.NS"
        try:
            raw = yf.download(symbol, start=start.isoformat(), end=end.isoformat(),
                              auto_adjust=False, progress=False, threads=False, timeout=12)
            piece = _normalise_yfinance(raw, ticker)
            if not piece.empty:
                pieces.append(piece)
        except Exception as exc:
            LOG.warning("Download failed for %s: %s", symbol, exc)
    if not pieces:
        return pd.DataFrame(columns=PRICE_COLUMNS)
    return pd.concat(pieces, ignore_index=True)


def _read_cache(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=PRICE_COLUMNS)
    try:
        return pd.read_csv(path)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        LOG.warning("Could not read market cache: %s", exc)
        return pd.DataFrame(columns=PRICE_COLUMNS)


def _market_complete(frame: pd.DataFrame) -> bool:
    """Require sufficient stock and benchmark history before activating a cache."""
    if frame.empty or "ticker" not in frame:
        return False
    counts = frame.loc[frame["ticker"] != "^NSEI"].groupby("ticker").size()
    expected = set(STOCKS) - {"^NSEI"}
    return set(counts.index) == expected and counts.min() >= 252 and (frame["ticker"] == "^NSEI").sum() >= 252


def run_pipeline(*, download: bool = True, db_path: Path = DB_PATH) -> dict:
    """Produce cleaned CSV and load one provenance-consistent price series into SQLite."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    original = pd.read_csv(ORIGINAL_CSV)
    supplied, report = clean_prices(original)
    supplied.drop(columns="source").to_csv(CLEANED_CSV, index=False)
    market_raw = _read_cache(MARKET_CACHE)
    if download and not _market_complete(market_raw):
        downloaded = download_market_history()
        if _market_complete(downloaded):
            market_raw = downloaded
            market_raw.to_csv(MARKET_CACHE, index=False)
        elif not downloaded.empty:
            LOG.warning("Market download was incomplete; retaining the previous cache or supplied dataset")
    if not market_raw.empty:
        market, market_report = clean_prices(market_raw, source="yfinance")
    else:
        market, market_report = supplied.iloc[0:0].copy(), None
    use_market = _market_complete(market)
    active = market if use_market else supplied
    report["active_source"] = "yfinance" if use_market else "supplied_synthetic"
    report["active_rows"] = len(active)
    report["market_download_rows"] = len(market)
    report["market_quality"] = market_report
    if not use_market:
        report["risk_limitation"] = "Only 63 calendar days of synthetic observations; annualised risk and ML results are unavailable."
    QUALITY_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    records = []
    for row in active.itertuples(index=False):
        return_pct = None if pd.isna(row.daily_return_pct) else float(row.daily_return_pct)
        records.append((row.date, row.ticker, float(row.open), float(row.high), float(row.low),
                        float(row.close), int(row.volume), return_pct, row.source))
    with transaction(db_path) as connection:
        create_schema(connection)
        connection.execute("DELETE FROM prices")
        connection.executemany("""
            INSERT INTO prices(date,ticker,open,high,low,close,volume,daily_return_pct,source)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, records)
    LOG.info("Loaded %s %s prices", len(active), report["active_source"])
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean and load virtual market data")
    parser.add_argument("--no-download", action="store_true", help="Use cache or supplied CSV")
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(json.dumps(run_pipeline(download=not arguments.no_download), indent=2))
