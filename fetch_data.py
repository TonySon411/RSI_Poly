"""Bulk-download Bybit kline history for every symbol/timeframe the dashboard
supports, from 2026-01-01 up to now, into the local data/ cache.

Run this once before using the dashboard (and re-run any time to top up the
cache with the newest candles):

    python fetch_data.py
"""

from __future__ import annotations

import datetime as dt
import sys

from rsi_backtest.config import SYMBOLS, TIMEFRAMES
from rsi_backtest.data_store import cache_bounds, ensure_data

START = int(dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)


def main() -> None:
    end = int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)

    for symbol in SYMBOLS:
        for timeframe in TIMEFRAMES:
            label = f"{symbol} {timeframe}"
            try:
                ensure_data(symbol, timeframe, START, end)
                bounds = cache_bounds(symbol, timeframe)
                print(f"[ok] {label:<10} {bounds['count']:>6} candles cached", flush=True)
            except Exception as exc:
                print(f"[FAIL] {label:<10} {exc}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
