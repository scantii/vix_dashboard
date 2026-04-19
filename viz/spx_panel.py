"""SPX recent path (same window as VVIX sparkline: last 60 daily closes from panel)."""

from __future__ import annotations

from datetime import datetime

import plotly.graph_objects as go


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


def make_spx_figure(
    sparkline_y: list[float] | None = None,
    sparkline_x: list[object] | None = None,
) -> go.Figure:
    """Line chart of recent SPX closes; empty series shows a no-data title."""
    has_spark = bool(sparkline_y) and len(sparkline_y) > 0
    title = "Recent SPX" if has_spark else "Recent SPX (no data)"
    fig = go.Figure()
    if has_spark and sparkline_y is not None:
        xs = _x_for_plot(sparkline_x, len(sparkline_y))
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=sparkline_y,
                mode="lines",
                name="SPX",
                line=dict(color="#2ca02c"),
                connectgaps=True,
            )
        )
    fig.update_layout(
        title=title,
        height=360,
        showlegend=False,
        xaxis_title="Date",
        yaxis_title="Level",
    )
    return fig
