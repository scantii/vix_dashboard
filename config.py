"""
Configuration for the VIX dashboard. Thresholds, symbols, and API settings.
Secrets (OAuth client secret, refresh token) come from environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v


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
    # Confirm against current OpenAPI: developer.tastytrade.com/open-api-spec/market-data/
    # Typical pattern: GET with symbol, instrument-type, interval, start-time, end-time (kebab-case).
    history_path: str = "/market-data/history"
    # Query param names (kebab-case per API conventions); adjust if OpenAPI differs.
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
class BacktestConfig:
    """Walk-forward backtest; Tier A: delta-scaled VIX options P&L proxy."""

    start_offset_days: int = 750  # history to pull / panel length
    hold_days: int = 5
    target_delta: Decimal = Decimal("0.30")
    target_dte_days: int = 30
    # Standard VIX options: $100 per index point per contract (approximation).
    dollars_per_vix_point: Decimal = Decimal("100")
    # Signal → position: long call when long_vol, long put when short_vol
    long_vol_vrp_min: Decimal = Decimal("0.0")
    short_vol_vrp_max: Decimal = Decimal("0.0")
    min_vvix_pct_for_short_vol: Decimal = Decimal("70.0")  # high fear → favor puts / short vol plays


@dataclass(frozen=True)
class DashConfig:
    refresh_seconds: int = 60
    backtest_refresh_seconds: int = 3600
    title: str = "VIX term structure & regime dashboard"


@dataclass(frozen=True)
class CsvFallbackConfig:
    """Optional panel CSV for offline / gap fill (date,vix,vvix,spx,f0,f1)."""

    panel_path: str | None = field(
        default_factory=lambda: _env("VIX_PANEL_CSV")
    )
    vvix_series_path: str | None = field(
        default_factory=lambda: _env("VVIX_CSV")
    )


@dataclass(frozen=True)
class AppConfig:
    api: ApiConfig = field(default_factory=ApiConfig)
    symbols: SymbolConfig = field(default_factory=SymbolConfig)
    regime: RegimeConfig = field(default_factory=RegimeConfig)
    vvix: VvixConfig = field(default_factory=VvixConfig)
    vrp: VrpConfig = field(default_factory=VrpConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
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
