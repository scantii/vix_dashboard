"""VIX futures term structure curve."""

from __future__ import annotations

import plotly.graph_objects as go

from vix_dashboard.data.models import Regime, TermStructure


def make_term_structure_figure(ts: TermStructure | None, regime: Regime | None) -> go.Figure:
    fig = go.Figure()
    _margin = dict(l=8, r=10, t=48, b=40)
    if not ts or not ts.prices_by_symbol:
        fig.update_layout(
            title="Term structure (no data)",
            xaxis_title="Contract",
            yaxis_title="Price",
            height=360,
            margin=_margin,
        )
        return fig
    labels: list[str] = []
    ys: list[float] = []
    for c in ts.contracts:
        if c.symbol in ts.prices_by_symbol:
            labels.append(c.symbol)
            ys.append(float(ts.prices_by_symbol[c.symbol]))
    fig.add_trace(go.Scatter(x=labels, y=ys, mode="lines+markers", name="VX"))
    title = "VX term structure"
    if regime:
        title += f" — {regime.value}"
    if ts.spot_vix is not None:
        fig.add_hline(y=float(ts.spot_vix), line_dash="dot", annotation_text="VIX spot")
    fig.update_layout(
        title=title,
        xaxis_title="Future",
        yaxis_title="Price",
        height=380,
        margin=_margin,
    )
    return fig
