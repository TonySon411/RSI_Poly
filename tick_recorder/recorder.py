"""Continuously records real Polymarket order-book tick data for one
symbol/timeframe pair so the RSI backtester can eventually replay real
historical price paths instead of just Bybit candle direction.

Ported from the Up_Down_both project's bot/recorder.py: book data streams
live over the CLOB websocket (tick_recorder/clob_ws.py); only real price
changes are written (a size-only update is dropped), and the next window's
token ids are pre-fetched shortly before the current one ends so the
websocket subscription goes out right at the boundary instead of losing the
first few seconds to a reactive post-boundary Gamma poll.

Market discovery/resolution reuse topbot's own Gamma client
(paper_engine/topbot_bridge.py) rather than a second parallel
implementation, since 5m/15m slugs are plain UTC-epoch-floor windows with no
extra complexity to handle.
"""

from __future__ import annotations

import threading
import time

from paper_engine.topbot_bridge import GAMMA_BASE, TIMEFRAMES, fetch_market, fetch_resolution

from . import clob_ws, store

PRE_FETCH_LEAD_SEC = 30  # start trying to fetch the next window's token ids this far before it starts
RESOLUTION_BUFFER_SEC = 90
RESOLUTION_RETRY_SEC = 10


def run(
    symbol: str,
    timeframe: str,
    stop_event: threading.Event,
    snapshot_interval_sec: float = 1.0,
    flush_interval_sec: float = 5.0,
) -> None:
    tf = TIMEFRAMES[timeframe]
    window_seconds = tf.window_seconds
    interval_label = tf.interval_label
    asset = symbol.lower()

    current_slug = None
    current_end_ts = None
    current_tokens = None
    current_record = None
    next_window = None  # a pre-fetched MarketInfo for the slot starting at current_end_ts
    last_flush = 0.0
    lock = threading.Lock()

    def on_update(asset_id: str, top, ts: float) -> None:
        with lock:
            if current_record is None or asset_id not in current_record["snapshots"]:
                return  # stray update for a token we've since unsubscribed from
            snaps = current_record["snapshots"][asset_id]
            if snaps:
                last = snaps[-1]
                if (last["best_bid"], last["best_ask"], last["last_trade_price"]) == \
                        (top.best_bid, top.best_ask, top.last_trade_price):
                    return  # size-only (or duplicate) update - price didn't actually move
            snaps.append(
                {
                    "ts": ts,
                    "best_bid": top.best_bid,
                    "best_ask": top.best_ask,
                    "best_bid_size": top.best_bid_size,
                    "best_ask_size": top.best_ask_size,
                    "last_trade_price": top.last_trade_price,
                }
            )

    stream = clob_ws.BookStream(on_update)

    now0 = time.time()
    pending_resolution: list[tuple[str, float]] = [
        (slug, now0) for slug in store.list_unresolved_ended(symbol, timeframe, now0 - RESOLUTION_BUFFER_SEC)
    ]
    if pending_resolution:
        print(f"[tick_recorder] {symbol} {timeframe}: re-queuing {len(pending_resolution)} unresolved market(s)")

    print(f"[tick_recorder] {symbol} {timeframe}: started, streaming book via websocket")

    def flush():
        nonlocal last_flush
        with lock:
            record, slug = current_record, current_slug
        if record is not None:
            store.save(store.market_json_path(symbol, timeframe, slug), record)
            last_flush = time.time()

    def begin_window(market) -> None:
        nonlocal current_slug, current_end_ts, current_tokens, current_record, last_flush
        up_token = market.tokens["Up"]
        down_token = market.tokens["Down"]
        record = store.get_or_create(
            symbol, timeframe, market.slug, market.condition_id,
            up_token, down_token, market.window_start, market.window_end,
        )
        with lock:
            current_record = record
        current_slug, current_end_ts = market.slug, market.window_end
        current_tokens = {"Up": up_token, "Down": down_token}
        stream.subscribe([up_token, down_token])
        last_flush = time.time()
        print(f"[tick_recorder] {symbol} {timeframe}: {market.slug} recording")

    try:
        while not stop_event.is_set():
            now = time.time()

            if current_slug is not None and now >= current_end_ts:
                flush()
                pending_resolution.append((current_slug, now + RESOLUTION_BUFFER_SEC))
                stream.unsubscribe(list(current_tokens.values()))
                ended_end_ts = current_end_ts
                current_slug, current_end_ts, current_tokens, current_record = None, None, None, None
                if next_window is not None and next_window.window_start == ended_end_ts:
                    # already have the next window's token ids - subscribe now, with no
                    # post-boundary Gamma round-trip delay before recording resumes
                    begin_window(next_window)
                next_window = None

            if current_slug is None:
                # startup, or the pre-fetch below didn't land in time - fall back to
                # reactive detection so recording still resumes
                try:
                    market = fetch_market(
                        gamma_base=GAMMA_BASE, asset=asset,
                        interval_label=interval_label, window_seconds=window_seconds, now=now,
                    )
                    if market.window_start <= now < market.window_end:
                        begin_window(market)
                except Exception:  # noqa: BLE001 - market not created yet / transient network hiccup
                    pass

            if current_record is not None and now - last_flush >= flush_interval_sec:
                flush()

            if current_end_ts is not None and next_window is None and (current_end_ts - now) <= PRE_FETCH_LEAD_SEC:
                try:
                    fetched = fetch_market(
                        gamma_base=GAMMA_BASE, asset=asset,
                        interval_label=interval_label, window_seconds=window_seconds, now=current_end_ts,
                    )
                    if fetched.window_start == current_end_ts:
                        next_window = fetched
                except Exception:  # noqa: BLE001
                    pass

            still_pending = []
            for slug, check_after in pending_resolution:
                if now < check_after:
                    still_pending.append((slug, check_after))
                    continue
                try:
                    resolution = fetch_resolution(gamma_base=GAMMA_BASE, slug=slug)
                except Exception:  # noqa: BLE001
                    resolution = None
                if resolution is None:
                    still_pending.append((slug, now + RESOLUTION_RETRY_SEC))
                    continue
                store.set_resolution(symbol, timeframe, slug, resolution)
                print(f"[tick_recorder] {symbol} {timeframe}: {slug} resolved {resolution}")
            pending_resolution = still_pending

            stop_event.wait(snapshot_interval_sec)
    finally:
        stream.close()
