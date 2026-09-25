"""Delete recorded Polymarket tick data (data/<SYMBOL>/<5m|15m>/*.json) for
one or more symbols, without touching anything else (the Bybit OHLC CSV
cache at data/<SYMBOL>_<timeframe>.csv, templates.db, etc. are untouched --
this only removes the tick_recorder's own per-market JSON files).

Usage:
    python clearRecordedData.py                 # all symbols, asks to confirm
    python clearRecordedData.py BTC ETH          # only these symbols
    python clearRecordedData.py BTC --timeframe 5m
    python clearRecordedData.py --all --yes      # no confirmation prompt

Safe to run whether or not recordData.py is currently running elsewhere --
each JSON file is only ever rewritten wholesale on its own flush, so deleting
a file just means the next flush recreates it from whatever's in memory at
that point. Still, running this while nothing is actively recording (e.g.
right after a fix, before restarting recordData.py) is the cleanest choice.
"""

from __future__ import annotations

import argparse
import shutil
import sys

from rsi_backtest.config import SYMBOLS
from tick_recorder.manager import TIMEFRAMES
from tick_recorder.store import series_dir


def _dir_stats(path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    files = list(path.glob("*.json"))
    return len(files), sum(f.stat().st_size for f in files)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("symbols", nargs="*", help="Symbols to clear (default: all)")
    parser.add_argument("--timeframe", choices=TIMEFRAMES, help="Only this timeframe (default: both 5m and 15m)")
    parser.add_argument("--all", action="store_true", help="Explicitly clear all symbols (same as passing none)")
    parser.add_argument("-y", "--yes", action="store_true", help="Don't ask for confirmation")
    args = parser.parse_args()

    symbols = [s.upper() for s in args.symbols] if args.symbols else list(SYMBOLS)
    timeframes = [args.timeframe] if args.timeframe else list(TIMEFRAMES)

    unknown = [s for s in symbols if s not in SYMBOLS]
    if unknown:
        print(f"Unknown symbol(s): {', '.join(unknown)}. Valid: {', '.join(SYMBOLS)}", file=sys.stderr)
        sys.exit(1)

    targets = []
    total_files = total_bytes = 0
    for symbol in symbols:
        for timeframe in timeframes:
            path = series_dir(symbol, timeframe)
            count, size = _dir_stats(path)
            if count == 0:
                continue
            targets.append((symbol, timeframe, path, count, size))
            total_files += count
            total_bytes += size

    if not targets:
        print("Nothing to delete.")
        return

    print("About to delete:")
    for symbol, timeframe, path, count, size in targets:
        print(f"  {symbol:6} {timeframe:4} {count:>6} files  {size / 1024:>10.1f} KB   ({path})")
    print(f"\nTotal: {total_files} files, {total_bytes / 1024:.1f} KB")

    if not args.yes:
        reply = input("\nType 'yes' to delete: ").strip().lower()
        if reply != "yes":
            print("Aborted, nothing deleted.")
            return

    for symbol, timeframe, path, count, size in targets:
        shutil.rmtree(path)
        print(f"[deleted] {symbol} {timeframe} ({count} files)")

    print("Done.")


if __name__ == "__main__":
    main()
