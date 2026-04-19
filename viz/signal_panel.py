"""Signal summary and health banner."""

from __future__ import annotations

from dash import html

from vix_dashboard.data.models import DataHealth, Signal


def make_health_banner(health: DataHealth) -> html.Div:
    if not any(
        (
            health.vvix_degraded,
            health.vx_chain_partial,
            health.spx_history_gap,
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
    if health.spx_history_gap:
        parts.append("SPX gap. ")
    if health.history_partial:
        parts.append("History partial. ")
    for m in health.messages:
        parts.append(html.Span(m + " "))
    return html.Div(parts, style={"background": "#fff3cd", "padding": "8px", "marginBottom": "8px"})


def make_signal_summary_div(sig: Signal) -> html.Div:
    rows = [
        html.Tr([html.Td("Regime"), html.Td(sig.regime.value)]),
        html.Tr([html.Td("VRP"), html.Td(str(sig.vrp) if sig.vrp is not None else "—")]),
        html.Tr([html.Td("HV20"), html.Td(str(sig.hv20) if sig.hv20 is not None else "—")]),
    ]
    if sig.vvix:
        rows.append(
            html.Tr(
                [
                    html.Td("VVIX"),
                    html.Td(f"{sig.vvix.vvix} (n={sig.vvix.raw_history_len})"),
                ]
            )
        )
    rules = html.Ul([html.Li(r) for r in sig.rules_fired])
    return html.Div(
        [
            html.H4("Live signal"),
            html.Table(rows),
            html.P("Rules:"),
            rules,
        ]
    )
