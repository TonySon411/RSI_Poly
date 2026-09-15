"""SQLite persistence for templates and their live paper-trade history."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "templates.db"

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
    return _conn


def init_db() -> None:
    conn = _get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS templates (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          symbol TEXT NOT NULL,
          timeframe TEXT NOT NULL,
          rsi_length INTEGER NOT NULL,
          overbought REAL NOT NULL,
          oversold REAL NOT NULL,
          status TEXT NOT NULL DEFAULT 'stopped',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS trades (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          template_id TEXT NOT NULL,
          ts TEXT NOT NULL,
          window_start INTEGER,
          window_end INTEGER,
          rsi REAL,
          side TEXT,
          skipped INTEGER NOT NULL DEFAULT 0,
          slug TEXT,
          question TEXT,
          filled_shares REAL,
          cost REAL,
          resolution TEXT,
          won INTEGER,
          pnl REAL,
          error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_trades_template ON trades(template_id);
        """
    )
    conn.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_template(*, name, symbol, timeframe, rsi_length, overbought, oversold) -> dict:
    tid = uuid.uuid4().hex[:8]
    now = _now_iso()
    with _lock:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO templates"
            " (id,name,symbol,timeframe,rsi_length,overbought,oversold,status,created_at,updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (tid, name, symbol, timeframe, rsi_length, overbought, oversold, "stopped", now, now),
        )
        conn.commit()
    return get_template(tid)


def get_template(template_id: str) -> dict | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM templates WHERE id=?", (template_id,)).fetchone()
    return dict(row) if row else None


def update_template(template_id: str, **fields) -> None:
    if not fields:
        return
    fields = {**fields, "updated_at": _now_iso()}
    cols = ", ".join(f"{k}=?" for k in fields)
    with _lock:
        conn = _get_conn()
        conn.execute(f"UPDATE templates SET {cols} WHERE id=?", (*fields.values(), template_id))
        conn.commit()


def set_status(template_id: str, status: str) -> None:
    update_template(template_id, status=status)


def delete_template(template_id: str) -> None:
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM trades WHERE template_id=?", (template_id,))
        conn.execute("DELETE FROM templates WHERE id=?", (template_id,))
        conn.commit()


def _stats_for(conn: sqlite3.Connection, template_id: str) -> dict:
    stats = conn.execute(
        "SELECT"
        " COUNT(CASE WHEN skipped=0 AND resolution IS NOT NULL THEN 1 END) AS markets,"
        " COALESCE(SUM(CASE WHEN skipped=0 AND resolution IS NOT NULL THEN pnl END), 0) AS pnl_sum,"
        " COUNT(CASE WHEN won=1 THEN 1 END) AS wins,"
        " COUNT(CASE WHEN won=0 THEN 1 END) AS losses"
        " FROM trades WHERE template_id=?",
        (template_id,),
    ).fetchone()
    wins, losses = stats["wins"], stats["losses"]
    decided = wins + losses
    return {
        "markets": stats["markets"],
        "pnl_sum": stats["pnl_sum"],
        "wins": wins,
        "losses": losses,
        "win_rate": (wins / decided * 100.0) if decided else None,
    }


def get_template_with_stats(template_id: str) -> dict | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM templates WHERE id=?", (template_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d.update(_stats_for(conn, template_id))
    return d


def list_templates() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM templates ORDER BY created_at ASC").fetchall()
    out = []
    for row in rows:
        d = dict(row)
        d.update(_stats_for(conn, row["id"]))
        out.append(d)
    return out


def list_running_templates() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM templates WHERE status='running'").fetchall()
    return [dict(r) for r in rows]


def list_unresolved_trades(limit: int = 500) -> list[dict]:
    """Trades that placed a real side (not skipped, not errored) but never
    got a resolution back before topbot's own short polling window gave up."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM trades WHERE skipped=0 AND error IS NULL AND resolution IS NULL"
        " AND slug IS NOT NULL ORDER BY window_end ASC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def update_trade_resolution(trade_id: int, *, resolution: str, won: bool, pnl: float) -> None:
    with _lock:
        conn = _get_conn()
        conn.execute(
            "UPDATE trades SET resolution=?, won=?, pnl=? WHERE id=?",
            (resolution, 1 if won else 0, pnl, trade_id),
        )
        conn.commit()


def save_trade(template_id: str, record: dict) -> None:
    with _lock:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO trades"
            " (template_id, ts, window_start, window_end, rsi, side, skipped,"
            "  slug, question, filled_shares, cost, resolution, won, pnl, error)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                template_id,
                record.get("ts") or _now_iso(),
                record.get("window_start"),
                record.get("window_end"),
                record.get("rsi"),
                record.get("side"),
                1 if record.get("skipped") else 0,
                record.get("slug"),
                record.get("question"),
                record.get("filled_shares"),
                record.get("cost"),
                record.get("resolution"),
                None if record.get("won") is None else (1 if record.get("won") else 0),
                record.get("pnl"),
                record.get("error"),
            ),
        )
        conn.commit()


def list_trades(template_id: str, limit: int = 300) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM trades WHERE template_id=? ORDER BY id DESC LIMIT ?",
        (template_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]
