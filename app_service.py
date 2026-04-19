"""Orchestration: fetch → models → signals → figures (no Dash imports here)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
import plotly.graph_objects as go
from dash import html

from vix_dashboard.auth.tasty_auth import AuthError, TastyAuth
from vix_dashboard.config import AppConfig
from vix_dashboard.data.fetcher import FetcherError, fetch_quotes_by_type, list_vx_futures
from vix_dashboard.data.historical import (
    ChainedHistoricalProvider,
    CsvHistoricalProvider,
    TastyHistoricalProvider,
)
from vix_dashboard.data.live_bundle import build_term_structure
from vix_dashboard.data.models import DataHealth
from vix_dashboard.data.yahoo_fallback import fetch_vvix_sparkline
from vix_dashboard.signals.signal_output import build_live_signal
from vix_dashboard.viz.signal_panel import make_health_banner, make_signal_summary_div
from vix_dashboard.viz.spx_panel import make_spx_figure
from vix_dashboard.viz.term_structure import make_term_structure_figure
from vix_dashboard.viz.vvix_panel import make_vvix_figure

logger = logging.getLogger(__name__)


def _auth_optional(cfg: AppConfig) -> TastyAuth | None:
    try:
        return TastyAuth(cfg.api)
    except (AuthError, RuntimeError) as e:
        logger.warning("Auth not configured: %s", e)
        return None


def _spot_vix(quotes: dict, sym: str) -> object | None:
    keys = (sym, sym.upper(), f"${sym.lstrip('$')}", f"${sym}")
    for k in keys:
        if k in quotes:
            q = quotes[k]
            return q.mark or q.bid or q.ask
    base = sym.lstrip("$").upper()
    for k, q in quotes.items():
        if k.replace("$", "").upper() == base:
            return q.mark or q.bid or q.ask
    return None


def refresh_dashboard(cfg: AppConfig, auth: TastyAuth | None) -> tuple:
    """
    Returns tuple for Dash outputs:
    health, ts_fig, vvix_fig, spx_fig, signal_div, last_updated
    """
    health = DataHealth()
    now = datetime.now(timezone.utc)
    if auth is None:
        health.auth_refresh_failed = True
        health.add("Set TT_SECRET and TT_REFRESH for live data.")
        empty = go.Figure()
        return (
            make_health_banner(health),
            make_term_structure_figure(None, None),
            make_vvix_figure(None),
            make_spx_figure(),
            html.Div("No auth"),
            now.isoformat(),
        )

    sc = cfg.symbols
    try:
        contracts = list_vx_futures(auth, cfg)
    except FetcherError as e:
        health.vx_chain_partial = True
        health.add(str(e))
        contracts = []

    front = sorted(contracts, key=lambda x: x.expiration_date)[: cfg.term_structure_months]
    front_syms = [c.symbol if c.symbol.startswith("/") else "/" + c.symbol.lstrip("/") for c in front]
    indices = [sc.vix_index, sc.vvix_index, sc.spx_index]
    try:
        quotes = fetch_quotes_by_type(
            auth,
            cfg,
            indices=indices,
            futures=front_syms,
        )
    except FetcherError as e:
        health.add(str(e))
        quotes = {}

    spot = _spot_vix(quotes, sc.vix_index)
    spot_dec = Decimal(str(float(spot))) if spot is not None else None
    ts = build_term_structure(contracts, quotes, spot_dec, cfg, as_of=now) if contracts else None

    end = date.today()
    start = end - timedelta(days=400)
    csvp = None
    if cfg.csv.panel_path:
        csvp = CsvHistoricalProvider(cfg.csv.panel_path)
    tasty_h = TastyHistoricalProvider(auth, cfg)
    chain = ChainedHistoricalProvider(tasty_h, csvp)
    panel_df, hist_notes = chain.get_daily_panel(start, end, vx_contracts=contracts)
    for n in hist_notes:
        health.add(n)
    if hist_notes:
        health.history_partial = True

    vvix_series = pd.Series(dtype=float)
    spx_series = pd.Series(dtype=float)
    if not panel_df.empty and "vvix" in panel_df.columns:
        vvix_series = panel_df.set_index("date")["vvix"].dropna()
    if not panel_df.empty and "spx" in panel_df.columns:
        spx_series = panel_df.set_index("date")["spx"].dropna()

    sig = build_live_signal(ts, vvix_series, spx_series, now, health, cfg)

    ts_fig = make_term_structure_figure(ts, sig.regime)

    spark_tail = vvix_series.tail(60)
    if spark_tail.empty:
        spark_tail = fetch_vvix_sparkline(sc, 60, end=end)
    spark_y = spark_tail.tolist()
    spark_x = list(spark_tail.index) if len(spark_tail) else None
    vvix_fig = make_vvix_figure(sig.vvix, sparkline_y=spark_y, sparkline_x=spark_x)

    spx_spark = spx_series.tail(60)
    spx_y = spx_spark.tolist()
    spx_x = list(spx_spark.index) if len(spx_spark) else None
    spx_fig = make_spx_figure(sparkline_y=spx_y, sparkline_x=spx_x)

    sig_div = make_signal_summary_div(sig)

    return (
        make_health_banner(health),
        ts_fig,
        vvix_fig,
        spx_fig,
        sig_div,
        now.isoformat(),
    )
