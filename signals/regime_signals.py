"""
Pure regime / composite signal calculations from a daily panel DataFrame.

No side effects — dashboard and logger import and call these functions only.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from vix_dashboard.config import THRESHOLDS, AppConfig
from vix_dashboard.signals.vrp import compute_hv20

# Regime labels for composite score bands
REGIME_GREEN = "GREEN"
REGIME_YELLOW = "YELLOW"
REGIME_RED = "RED"
REGIME_BLACK = "BLACK"


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    if name in df.columns:
        return pd.to_numeric(df[name], errors="coerce")
    return pd.Series(np.nan, index=df.index, dtype="float64")


def _vx_mi(df: pd.DataFrame, i: int) -> pd.Series:
    c = f"vx_m{i}"
    if c in df.columns:
        return pd.to_numeric(df[c], errors="coerce")
    if i == 1 and "vx_front" in df.columns:
        return pd.to_numeric(df["vx_front"], errors="coerce")
    if i == 2 and "vx_next" in df.columns:
        return pd.to_numeric(df["vx_next"], errors="coerce")
    return pd.Series(np.nan, index=df.index, dtype="float64")


def _norm_window(th: dict[str, float]) -> int:
    w = int(th.get("normalize_window", 252))
    return max(1, w)


def rolling_min_max_norm(
    s: pd.Series,
    window: int,
    *,
    min_periods: int | None = None,
) -> pd.Series:
    """Min–max normalize each point using a trailing window (self-calibrating)."""
    w = max(1, window)
    mp = min_periods if min_periods is not None else max(10, min(w // 4, w))
    rmin = s.rolling(w, min_periods=mp).min()
    rmax = s.rolling(w, min_periods=mp).max()
    den = (rmax - rmin).replace(0, np.nan)
    out = (s - rmin) / den
    out = out.where(den.notna(), 0.5)
    return out.clip(lower=0.0, upper=1.0)


def rolling_min_max_norm_inverted(s: pd.Series, window: int, **kw: Any) -> pd.Series:
    """Higher when *raw* values are lower (danger when VRP is low)."""
    return 1.0 - rolling_min_max_norm(s, window, **kw)


def regime_label_from_score(score: float | None, th: dict[str, float] | None = None) -> str:
    th = th or THRESHOLDS
    if score is None or score != score:
        return REGIME_YELLOW
    gy = float(th["regime_green_yellow"])
    yr = float(th["regime_yellow_red"])
    bl = float(th["regime_red_entry"])
    if score < gy:
        return REGIME_GREEN
    if score < yr:
        return REGIME_YELLOW
    if score < bl:
        return REGIME_RED
    return REGIME_BLACK


def compute_regime_signals(
    panel: pd.DataFrame,
    cfg: AppConfig,
    thresholds: dict[str, float] | None = None,
) -> pd.DataFrame:
    """
    Compute all regime columns aligned to ``panel`` rows (sorted by date).

    Expects columns such as: date, vix, vvix, spx, vix3m, vx_m1..vx_m8 (or vx_front/vx_next).
    """
    th = thresholds or THRESHOLDS
    if panel.empty:
        return pd.DataFrame()

    df = panel.sort_values("date").copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df = df.set_index("date")

    vix = _col(df, "vix")
    vvix = _col(df, "vvix")
    spx = _col(df, "spx")
    vix3m = _col(df, "vix3m")

    m1 = _vx_mi(df, 1)
    m2 = _vx_mi(df, 2)
    m3 = _vx_mi(df, 3)
    m4 = _vx_mi(df, 4)

    slope = m1 - m2
    slope_lag3 = slope.shift(3)
    slope_roc_3d = (slope - slope_lag3) / slope_lag3.abs()
    slope_roc_3d = slope_roc_3d.where(slope_lag3.notna() & (slope_lag3.abs() > 1e-12))

    backwardation = slope > 0
    prev_roc = slope_roc_3d.shift(1)
    slope_flipping = (
        prev_roc.notna()
        & slope_roc_3d.notna()
        & (prev_roc * slope_roc_3d < 0)
    )

    term_denom = vix3m.where(vix3m.notna() & (vix3m > 0), m4)
    term_ratio = (vix / term_denom).where(term_denom.notna() & (term_denom > 0))

    tr_cont = float(th["term_ratio_contango_calm"])
    tr_back = float(th["term_ratio_backwardation"])
    tr_panic = float(th["term_ratio_panic"])
    trs = term_ratio
    term_band = pd.Series("neutral", index=df.index, dtype=object)
    term_band = term_band.mask(trs >= tr_panic, "panic")
    term_band = term_band.mask((trs >= tr_back) & (trs < tr_panic), "backwardation_stress")
    term_band = term_band.mask((trs >= tr_cont) & (trs < tr_back), "neutral")
    term_band = term_band.mask(trs < tr_cont, "contango_calm")

    vvix_l3 = vvix.shift(3)
    vvix_roc_3d = (vvix - vvix_l3) / vvix_l3
    vvix_roc_3d = vvix_roc_3d.where(vvix_l3.notna() & (vvix_l3.abs() > 1e-12))

    vix_l3 = vix.shift(3)
    vix_move_3d = (vix - vix_l3) / vix_l3.abs()
    vix_move_3d = vix_move_3d.where(vix_l3.notna() & (vix_l3.abs() > 1e-12))

    ew_roc = float(th["vvix_early_warning_roc"])
    ew_vix = float(th["vix_early_warning_max_move"])
    early_warning = (vvix_roc_3d > ew_roc) & (vix_move_3d.abs() <= ew_vix)

    spx_series = spx.copy()
    spx_series.index = pd.DatetimeIndex(spx_series.index)
    hv20 = compute_hv20(spx_series, cfg)
    hv20 = hv20.reindex(df.index)
    vrp = vix - hv20

    conv_denom = 2.0 * m2
    convexity = (m1 + m3) / conv_denom
    convexity = convexity.where(conv_denom.notna() & (conv_denom.abs() > 1e-12))

    dvix = vix.diff()
    rspx = np.log(spx / spx.shift(1))
    corr_10d = dvix.rolling(10, min_periods=5).corr(rspx)

    cbrk = float(th["correlation_breakdown"])
    correlation_breakdown = corr_10d > cbrk

    w = _norm_window(th)
    comp_slope = rolling_min_max_norm(slope_roc_3d, w)
    comp_vvix = rolling_min_max_norm(vvix_roc_3d, w)
    comp_term = rolling_min_max_norm(term_ratio, w)
    comp_vrp = rolling_min_max_norm_inverted(vrp, w)

    composite_score = (
        comp_slope * 0.25 + comp_vvix * 0.25 + comp_term * 0.25 + comp_vrp * 0.25
    ) * 100.0

    regime_lbl = composite_score.map(lambda x: regime_label_from_score(float(x) if pd.notna(x) else None, th))

    out = pd.DataFrame(
        {
            "slope": slope,
            "slope_roc_3d": slope_roc_3d,
            "backwardation_flag": backwardation,
            "slope_flipping": slope_flipping,
            "term_ratio": term_ratio,
            "term_structure_band": term_band,
            "vvix_roc_3d": vvix_roc_3d,
            "vix_move_3d": vix_move_3d,
            "early_warning_flag": early_warning,
            "hv20": hv20,
            "vrp": vrp,
            "convexity": convexity,
            "corr_10d": corr_10d,
            "correlation_breakdown": correlation_breakdown,
            "norm_slope": comp_slope,
            "norm_vvix_roc": comp_vvix,
            "norm_term_ratio": comp_term,
            "norm_vrp_inv": comp_vrp,
            "composite_score": composite_score,
            "regime_label": regime_lbl,
        },
        index=df.index,
    )
    return out


def score_crossing_events(
    score: pd.Series,
    th: dict[str, float] | None = None,
) -> pd.DataFrame:
    """
    Rows where composite score crosses key thresholds (for chart markers).

    Columns: date, crossing_kind (UP_35, UP_60, DOWN_50).
    """
    th = th or THRESHOLDS
    if score.empty:
        return pd.DataFrame(columns=["date", "crossing_kind"])

    gy = float(th["regime_green_yellow"])
    yr = float(th["regime_yellow_red"])
    ex = float(th["red_to_yellow_exit"])

    s = score.sort_index()
    prev = s.shift(1)
    rows: list[dict[str, object]] = []
    idx = s.index
    for i in range(1, len(s)):
        p = prev.iloc[i]
        c = s.iloc[i]
        if p != p or c != c:
            continue
        if p < gy <= c:
            rows.append({"date": idx[i], "crossing_kind": "UP_35"})
        if p < yr <= c:
            rows.append({"date": idx[i], "crossing_kind": "UP_60"})
        if p > ex >= c:
            rows.append({"date": idx[i], "crossing_kind": "DOWN_50"})
    return pd.DataFrame(rows)


def signal_row_statuses(row: pd.Series, th: dict[str, float] | None = None) -> dict[str, str]:
    """normal / watch / alert for dashboard rows (latest observation)."""
    th = th or THRESHOLDS
    tr_cont = float(th["term_ratio_contango_calm"])
    tr_back = float(th["term_ratio_backwardation"])
    tr_panic = float(th["term_ratio_panic"])
    vrp_f = float(th["vrp_favorable"])

    def _tri(cond_a: Any, cond_w: Any) -> str:
        if bool(cond_a):
            return "alert"
        if bool(cond_w):
            return "watch"
        return "normal"

    out: dict[str, str] = {}
    sl = row.get("slope")
    out["VX curve slope"] = _tri(
        bool(row.get("backwardation_flag")) or bool(row.get("slope_flipping")),
        (not bool(row.get("backwardation_flag")))
        and sl is not None
        and sl == sl
        and abs(float(sl)) > 0.25,
    )
    tr = row.get("term_ratio")
    if tr is not None and tr == tr:
        trf = float(tr)
        if trf >= tr_panic:
            out["VIX term ratio"] = "alert"
        elif trf >= tr_back:
            out["VIX term ratio"] = "watch"
        elif trf >= tr_cont:
            out["VIX term ratio"] = "watch"
        else:
            out["VIX term ratio"] = "normal"
    else:
        out["VIX term ratio"] = "normal"

    out["VVIX velocity"] = _tri(
        bool(row.get("early_warning_flag")),
        pd.notna(row.get("vvix_roc_3d")) and abs(float(row["vvix_roc_3d"])) > 0.05,
    )
    vrp = row.get("vrp")
    if vrp is not None and vrp == vrp:
        vf = float(vrp)
        out["VRP"] = _tri(vf < 0, 0 <= vf < vrp_f)
    else:
        out["VRP"] = "normal"

    cx = row.get("convexity")
    if cx is not None and cx == cx:
        out["Curve convexity"] = _tri(float(cx) < 1.0, float(cx) < 1.02)
    else:
        out["Curve convexity"] = "normal"

    out["VIX/SPX corr"] = _tri(
        bool(row.get("correlation_breakdown")),
        pd.notna(row.get("corr_10d")) and float(row["corr_10d"]) > -0.6,
    )
    return out
