"""VVIX gauge and recent path."""

from __future__ import annotations

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


def make_vvix_figure(
    reading: VVIXReading | None,
    sparkline_y: list[float] | None = None,
    sparkline_x: list[object] | None = None,
) -> go.Figure:
    """
    Left: gauge. Right: recent daily closes.

    Do not set ``domain`` on ``go.Indicator`` when using subplots: ``[0,1]x[0,1]`` is in
    *figure* coordinates and covers both columns, which hides the sparkline.
    """
    has_spark = bool(sparkline_y) and len(sparkline_y) > 0
    right_title = "Recent VVIX" if has_spark else "Recent VVIX (no data)"

    fig = make_subplots(
        rows=1,
        cols=2,
        column_widths=[0.36, 0.64],
        horizontal_spacing=0.06,
        specs=[[{"type": "indicator"}, {"type": "scatter"}]],
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
            mode="gauge+number+delta",
            value=level,
            title={"text": gauge_title},
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
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=sparkline_y,
                mode="lines",
                name="VVIX",
                line=dict(color="#1f77b4"),
                connectgaps=True,
            ),
            row=1,
            col=2,
        )
        fig.update_xaxes(title_text="Date", row=1, col=2)
        fig.update_yaxes(title_text="Level", row=1, col=2)

    # Nudge gauge subplot down and left so the meter sits more between term structure and sparkline.
    # Extra space before the sparkline (col 2 domain start) keeps it from overlapping the gauge.
    fig.update_xaxes(domain=[0.0, 0.30], row=1, col=1)
    fig.update_xaxes(domain=[0.42, 1.0], row=1, col=2)
    fig.update_yaxes(domain=[0.06, 0.72], row=1, col=1)
    fig.update_yaxes(domain=[0.0, 1.0], row=1, col=2)

    fig.update_layout(height=360, showlegend=False, margin=dict(l=0, r=8, t=36, b=28))
    return fig
