"""Term-structure regime from front two VX futures."""

from __future__ import annotations

from decimal import Decimal

from vix_dashboard.config import AppConfig
from vix_dashboard.data.models import Regime, TermStructure


def classify_regime(ts: TermStructure, cfg: AppConfig) -> Regime:
    """Classify using contango_pct when present; else UNKNOWN."""
    p = ts.contango_pct
    if p is None:
        return Regime.UNKNOWN
    th = cfg.regime
    if p * Decimal(100) >= th.contango_threshold_pct:
        return Regime.CONTANGO
    if p * Decimal(100) <= th.backwardation_threshold_pct:
        return Regime.BACKWARDATION
    if abs(p) * Decimal(100) <= th.flat_band_abs_pct:
        return Regime.FLAT
    # Between flat band and thresholds: use sign of contango
    if p > 0:
        return Regime.CONTANGO
    if p < 0:
        return Regime.BACKWARDATION
    return Regime.FLAT


def contango_fraction(f0: Decimal, f1: Decimal) -> Decimal | None:
    """(F1 - F0) / F0."""
    if f0 <= 0:
        return None
    return (f1 - f0) / f0
