"""Daily index history via Yahoo Finance when Tastytrade REST candles are unavailable."""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from vix_dashboard.config import SymbolConfig

logger = logging.getLogger(__name__)


def _extract_close_series(df: pd.DataFrame) -> pd.Series:
    """yfinance returns flat or MultiIndex columns depending on version/ticker count."""
    if df is None or df.empty:
        return pd.Series(dtype="float64")
    if isinstance(df.columns, pd.MultiIndex):
        if "Close" in df.columns.get_level_values(0):
            level = df["Close"]
            if isinstance(level, pd.DataFrame):
                return level.iloc[:, 0].dropna()
            return level.dropna()
        return df.iloc[:, -1].dropna()
    col = "Close" if "Close" in df.columns else df.columns[0]
    return df[col].dropna()


def yahoo_ticker_for_index(sym: str, sc: SymbolConfig) -> str | None:
    """Map config index symbols to Yahoo tickers."""
    base = sym.lstrip("/").upper()
    m = {
        sc.vix_index.upper(): "^VIX",
        sc.vvix_index.upper(): "^VVIX",
        sc.spx_index.upper(): "^GSPC",
        sc.vix3m_index.upper(): "^VIX3M",
    }
    return m.get(base)


def fetch_index_closes(
    symbols: list[str],
    sc: SymbolConfig,
    start: date,
    end: date,
) -> dict[str, pd.Series]:
    """
    Returns symbol -> daily close series (date index normalized, ascending).
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed; cannot backfill index history")
        return {}

    end_excl = end + timedelta(days=1)
    out: dict[str, pd.Series] = {}
    for sym in symbols:
        y = yahoo_ticker_for_index(sym, sc)
        if not y:
            continue
        try:
            df = yf.download(
                y,
                start=start.isoformat(),
                end=end_excl.isoformat(),
                interval="1d",
                progress=False,
                auto_adjust=True,
                threads=False,
            )
        except Exception as e:
            logger.debug("Yahoo download failed for %s: %s", y, e)
            continue
        if df is None or df.empty:
            continue
        s = _extract_close_series(df)
        s.index = pd.to_datetime(s.index).normalize()
        out[sym] = s.sort_index()
    return out


def fetch_vvix_sparkline(
    sc: SymbolConfig,
    last_n: int,
    *,
    end: date | None = None,
) -> pd.Series:
    """Last ``last_n`` trading days of VVIX from Yahoo (^VVIX), for chart fallback."""
    if not yahoo_ticker_for_index(sc.vvix_index, sc):
        return pd.Series(dtype="float64")
    end_d = end or date.today()
    start_d = end_d - timedelta(days=max(400, last_n * 3))
    m = fetch_index_closes([sc.vvix_index], sc, start_d, end_d)
    s = m.get(sc.vvix_index)
    if s is None or s.empty:
        return pd.Series(dtype="float64")
    return s.dropna().tail(last_n)
