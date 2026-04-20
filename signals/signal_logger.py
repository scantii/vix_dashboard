"""
Append-only CSV + SQLite logging for regime signals and threshold crossings.

Side effects are confined to this module (dashboard calls it after pure calcs).
"""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from vix_dashboard.config import THRESHOLDS

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
SIGNAL_LOG_CSV = PACKAGE_ROOT / "regime_signal_log.csv"
THRESHOLD_CROSSINGS_CSV = PACKAGE_ROOT / "threshold_crossings.csv"
SIGNAL_DB_PATH = PACKAGE_ROOT / "regime_signals.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(SIGNAL_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_signal_db() -> None:
    """Create SQLite schema if missing (idempotent)."""
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS daily_signal_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                observation_date TEXT NOT NULL,
                composite_score REAL,
                regime_label TEXT,
                score_3d_change REAL,
                slope REAL,
                slope_roc_3d REAL,
                backwardation_flag INTEGER,
                term_ratio REAL,
                vvix_roc_3d REAL,
                early_warning_flag INTEGER,
                vrp REAL,
                hv20 REAL,
                convexity REAL,
                corr_10d REAL,
                spx_price REAL,
                vix_level REAL,
                vvix_level REAL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_obs_date
                ON daily_signal_log(observation_date);

            CREATE TABLE IF NOT EXISTS threshold_crossings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                crossing_type TEXT NOT NULL,
                observation_date TEXT NOT NULL,
                composite_score REAL,
                regime_label TEXT,
                score_3d_change REAL,
                slope REAL,
                slope_roc_3d REAL,
                backwardation_flag INTEGER,
                term_ratio REAL,
                vvix_roc_3d REAL,
                early_warning_flag INTEGER,
                vrp REAL,
                hv20 REAL,
                convexity REAL,
                corr_10d REAL,
                spx_price REAL,
                vix_level REAL,
                vvix_level REAL,
                spx_return_3d REAL,
                spx_return_5d REAL,
                spx_return_10d REAL,
                vix_change_3d REAL,
                vix_change_5d REAL
            );

            CREATE TABLE IF NOT EXISTS regime_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def _bool_int(x: Any) -> int:
    return 1 if bool(x) else 0


