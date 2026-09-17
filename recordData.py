"""Standalone Polymarket tick recorder.

Records real order-book price ticks for every symbol/timeframe pair (7
assets x [5m, 15m]) into data/<SYMBOL>/<5m|15m>/<slug>.json via a persistent
CLOB websocket per pair -- the same tick_recorder package app.py starts
automatically as part of the dashboard. Run this instead when you only want
recording (e.g. as its own standalone process / PM2 app) without also
running the Flask dashboard.

    python recordData.py
"""

from __future__ import annotations

import signal
import sys
import time

# tick_recorder prints market slugs/status lines; keep this consistent with
# app.py so a stray non-ASCII character can't crash the process on Windows.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from tick_recorder.manager import manager

_stop = False


def _handle_signal(signum, frame) -> None:
    global _stop
    _stop = True


def main() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    manager.start_all()

    try:
        while not _stop:
            time.sleep(1.0)
    finally:
        print("[recordData] stopping recorders...")
        manager.stop_all()
        time.sleep(1.0)  # let each recorder thread's current loop iteration exit cleanly


if __name__ == "__main__":
    main()
