"""VVIX gauge and VIX/VVIX recent path."""

from __future__ import annotations

import math
from datetime import datetime

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from vix_dashboard.data.models import VVIXReading


def _x_for_plot(sparkline_x: list[object] | None, n: int) -> list:
    if sparkline_x and len(sparkline_x) == n:
        out: list[object] = []
        for t in sparkline_x:
            if hasattr(t, "date"):
                out.append(t.date() if isinstance(t, datetime) else t)
            else:
                out.append(t)
        return out
    return list(range(n))


def _any_finite(y: list[float] | None) -> bool:
    if not y:
        return False
    for v in y:
        try:
            if math.isfinite(float(v)):
                return True
        except (TypeError, ValueError):
            continue
    return False


def make_vvix_figure(
    reading: VVIXReading | None,
    sparkline_y: list[float] | None = None,
    sparkline_x: list[object] | None = None,
    vix_sparkline_y: list[float] | None = None,
    vrp_sparkline_y: list[float] | None = None,
) -> go.Figure:
    """
    Left: gauge. Right: VIX + VVIX daily closes (same window). Dual y when VIX data exists:
    VIX scale on the left, VVIX on the right.
    """
    has_spark = bool(sparkline_y) and len(sparkline_y) > 0
    use_dual = (
        has_spark
        and _any_finite(vix_sparkline_y)
        and vix_sparkline_y is not None
        and len(vix_sparkline_y) == len(sparkline_y)
    )
    has_vrp = (
        has_spark
        and vrp_sparkline_y is not None
        and len(vrp_sparkline_y) == len(sparkline_y)
        and _any_finite(vrp_sparkline_y)
    )
    right_title = "VIX/VVIX" if has_spark else "VIX/VVIX (no data)"

    # secondary_y requires subplot type "xy", not "scatter"
    scatter_spec: dict = {"type": "xy"}
    if use_dual:
        scatter_spec["secondary_y"] = True

    fig = make_subplots(
        rows=1,
        cols=2,
        column_widths=[0.36, 0.64],
        horizontal_spacing=0.06,
        specs=[[{"type": "indicator"}, scatter_spec]],
        subplot_titles=("", right_title),
    )
    for ann in list(fig.layout.annotations or []):
        if not str(ann.text or "").strip():
            ann.visible = False
    level = float(reading.vvix) if reading else 0.0
    gauge_title = "VVIX"
    if reading and reading.pct_rank_252 is not None:
        gauge_title = f"VVIX (~{float(reading.pct_rank_252):.0f}th pct)"

    fig.add_trace(
        go.Indicator(
            mode="gauge+number",
            value=level,
            title={"text": gauge_title},
            number={"valueformat": ".2f"},
            gauge={
                "axis": {"range": [None, 200]},
                "bar": {"color": "darkblue"},
                "steps": [
                    {"range": [0, 80], "color": "#efe"},
                    {"range": [80, 120], "color": "#ffd"},
                    {"range": [120, 200], "color": "#fdd"},
                ],
            },
        ),
        row=1,
        col=1,
    )

    if has_spark and sparkline_y is not None:
        xs = _x_for_plot(sparkline_x, len(sparkline_y))
        if use_dual and vix_sparkline_y is not None:
            if has_vrp:
                vrp = [float(v) if v == v and math.isfinite(float(v)) else float("nan") for v in vrp_sparkline_y]
                vrp_pos = [v if v == v and v > 0 else 0.0 for v in vrp]
                vrp_neg = [v if v == v and v < 0 else 0.0 for v in vrp]
                fig.add_trace(
                    go.Scatter(
                        x=xs,
                        y=vrp_pos,
                        mode="lines",
                        name="VRP+",
                        line=dict(color="rgba(46, 125, 50, 0.9)", width=1.5),
                        fill="tozeroy",
                        fillcolor="rgba(46, 125, 50, 0.22)",
                        connectgaps=False,
                        hovertemplate="%{x}<br>VRP %{y:.2f}<extra></extra>",
                    ),
                    row=1,
                    col=2,
                    secondary_y=False,
                )
                fig.add_trace(
                    go.Scatter(
                        x=xs,
                        y=vrp_neg,
                        mode="lines",
                        name="VRP−",
                        line=dict(color="rgba(198, 40, 40, 0.9)", width=1.5),
                        fill="tozeroy",
                        fillcolor="rgba(198, 40, 40, 0.22)",
                        connectgaps=False,
                        hovertemplate="%{x}<br>VRP %{y:.2f}<extra></extra>",
                    ),
                    row=1,
                    col=2,
                    secondary_y=False,
                )
            fig.add_trace(
                go.Scatter(
                    x=xs,
                    y=vix_sparkline_y,
                    mode="lines",
                    name="VIX",
                    line=dict(color="#7f7f7f"),
                    connectgaps=True,
                    hovertemplate="%{x}<br>VIX %{y:.2f}<extra></extra>",
                ),
                row=1,
                col=2,
                secondary_y=False,
            )
            fig.add_trace(
                go.Scatter(
                    x=xs,
                    y=sparkline_y,
                    mode="lines",
                    name="VVIX",
                    line=dict(color="#1f77b4"),
                    connectgaps=True,
                    hovertemplate="%{x}<br>VVIX %{y:.2f}<extra></extra>",
                ),
                row=1,
                col=2,
                secondary_y=True,
            )
            y_left = "VIX + VRP" if has_vrp else "VIX"
            fig.update_yaxes(
                title_text=y_left,
                tickformat=".2f",
                side="left",
                secondary_y=False,
                row=1,
                col=2,
            )
            fig.update_yaxes(
                title_text="VVIX",
                tickformat=".2f",
                side="right",
                secondary_y=True,
                row=1,
                col=2,
            )
            # add_hline() spans all subplot types and breaks on the Indicator pane; draw zero in data space.
            if has_vrp and xs:
                fig.add_trace(
                    go.Scatter(
                        x=[xs[0], xs[-1]],
                        y=[0.0, 0.0],
                        mode="lines",
                        line=dict(color="#9e9e9e", width=1, dash="dot"),
                        name="VRP 0",
                        showlegend=False,
                        hoverinfo="skip",
                    ),
                    row=1,
                    col=2,
                    secondary_y=False,
                )
        else:
            fig.add_trace(
                go.Scatter(
                    x=xs,
                    y=sparkline_y,
                    mode="lines",
                    name="VVIX",
                    line=dict(color="#1f77b4"),
                    connectgaps=True,
                    hovertemplate="%{x}<br>%{y:.2f}<extra></extra>",
                ),
                row=1,
                col=2,
            )
            fig.update_yaxes(
                title_text="VVIX",
                tickformat=".2f",
                side="left",
                row=1,
                col=2,
            )
        fig.update_xaxes(title_text="Date", row=1, col=2)

    fig.update_xaxes(domain=[0.0, 0.30], row=1, col=1)
    fig.update_xaxes(domain=[0.42, 1.0], row=1, col=2)
    fig.update_yaxes(domain=[0.06, 0.72], row=1, col=1)
    fig.update_yaxes(domain=[0.0, 1.0], row=1, col=2)

    fig.update_layout(
        height=360,
        showlegend=use_dual or has_vrp,
        legend=dict(orientation="h", yanchor="bottom", y=-0.22, x=0.5, xanchor="center"),
        margin=dict(l=0, r=8, t=36, b=28),
    )
    return fig
