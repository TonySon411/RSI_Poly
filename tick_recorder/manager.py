"""Spawns one background tick-recording thread per (symbol, timeframe) pair
-- 7 assets x [5m, 15m] -- each with its own persistent CLOB websocket
connection, matching the Up_Down_both project's "total mode" concurrency
model (one connection per asset/series, not shared).
"""

from __future__ import annotations

import threading

from paper_engine.topbot_bridge import SYMBOLS

from .recorder import run

TIMEFRAMES = ["5m", "15m"]

# 5m rolls over every 5 minutes -> check Gamma for the active window more
# often; 15m much less so. Book data itself streams live regardless of this
# -- it only paces the Gamma re-check / pending-resolution poll.
POLL_INTERVAL_SEC = {"5m": 2.0, "15m": 4.0}


class TickRecorderManager:
    def __init__(self) -> None:
        self._threads: list[threading.Thread] = []
        self._stop_event = threading.Event()

    def start_all(self) -> None:
        if self._threads:
            return
        for symbol in SYMBOLS:
            for timeframe in TIMEFRAMES:
                thread = threading.Thread(
                    target=run,
                    args=(symbol, timeframe, self._stop_event),
                    kwargs={"snapshot_interval_sec": POLL_INTERVAL_SEC[timeframe]},
                    name=f"tick-recorder-{symbol}-{timeframe}",
                    daemon=True,
                )
                self._threads.append(thread)
                thread.start()
        print(
            f"[tick_recorder] started {len(self._threads)} recorders "
            f"({len(SYMBOLS)} assets x {len(TIMEFRAMES)} timeframes)"
        )

    def stop_all(self) -> None:
        self._stop_event.set()


manager = TickRecorderManager()
