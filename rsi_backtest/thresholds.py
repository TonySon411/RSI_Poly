"""Maps an ATR (volatility) value to an overbought/oversold pair via config.json.

Higher ATR means a more volatile market, where RSI swings more wildly, so it
needs a narrower (closer to 50) overbought/oversold band to fire at a similar
rate to a calmer, low-ATR market, which needs a much more extreme band. The
mapping is a simple set of [min_atr, max_atr) buckets read from config.json.
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def load_buckets() -> list[dict]:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)["atr_buckets"]


def get_thresholds(atr_value: float) -> tuple[float, float]:
    """Return (overbought, oversold) for the given ATR value."""
    buckets = load_buckets()

    for bucket in buckets:
        lo = bucket["min_atr"]
        hi = bucket["max_atr"]
        if hi is None:
            if atr_value >= lo:
                return bucket["overbought"], bucket["oversold"]
        elif lo <= atr_value < hi:
            return bucket["overbought"], bucket["oversold"]

    # below the smallest configured bucket -- clamp to it rather than error
    return 0, 0
