"""Orchestration: fetch → models → signals → figures (no Dash imports here)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from dash import html

from vix_dashboard.auth.tasty_auth import AuthError, TastyAuth
from vix_dashboard.config import AppConfig, load_config
from vix_dashboard.data.fetcher import FetcherError, fetch_quotes_by_type, list_vx_futures
from vix_dashboard.data.historical import (
    ChainedHistoricalProvider,
    CsvHistoricalProvider,
    TastyHistoricalProvider,
)
from vix_dashboard.data.live_bundle import build_term_structure
from vix_dashboard.data.models import DataHealth
from vix_dashboard.signals.backtest import run_walk_forward
from vix_dashboard.signals.signal_output import build_live_signal
from vix_dashboard.viz.signal_panel import (
    make_backtest_figure,
    make_backtest_table,
    make_health_banner,
    make_signal_summary_div,
)
from vix_dashboard.viz.term_structure import make_term_structure_figure
from vix_dashboard.viz.vvix_panel import make_vvix_figure

logger = logging.getLogger(__name__)

_BACKTEST_CACHE: dict[str, Any] = {"as_of_date": None, "summary": None}


def _auth_optional(cfg: AppConfig) -> TastyAuth | None:
    try:
        return TastyAuth(cfg.api)
    except (AuthError, RuntimeError) as e:
        logger.warning("Auth not configured: %s", e)
        return None


def _spot_vix(quotes: dict, sym: str) -> Any:
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


def refresh_dashboard(
    cfg: AppConfig,
    auth: TastyAuth | None,
    triggered_id: str | None,
) -> tuple:
    """
    Returns tuple for Dash outputs:
    health, ts_fig, vvix_fig, signal_div, bt_fig, bt_table, last_updated
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
            html.Div("No auth"),
            empty,
            make_backtest_table(None),
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
    from decimal import Decimal

    spot_dec = Decimal(str(float(spot))) if spot is not None else None
    ts = build_term_structure(contracts, quotes, spot_dec, cfg, as_of=now) if contracts else None

    # Historical series for features (shorter window)
    end = date.today()
    start = end - timedelta(days=400)
    csvp = None
    if cfg.csv.panel_path:
        csvp = CsvHistoricalProvider(cfg.csv.panel_path)
    tasty_h = TastyHistoricalProvider(auth, cfg)
    chain = ChainedHistoricalProvider(tasty_h, csvp)
    panel_df, hist_notes = chain.get_daily_panel(start, end)
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
    spark = vvix_series.tail(60).tolist() if len(vvix_series) else None
    vvix_fig = make_vvix_figure(sig.vvix, sparkline_y=spark)
    sig_div = make_signal_summary_div(sig)

    # Backtest: not on every live tick — only new day, missing cache, or backtest interval
    global _BACKTEST_CACHE
    today = date.today()
    run_bt = (
        _BACKTEST_CACHE["summary"] is None
        or _BACKTEST_CACHE["as_of_date"] != today
        or triggered_id == "interval-bt"
    )
    if run_bt:
        bt_start = today - timedelta(days=cfg.backtest.start_offset_days)
        bt_panel, _ = chain.get_daily_panel(bt_start, today)
        if bt_panel.empty:
            _BACKTEST_CACHE["summary"] = None
        else:
            _BACKTEST_CACHE["summary"] = run_walk_forward(bt_panel, cfg)
        _BACKTEST_CACHE["as_of_date"] = today

    summary = _BACKTEST_CACHE.get("summary")
    bt_fig = make_backtest_figure(summary)
    bt_table = make_backtest_table(summary)

    return (
        make_health_banner(health),
        ts_fig,
        vvix_fig,
        sig_div,
        bt_fig,
        bt_table,
        now.isoformat(),
    )


def default_config() -> AppConfig:
    return load_config()
