"""Backfill Bybit kline history from 2023-01-01 to 2026-01-01, extending the
local data/ cache backwards in time (fetch_data.py only covers 2026-01-01
onward). Only 5m and 15m are backfilled here.

ensure_data() only fetches whatever is missing, so this is safe to re-run --
it will not re-download candles that are already cached. Some symbols (e.g.
HYPE) simply didn't exist as a Bybit perpetual for all of this range; those
will just end up with less history than the older, longer-listed coins,
which is expected rather than an error.

    python fetch_historical_data.py
"""

from __future__ import annotations

import datetime as dt
import sys

from rsi_backtest.config import SYMBOLS
from rsi_backtest.data_store import cache_bounds, ensure_data

TIMEFRAMES = ["5m", "15m"]

START = int(dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
END = int(dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)


def main() -> None:
    for symbol in SYMBOLS:
        for timeframe in TIMEFRAMES:
            label = f"{symbol} {timeframe}"
            try:
                ensure_data(symbol, timeframe, START, END)
                bounds = cache_bounds(symbol, timeframe)
                print(f"[ok] {label:<10} {bounds['count']:>6} candles cached total", flush=True)
            except Exception as exc:
                print(f"[FAIL] {label:<10} {exc}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
