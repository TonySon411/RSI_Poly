"""Backtest engine that replays REAL recorded Polymarket order-book prices
(tick_recorder's JSON files) to simulate actual ladder fills, instead of
guessing win/loss from Bybit candle direction alone (see rsi_backtest for
that simpler version). This is a much closer match to what the live
Templates actually experience -- but coverage is inherently limited to
whatever the tick recorder has captured so far, which is surfaced
explicitly (`no_recording`, `pending`) rather than silently ignored.
"""

from __future__ import annotations

import pandas as pd

from rsi_backtest.rsi import wilder_rsi
from tick_recorder.store import list_market_files, load, market_json_path

# topbot's default 5-rung paper ladder -- the same one every live Template trades.
LADDER = [
    (0.50, 5),
    (0.40, 5),
    (0.30, 10),
    (0.20, 15),
    (0.10, 20),
]


def _simulate_fill(snapshots: list[dict]) -> tuple[float, float]:
    """Replay recorded best_ask snapshots in time order; a rung fills (once,
    permanently) the first time ask <= its limit price -- the same rule as
    topbot's PaperExecutor.poll_fills."""
    filled = [False] * len(LADDER)
    for snap in snapshots:
        ask = snap.get("best_ask")
        if ask is None:
            continue
        for i, (price, _size) in enumerate(LADDER):
            if not filled[i] and ask <= price:
                filled[i] = True
    filled_shares = sum(size for (_price, size), f in zip(LADDER, filled) if f)
    cost = sum(price * size for (price, size), f in zip(LADDER, filled) if f)
    return filled_shares, cost


def run_live_backtest(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
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
    n = len(df)

    trades: list[dict] = []
    no_recording = 0
    pending = 0

    for i in range(n):
        ts_i = df["ts"].iat[i]
        if ts_i < start_ms or ts_i > end_ms:
            continue

        r = rsi.iat[i]
        if pd.isna(r):
            continue

        if r > overbought:
            side = "Down"
        elif r < oversold:
            side = "Up"
        else:
            continue

        if i + 1 >= n:
            continue  # trailing signal, no next window at all

        next_ts = df["ts"].iat[i + 1]
        window_start = int(next_ts // 1000)
        slug = f"{symbol.lower()}-updown-{timeframe}-{window_start}"
        record = load(market_json_path(symbol, timeframe, slug))

        if record is None:
            no_recording += 1
            continue

        token_id = record["up_token_id"] if side == "Up" else record["down_token_id"]
        snaps = record["snapshots"].get(token_id, [])
        filled_shares, cost = _simulate_fill(snaps)

        resolution = record.get("resolution")
        if resolution is None:
            pending += 1
            continue

        won = side == resolution
        payout = filled_shares * 1.0 if won else 0.0
        pnl = payout - cost

        trades.append(
            {
                "ts": int(ts_i),
                "window_start": window_start,
                "rsi": round(float(r), 2),
                "side": side,
                "filled_shares": round(filled_shares, 4),
                "cost": round(cost, 4),
                "resolution": resolution,
                "won": bool(won),
                "pnl": round(pnl, 4),
            }
        )

    wins = sum(1 for t in trades if t["won"])
    losses = len(trades) - wins
    decided = wins + losses
    win_rate = (wins / decided * 100.0) if decided else 0.0
    pnl_sum = sum(t["pnl"] for t in trades)

    return {
        "win_rate": round(win_rate, 2),
        "decided": decided,
        "wins": wins,
        "losses": losses,
        "pending": pending,
        "no_recording": no_recording,
        "pnl_sum": round(pnl_sum, 2),
        "trades": trades,
    }


def _empty_summary() -> dict:
    return {
        "win_rate": 0.0,
        "decided": 0,
        "wins": 0,
        "losses": 0,
        "pending": 0,
        "no_recording": 0,
        "pnl_sum": 0.0,
        "trades": [],
    }


def recording_coverage(symbol: str, timeframe: str) -> dict:
    """How much recorded tick data actually exists for this symbol/timeframe,
    for the dashboard's "coverage" display."""
    files = list_market_files(symbol, timeframe)
    if not files:
        return {"count": 0, "range_from": None, "range_to": None, "resolved_count": 0}

    min_start = None
    max_end = None
    resolved_count = 0
    for path in files:
        record = load(path)
        if record is None:
            continue
        start_ts, end_ts = record.get("start_ts"), record.get("end_ts")
        if start_ts is not None:
            min_start = start_ts if min_start is None else min(min_start, start_ts)
        if end_ts is not None:
            max_end = end_ts if max_end is None else max(max_end, end_ts)
        if record.get("resolution") is not None:
            resolved_count += 1

    return {
        "count": len(files),
        "range_from": min_start,
        "range_to": max_end,
        "resolved_count": resolved_count,
    }
