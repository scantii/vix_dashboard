"""Walk-forward backtest with Tier A delta-scaled VIX option P&L proxy."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from vix_dashboard.config import AppConfig
from vix_dashboard.data.models import BacktestSummary, BacktestTrade, Regime, RegimeStats
from vix_dashboard.signals.regime import contango_fraction


def _regime_from_row(row: pd.Series, cfg: AppConfig) -> Regime:
    f0 = row.get("vx_front")
    f1 = row.get("vx_next")
    if f0 is None or f1 is None or f0 != f0 or f1 != f1:
        return Regime.UNKNOWN
    c = contango_fraction(Decimal(str(f0)), Decimal(str(f1)))
    if c is None:
        return Regime.UNKNOWN
    p = c * Decimal(100)
    th = cfg.regime
    if p >= th.contango_threshold_pct:
        return Regime.CONTANGO
    if p <= th.backwardation_threshold_pct:
        return Regime.BACKWARDATION
    if abs(p) <= th.flat_band_abs_pct:
        return Regime.FLAT
    return Regime.CONTANGO if c > 0 else Regime.BACKWARDATION


def _desired_side(row: pd.Series, vvix_pct: Decimal | None, vrp: Decimal | None, cfg: AppConfig) -> str | None:
    """long_call = long vol; long_put = short vol proxy."""
    if vrp is None:
        return None
    if vrp >= cfg.backtest.long_vol_vrp_min:
        return "long_call"
    if vrp <= cfg.backtest.short_vol_vrp_max and vvix_pct is not None:
        if vvix_pct >= cfg.backtest.min_vvix_pct_for_short_vol:
            return "long_put"
    return None


def _pnl_delta_proxy(entry_vix: float, exit_vix: float, side: str, cfg: AppConfig) -> Decimal:
    """Approximate P&L in dollars for one contract."""
    dvix = Decimal(str(exit_vix - entry_vix))
    delta = cfg.backtest.target_delta
    mult = cfg.backtest.dollars_per_vix_point
    sign = Decimal(1) if side == "long_call" else Decimal(-1)
    # Long put benefits when VIX falls (short vol)
    return sign * delta * dvix * mult


def run_walk_forward(panel: pd.DataFrame, cfg: AppConfig) -> BacktestSummary:
    """Replay daily; enter on signal when flat; hold fixed days."""
    df = panel.sort_values("date").reset_index(drop=True)
    if df.empty:
        return BacktestSummary(trades=[], by_regime={}, overall_win_rate=None, overall_avg_pnl=None)

    vvix = df["vvix"].astype(float)
    vix = df["vix"].astype(float)
    spx = df["spx"].astype(float)

    hv = pd.Series(index=df.index, dtype=float)
    if spx.notna().sum() > cfg.vrp.hv_window + 2:
        lr = pd.Series(np.log(spx / spx.shift(1)), index=df.index)
        hv = lr.rolling(cfg.vrp.hv_window).std() * (252**0.5) * 100.0

    trades: list[BacktestTrade] = []
    hold = cfg.backtest.hold_days
    i = 0
    n = len(df)
    while i < n:
        row = df.iloc[i]
        d = row["date"]
        if isinstance(d, pd.Timestamp):
            d_date = d.date()
        else:
            d_date = d
        regime = _regime_from_row(row, cfg)
        vrp_val: Decimal | None = None
        if hv.iloc[i] == hv.iloc[i] and vix.iloc[i] == vix.iloc[i]:
            vrp_val = Decimal(str(vix.iloc[i])) - Decimal(str(hv.iloc[i]))
        vvix_hist = vvix.iloc[:i]
        vvix_pct: Decimal | None = None
        if len(vvix_hist.dropna()) > 30 and vvix.iloc[i] == vvix.iloc[i]:
            arr = vvix_hist.dropna().values
            last = float(vvix.iloc[i])
            vvix_pct = Decimal(str(100.0 * (arr <= last).mean()))

        side = _desired_side(row, vvix_pct, vrp_val, cfg)
        if side and i + hold < n:
            entry_vix = float(vix.iloc[i])
            exit_row = df.iloc[i + hold]
            exit_vix = float(vix.iloc[i + hold])
            pnl = _pnl_delta_proxy(entry_vix, exit_vix, side, cfg)
            ed = df.iloc[i]["date"]
            xd = df.iloc[i + hold]["date"]
            trades.append(
                BacktestTrade(
                    entry_date=ed.date() if isinstance(ed, pd.Timestamp) else ed,
                    exit_date=xd.date() if isinstance(xd, pd.Timestamp) else xd,
                    regime=regime,
                    side=side,
                    pnl_dollars=pnl,
                    entry_vix=Decimal(str(entry_vix)),
                    exit_vix=Decimal(str(exit_vix)),
                )
            )
            i += hold
        else:
            i += 1

    by_regime: dict[Regime, RegimeStats] = {}
    for rg in Regime:
        sub = [t for t in trades if t.regime == rg]
        if not sub:
            by_regime[rg] = RegimeStats(rg, 0, None, None, None)
            continue
        wins = sum(1 for t in sub if t.pnl_dollars > 0)
        wr = Decimal(str(100.0 * wins / len(sub)))
        avg = sum((t.pnl_dollars for t in sub), Decimal(0)) / len(sub)
        # max drawdown of cumulative pnl
        cum = Decimal(0)
        peak = Decimal(0)
        max_dd = Decimal(0)
        for t in sub:
            cum += t.pnl_dollars
            peak = max(peak, cum)
            max_dd = min(max_dd, cum - peak)
        by_regime[rg] = RegimeStats(rg, len(sub), wr, avg, max_dd)

    overall_win_rate = None
    overall_avg = None
    if trades:
        wins = sum(1 for t in trades if t.pnl_dollars > 0)
        overall_win_rate = Decimal(str(100.0 * wins / len(trades)))
        overall_avg = sum((t.pnl_dollars for t in trades), Decimal(0)) / len(trades)

    return BacktestSummary(trades=trades, by_regime=by_regime, overall_win_rate=overall_win_rate, overall_avg_pnl=overall_avg)
