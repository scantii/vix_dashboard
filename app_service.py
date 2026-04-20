"""Orchestration: fetch → models → signals → figures (no Dash imports here)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd
import plotly.graph_objects as go
from dash import html

from vix_dashboard.auth.tasty_auth import AuthError, TastyAuth
from vix_dashboard.config import AppConfig, SymbolConfig
from vix_dashboard.data.fetcher import FetcherError, fetch_quotes_by_type, list_vx_futures
from vix_dashboard.data.historical import (
    ChainedHistoricalProvider,
    CsvHistoricalProvider,
    TastyHistoricalProvider,
)
from vix_dashboard.data.live_bundle import build_term_structure
from vix_dashboard.data.models import DataHealth, Signal
from vix_dashboard.data.yahoo_fallback import fetch_index_closes, fetch_vvix_sparkline
from vix_dashboard.signals.regime_signals import compute_regime_signals, signal_row_statuses
from vix_dashboard.signals.signal_logger import (
    append_daily_signal_log,
    build_log_snapshot,
    ensure_initial_regime_state,
    process_threshold_crossings,
    update_forward_returns,
)
from vix_dashboard.signals.signal_output import build_live_signal
from vix_dashboard.viz.regime_panel import (
    make_alert_banner,
    make_regime_gauge_block,
    make_regime_history_figure,
    make_signal_component_table,
)
from vix_dashboard.viz.signal_panel import make_health_banner
from vix_dashboard.viz.spx_panel import make_spx_figure
from vix_dashboard.viz.term_structure import make_term_structure_figure
from vix_dashboard.viz.vvix_panel import make_vvix_figure

logger = logging.getLogger(__name__)

_Q2 = Decimal("0.01")


def _fmt_2dp(val: object) -> str:
    """Round to hundredths for UI. Never use str(Decimal) for output (unbounded digits)."""
    if val is None:
        return "—"
    if hasattr(val, "item"):
        try:
            val = val.item()
        except Exception:
            pass
    d = val if isinstance(val, Decimal) else Decimal(str(val))
    return format(d.quantize(_Q2, rounding=ROUND_HALF_UP), "f")


def _live_signal_div(sig: Signal) -> html.Div:
    """Built next to refresh_dashboard so the running process always uses this formatting."""
    lines = [
        f"Regime: {sig.regime.value}",
        f"VRP:    {_fmt_2dp(sig.vrp)}",
        f"HV20:   {_fmt_2dp(sig.hv20)}",
    ]
    if sig.vvix:
        lines.append(f"VVIX:   {_fmt_2dp(sig.vvix.vvix)} (n={int(sig.vvix.raw_history_len)})")
    block = "\n".join(lines)
    rules = html.Ul([html.Li(r) for r in sig.rules_fired])
    return html.Div(
        [
            html.H4("Live signal"),
            html.Pre(
                block,
                style={
                    "fontFamily": "system-ui, sans-serif",
                    "fontSize": "14px",
                    "margin": "0 0 0.75em 0",
                    "whiteSpace": "pre-wrap",
                },
            ),
            html.P("Rules:"),
            rules,
        ]
    )


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


def _vix_sparkline_aligned(
    spark_tail: pd.Series,
    vix_panel: pd.Series,
    sc: SymbolConfig,
) -> list[float] | None:
    """VIX daily closes on the same dates as the VVIX spark; Yahoo fill if panel has no VIX."""
    if spark_tail.empty:
        return None
    ix = spark_tail.index
    if not vix_panel.empty:
        aligned = vix_panel.reindex(ix)
        if aligned.notna().any():
            return [float(x) if pd.notna(x) else float("nan") for x in aligned]
    start_d = pd.Timestamp(ix.min()).date()
    end_d = pd.Timestamp(ix.max()).date()
    try:
        m = fetch_index_closes([sc.vix_index], sc, start_d, end_d)
        s = m.get(sc.vix_index)
        if s is None or s.empty:
            return None
        aligned = s.reindex(pd.to_datetime(ix).normalize())
        if not aligned.notna().any():
            return None
        return [float(x) if pd.notna(x) else float("nan") for x in aligned]
    except Exception:
        logger.debug("VIX align for spark failed", exc_info=True)
        return None


def refresh_dashboard(
    cfg: AppConfig,
    auth: TastyAuth | None,
    *,
    dismissed_alert_sig: str | None = None,
) -> tuple:
    """
    Returns tuple for Dash outputs:
    health, ts_fig, vvix_fig, spx_fig, signal_div, last_updated,
    alert_banner, current_alert_sig, regime_sidebar, regime_hist_fig
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
            html.Div(),
            None,
            html.Div(),
            empty,
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
    vix_series = pd.Series(dtype=float)
    spx_series = pd.Series(dtype=float)
    if not panel_df.empty and "vvix" in panel_df.columns:
        vvix_series = panel_df.set_index("date")["vvix"].dropna()
    if not panel_df.empty and "vix" in panel_df.columns:
        vix_series = panel_df.set_index("date")["vix"].dropna()
    if not panel_df.empty and "spx" in panel_df.columns:
        spx_series = panel_df.set_index("date")["spx"].dropna()

    sig = build_live_signal(ts, vvix_series, spx_series, now, health, cfg)

    signals_df = compute_regime_signals(panel_df, cfg)
    ts_fig = make_term_structure_figure(ts, sig.regime)

    spark_tail = vvix_series.tail(60)
    if spark_tail.empty:
        spark_tail = fetch_vvix_sparkline(sc, 60, end=end)
    spark_y = spark_tail.tolist()
    spark_x = list(spark_tail.index) if len(spark_tail) else None
    vix_spark_y = _vix_sparkline_aligned(spark_tail, vix_series, sc)
    vrp_spark_y: list[float] | None = None
    if not signals_df.empty and spark_tail is not None and len(spark_tail):
        ix = pd.DatetimeIndex(pd.to_datetime(spark_tail.index).normalize())
        vrp_aligned = signals_df["vrp"].reindex(ix)
        vrp_spark_y = [float(v) if pd.notna(v) else float("nan") for v in vrp_aligned]

    vvix_fig = make_vvix_figure(
        sig.vvix,
        sparkline_y=spark_y,
        sparkline_x=spark_x,
        vix_sparkline_y=vix_spark_y,
        vrp_sparkline_y=vrp_spark_y,
    )

    spx_spark = spx_series.tail(60)
    spx_y = spx_spark.tolist()
    spx_x = list(spx_spark.index) if len(spx_spark) else None
    spx_fig = make_spx_figure(sparkline_y=spx_y, sparkline_x=spx_x)

    sig_div = _live_signal_div(sig)

    last_sig_row = signals_df.iloc[-1] if not signals_df.empty else None
    score_3d_change: float | None = None
    if not signals_df.empty and len(signals_df) >= 1:
        cs = signals_df["composite_score"]
        prev = cs.shift(3)
        if pd.notna(cs.iloc[-1]) and pd.notna(prev.iloc[-1]):
            score_3d_change = float(cs.iloc[-1] - prev.iloc[-1])

    gauge = make_regime_gauge_block(
        float(last_sig_row["composite_score"]) if last_sig_row is not None else None,
        str(last_sig_row["regime_label"]) if last_sig_row is not None else None,
        score_3d_change,
    )
    statuses: dict[str, str] = signal_row_statuses(last_sig_row) if last_sig_row is not None else {}
    sig_table = make_signal_component_table(signals_df, statuses)
    regime_sidebar = html.Div(
        [gauge, sig_table],
        style={
            "display": "flex",
            "gap": "16px",
            "alignItems": "flex-start",
            "flexWrap": "wrap",
        },
    )
    regime_hist_fig = make_regime_history_figure(signals_df)

    trigs: list[str] = []
    if last_sig_row is not None:
        if bool(last_sig_row.get("early_warning_flag")):
            trigs.append("VVIX leading VIX (early warning)")
        if bool(last_sig_row.get("slope_flipping")):
            trigs.append("VX curve slope ROC crossed zero (slope flipping)")
        if bool(last_sig_row.get("correlation_breakdown")):
            trigs.append("VIX/SPX correlation breakdown")
    alert_sig = "|".join(sorted(trigs)) if trigs else None
    show_banner = bool(trigs) and (dismissed_alert_sig != alert_sig)
    alert_banner = make_alert_banner(trigs, visible=show_banner)
    if alert_banner is None:
        alert_banner = html.Div()

    if not panel_df.empty and last_sig_row is not None:
        pr = panel_df.sort_values("date").iloc[-1]
        snap = build_log_snapshot(pr, last_sig_row, score_3d_change)
        try:
            ensure_initial_regime_state(snap)
            process_threshold_crossings(snap)
            append_daily_signal_log(snap, now=now)
            update_forward_returns(panel_df)
        except Exception:
            logger.exception("Regime signal logging failed")

    return (
        make_health_banner(health),
        ts_fig,
        vvix_fig,
        spx_fig,
        sig_div,
        now.isoformat(),
        alert_banner,
        alert_sig,
        regime_sidebar,
        regime_hist_fig,
    )
