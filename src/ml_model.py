"""Chronological next-day direction model with leakage-safe features."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .signals import rsi

FEATURES = ["return_1d", "return_5d", "range_pct", "intraday_pct", "volume_change",
            "sma20_gap", "sma50_gap", "rsi14", "volatility_5d"]


def feature_frame(prices: pd.DataFrame) -> pd.DataFrame:
    """Create features observable at each close and a following-close label."""
    frame = prices.sort_values("date").copy().reset_index(drop=True)
    if frame.empty:
        return pd.DataFrame(columns=["date", "close", "target", "label_date", *FEATURES])
    frame["date"] = pd.to_datetime(frame["date"])
    close = frame["close"].astype(float)
    frame["return_1d"] = close.pct_change(fill_method=None)
    frame["return_5d"] = close.pct_change(5, fill_method=None)
    frame["range_pct"] = (frame["high"] - frame["low"]) / close
    frame["intraday_pct"] = (close - frame["open"]) / frame["open"]
    frame["volume_change"] = frame["volume"].pct_change(fill_method=None)
    frame["sma20_gap"] = close / close.rolling(20, min_periods=20).mean() - 1
    frame["sma50_gap"] = close / close.rolling(50, min_periods=50).mean() - 1
    frame["rsi14"] = rsi(close)
    frame["volatility_5d"] = frame["return_1d"].rolling(5, min_periods=5).std()
    frame["label_date"] = frame["date"].shift(-1)
    frame["target"] = (close.shift(-1) > close).astype(float)
    frame.loc[frame.index[-1], "target"] = np.nan
    frame[FEATURES] = frame[FEATURES].replace([np.inf, -np.inf], np.nan)
    return frame.dropna(subset=FEATURES + ["target", "label_date"]).reset_index(drop=True)


def train_direction_model(prices: pd.DataFrame, min_observations: int = 252) -> dict:
    """Train on the first 80%, leave a label gap, and evaluate on the final 20%."""
    samples = feature_frame(prices)
    if len(prices) < min_observations or len(samples) < 100:
        return {"available": False, "reason": "At least 252 dated observations are required for an honest model evaluation.",
                "observations": len(prices)}
    split = int(len(samples) * 0.8)
    testing = samples.iloc[split:]
    test_start = testing.iloc[0]["date"]
    training = samples.iloc[:split].loc[lambda frame: frame["label_date"] < test_start]
    if training["target"].nunique() < 2 or testing.empty:
        return {"available": False, "reason": "Training history has too little class variation.",
                "observations": len(prices)}
    model = Pipeline([
        ("scale", StandardScaler()),
        ("classifier", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)),
    ])
    model.fit(training[FEATURES], training["target"].astype(int))
    actual = testing["target"].astype(int)
    predicted = model.predict(testing[FEATURES])
    baseline_class = int(training["target"].mean() >= 0.5)
    results = testing[["date", "close", "target"]].copy()
    results["prediction"] = predicted
    return {
        "available": True, "train_rows": len(training), "test_rows": len(testing),
        "train_end": str(training.iloc[-1]["date"]),
        "train_label_end": str(training.iloc[-1]["label_date"]),
        "test_start": str(test_start),
        "accuracy": float(accuracy_score(actual, predicted)),
        "precision": float(precision_score(actual, predicted, zero_division=0)),
        "recall": float(recall_score(actual, predicted, zero_division=0)),
        "f1": float(f1_score(actual, predicted, zero_division=0)),
        "majority_baseline_accuracy": float(accuracy_score(actual, np.full(len(actual), baseline_class))),
        "confusion_matrix": confusion_matrix(actual, predicted, labels=[0, 1]).tolist(),
        "predictions": results,
    }
