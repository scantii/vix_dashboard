"""
Configuration for the VIX dashboard. Thresholds, symbols, and API settings.
Secrets (OAuth client secret, refresh token) come from environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from pathlib import Path


def _load_dotenv() -> None:
    """Load ``.env`` from the package directory if ``python-dotenv`` is installed."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.is_file():
        load_dotenv(env_path)


_load_dotenv()


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v


def _resolve_config_path(raw: str | None) -> str | None:
    """
    Turn optional env path into an absolute path: expand ${VAR} and ``~``,
    then resolve relative paths against this package directory (same folder as ``config.py``).
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    expanded = os.path.expandvars(os.path.expanduser(s))
    p = Path(expanded)
    if not p.is_absolute():
        p = (Path(__file__).resolve().parent / p).resolve()
    return str(p)


@dataclass(frozen=True)
class ApiConfig:
    """Tastytrade REST settings (see https://developer.tastytrade.com/)."""

    base_url: str = "https://api.tastyworks.com"
    # Lock to SDK default; override via TT_API_VERSION if needed.
    accept_version: str = field(
        default_factory=lambda: _env("TT_API_VERSION", "20251101") or "20251101"
    )
    user_agent: str = field(
        default_factory=lambda: _env("TT_USER_AGENT", "vix-dashboard / 1.0.0")
        or "vix-dashboard / 1.0.0"
    )
    oauth_token_path: str = "/oauth/token"
    # Historical OHLC via REST: the public API does not expose a working candle/history route
    # at this path (responses are 404). The official Python SDK also relies on DXLink streaming
    # for candles—not on a stable REST pull—so we fall back to Yahoo Finance for daily index
    # history. See developer.tastytrade.com/streaming-market-data/ for streaming candles.
    history_path: str = "/market-data/history"
    history_params_style: str = "kebab"


@dataclass(frozen=True)
class SymbolConfig:
    """Index and futures symbology (tastytrade docs often use VIX, SPX without $)."""

    vix_index: str = "VIX"
    vvix_index: str = "VVIX"
    spx_index: str = "SPX"
    vx_exchange: str = "CFE"
    vx_product_code: str = "VX"
    # Instrument types for market-data paths (must match API enum strings).
    index_instrument_type: str = "Index"
    future_instrument_type: str = "Future"


@dataclass(frozen=True)
class RegimeConfig:
    """Term-structure regime: contango % = (F1 - F0) / F0 using front two futures."""

    contango_threshold_pct: Decimal = Decimal("2.0")  # above => contango label
    backwardation_threshold_pct: Decimal = Decimal("-2.0")  # below => backwardation
    flat_band_abs_pct: Decimal = Decimal("0.5")  # within band of 0 => flat


@dataclass(frozen=True)
class VvixConfig:
    rolling_days: int = 252
    ma_days: int = 20


@dataclass(frozen=True)
class VrpConfig:
    hv_window: int = 20
    # Annualized HV from daily log returns * sqrt(252)
    annualization: int = 252


@dataclass(frozen=True)
class DashConfig:
    refresh_seconds: int = 60
    title: str = "VIX term structure & regime dashboard"


@dataclass(frozen=True)
class CsvFallbackConfig:
    """Optional panel CSV for offline / gap fill (date,vix,vvix,spx,f0,f1)."""

    panel_path: str | None = field(
        default_factory=lambda: _resolve_config_path(_env("VIX_PANEL_CSV"))
    )
    vvix_series_path: str | None = field(
        default_factory=lambda: _resolve_config_path(_env("VVIX_CSV"))
    )


@dataclass(frozen=True)
class AppConfig:
    api: ApiConfig = field(default_factory=ApiConfig)
    symbols: SymbolConfig = field(default_factory=SymbolConfig)
    regime: RegimeConfig = field(default_factory=RegimeConfig)
    vvix: VvixConfig = field(default_factory=VvixConfig)
    vrp: VrpConfig = field(default_factory=VrpConfig)
    dash: DashConfig = field(default_factory=DashConfig)
    csv: CsvFallbackConfig = field(default_factory=CsvFallbackConfig)
    term_structure_months: int = 6  # number of front months to show live


def load_config() -> AppConfig:
    """Default application configuration."""
    return AppConfig()


def oauth_credentials() -> tuple[str, str]:
    """Return (client_secret, refresh_token) from environment."""
    secret = _env("TT_SECRET")
    refresh = _env("TT_REFRESH")
    if not secret or not refresh:
        raise RuntimeError(
            "Set TT_SECRET (OAuth client secret) and TT_REFRESH (refresh token) in the environment."
        )
    return secret, refresh


def timedelta_refresh(cfg: AppConfig) -> timedelta:
    return timedelta(seconds=cfg.dash.refresh_seconds)