def _float_or_none(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v:
        return None
    return v


@dataclass
class LogSnapshot:
    observation_date: date
    composite_score: float | None
    regime_label: str | None
    score_3d_change: float | None
    slope: float | None
    slope_roc_3d: float | None
    backwardation_flag: bool
    term_ratio: float | None
    vvix_roc_3d: float | None
    early_warning_flag: bool
    vrp: float | None
    hv20: float | None
    convexity: float | None
    corr_10d: float | None
    spx_price: float | None
    vix_level: float | None
    vvix_level: float | None


def build_log_snapshot(
    panel_row: pd.Series,
    sig_row: pd.Series,
    score_3d_change: float | None,
) -> LogSnapshot:
    d = pd.Timestamp(panel_row["date"]).date()
    return LogSnapshot(
        observation_date=d,
        composite_score=_float_or_none(sig_row.get("composite_score")),
        regime_label=str(sig_row["regime_label"]) if pd.notna(sig_row.get("regime_label")) else None,
        score_3d_change=score_3d_change,
        slope=_float_or_none(sig_row.get("slope")),
        slope_roc_3d=_float_or_none(sig_row.get("slope_roc_3d")),
        backwardation_flag=bool(sig_row.get("backwardation_flag")),
        term_ratio=_float_or_none(sig_row.get("term_ratio")),
        vvix_roc_3d=_float_or_none(sig_row.get("vvix_roc_3d")),
        early_warning_flag=bool(sig_row.get("early_warning_flag")),
        vrp=_float_or_none(sig_row.get("vrp")),
        hv20=_float_or_none(sig_row.get("hv20")),
        convexity=_float_or_none(sig_row.get("convexity")),
        corr_10d=_float_or_none(sig_row.get("corr_10d")),
        spx_price=_float_or_none(panel_row.get("spx")),
        vix_level=_float_or_none(panel_row.get("vix")),
        vvix_level=_float_or_none(panel_row.get("vvix")),
    )


def _append_csv_row(path: Path, fieldnames: list[str], row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if new_file:
            w.writeheader()
        w.writerow(row)


def append_daily_signal_log(
    snap: LogSnapshot,
    *,
    now: datetime | None = None,
) -> bool:
    """
    Append one daily observation if we have not already logged ``observation_date``.

    Returns True if a row was written.
    """
    init_signal_db()
    ts = now or datetime.now(timezone.utc)
    obs = snap.observation_date.isoformat()

    conn = _connect()
    try:
        cur = conn.execute(
            "SELECT 1 FROM daily_signal_log WHERE observation_date = ? LIMIT 1",
            (obs,),
        )
        if cur.fetchone() is not None:
            return False

        row = {
            "timestamp": ts.isoformat(),
            "observation_date": obs,
            "composite_score": snap.composite_score,
            "regime_label": snap.regime_label,
            "score_3d_change": snap.score_3d_change,
            "slope": snap.slope,
            "slope_roc_3d": snap.slope_roc_3d,
            "backwardation_flag": _bool_int(snap.backwardation_flag),
            "term_ratio": snap.term_ratio,
            "vvix_roc_3d": snap.vvix_roc_3d,
            "early_warning_flag": _bool_int(snap.early_warning_flag),
            "vrp": snap.vrp,
            "hv20": snap.hv20,
            "convexity": snap.convexity,
            "corr_10d": snap.corr_10d,
            "spx_price": snap.spx_price,
            "vix_level": snap.vix_level,
            "vvix_level": snap.vvix_level,
        }
        conn.execute(
            """
            INSERT INTO daily_signal_log (
                timestamp, observation_date, composite_score, regime_label, score_3d_change,
                slope, slope_roc_3d, backwardation_flag, term_ratio, vvix_roc_3d,
                early_warning_flag, vrp, hv20, convexity, corr_10d,
                spx_price, vix_level, vvix_level
            ) VALUES (
                :timestamp, :observation_date, :composite_score, :regime_label, :score_3d_change,
                :slope, :slope_roc_3d, :backwardation_flag, :term_ratio, :vvix_roc_3d,
                :early_warning_flag, :vrp, :hv20, :convexity, :corr_10d,
                :spx_price, :vix_level, :vvix_level
            )
            """,
            row,
        )
        conn.commit()
    finally:
        conn.close()

    fields = list(row.keys())
    _append_csv_row(SIGNAL_LOG_CSV, fields, row)
    return True


def _get_state(conn: sqlite3.Connection, key: str) -> str | None:
    cur = conn.execute("SELECT value FROM regime_state WHERE key = ?", (key,))
    r = cur.fetchone()
    return str(r[0]) if r else None


def _set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO regime_state(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def process_threshold_crossings(
    snap: LogSnapshot,
    thresholds: dict[str, float] | None = None,
    *,
    now: datetime | None = None,
) -> list[str]:
    """
    Emit threshold crossing rows when edges are detected vs persisted state.

    Returns list of crossing_type strings written.
    """
    th = thresholds or THRESHOLDS
    init_signal_db()
    ts = now or datetime.now(timezone.utc)
    written: list[str] = []

    conn = _connect()
    try:
        prev_score_s = _get_state(conn, "prev_composite_score")
        prev_back_s = _get_state(conn, "prev_backwardation")
        prev_ew_s = _get_state(conn, "prev_early_warning")

        prev_score: float | None
        if prev_score_s is None or prev_score_s.lower() == "nan":
            prev_score = None
        else:
            try:
                prev_score = float(prev_score_s)
            except ValueError:
                prev_score = None
            if prev_score is not None and prev_score != prev_score:
                prev_score = None
        cur_score = snap.composite_score

        gy = float(th["regime_green_yellow"])
        yr = float(th["regime_yellow_red"])
        ex = float(th["red_to_yellow_exit"])

        def _emit(crossing_type: str) -> None:
            row = {
                "timestamp": ts.isoformat(),
                "crossing_type": crossing_type,
                "observation_date": snap.observation_date.isoformat(),
                "composite_score": snap.composite_score,
                "regime_label": snap.regime_label,
                "score_3d_change": snap.score_3d_change,
                "slope": snap.slope,
                "slope_roc_3d": snap.slope_roc_3d,
                "backwardation_flag": _bool_int(snap.backwardation_flag),
                "term_ratio": snap.term_ratio,
                "vvix_roc_3d": snap.vvix_roc_3d,
                "early_warning_flag": _bool_int(snap.early_warning_flag),
                "vrp": snap.vrp,
                "hv20": snap.hv20,
                "convexity": snap.convexity,
                "corr_10d": snap.corr_10d,
                "spx_price": snap.spx_price,
                "vix_level": snap.vix_level,
                "vvix_level": snap.vvix_level,
                "spx_return_3d": None,
                "spx_return_5d": None,
                "spx_return_10d": None,
                "vix_change_3d": None,
                "vix_change_5d": None,
            }
            conn.execute(
                """
                INSERT INTO threshold_crossings (
                    timestamp, crossing_type, observation_date, composite_score, regime_label, score_3d_change,
                    slope, slope_roc_3d, backwardation_flag, term_ratio, vvix_roc_3d, early_warning_flag,
                    vrp, hv20, convexity, corr_10d, spx_price, vix_level, vvix_level,
                    spx_return_3d, spx_return_5d, spx_return_10d, vix_change_3d, vix_change_5d
                ) VALUES (
                    :timestamp, :crossing_type, :observation_date, :composite_score, :regime_label, :score_3d_change,
                    :slope, :slope_roc_3d, :backwardation_flag, :term_ratio, :vvix_roc_3d, :early_warning_flag,
                    :vrp, :hv20, :convexity, :corr_10d, :spx_price, :vix_level, :vvix_level,
                    :spx_return_3d, :spx_return_5d, :spx_return_10d, :vix_change_3d, :vix_change_5d
                )
                """,
                row,
            )
            fields = list(row.keys())
            _append_csv_row(THRESHOLD_CROSSINGS_CSV, fields, row)
            written.append(crossing_type)

        if prev_score is not None and cur_score is not None and cur_score == cur_score:
            ps = prev_score
            cs = float(cur_score)
            if ps < gy <= cs:
                _emit("GREEN_TO_YELLOW")
            if ps < yr <= cs:
                _emit("YELLOW_TO_RED")
            if ps > ex >= cs:
                _emit("RED_TO_YELLOW")

        prev_back = prev_back_s == "1" if prev_back_s is not None else None
        if prev_back is not None and (not prev_back) and snap.backwardation_flag:
            _emit("BACKWARDATION_FLIP")

        prev_ew = prev_ew_s == "1" if prev_ew_s is not None else None
        if prev_ew is not None and (not prev_ew) and snap.early_warning_flag:
            _emit("EARLY_WARNING")

        if cur_score is not None and cur_score == cur_score:
            _set_state(conn, "prev_composite_score", f"{float(cur_score):.8f}")
        _set_state(conn, "prev_backwardation", "1" if snap.backwardation_flag else "0")
        _set_state(conn, "prev_early_warning", "1" if snap.early_warning_flag else "0")

        conn.commit()
    finally:
        conn.close()

    return written


def _panel_sorted(panel: pd.DataFrame) -> pd.DataFrame:
    if panel.empty:
        return panel
    out = panel.sort_values("date").copy()
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    return out


def _nth_future_value(panel: pd.DataFrame, start_ts: pd.Timestamp, n: int, col: str) -> float | None:
    sub = _panel_sorted(panel)
    sub = sub[sub["date"] >= start_ts].dropna(subset=[col])
    if sub.empty or n >= len(sub):
        return None
    v = sub.iloc[n][col]
    if pd.isna(v):
        return None
    return float(v)


def update_forward_returns(panel: pd.DataFrame) -> int:
    """
    Backfill forward return columns on threshold crossing rows when enough
    trading history exists in ``panel``.
    """
    init_signal_db()
    if panel.empty:
        return 0

    panel = _panel_sorted(panel)
    conn = _connect()
    updated = 0
    try:
        cur = conn.execute(
            """
            SELECT id, observation_date, spx_return_3d, spx_return_5d, spx_return_10d, vix_change_3d, vix_change_5d
            FROM threshold_crossings
            WHERE spx_return_3d IS NULL OR spx_return_5d IS NULL OR spx_return_10d IS NULL
               OR vix_change_3d IS NULL OR vix_change_5d IS NULL
            """
        )
        rows = cur.fetchall()
        for r in rows:
            rid = int(r["id"])
            start = pd.Timestamp(r["observation_date"]).normalize()

            spx0 = _nth_future_value(panel, start, 0, "spx")
            vix0 = _nth_future_value(panel, start, 0, "vix")
            if spx0 is None or spx0 == 0:
                continue

            vals: dict[str, float | None] = {}

            if r["spx_return_3d"] is None:
                spx3 = _nth_future_value(panel, start, 3, "spx")
                if spx3 is not None:
                    vals["spx_return_3d"] = spx3 / spx0 - 1.0
            if r["spx_return_5d"] is None:
                spx5 = _nth_future_value(panel, start, 5, "spx")
                if spx5 is not None:
                    vals["spx_return_5d"] = spx5 / spx0 - 1.0
            if r["spx_return_10d"] is None:
                spx10 = _nth_future_value(panel, start, 10, "spx")
                if spx10 is not None:
                    vals["spx_return_10d"] = spx10 / spx0 - 1.0

            if r["vix_change_3d"] is None and vix0 is not None:
                vix3 = _nth_future_value(panel, start, 3, "vix")
                if vix3 is not None:
                    vals["vix_change_3d"] = vix3 - vix0
            if r["vix_change_5d"] is None and vix0 is not None:
                vix5 = _nth_future_value(panel, start, 5, "vix")
                if vix5 is not None:
                    vals["vix_change_5d"] = vix5 - vix0

            if not vals:
                continue

            sets = ", ".join(f"{k} = ?" for k in vals)
            args = list(vals.values()) + [rid]
            conn.execute(f"UPDATE threshold_crossings SET {sets} WHERE id = ?", args)
            updated += 1

        conn.commit()
    finally:
        conn.close()

    # Also refresh CSV file from DB tail — keep CSV in sync for rows updated (optional).
    # For simplicity, CSV remains append-only at write time; DB is source of truth for backfills.
    return updated


def ensure_initial_regime_state(snap: LogSnapshot) -> None:
    """On first run, seed persisted edge-detection state from the current snapshot."""
    init_signal_db()
    conn = _connect()
    try:
        cur = conn.execute("SELECT COUNT(*) FROM regime_state")
        if int(cur.fetchone()[0]) > 0:
            return
        if snap.composite_score is not None and snap.composite_score == snap.composite_score:
            _set_state(conn, "prev_composite_score", f"{float(snap.composite_score):.8f}")
        else:
            _set_state(conn, "prev_composite_score", "nan")
        _set_state(conn, "prev_backwardation", "1" if snap.backwardation_flag else "0")
        _set_state(conn, "prev_early_warning", "1" if snap.early_warning_flag else "0")
        conn.commit()
    finally:
        conn.close()
