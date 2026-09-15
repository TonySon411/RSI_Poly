"""Wilder's RSI, matching the calculation topbot uses live."""

from __future__ import annotations

import pandas as pd


def wilder_rsi(closes: pd.Series, length: int) -> pd.Series:
    """Classic Wilder RSI. First `length` values are NaN (warm-up)."""
    delta = closes.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1.0 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / length, min_periods=length, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    rsi[avg_loss == 0] = 100.0
    rsi[(avg_gain == 0) & (avg_loss == 0)] = 50.0
    return rsi
