"""Backtest engine for the topbot RSI ladder strategy.

Each closed candle is an independent decision (no retry / no attempt ladder):
  RSI > overbought  -> predict the *next* window resolves Down
  RSI < oversold    -> predict the *next* window resolves Up
  otherwise         -> no trade that window

A window "resolves Down" if its close is below its open, "Up" otherwise.
Win rate is measured over fully-decided trades, excluding a trailing signal
at the very end of the data that has no next candle to resolve against yet.
"""

from __future__ import annotations

import pandas as pd

from .rsi import wilder_rsi


def run_backtest(
    df: pd.DataFrame,
    start_ms: int,
    end_ms: int,
    rsi_length: int,
    overbought: float,
    oversold: float,
) -> dict:
    df = df.sort_values("ts").reset_index(drop=True)

    if df.empty:
        return _empty_summary()

    rsi = wilder_rsi(df["close"], rsi_length)

    trades = []
    incomplete = 0
    n = len(df)

    for i in range(n):
        ts_i = df["ts"].iat[i]
        if ts_i < start_ms or ts_i > end_ms:
            continue

        r = rsi.iat[i]
        if pd.isna(r):
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
