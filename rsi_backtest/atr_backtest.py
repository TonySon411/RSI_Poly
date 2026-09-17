"""Backtest engine for the topbot RSI strategy where the overbought/oversold
thresholds are not fixed but chosen per-candle from that candle's own ATR,
via the bucket table in config.json (see thresholds.py).

Otherwise identical to backtest.run_backtest: each closed candle is an
independent decision (no retry / no attempt ladder), and a window "resolves
Down" if its close is below its open, "Up" otherwise.
"""

from __future__ import annotations

import pandas as pd

from .atr import wilder_atr
from .rsi import wilder_rsi
from .thresholds import get_thresholds


def run_atr_backtest(
    df: pd.DataFrame,
    start_ms: int,
    end_ms: int,
    rsi_length: int,
    atr_length: int,
) -> dict:
    df = df.sort_values("ts").reset_index(drop=True)

    if df.empty:
        return _empty_summary()

    rsi = wilder_rsi(df["close"], rsi_length)
    atr = wilder_atr(df["high"], df["low"], df["close"], atr_length)

    trades = []
    incomplete = 0
    n = len(df)

    for i in range(n):
        ts_i = df["ts"].iat[i]
        if ts_i < start_ms or ts_i > end_ms:
            continue

        r = rsi.iat[i]
        a = atr.iat[i]
        if pd.isna(r) or pd.isna(a):
            continue

        overbought, oversold = get_thresholds(float(a))

        if overbought == 0 and oversold == 0:
            continue

        if r > overbought:
            prediction = "Down"
        elif r < oversold:
            prediction = "Up"
        else:
            continue

        if i + 1 >= n:
            incomplete += 1
            continue

        next_open = df["open"].iat[i + 1]
        next_close = df["close"].iat[i + 1]
        actual = "Up" if next_close > next_open else "Down"
        win = prediction == actual

        trades.append(
            {
                "ts": int(ts_i),
                "rsi": round(float(r), 2),
                "atr": round(float(a), 4),
                "overbought": overbought,
                "oversold": oversold,
                "prediction": prediction,
                "actual": actual,
                "win": bool(win),
            }
        )

    wins = sum(1 for t in trades if t["win"])
    losses = len(trades) - wins
    decided = wins + losses
    win_rate = (wins / decided * 100.0) if decided else 0.0

    return {
        "win_rate": round(win_rate, 2),
        "total_signals": len(trades) + incomplete,
        "decided": decided,
        "wins": wins,
        "losses": losses,
        "incomplete": incomplete,
        "trades": trades,
    }


def _empty_summary() -> dict:
    return {
        "win_rate": 0.0,
        "total_signals": 0,
        "decided": 0,
        "wins": 0,
        "losses": 0,
        "incomplete": 0,
        "trades": [],
    }
