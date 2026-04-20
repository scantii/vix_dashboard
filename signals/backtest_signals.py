"""
Historical backtest over a merged daily panel (stub — populate with data loaders).

Pure structure only; implementations are intentionally left for later work.
"""

from __future__ import annotations

import pandas as pd


def run_backtest(df: pd.DataFrame) -> pd.DataFrame:
    """
    Expects df with columns:
      date, spx, vix, vvix, vix3m, vx_m1, vx_m2, vx_m3, vx_m4

    Returns:
      DataFrame with all signals calculated for each row,
      composite score, regime label, threshold crossing events,
      and forward returns (3d, 5d, 10d) for each crossing.

    Outputs summary statistics:
      - Hit rate per threshold crossing type
      - Median forward SPX return per regime transition
      - Median forward VIX change per regime transition
      - Signal lead time distribution (days before VIX spike >5pts)
      - False positive rate per threshold
    """
    return pd.DataFrame()


def load_cboe_csv(filepath: str) -> pd.DataFrame:
    """
    Parses CBOE-formatted CSV for VIX, VVIX, or VIX3M.
    Handles their date format and column naming.
    """
    return pd.DataFrame()


def load_vx_futures_history(filepath: str) -> pd.DataFrame:
    """
    Parses raw VX futures settlement data and maps each
    contract to its M1/M2/M3/M4 position by expiration date.
    """
    return pd.DataFrame()
