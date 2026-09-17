"""Wilder's Average True Range, computed the same way topbot's RSI is (an
ewm with alpha = 1/length), so it warms up and smooths consistently with the
RSI series it's paired with."""

from __future__ import annotations

import pandas as pd


def wilder_atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int) -> pd.Series:
    """Classic Wilder ATR. First `length` values are NaN (warm-up)."""
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    return true_range.ewm(alpha=1.0 / length, min_periods=length, adjust=False).mean()


def latest_atr(df: pd.DataFrame, length: int) -> float | None:
    """Most recent non-NaN ATR value in `df`, or None if not enough data."""
    if df.empty:
        return None

    atr = wilder_atr(df["high"], df["low"], df["close"], length)
    atr = atr.dropna()
    if atr.empty:
        return None
    return float(atr.iat[-1])
