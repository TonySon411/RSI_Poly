from dataclasses import dataclass
from typing import Optional


@dataclass
class BookTop:
    best_bid: Optional[float]
    best_ask: Optional[float]
    best_bid_size: Optional[float]
    best_ask_size: Optional[float]
    last_trade_price: Optional[float] = None
