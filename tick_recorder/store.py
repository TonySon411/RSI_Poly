"""JSON-file storage for recorded order-book snapshots. One market -> one
file at data/<SYMBOL>/<5m|15m>/<slug>.json, matching the Up_Down_both
project's recording format/layout, adapted to this project's symbol/
timeframe naming instead of its market_slug_prefix convention.

Snapshots are buffered in memory by the caller (tick_recorder/recorder.py)
while a market is actively recording and flushed to disk periodically, not
on every websocket tick. `save()` writes to a temp file and os.replace()s it
into place, so a crash mid-write never leaves a truncated/corrupt file.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_REPLACE_RETRIES = 5
_REPLACE_RETRY_DELAY_SEC = 0.05


def _atomic_replace(tmp_path: Path, path: Path) -> None:
    for attempt in range(_REPLACE_RETRIES):
        try:
            os.replace(tmp_path, path)
            return
        except PermissionError:
            if attempt == _REPLACE_RETRIES - 1:
                raise
            time.sleep(_REPLACE_RETRY_DELAY_SEC)


def market_json_path(symbol: str, timeframe: str, slug: str) -> Path:
    return DATA_DIR / symbol.upper() / timeframe / f"{slug}.json"


def series_dir(symbol: str, timeframe: str) -> Path:
    return DATA_DIR / symbol.upper() / timeframe


def new_record(
    symbol: str,
    timeframe: str,
    slug: str,
    condition_id: str,
    up_token_id: str,
    down_token_id: str,
    start_ts: int,
    end_ts: int,
) -> dict:
    return {
        "asset": symbol.upper(),
        "series": timeframe,
        "slug": slug,
        "condition_id": condition_id,
        "up_token_id": up_token_id,
        "down_token_id": down_token_id,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "resolution": None,
        "snapshots": {up_token_id: [], down_token_id: []},
    }


def load(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(record, f)
    _atomic_replace(tmp_path, path)


def get_or_create(
    symbol: str,
    timeframe: str,
    slug: str,
    condition_id: str,
    up_token_id: str,
    down_token_id: str,
    start_ts: int,
    end_ts: int,
) -> dict:
    path = market_json_path(symbol, timeframe, slug)
    record = load(path)
    if record is not None:
        # A previous recorder run may have created this file already (e.g.
        # restarted mid-window).
        record["snapshots"].setdefault(up_token_id, [])
        record["snapshots"].setdefault(down_token_id, [])
        return record
    record = new_record(symbol, timeframe, slug, condition_id, up_token_id, down_token_id, start_ts, end_ts)
    save(path, record)
    return record


def set_resolution(symbol: str, timeframe: str, slug: str, resolution: str) -> None:
    path = market_json_path(symbol, timeframe, slug)
    record = load(path)
    if record is None:
        return
    record["resolution"] = resolution
    save(path, record)


def list_market_files(symbol: str, timeframe: str) -> list[Path]:
    folder = series_dir(symbol, timeframe)
    if not folder.exists():
        return []
    return sorted(folder.glob("*.json"))


def list_unresolved_ended(symbol: str, timeframe: str, now_ts: float) -> list[str]:
    """Slugs of recorded markets whose window ended a while ago but have no
    resolution yet - typically because a prior recorder run was interrupted
    before resolving them."""
    out = []
    for path in list_market_files(symbol, timeframe):
        record = load(path)
        if record and record.get("resolution") is None and record.get("end_ts", 0) < now_ts:
            out.append(record["slug"])
    return out
