"""Shared constants: symbols, timeframes, Bybit interval mapping."""

SYMBOLS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "HYPE", "BNB"]

# label -> (Bybit kline "interval" param, interval length in milliseconds)
TIMEFRAMES = {
    "5m": ("5", 5 * 60_000),
    "15m": ("15", 15 * 60_000),
    "1h": ("60", 60 * 60_000),
    "4h": ("240", 240 * 60_000),
}

BYBIT_CATEGORY = "linear"


def bybit_symbol(symbol: str) -> str:
    return f"{symbol.upper()}USDT"
