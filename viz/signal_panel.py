"""Health banner for the dashboard (live signal UI is built in app_service)."""

from __future__ import annotations

from dash import html

from vix_dashboard.data.models import DataHealth


def make_health_banner(health: DataHealth) -> html.Div:
    if not any(
        (
            health.vvix_degraded,
            health.vx_chain_partial,
            health.auth_refresh_failed,
            health.history_partial,
        )
    ) and not health.messages:
        return html.Div()
    parts = [html.Strong("Data health: ")]
    if health.auth_refresh_failed:
        parts.append("Auth failed. ")
    if health.vx_chain_partial:
        parts.append("VX chain partial. ")
    if health.vvix_degraded:
        parts.append("VVIX degraded. ")
    if health.history_partial:
        parts.append("History partial. ")
    for m in health.messages:
        parts.append(html.Span(m + " "))
    return html.Div(parts, style={"background": "#fff3cd", "padding": "8px", "marginBottom": "8px"})
