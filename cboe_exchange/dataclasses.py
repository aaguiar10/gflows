from dataclasses import dataclass, field, asdict
from typing import List, Optional

@dataclass
class CBOEOption:
    option: str
    bid: float
    bid_size: int
    ask: float
    ask_size: int
    iv: float
    open_interest: int
    volume: int
    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float
    theo: float
    change: float
    open: float
    high: float
    low: float
    tick: str
    last_trade_price: float
    last_trade_time: str
    percent_change: float
    prev_day_close: float

    def to_dict(self):
        return asdict(self)

@dataclass
class CBOEStockData:
    symbol: str
    security_type: str
    exchange_id: int
    current_price: float
    price_change: float
    price_change_percent: float
    bid: float
    ask: float
    bid_size: int
    ask_size: int
    open: float
    high: float
    low: float
    close: float
    prev_day_close: float
    volume: int
    iv30: float
    iv30_change: float
    iv30_change_percent: float
    seqno: int
    last_trade_time: str
    tick: str
    options: List[CBOEOption] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

@dataclass
class CBOEData:
    timestamp: str
    symbol: str
    data: CBOEStockData

    def to_dict(self):
        return asdict(self)
