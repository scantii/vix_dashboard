"""Signal summary and backtest stats tables."""

from __future__ import annotations

import plotly.graph_objects as go
from dash import html

from vix_dashboard.data.models import BacktestSummary, DataHealth, Signal


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
            html.P(sig.live_vs_backtest_note or "", style={"fontSize": "12px", "color": "#666"}),
        ]
    )


def make_backtest_figure(summary: BacktestSummary | None) -> go.Figure:
    fig = go.Figure()
    if not summary or not summary.by_regime:
        fig.update_layout(title="Backtest (no data)", height=280)
        return fig
    regs = []
    wins = []
    avgs = []
    for rg, st in summary.by_regime.items():
        if st.trade_count == 0:
            continue
        regs.append(rg.value)
        wins.append(float(st.win_rate or 0))
        avgs.append(float(st.avg_pnl or 0))
    fig.add_trace(go.Bar(x=regs, y=wins, name="Win rate %"))
    fig.update_layout(title="Backtest win rate by regime", yaxis_title="%", height=320)
    return fig


def make_backtest_table(summary: BacktestSummary | None) -> html.Table:
    if not summary:
        return html.Table([html.Tr([html.Td("No backtest yet")])])
    head = html.Tr(
        [
            html.Th("Regime"),
            html.Th("Trades"),
            html.Th("Win %"),
            html.Th("Avg PnL $"),
            html.Th("Max DD $"),
        ]
    )
    body = []
    for rg, st in summary.by_regime.items():
        body.append(
            html.Tr(
                [
                    html.Td(rg.value),
                    html.Td(str(st.trade_count)),
                    html.Td(f"{float(st.win_rate):.1f}" if st.win_rate is not None else "—"),
                    html.Td(f"{float(st.avg_pnl):.2f}" if st.avg_pnl is not None else "—"),
                    html.Td(f"{float(st.max_drawdown):.2f}" if st.max_drawdown is not None else "—"),
                ]
            )
        )
    ov = html.Tr(
        [
            html.Td("Overall"),
            html.Td(str(len(summary.trades))),
            html.Td(
                f"{float(summary.overall_win_rate):.1f}"
                if summary.overall_win_rate is not None
                else "—"
            ),
            html.Td(
                f"{float(summary.overall_avg_pnl):.2f}"
                if summary.overall_avg_pnl is not None
                else "—"
            ),
            html.Td("—"),
        ]
    )
    return html.Table([head] + body + [ov], style={"width": "100%", "fontSize": "14px"})
