"""VVIX rolling percentile and moving average."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import numpy as np
import pandas as pd

from vix_dashboard.config import AppConfig
from vix_dashboard.data.models import VVIXReading


@dataclass
class VVIXFeatures:
    as_of: datetime
    level: Decimal
    pct_rank_252: Decimal | None
    ma_20: Decimal | None
    history_len: int


def compute_vvix_features(
    vvix_series: pd.Series,
    as_of: datetime,
    cfg: AppConfig,
) -> VVIXFeatures:
    """
    vvix_series: daily closes indexed by date (Timestamp), sorted.
    Percentile rank uses prior closes strictly before as_of date (no lookahead).
    """
    day = pd.Timestamp(as_of.date())
    s = vvix_series.sort_index()
    prior = s[s.index < day].dropna()
    n = cfg.vvix.rolling_days
    tail = prior.iloc[-n:] if len(prior) >= n else prior
    level = s.get(day, np.nan)
    if level != level:  # nan
        level = prior.iloc[-1] if len(prior) else np.nan
    hist_len = len(prior)
    pct: Decimal | None = None
    if hist_len >= 2 and level == level:
        arr = tail.values.astype(float)
        last = float(level)
        pct = Decimal(str(100.0 * float(np.mean(arr <= last))))
    ma20: Decimal | None = None
    if len(prior) >= cfg.vvix.ma_days:
        ma20 = Decimal(str(float(prior.iloc[-cfg.vvix.ma_days :].mean())))
    lev_dec = Decimal(str(float(level))) if level == level else Decimal(0)
    return VVIXFeatures(
        as_of=as_of,
        level=lev_dec,
        pct_rank_252=pct,
        ma_20=ma20,
        history_len=hist_len,
    )


def features_to_reading(f: VVIXFeatures) -> VVIXReading:
    return VVIXReading(
        as_of=f.as_of,
        vvix=f.level,
        pct_rank_252=f.pct_rank_252,
        ma_20=f.ma_20,
        raw_history_len=f.history_len,
    )
