"""Assemble live term structure and quotes into domain models."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from vix_dashboard.config import AppConfig
from vix_dashboard.data.models import FuturesContract, QuoteSnapshot, Regime, TermStructure
from vix_dashboard.signals.regime import classify_regime, contango_fraction


def _mid(q: QuoteSnapshot) -> Decimal | None:
    if q.mark is not None:
        return q.mark
    if q.bid is not None and q.ask is not None:
        return (q.bid + q.ask) / Decimal(2)
    return q.bid or q.ask


def build_term_structure(
    contracts: list[FuturesContract],
    quotes: dict[str, QuoteSnapshot],
    spot_vix: Decimal | None,
    cfg: AppConfig,
    as_of: datetime | None = None,
) -> TermStructure:
    """Take first N active contracts by expiration; compute contango from front two."""
    now = as_of or datetime.now(timezone.utc)
    active = [c for c in contracts if c.active]
    active.sort(key=lambda c: c.expiration_date)
    front = active[: cfg.term_structure_months]
    prices: dict[str, Decimal] = {}
    ordered: list[str] = []
    for i, c in enumerate(front):
        sym = c.symbol
        q = quotes.get(sym) or quotes.get(sym.lstrip("/")) or quotes.get("/" + sym.lstrip("/"))
        if q:
            m = _mid(q)
            if m is not None:
                prices[sym] = m
                ordered.append(f"M{i+1}:{sym}")
        c.is_front_month = i == 0

    contango: Decimal | None = None
    if len(front) >= 2:
        p0 = prices.get(front[0].symbol)
        p1 = prices.get(front[1].symbol)
        if p0 is not None and p1 is not None:
            contango = contango_fraction(p0, p1)

    ts = TermStructure(
        as_of=now,
        contracts=front,
        prices_by_symbol=prices,
        spot_vix=spot_vix,
        ordered_tenors=ordered,
        contango_pct=contango,
        regime=Regime.UNKNOWN,
    )
    ts.regime = classify_regime(ts, cfg)
    return ts
