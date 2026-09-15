"""Local CSV cache for Bybit klines, with on-demand fetch of missing ranges."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .bybit_client import fetch_klines
from .config import TIMEFRAMES

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
COLUMNS = ["ts", "open", "high", "low", "close", "volume"]


def _cache_path(symbol: str, timeframe: str) -> Path:
    return DATA_DIR / f"{symbol.upper()}_{timeframe}.csv"


def _load_cache(symbol: str, timeframe: str) -> pd.DataFrame:
    path = _cache_path(symbol, timeframe)
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path)
    return df.sort_values("ts").drop_duplicates(subset="ts").reset_index(drop=True)


def _save_cache(symbol: str, timeframe: str, df: pd.DataFrame) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.sort_values("ts").drop_duplicates(subset="ts").to_csv(_cache_path(symbol, timeframe), index=False)


def ensure_data(symbol: str, timeframe: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    """Make sure the local cache covers [start_ms, end_ms], fetching gaps from Bybit.

    Returns the full cached DataFrame (not filtered to the requested range).
    """
    bybit_interval, interval_ms = TIMEFRAMES[timeframe]
    df = _load_cache(symbol, timeframe)

    fetch_ranges: list[tuple[int, int]] = []
    if df.empty:
        fetch_ranges.append((start_ms, end_ms))
    else:
        cached_min = int(df["ts"].min())
        cached_max = int(df["ts"].max())
        if start_ms < cached_min:
            fetch_ranges.append((start_ms, cached_min - interval_ms))
        if end_ms > cached_max:
            fetch_ranges.append((cached_max + interval_ms, end_ms))

    new_rows: list[list] = []
    for r_start, r_end in fetch_ranges:
        if r_start > r_end:
            continue
        new_rows.extend(fetch_klines(symbol, bybit_interval, r_start, r_end))

    if new_rows:
        new_df = pd.DataFrame(new_rows, columns=COLUMNS)
        df = pd.concat([df, new_df], ignore_index=True)
        _save_cache(symbol, timeframe, df)
        df = _load_cache(symbol, timeframe)

    return df


def load_range(symbol: str, timeframe: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    """Read cached data (no network) filtered to [start_ms, end_ms]."""
    df = _load_cache(symbol, timeframe)
    if df.empty:
        return df
    return df[(df["ts"] >= start_ms) & (df["ts"] <= end_ms)].reset_index(drop=True)


def cache_bounds(symbol: str, timeframe: str) -> dict:
    """Candle count and covered date range for the cached data, for display."""
    df = _load_cache(symbol, timeframe)
    if df.empty:
        return {"count": 0, "min_ts": None, "max_ts": None}
    return {"count": len(df), "min_ts": int(df["ts"].min()), "max_ts": int(df["ts"].max())}
