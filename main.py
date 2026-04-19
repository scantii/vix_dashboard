"""
Plotly Dash entrypoint: thin callbacks delegate to app_service.
Run: ``python -m vix_dashboard.main`` from the parent of the ``vix_dashboard`` package.
"""

from __future__ import annotations

import logging

from dash import Dash, Input, Output, callback, dcc, html

from vix_dashboard.app_service import _auth_optional, refresh_dashboard
from vix_dashboard.config import load_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app(cfg=None) -> Dash:
    cfg = cfg or load_config()
    auth = _auth_optional(cfg)

    app = Dash(__name__)
    app.title = cfg.dash.title

    app.layout = html.Div(
        [
            html.H2(cfg.dash.title),
            html.Div(id="last-updated"),
            dcc.Interval(
                id="interval-live",
                interval=cfg.dash.refresh_seconds * 1000,
                n_intervals=0,
            ),
            dcc.Loading(
                [
                    html.Div(id="health-banner"),
                    html.Div(
                        style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "12px"},
                        children=[
                            dcc.Graph(id="graph-term-structure"),
                            dcc.Graph(id="graph-vvix"),
                        ],
                    ),
                    html.Div(id="panel-signal"),
                ]
            ),
        ],
        style={"padding": "16px", "fontFamily": "system-ui, sans-serif"},
    )

    @callback(
        Output("health-banner", "children"),
        Output("graph-term-structure", "figure"),
        Output("graph-vvix", "figure"),
        Output("panel-signal", "children"),
        Output("last-updated", "children"),
        Input("interval-live", "n_intervals"),
    )
    def _on_tick(_live: int) -> tuple:
        return refresh_dashboard(cfg, auth)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=8050)
