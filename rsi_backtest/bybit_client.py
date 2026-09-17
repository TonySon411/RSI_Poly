"""Minimal client for Bybit's public kline (candlestick) REST endpoint."""

from __future__ import annotations

import time

import requests

from .config import BYBIT_CATEGORY, bybit_symbol

KLINE_URL = "https://api.bybit.com/v5/market/kline"
PAGE_LIMIT = 1000
MAX_PAGE_ATTEMPTS = 5
RETRY_DELAY_SEC = 2.0


def _get_page(session: requests.Session, params: dict, symbol: str) -> dict:
    """Fetch one page, retrying on transient network errors (timeouts, resets,
    etc). A long backfill can be hundreds of pages, so without this a single
    flaky read wipes out everything fetched so far for that gap."""
    last_exc: Exception | None = None
    for attempt in range(1, MAX_PAGE_ATTEMPTS + 1):
        try:
            resp = session.get(KLINE_URL, params=params, timeout=20)
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("retCode") != 0:
                raise RuntimeError(f"Bybit error for {symbol}: {payload.get('retMsg')}")
            return payload
        except (requests.exceptions.RequestException, RuntimeError) as exc:
            last_exc = exc
            if attempt < MAX_PAGE_ATTEMPTS:
                time.sleep(RETRY_DELAY_SEC * attempt)
    raise last_exc  # type: ignore[misc]


def fetch_klines(symbol: str, bybit_interval: str, start_ms: int, end_ms: int) -> list[list]:
    """Fetch all closed klines for `symbol` between start_ms and end_ms (inclusive).

    Returns a list of [open_time_ms, open, high, low, close, volume] rows,
    sorted ascending by open_time_ms, deduplicated.

    Bybit's kline endpoint returns the newest `limit` candles within
    [start, end], so we page backwards from `end_ms` toward `start_ms`.
    """
    rows: dict[int, list] = {}
    cursor_end = end_ms
    session = requests.Session()

    while cursor_end >= start_ms:
        params = {
            "category": BYBIT_CATEGORY,
            "symbol": bybit_symbol(symbol),
            "interval": bybit_interval,
            "start": start_ms,
            "end": cursor_end,
            "limit": PAGE_LIMIT,
        }
        payload = _get_page(session, params, symbol)

        batch = payload["result"]["list"]
        if not batch:
            break

        oldest_ts = min(int(r[0]) for r in batch)

        for r in batch:
            ts = int(r[0])
            rows[ts] = [ts, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])]

        if len(batch) < PAGE_LIMIT or oldest_ts <= start_ms:
            break

        cursor_end = oldest_ts - 1
        time.sleep(0.05)  # be polite to the API

    return [rows[ts] for ts in sorted(rows)]
