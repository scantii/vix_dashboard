"""Domain dataclasses for the VIX dashboard."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


class Regime(str, Enum):
    CONTANGO = "contango"
    BACKWARDATION = "backwardation"
    FLAT = "flat"
    UNKNOWN = "unknown"


@dataclass
class FuturesContract:
    symbol: str
    expiration_date: date
    root: str
    active: bool
    last_trade_date: date | None = None
    exchange: str | None = None
    is_front_month: bool = False


@dataclass
class TermStructure:
    as_of: datetime
    contracts: list[FuturesContract]
    prices_by_symbol: dict[str, Decimal]
    spot_vix: Decimal | None
    ordered_tenors: list[str]
    contango_pct: Decimal | None
    regime: Regime


@dataclass
class VVIXReading:
    as_of: datetime
    vvix: Decimal
    pct_rank_252: Decimal | None
    ma_20: Decimal | None
    raw_history_len: int


@dataclass
class DataHealth:
    vvix_degraded: bool = False
    vx_chain_partial: bool = False
    spx_history_gap: bool = False
    auth_refresh_failed: bool = False
    history_partial: bool = False
    messages: list[str] = field(default_factory=list)

    def add(self, msg: str) -> None:
        self.messages.append(msg)


@dataclass
class Signal:
    timestamp: datetime
    regime: Regime
    contango_pct: Decimal | None
    vvix: VVIXReading | None
    vrp: Decimal | None
    hv20: Decimal | None
    rules_fired: list[str]
    health: DataHealth


@dataclass
class Candle:
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None


@dataclass
class QuoteSnapshot:
    symbol: str
    mark: Decimal | None
    bid: Decimal | None
    ask: Decimal | None
    updated_at: datetime | None


