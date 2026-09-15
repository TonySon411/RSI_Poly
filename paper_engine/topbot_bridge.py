"""Bridge into the existing `topbot` project's real Polymarket paper-trading
logic (RSI decision -> ladder orders -> live CLOB fill simulation -> Gamma
resolution), reused here read-only via sys.path so templates trade against
the actual market instead of a re-implementation.

Paper mode only touches public, unauthenticated Bybit/Gamma/CLOB endpoints —
no credentials required.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def _resolve_topbot_src() -> Path:
    override = os.environ.get("TOPBOT_SRC")
    if override:
        return Path(override)
    # Default: topbot is a sibling directory of this project
    # (<parent>/RSI + <parent>/topbot) -- portable across OS/deploy layout as
    # long as both projects are cloned side by side. Override with the
    # TOPBOT_SRC env var if that's not how a given server is laid out.
    return Path(__file__).resolve().parent.parent.parent / "topbot" / "src"


TOPBOT_SRC = _resolve_topbot_src()
if TOPBOT_SRC.is_dir():
    if str(TOPBOT_SRC) not in sys.path:
        sys.path.insert(0, str(TOPBOT_SRC))
else:
    print(
        f"[paper_engine] WARNING: topbot source not found at {TOPBOT_SRC} -- "
        "set the TOPBOT_SRC env var to its src/ directory, or clone topbot as "
        "a sibling of this project. Templates and the tick recorder will fail "
        "to import until this is fixed."
    )

from topbot.config import Config, LadderRung  # noqa: E402
from topbot.polymarket.executor import PaperExecutor  # noqa: E402
from topbot.polymarket.gamma import MarketInfo, fetch_market, fetch_resolution, window_start  # noqa: E402
from topbot.runner import run_window  # noqa: E402
from topbot.strategy import RetryState  # noqa: E402

__all__ = [
    "Config",
    "PaperExecutor",
    "RetryState",
    "run_window",
    "window_start",
    "fetch_market",
    "fetch_resolution",
    "MarketInfo",
    "build_config",
    "config_summary",
    "SYMBOLS",
    "TIMEFRAMES",
    "TIMEFRAME_LABELS",
    "GAMMA_BASE",
]

SYMBOLS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "HYPE", "BNB"]

GAMMA_BASE = "https://gamma-api.polymarket.com"

# topbot's default 5-rung ladder (same as its shipped config.yaml).
DEFAULT_LADDER = (
    LadderRung(price=0.50, size=5),
    LadderRung(price=0.40, size=5),
    LadderRung(price=0.30, size=10),
    LadderRung(price=0.20, size=15),
    LadderRung(price=0.10, size=20),
)


@dataclass(frozen=True)
class TimeframeSpec:
    bybit_interval: str
    interval_label: str
    window_seconds: int
    poll_interval_sec: float


TIMEFRAMES: dict[str, TimeframeSpec] = {
    "5m": TimeframeSpec("5", "5m", 300, 2.0),
    "15m": TimeframeSpec("15", "15m", 900, 5.0),
    "1h": TimeframeSpec("60", "1h", 3600, 10.0),
    "4h": TimeframeSpec("240", "4h", 14400, 20.0),
}

TIMEFRAME_LABELS = {"5m": "5 minute", "15m": "15 minute", "1h": "1 hour", "4h": "4 hour"}

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"


def build_config(row: dict) -> Config:
    """Build a topbot Config for one template row (always paper mode, no retry)."""
    tf = TIMEFRAMES[row["timeframe"]]
    rsi_length = int(row["rsi_length"])
    return Config(
        mode="paper",
        bybit_symbol=f"{row['symbol'].upper()}USDT",
        bybit_interval=tf.bybit_interval,
        bybit_category="linear",
        candle_limit=max(50, rsi_length + 20),
        rsi_period=rsi_length,
        rsi_overbought=float(row["overbought"]),
        rsi_oversold=float(row["oversold"]),
        max_attempts=1,  # no loss-retry ladder: every RSI signal is independent
        asset=row["symbol"].lower(),
        interval_label=tf.interval_label,
        window_seconds=tf.window_seconds,
        gamma_base=GAMMA_BASE,
        clob_host="https://clob.polymarket.com",
        chain_id=137,
        resolution_buffer_sec=15.0,
        poll_interval_sec=tf.poll_interval_sec,
        ladder=DEFAULT_LADDER,
        trades_path=LOGS_DIR / f"template-{row['id']}.jsonl",
        private_key=None,
        funder=None,
        signature_type=0,
    )


def config_summary(row: dict) -> str:
    tf_label = TIMEFRAME_LABELS[row["timeframe"]]
    slug_prefix = f"{row['symbol'].lower()}-updown-{row['timeframe']}"
    return (
        f"{row['symbol']} {tf_label} ({slug_prefix}) \u00b7 "
        f"RSI({row['rsi_length']}) OB={row['overbought']:g}/OS={row['oversold']:g}"
    )
