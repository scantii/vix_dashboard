"""Aggregate health + sub-signals into a single Signal DTO."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pandas as pd

from vix_dashboard.config import AppConfig
from vix_dashboard.data.models import DataHealth, Regime, Signal, TermStructure, VVIXReading
from vix_dashboard.signals.vrp import compute_hv20, compute_vrp
from vix_dashboard.signals.vvix_signal import compute_vvix_features, features_to_reading


def build_live_signal(
    ts: TermStructure | None,
    vvix_series: pd.Series | None,
    spx_series: pd.Series | None,
    now: datetime,
    health: DataHealth,
    cfg: AppConfig,
) -> Signal:
    """Compose regime, VVIX features, VRP for the current instant."""
    rules: list[str] = []
    regime = ts.regime if ts else Regime.UNKNOWN
    contango = ts.contango_pct * Decimal(100) if ts and ts.contango_pct is not None else None
    if contango is not None:
        rules.append(f"Contango {contango:.2f}% (thresholds in config)")

    vvix_read: VVIXReading | None = None
    if vvix_series is not None and not vvix_series.empty:
        feat = compute_vvix_features(vvix_series, now, cfg)
        vvix_read = features_to_reading(feat)
        if feat.pct_rank_252 is not None:
            rules.append(f"VVIX pct rank ~{feat.pct_rank_252:.1f}")
    else:
        health.vvix_degraded = True
        health.add("VVIX history unavailable for features")

    hv20_f: float | None = None
    if spx_series is not None and len(spx_series.dropna()) > cfg.vrp.hv_window + 1:
        hv = compute_hv20(spx_series, cfg)
        last = hv.iloc[-1]
        hv20_f = float(last) if last == last else None

    vix_spot = ts.spot_vix if ts else None
    vrp = compute_vrp(vix_spot, hv20_f)
    if vrp is not None:
        rules.append(f"VRP (VIX - HV{cfg.vrp.hv_window}) ≈ {vrp:.2f}")

    hv_dec = Decimal(str(hv20_f)) if hv20_f is not None else None

    return Signal(
        regime=regime,
        contango_pct=contango,
        vvix=vvix_read,
        vrp=vrp,
        hv20=hv_dec,
        rules_fired=rules,
    )
