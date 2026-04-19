"""Historical volatility (HV20) and variance risk premium (VRP)."""

from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd

from vix_dashboard.config import AppConfig


def compute_hv20(spx_close: pd.Series, cfg: AppConfig) -> pd.Series:
    """Annualized HV from log returns, window from config."""
    w = cfg.vrp.hv_window
    ann = cfg.vrp.annualization
    log_ret = np.log(spx_close / spx_close.shift(1))
    hv = log_ret.rolling(w).std() * np.sqrt(float(ann)) * 100.0
    return hv


def compute_vrp(vix_spot: Decimal | None, hv20: float | None) -> Decimal | None:
    if vix_spot is None or hv20 is None or hv20 != hv20:
        return None
    return vix_spot - Decimal(str(hv20))
