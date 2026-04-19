"""Tastytrade REST client: instruments and market data."""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import quote

from vix_dashboard.auth.tasty_auth import TastyAuth, safe_request
from vix_dashboard.config import AppConfig
from vix_dashboard.data.models import Candle, FuturesContract, QuoteSnapshot

logger = logging.getLogger(__name__)

# After one 404 on the REST history route, skip further GETs for this process (same endpoint).
_tasty_history_endpoint_dead: bool = False


class FetcherError(Exception):
    """API or parsing error."""


def _unwrap_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if data is None:
        raise FetcherError(f"Missing data key: {list(payload.keys())}")
    return data


def _decimal(x: Any) -> Decimal | None:
    if x is None:
        return None
    return Decimal(str(x))


def list_vx_futures(auth: TastyAuth, cfg: AppConfig) -> list[FuturesContract]:
    """Paginate GET /instruments/futures for VX product."""
    items: list[dict[str, Any]] = []
    offset = 0
    per_page = 250
    while True:
        params: dict[str, Any] = {
            "product-code[]": cfg.symbols.vx_product_code,
            "per-page": per_page,
            "page-offset": offset,
        }
        resp, err = safe_request(auth, "GET", "/instruments/futures", params=params)
        if err or resp is None:
            raise FetcherError(err or "no response")
        if resp.status_code // 100 != 2:
            raise FetcherError(f"futures list {resp.status_code}: {resp.text}")
        body = resp.json()
        data = _unwrap_data(body)
        batch = data.get("items", [])
        items.extend(batch)
        if len(batch) < per_page:
            break
        pag = body.get("pagination") or {}
        total_pages = int(pag.get("total-pages", offset + 2))
        if offset >= total_pages - 1:
            break
        offset += 1
    out: list[FuturesContract] = []
    for row in items:
        try:
            exp = row.get("expiration-date") or row.get("expiration_date")
            if isinstance(exp, str):
                exp_d = date.fromisoformat(exp[:10])
            else:
                exp_d = exp
            sym = row.get("symbol", "")
            out.append(
                FuturesContract(
                    symbol=sym,
                    expiration_date=exp_d,
                    root=row.get("product-code") or row.get("product_code") or cfg.symbols.vx_product_code,
                    active=bool(row.get("active", True)),
                    last_trade_date=None,
                    exchange=row.get("exchange"),
                )
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("skip future row %s: %s", row, e)
    out.sort(key=lambda c: c.expiration_date)
    return out


def fetch_quotes_by_type(
    auth: TastyAuth,
    cfg: AppConfig,
    *,
    indices: list[str] | None = None,
    futures: list[str] | None = None,
) -> dict[str, QuoteSnapshot]:
    """GET /market-data/by-type — returns map symbol -> QuoteSnapshot."""
    params: dict[str, Any] = {}
    if indices:
        params["index[]"] = indices
    if futures:
        params["future[]"] = futures
    resp, err = safe_request(auth, "GET", "/market-data/by-type", params=params)
    if err or resp is None:
        raise FetcherError(err or "no response")
    if resp.status_code // 100 != 2:
        raise FetcherError(f"by-type {resp.status_code}: {resp.text}")
    data = _unwrap_data(resp.json())
    out: dict[str, QuoteSnapshot] = {}
    for row in data.get("items", []):
        sym = row.get("symbol", "")
        ts_raw = row.get("updated-at") or row.get("updated_at")
        ts: datetime | None
        if isinstance(ts_raw, str):
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        else:
            ts = ts_raw
        out[sym] = QuoteSnapshot(
            symbol=sym,
            mark=_decimal(row.get("mark")),
            bid=_decimal(row.get("bid")),
            ask=_decimal(row.get("ask")),
            updated_at=ts,
        )
    return out


def _parse_candle_rows(raw: dict[str, Any]) -> list[Candle]:
    """Accept several possible API shapes for candle lists."""
    items = raw.get("items") or raw.get("candles") or raw.get("history") or []
    if isinstance(items, dict):
        items = list(items.values())
    out: list[Candle] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        t = row.get("time") or row.get("timestamp") or row.get("start-time") or row.get("start_time")
        if t is None:
            continue
        if isinstance(t, (int, float)):
            ts = datetime.utcfromtimestamp(t / 1000.0) if t > 1e12 else datetime.utcfromtimestamp(float(t))
        elif isinstance(t, str):
            ts = datetime.fromisoformat(t.replace("Z", "+00:00"))
        else:
            continue
        out.append(
            Candle(
                ts=ts,
                open=_decimal(row.get("open")) or Decimal(0),
                high=_decimal(row.get("high")) or Decimal(0),
                low=_decimal(row.get("low")) or Decimal(0),
                close=_decimal(row.get("close")) or Decimal(0),
                volume=_decimal(row.get("volume")),
            )
        )
    out.sort(key=lambda c: c.ts)
    return out


def fetch_history_candles(
    auth: TastyAuth,
    cfg: AppConfig,
    *,
    symbol: str,
    instrument_type: str,
    start: date,
    end: date,
    interval: str = "1d",
) -> list[Candle]:
    """
    GET {history_path} with instrument type and symbol.
    Tastytrade OpenAPI: confirm parameter names against live spec; this uses kebab-case.
    """
    global _tasty_history_endpoint_dead
    if _tasty_history_endpoint_dead:
        return []

    sym = symbol.lstrip("/")
    params: dict[str, Any] = {
        "symbol": sym,
        "instrument-type": instrument_type,
        "interval": interval,
        "start-time": start.isoformat(),
        "end-time": end.isoformat(),
    }
    resp, err = safe_request(auth, "GET", cfg.api.history_path, params=params)
    if err or resp is None:
        raise FetcherError(err or "no response")
    if resp.status_code == 404:
        if not _tasty_history_endpoint_dead:
            logger.info(
                "Tasty REST %s returned 404; skipping further history GETs this session "
                "(indices use Yahoo fallback where implemented).",
                cfg.api.history_path,
            )
        _tasty_history_endpoint_dead = True
        logger.debug(
            "History 404 for %s at %s (often absent on REST; Yahoo fallback may apply)",
            sym,
            cfg.api.history_path,
        )
        return []
    if resp.status_code // 100 != 2:
        raise FetcherError(f"history {resp.status_code}: {resp.text[:500]}")
    body = resp.json()
    data = body.get("data") or body
    out = _parse_candle_rows(data if isinstance(data, dict) else {"items": data})
    if out:
        _tasty_history_endpoint_dead = False
    return out


def fetch_single_quote(
    auth: TastyAuth,
    cfg: AppConfig,
    symbol: str,
    instrument_type: str,
) -> QuoteSnapshot | None:
    """GET /market-data/{InstrumentType}/{symbol}"""
    sym = quote(symbol, safe="")
    path = f"/market-data/{instrument_type}/{sym}"
    resp, err = safe_request(auth, "GET", path)
    if err or resp is None:
        return None
    if resp.status_code // 100 != 2:
        return None
    data = _unwrap_data(resp.json())
    ts_raw = data.get("updated-at") or data.get("updated_at")
    if isinstance(ts_raw, str):
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
    else:
        ts = ts_raw
    return QuoteSnapshot(
        symbol=data.get("symbol", symbol),
        mark=_decimal(data.get("mark")),
        bid=_decimal(data.get("bid")),
        ask=_decimal(data.get("ask")),
        updated_at=ts,
    )
