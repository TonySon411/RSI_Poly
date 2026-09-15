"""Real-time order-book streaming over Polymarket's CLOB "market" websocket
channel. Ported from the Up_Down_both project's bot/clob_ws.py, unchanged
aside from the import path.

  - URL: wss://ws-subscriptions-clob.polymarket.com/ws/market
  - Subscribe: {"assets_ids": [<token_id>, ...], "type": "market"}; add/drop
    ids on a live connection with {"assets_ids": [...], "operation":
    "subscribe"|"unsubscribe"} instead of reconnecting.
  - Heartbeat is application-level, not a websocket ping frame: send the text
    "PING" every 10s, server replies "PONG".
  - "book" events carry a full bids/asks snapshot for one asset_id. No
    documented sort order, so best bid/ask here is taken as max(bids)/
    min(asks) by price rather than assumed from list position.
  - "price_change" events carry incremental {price, size, side, best_bid,
    best_ask} entries. best_bid/best_ask give the new top-of-book *price*;
    the accompanying "size" is only trusted as the new top-of-book size when
    that level's price actually equals best_bid/best_ask.
  - "last_trade_price" events update last_trade_price only.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Callable, Optional

import websocket  # websocket-client

from .models import BookTop

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
_PING_INTERVAL_SEC = 10
_RECONNECT_DELAY_SEC = 2
# If neither a real event nor our own PONG has arrived in this long, the
# socket is treated as dead even though nothing raised an error - a
# connection can go silently unresponsive without the underlying TCP socket
# ever actually closing, so run_forever() has nothing to raise on and never
# reconnects on its own.
_STALE_TIMEOUT_SEC = 30


def _is_stale(last_message_at: float, now: float) -> bool:
    return now - last_message_at > _STALE_TIMEOUT_SEC


OnUpdate = Callable[[str, BookTop, float], None]


def _to_float(value, default=None):
    if value in (None, ""):
        return default
    return float(value)


def _best(levels: list[dict], pick) -> tuple[Optional[float], Optional[float]]:
    if not levels:
        return None, None
    lvl = pick(levels, key=lambda l: float(l["price"]))
    return float(lvl["price"]), float(lvl["size"])


class BookStream:
    """One persistent websocket connection, auto-reconnecting, driving a
    per-token top-of-book (BookTop) it pushes to `on_update` every time the
    exchange reports a change. Runs entirely on its own background thread(s)
    - `on_update` is called from there, so it must be cheap and thread-safe."""

    def __init__(self, on_update: OnUpdate):
        self._on_update = on_update
        self._ws: Optional[websocket.WebSocketApp] = None
        self._subscribed: set[str] = set()
        self._tops: dict[str, BookTop] = {}
        self._stop = False
        self._last_message_at = time.time()
        self._thread = threading.Thread(target=self._run_forever, daemon=True)
        self._thread.start()

    def subscribe(self, asset_ids: list[str]) -> None:
        new_ids = [a for a in asset_ids if a not in self._subscribed]
        if not new_ids:
            return
        self._subscribed.update(new_ids)
        self._send({"assets_ids": new_ids, "type": "market", "operation": "subscribe"})

    def unsubscribe(self, asset_ids: list[str]) -> None:
        old_ids = [a for a in asset_ids if a in self._subscribed]
        if not old_ids:
            return
        self._subscribed.difference_update(old_ids)
        for asset_id in old_ids:
            self._tops.pop(asset_id, None)
        self._send({"assets_ids": old_ids, "operation": "unsubscribe"})

    def close(self) -> None:
        self._stop = True
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:  # noqa: BLE001 - best-effort on shutdown
                pass

    def _send(self, payload: dict) -> None:
        ws = self._ws
        if ws is not None and ws.sock and ws.sock.connected:
            try:
                ws.send(json.dumps(payload))
            except Exception:  # noqa: BLE001 - dropped mid-send; _on_open resubscribes on reconnect
                pass

    def _on_open(self, ws):
        self._last_message_at = time.time()
        if self._subscribed:
            ws.send(json.dumps({"assets_ids": list(self._subscribed), "type": "market"}))

        def _pinger():
            while not self._stop and ws.sock and ws.sock.connected:
                if _is_stale(self._last_message_at, time.time()):
                    print(f"[clob_ws] no data for {_STALE_TIMEOUT_SEC}s - forcing reconnect")
                    try:
                        ws.close()
                    except Exception:  # noqa: BLE001 - best-effort; run_forever reconnects either way
                        pass
                    return
                try:
                    ws.send("PING")
                except Exception:  # noqa: BLE001 - connection dropped; run_forever will notice and reconnect
                    return
                time.sleep(_PING_INTERVAL_SEC)

        threading.Thread(target=_pinger, daemon=True).start()

    def _on_message(self, ws, message):
        self._last_message_at = time.time()
        if message == "PONG":
            return
        try:
            events = json.loads(message)
        except json.JSONDecodeError:
            return
        for event in events if isinstance(events, list) else [events]:
            self._handle_event(event)

    def _handle_event(self, event: dict) -> None:
        event_type = event.get("event_type")
        if event_type == "book":
            asset_id = event.get("asset_id")
            if not asset_id:
                return
            prev = self._tops.get(asset_id)
            best_bid, best_bid_size = _best(event.get("bids") or [], max)
            best_ask, best_ask_size = _best(event.get("asks") or [], min)
            top = BookTop(best_bid, best_ask, best_bid_size, best_ask_size,
                          last_trade_price=prev.last_trade_price if prev else None)
            self._tops[asset_id] = top
            self._emit(asset_id, top, event.get("timestamp"))
        elif event_type == "price_change":
            for change in event.get("price_changes", []):
                asset_id = change.get("asset_id")
                if not asset_id:
                    continue
                prev = self._tops.get(asset_id) or BookTop(None, None, None, None, None)
                best_bid = _to_float(change.get("best_bid"), prev.best_bid)
                best_ask = _to_float(change.get("best_ask"), prev.best_ask)
                best_bid_size, best_ask_size = prev.best_bid_size, prev.best_ask_size
                price, size = change.get("price"), change.get("size")
                if price is not None and size is not None:
                    price_f = float(price)
                    if best_bid is not None and price_f == best_bid:
                        best_bid_size = float(size)
                    if best_ask is not None and price_f == best_ask:
                        best_ask_size = float(size)
                top = BookTop(best_bid, best_ask, best_bid_size, best_ask_size, prev.last_trade_price)
                self._tops[asset_id] = top
                self._emit(asset_id, top, change.get("timestamp") or event.get("timestamp"))
        elif event_type == "last_trade_price":
            asset_id = event.get("asset_id")
            if not asset_id:
                return
            prev = self._tops.get(asset_id) or BookTop(None, None, None, None, None)
            top = BookTop(prev.best_bid, prev.best_ask, prev.best_bid_size, prev.best_ask_size,
                          last_trade_price=_to_float(event.get("price")))
            self._tops[asset_id] = top
            self._emit(asset_id, top, event.get("timestamp"))
        # tick_size_change / new_market / market_resolved carry nothing this
        # recorder needs - ignored.

    def _emit(self, asset_id: str, top: BookTop, ts_raw) -> None:
        try:
            ts = float(ts_raw) / 1000.0 if ts_raw is not None else time.time()
        except (TypeError, ValueError):
            ts = time.time()
        self._on_update(asset_id, top, ts)

    def _run_forever(self):
        while not self._stop:
            self._ws = websocket.WebSocketApp(WS_URL, on_open=self._on_open, on_message=self._on_message)
            try:
                self._ws.run_forever(ping_interval=0)  # heartbeat is our own text "PING", not a ws ping frame
            except Exception as exc:  # noqa: BLE001 - keep reconnecting
                print(f"[clob_ws] connection error: {exc}")
            if self._stop:
                return
            time.sleep(_RECONNECT_DELAY_SEC)
