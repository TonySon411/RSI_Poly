"""Re-checks trades that placed a real side but never got a resolution back
within topbot's own short post-window polling window (it gives up ~45s after
the window closes and never looks again). Without this, any market Gamma is
slow to finalize stays "Pending" forever and never counts toward a
template's win rate / PnL.
"""

from __future__ import annotations

import threading
import time
import traceback

from . import store
from .topbot_bridge import GAMMA_BASE, fetch_resolution

POLL_BATCH_INTERVAL_SEC = 30.0
PER_TRADE_DELAY_SEC = 0.2


def _resolve_one(trade: dict) -> None:
    resolution = fetch_resolution(gamma_base=GAMMA_BASE, slug=trade["slug"])
    if resolution is None:
        return

    filled_shares = trade["filled_shares"] or 0.0
    cost = trade["cost"] or 0.0
    won = trade["side"] == resolution
    payout = filled_shares * 1.0 if won else 0.0
    pnl = payout - cost

    store.update_trade_resolution(trade["id"], resolution=resolution, won=won, pnl=pnl)


class PendingResolver:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="pending-resolver", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while True:
            try:
                pending = store.list_unresolved_trades()
                for trade in pending:
                    try:
                        _resolve_one(trade)
                    except Exception:  # noqa: BLE001
                        traceback.print_exc()
                    time.sleep(PER_TRADE_DELAY_SEC)
            except Exception:  # noqa: BLE001
                traceback.print_exc()
            time.sleep(POLL_BATCH_INTERVAL_SEC)


resolver = PendingResolver()
