"""Regime gauge, signal rows, alert banner, and regime score history chart."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

from vix_dashboard.config import THRESHOLDS
from vix_dashboard.signals.regime_signals import (
    REGIME_BLACK,
    REGIME_GREEN,
    REGIME_RED,
    REGIME_YELLOW,
    score_crossing_events,
)


def _regime_colors(label: str | None) -> tuple[str, str]:
    if label == REGIME_GREEN:
        return "#1b5e20", "#e8f5e9"
    if label == REGIME_YELLOW:
        return "#f57f17", "#fffde7"
    if label == REGIME_RED:
        return "#b71c1c", "#ffebee"
    if label == REGIME_BLACK:
        return "#212121", "#eeeeee"
    return "#455a64", "#eceff1"


def make_regime_gauge_block(
    score: float | None,
    regime_label: str | None,
    score_3d_change: float | None,
) -> html.Div:
    """Large composite score display with regime-colored background."""
    if score is None or score != score:
        disp = "—"
        arrow = "→"
        bg = "#eceff1"
        fg = "#333"
    else:
        sc = float(score)
        disp = f"{sc:.1f}"
        if score_3d_change is None or score_3d_change != score_3d_change:
            arrow = "→"
        elif float(score_3d_change) > 0.5:
            arrow = "↑"
        elif float(score_3d_change) < -0.5:
            arrow = "↓"
        else:
            arrow = "→"
        fg, bg = _regime_colors(regime_label)

    return html.Div(
        [
            html.Div("Composite regime score", style={"fontSize": "13px", "opacity": 0.9}),
            html.Div(
                [
                    html.Span(disp, style={"fontSize": "42px", "fontWeight": "700"}),
                    html.Span(f"  {arrow}", style={"fontSize": "28px"}),
                ],
                style={"display": "flex", "alignItems": "baseline", "gap": "8px"},
            ),
            html.Div(
                regime_label or "—",
                style={"fontSize": "16px", "fontWeight": "600", "letterSpacing": "0.06em"},
            ),
        ],
        style={
            "background": bg,
            "color": fg,
            "padding": "16px",
            "borderRadius": "8px",
            "minWidth": "200px",
            "boxShadow": "0 1px 3px rgba(0,0,0,0.12)",
        },
    )


def _sparkline_fig(y: list[float], color: str) -> go.Figure:
    ys = [float(v) if v == v and math.isfinite(float(v)) else float("nan") for v in y]
    fig = go.Figure(
        data=[
            go.Scatter(
                y=ys,
                x=list(range(len(ys))),
                mode="lines",
                line=dict(color=color, width=2),
                hoverinfo="skip",
            )
        ]
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        height=44,
        plot_bgcolor="white",
        paper_bgcolor="white",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        showlegend=False,
    )
    return fig


def make_signal_component_table(
    signals_df: pd.DataFrame,
    statuses: dict[str, str],
) -> html.Div:
    """Six signal rows with value, status pill, and 20d sparkline."""
    if signals_df.empty:
        return html.Div("No signal history yet.", style={"fontSize": "13px", "color": "#666"})

    tail = signals_df.tail(400)

    def _series_for(name: str) -> pd.Series:
        m = {
            "VX curve slope": "slope",
            "VIX term ratio": "term_ratio",
            "VVIX velocity": "vvix_roc_3d",
            "VRP": "vrp",
            "Curve convexity": "convexity",
            "VIX/SPX corr": "corr_10d",
        }
        col = m[name]
        return tail[col] if col in tail.columns else pd.Series(dtype=float)

    def _fmt_val(name: str, row: pd.Series) -> str:
        if name == "VX curve slope":
            v = row.get("slope")
            return f"{float(v):.3f}" if v == v else "—"
        if name == "VIX term ratio":
            v = row.get("term_ratio")
            return f"{float(v):.3f}" if v == v else "—"
        if name == "VVIX velocity":
            v = row.get("vvix_roc_3d")
            return f"{float(v) * 100.0:.2f}%" if v == v else "—"
        if name == "VRP":
            v = row.get("vrp")
            return f"{float(v):.2f}" if v == v else "—"
        if name == "Curve convexity":
            v = row.get("convexity")
            return f"{float(v):.3f}" if v == v else "—"
        if name == "VIX/SPX corr":
            v = row.get("corr_10d")
            return f"{float(v):.3f}" if v == v else "—"
        return "—"

    last = signals_df.iloc[-1]
    names = [
        "VX curve slope",
        "VIX term ratio",
        "VVIX velocity",
        "VRP",
        "Curve convexity",
        "VIX/SPX corr",
    ]
    rows = []
    for nm in names:
        st = statuses.get(nm, "normal")
        pill_bg = {"normal": "#e8f5e9", "watch": "#fff8e1", "alert": "#ffebee"}[st]
        pill_fg = {"normal": "#1b5e20", "watch": "#f57f17", "alert": "#c62828"}[st]
        spark = _series_for(nm).dropna().tail(20)
        spark_y = spark.tolist() if len(spark) else [float("nan")]
        fig = _sparkline_fig(spark_y, pill_fg)
        rows.append(
            html.Tr(
                [
                    html.Td(nm, style={"padding": "6px 8px", "fontSize": "13px"}),
                    html.Td(
                        _fmt_val(nm, last),
                        style={"padding": "6px 8px", "fontSize": "13px", "fontFamily": "ui-monospace, monospace"},
                    ),
                    html.Td(
                        html.Span(
                            st.upper(),
                            style={
                                "background": pill_bg,
                                "color": pill_fg,
                                "padding": "2px 8px",
                                "borderRadius": "999px",
                                "fontSize": "11px",
                                "fontWeight": "600",
                            },
                        ),
                        style={"padding": "6px 8px"},
                    ),
                    html.Td(
                        dcc.Graph(figure=fig, config={"displayModeBar": False, "staticPlot": True}),
                        style={"padding": "2px 4px", "width": "140px"},
                    ),
                ]
            )
        )

    tbl = html.Table(
        [
            html.Tr(
                [
                    html.Th("Signal", style={"textAlign": "left", "fontSize": "12px"}),
                    html.Th("Value", style={"textAlign": "left", "fontSize": "12px"}),
                    html.Th("Status", style={"textAlign": "left", "fontSize": "12px"}),
                    html.Th("20d", style={"textAlign": "left", "fontSize": "12px"}),
                ]
            ),
            *rows,
        ],
        style={"width": "100%", "borderCollapse": "collapse"},
    )
    return html.Div(
        [
            html.H4("Regime signals", style={"margin": "0 0 8px 0"}),
            tbl,
        ],
        style={"border": "1px solid #e0e0e0", "borderRadius": "8px", "padding": "10px", "background": "#fafafa"},
    )


def make_regime_history_figure(signals_df: pd.DataFrame) -> go.Figure:
    """Composite score line with regime shading and threshold crossing markers."""
    th = THRESHOLDS
    if signals_df.empty or "composite_score" not in signals_df.columns:
        fig = go.Figure()
        fig.update_layout(title="Regime score history", height=280, margin=dict(l=40, r=20, t=40, b=36))
        return fig

    s = signals_df["composite_score"].sort_index()
    idx = s.index
    x = [pd.Timestamp(t).date() if hasattr(t, "date") else t for t in idx]

    fig = go.Figure()
    gy = float(th["regime_green_yellow"])
    yr = float(th["regime_yellow_red"])
    bl = float(th["regime_red_entry"])

    xmax = max(x) if x else None
    xmin = min(x) if x else None
    if xmin and xmax:
        fig.add_hrect(y0=0, y1=gy, fillcolor="rgba(46, 125, 50, 0.12)", line_width=0, layer="below")
        fig.add_hrect(y0=gy, y1=yr, fillcolor="rgba(251, 192, 45, 0.12)", line_width=0, layer="below")
        fig.add_hrect(y0=yr, y1=bl, fillcolor="rgba(211, 47, 47, 0.12)", line_width=0, layer="below")
        fig.add_hrect(y0=bl, y1=100, fillcolor="rgba(33, 33, 33, 0.14)", line_width=0, layer="below")

    fig.add_trace(
        go.Scatter(
            x=x,
            y=s.tolist(),
            mode="lines",
            name="Composite score",
            line=dict(color="#0d47a1", width=2),
            hovertemplate="%{x}<br>Score %{y:.1f}<extra></extra>",
        )
    )

    ev = score_crossing_events(s, th)
    if not ev.empty:
        shapes = []
        ann = []
        for _, r in ev.iterrows():
            xd = r["date"]
            xd = pd.Timestamp(xd).date() if xd is not None else None
            if xd is None:
                continue
            kind = str(r["crossing_kind"])
            color = "#6a1b9a" if kind == "UP_35" else "#0277bd" if kind == "UP_60" else "#6d4c41"
            shapes.append(
                dict(
                    type="line",
                    xref="x",
                    yref="paper",
                    x0=xd,
                    x1=xd,
                    y0=0,
                    y1=1,
                    line=dict(color=color, width=1, dash="dash"),
                )
            )
            ann.append(
                dict(
                    x=xd,
                    y=1.02,
                    xref="x",
                    yref="paper",
                    text=kind.replace("_", " "),
                    showarrow=False,
                    font=dict(size=10, color=color),
                )
            )
        fig.update_layout(shapes=shapes, annotations=ann)

    fig.update_layout(
        title="Regime score history",
        height=280,
        margin=dict(l=48, r=20, t=48, b=40),
        yaxis=dict(range=[0, 100], title="Score"),
        xaxis=dict(title="Date"),
        showlegend=False,
    )
    return fig


def make_alert_banner(
    triggers: list[str],
    *,
    visible: bool,
) -> html.Div | None:
    if not visible or not triggers:
        return None
    text = " · ".join(triggers)
    return html.Div(
        [
            html.Div(
                [
                    html.Span("⚠ Alert: ", style={"fontWeight": "700"}),
                    html.Span(text),
                ],
                style={"flex": "1"},
            ),
            html.Button(
                "Dismiss",
                id="btn-dismiss-banner",
                n_clicks=0,
                style={"marginLeft": "12px", "cursor": "pointer"},
            ),
        ],
        style={
            "background": "#fff3e0",
            "border": "1px solid #ffb74d",
            "padding": "10px 12px",
            "borderRadius": "6px",
            "marginBottom": "10px",
            "fontSize": "14px",
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "space-between",
        },
    )
