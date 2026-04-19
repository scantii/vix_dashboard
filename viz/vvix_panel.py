"""VVIX gauge and recent path."""

from __future__ import annotations

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from vix_dashboard.data.models import VVIXReading


def make_vvix_figure(reading: VVIXReading | None, sparkline_y: list[float] | None = None) -> go.Figure:
    fig = make_subplots(
        rows=1,
        cols=2,
        column_widths=[0.35, 0.65],
        specs=[[{"type": "indicator"}, {"type": "scatter"}]],
        subplot_titles=("VVIX level", "Recent VVIX"),
    )
    level = float(reading.vvix) if reading else 0.0
    fig.add_trace(
        go.Indicator(
            mode="gauge+number+delta",
            value=level,
            domain={"x": [0, 1], "y": [0, 1]},
            title={"text": "VVIX"},
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
    if sparkline_y:
        fig.add_trace(
            go.Scatter(y=sparkline_y, mode="lines", name="VVIX", line=dict(color="#1f77b4")),
            row=1,
            col=2,
        )
    if reading and reading.pct_rank_252 is not None and fig.layout.annotations:
        fig.layout.annotations[0].text = f"VVIX (~pct {float(reading.pct_rank_252):.1f})"
    fig.update_layout(height=360, showlegend=False)
    return fig
