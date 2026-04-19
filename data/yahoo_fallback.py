"""Daily index history via Yahoo Finance when Tastytrade REST candles are unavailable."""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from vix_dashboard.config import SymbolConfig

logger = logging.getLogger(__name__)


def yahoo_ticker_for_index(sym: str, sc: SymbolConfig) -> str | None:
    """Map config index symbols to Yahoo tickers."""
    base = sym.lstrip("/").upper()
    m = {
        sc.vix_index.upper(): "^VIX",
        sc.vvix_index.upper(): "^VVIX",
        sc.spx_index.upper(): "^GSPC",
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
        col = "Close" if "Close" in df.columns else df.columns[0]
        s = df[col].dropna()
        s.index = pd.to_datetime(s.index).normalize()
        out[sym] = s.sort_index()
    return out
