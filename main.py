"""
Plotly Dash entrypoint: thin callbacks delegate to app_service.
Run: ``python -m vix_dashboard.main`` from the parent of the ``vix_dashboard`` package.
"""

from __future__ import annotations

import logging

# No INFO lines on stderr: only WARNING and above (from any logger).
logging.basicConfig(level=logging.WARNING, force=True)
logging.getLogger("tastytrade").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpx_ws").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.ERROR)

from dash import Dash, Input, Output, State, callback, dcc, html

from vix_dashboard.app_service import _auth_optional, refresh_dashboard
from vix_dashboard.config import load_config

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
            dcc.Store(id="dismissed-alert-sig", data=None),
            dcc.Store(id="current-alert-sig", data=None),
            dcc.Interval(
                id="interval-live",
                interval=cfg.dash.refresh_seconds * 1000,
                n_intervals=0,
            ),
            dcc.Loading(
                [
                    html.Div(id="alert-banner"),
                    html.Div(id="health-banner"),
                    html.Div(
                        style={
                            "display": "grid",
                            "gridTemplateColumns": "1fr 1fr",
                            "gap": "12px",
                            "alignItems": "start",
                        },
                        children=[
                            html.Div(
                                style={
                                    "gridColumn": "1 / -1",
                                    "display": "grid",
                                    "gridTemplateColumns": "1fr 1fr",
                                    "gap": "12px",
                                },
                                children=[
                                    dcc.Graph(id="graph-term-structure"),
                                    dcc.Graph(id="graph-vvix"),
                                ],
                            ),
                            html.Div(
                                style={
                                    "gridColumn": "1 / -1",
                                    "display": "grid",
                                    "gridTemplateColumns": "minmax(320px, 1fr) 1fr",
                                    "gap": "12px",
                                    "alignItems": "start",
                                },
                                children=[
                                    html.Div(id="regime-sidebar"),
                                    dcc.Graph(id="graph-spx"),
                                ],
                            ),
                            html.Div(
                                style={
                                    "gridColumn": "1 / -1",
                                    "display": "grid",
                                    # Give the history chart more space; keep live signal readable but narrower.
                                    "gridTemplateColumns": "minmax(300px, 420px) 1fr",
                                    "gap": "12px",
                                    "alignItems": "start",
                                },
                                children=[
                                    html.Div(
                                        id="panel-signal",
                                        style={"width": "100%", "maxWidth": "420px"},
                                    ),
                                    dcc.Graph(
                                        id="graph-regime-history",
                                        style={"width": "100%"},
                                    ),
                                ],
                            ),
                        ],
                    ),
                ]
            ),
        ],
        style={"padding": "16px", "fontFamily": "system-ui, sans-serif"},
    )

    @callback(
        Output("health-banner", "children"),
        Output("graph-term-structure", "figure"),
        Output("graph-vvix", "figure"),
        Output("graph-spx", "figure"),
        Output("panel-signal", "children"),
        Output("last-updated", "children"),
        Output("alert-banner", "children"),
        Output("current-alert-sig", "data"),
        Output("regime-sidebar", "children"),
        Output("graph-regime-history", "figure"),
        Input("interval-live", "n_intervals"),
        State("dismissed-alert-sig", "data"),
    )
    def _on_tick(_live: int, dismissed: str | None) -> tuple:
        return refresh_dashboard(cfg, auth, dismissed_alert_sig=dismissed)

    @callback(
        Output("dismissed-alert-sig", "data"),
        Input("btn-dismiss-banner", "n_clicks"),
        State("current-alert-sig", "data"),
        prevent_initial_call=True,
    )
    def _dismiss_banner(_n: int | None, current_sig: str | None) -> str | None:
        return current_sig

    return app


app = create_app()


if __name__ == "__main__":
    # Debug reloader spawns multiple processes and can duplicate DXLink subscriptions.
    # Opt-in via env var to keep default behavior stable.
    import os

    debug = os.environ.get("DASH_DEBUG", "").strip() in ("1", "true", "True", "yes", "YES")
    app.run(debug=debug, host="127.0.0.1", port=8050)
