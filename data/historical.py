"""Source-agnostic historical data: Tastytrade REST + CSV fallback + merge."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from vix_dashboard.config import AppConfig
from vix_dashboard.data.fetcher import FetcherError, fetch_history_candles, list_vx_futures
from vix_dashboard.data.models import Candle, FuturesContract
from vix_dashboard.data.yahoo_fallback import fetch_index_closes
from vix_dashboard.auth.tasty_auth import TastyAuth

logger = logging.getLogger(__name__)


def _candles_to_series(candles: list[Candle]) -> pd.Series:
    s = pd.Series(
        {pd.Timestamp(c.ts.date()): float(c.close) for c in candles},
        dtype="float64",
    )
    s.index = pd.to_datetime(s.index).normalize()
    return s.sort_index()


def _read_panel_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    for col in ("vix", "vvix", "spx", "vix3m", "vx_front", "vx_next"):
        if col not in df.columns:
            df[col] = pd.NA
    for k in range(1, 9):
        c = f"vx_m{k}"
        if c not in df.columns:
            df[c] = pd.NA
    return df.sort_values("date")


class CsvHistoricalProvider:
    """Panel CSV: date,vix,vvix,spx,vx_front,vx_next (optional columns)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def get_daily_panel(self, start: date, end: date) -> tuple[pd.DataFrame, list[str]]:
        if not self.path.exists():
            return pd.DataFrame(), [f"CSV missing: {self.path}"]
        df = _read_panel_csv(self.path)
        mask = (df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))
        return df.loc[mask].copy(), []


class TastyHistoricalProvider:
    """Pull daily candles from Tastytrade and assemble a term-structure panel."""

    def __init__(self, auth: TastyAuth, cfg: AppConfig) -> None:
        self.auth = auth
        self.cfg = cfg

    def get_daily_panel(
        self,
        start: date,
        end: date,
        *,
        vx_contracts: list[FuturesContract] | None = None,
    ) -> tuple[pd.DataFrame, list[str]]:
        notes: list[str] = []
        sc = self.cfg.symbols
        idx_type = sc.index_instrument_type
        fut_type = sc.future_instrument_type

        def load(sym: str) -> pd.Series:
            try:
                c = fetch_history_candles(
                    self.auth,
                    self.cfg,
                    symbol=sym,
                    instrument_type=idx_type,
                    start=start,
                    end=end,
                    interval="1d",
                )
            except FetcherError as e:
                notes.append(f"{sym}: {e}")
                c = []
            if c:
                return _candles_to_series(c)
            ymap = fetch_index_closes([sym], sc, start, end)
            if sym in ymap and not ymap[sym].empty:
                notes.append(
                    f"{sym}: filled from Yahoo Finance (Tasty candle history unavailable)"
                )
                return ymap[sym]
            notes.append(f"{sym}: empty history")
            return pd.Series(dtype="float64")

        vix_s = load(sc.vix_index)
        vvix_s = load(sc.vvix_index)
        spx_s = load(sc.spx_index)
        vix3m_s = load(sc.vix3m_index)
        if vix3m_s.empty:
            y3 = fetch_index_closes([sc.vix3m_index], sc, start, end)
            vix3m_s = y3.get(sc.vix3m_index, pd.Series(dtype="float64"))

        if vx_contracts is not None:
            contracts = [c for c in vx_contracts if c.expiration_date >= start]
        else:
            try:
                contracts = [c for c in list_vx_futures(self.auth, self.cfg) if c.expiration_date >= start]
            except FetcherError as e:
                notes.append(f"futures list: {e}")
                contracts = []

        contracts.sort(key=lambda x: x.expiration_date)
        # Limit to reasonable number of contracts to query
        contracts = contracts[:24]

        fut_frames: dict[str, pd.Series] = {}
        for c in contracts:
            try:
                sym = c.symbol.lstrip("/")
                candles = fetch_history_candles(
                    self.auth,
                    self.cfg,
                    symbol=sym,
                    instrument_type=fut_type,
                    start=start,
                    end=min(end, c.expiration_date),
                    interval="1d",
                )
                if candles:
                    fut_frames[sym] = _candles_to_series(candles)
            except FetcherError as e:
                notes.append(f"{sym}: {e}")

        idx_set: set[pd.Timestamp] = set()
        for s in (vix_s, vvix_s, spx_s, vix3m_s):
            idx_set |= set(s.index)
        for s in fut_frames.values():
            idx_set |= set(s.index)
        all_dates = pd.DatetimeIndex(sorted(idx_set))
        if all_dates.empty:
            return pd.DataFrame(), notes + ["no dates from API"]

        exp_by_sym = {c.symbol.lstrip("/"): c.expiration_date for c in contracts}
        rows: list[dict[str, object]] = []
        for d_ts in all_dates:
            d = d_ts.date()
            if d < start or d > end:
                continue
            vx_front: float | None = None
            vx_next: float | None = None
            eligible = [sym for sym in exp_by_sym if exp_by_sym[sym] > d and sym in fut_frames]
            eligible.sort(key=lambda s: exp_by_sym[s])
            vx_months: dict[str, float | None] = {}
            for mi in range(1, 9):
                key = f"vx_m{mi}"
                if len(eligible) >= mi:
                    sym_i = eligible[mi - 1]
                    vi = fut_frames[sym_i].get(d_ts, float("nan"))
                    vx_months[key] = None if vi != vi else float(vi)
                else:
                    vx_months[key] = None
            if len(eligible) >= 1:
                s0 = eligible[0]
                v0 = fut_frames[s0].get(d_ts, float("nan"))
                vx_front = None if v0 != v0 else v0
            if len(eligible) >= 2:
                s1 = eligible[1]
                v1 = fut_frames[s1].get(d_ts, float("nan"))
                vx_next = None if v1 != v1 else v1

            v3 = vix3m_s.get(d_ts, float("nan"))
            vix3m_v = None if v3 != v3 else float(v3)

            row = {
                "date": d_ts,
                "vix": vix_s.get(d_ts, float("nan")),
                "vvix": vvix_s.get(d_ts, float("nan")),
                "spx": spx_s.get(d_ts, float("nan")),
                "vix3m": vix3m_v,
                "vx_front": vx_front,
                "vx_next": vx_next,
            }
            row.update(vx_months)
            rows.append(row)

        df = pd.DataFrame(rows)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        return df, notes


class ChainedHistoricalProvider:
    """Try primary (Tasty); fill gaps from CSV panel if configured."""

    def __init__(
        self,
        primary: TastyHistoricalProvider,
        csv: CsvHistoricalProvider | None,
    ) -> None:
        self.primary = primary
        self.csv = csv

    def get_daily_panel(
        self,
        start: date,
        end: date,
        *,
        vx_contracts: list[FuturesContract] | None = None,
    ) -> tuple[pd.DataFrame, list[str]]:
        df, notes = self.primary.get_daily_panel(start, end, vx_contracts=vx_contracts)
        if self.csv is None:
            return df, notes
        cdf, cnotes = self.csv.get_daily_panel(start, end)
        notes.extend(cnotes)
        if cdf.empty:
            return df, notes
        if df.empty:
            return cdf, notes
        cdf = cdf.set_index("date")
        df = df.set_index("date")
        merge_cols = ["vix", "vvix", "spx", "vix3m", "vx_front", "vx_next"]
        merge_cols += [f"vx_m{k}" for k in range(1, 9)]
        for col in merge_cols:
            if col in cdf.columns:
                df[col] = df[col].combine_first(cdf[col])
        df = df.reset_index()
        return df, notes
