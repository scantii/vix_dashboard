"""OAuth2 refresh-token session for Tastytrade REST API."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

import httpx

from vix_dashboard.config import ApiConfig, oauth_credentials

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Raised when OAuth refresh fails permanently."""


class TastyAuth:
    """
    Thread-safe bearer token management.
    Mirrors the flow in tastyware/tastytrade Session.refresh.
    """

    def __init__(self, api: ApiConfig | None = None) -> None:
        self.api = api or ApiConfig()
        self._client_secret, self._refresh_token = oauth_credentials()
        self._access_token: str | None = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()

    def _build_client(self) -> httpx.Client:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Version": self.api.accept_version,
            "User-Agent": self.api.user_agent,
        }
        return httpx.Client(base_url=self.api.base_url, headers=headers, timeout=60.0)

    def refresh(self, force: bool = False) -> None:
        """Obtain a new access token using the refresh token."""
        with self._lock:
            if not force and time.time() < self._expires_at - 60:
                return
            self._refresh_unlocked()

    def _refresh_unlocked(self) -> None:
        body = {
            "grant_type": "refresh_token",
            "client_secret": self._client_secret,
            "refresh_token": self._refresh_token,
        }
        with httpx.Client(base_url=self.api.base_url, timeout=60.0) as raw:
            req = raw.build_request(
                "POST",
                self.api.oauth_token_path,
                json=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Accept-Version": self.api.accept_version,
                    "User-Agent": self.api.user_agent,
                },
            )
            req.headers.pop("Authorization", None)
            resp = raw.send(req)
        if resp.status_code // 100 != 2:
            logger.error("OAuth refresh failed: %s %s", resp.status_code, resp.text)
            raise AuthError(f"OAuth refresh failed: {resp.status_code}")
        data = resp.json()
        self._access_token = data["access_token"]
        ttl = int(data.get("expires_in", 900))
        self._expires_at = time.time() + ttl
        new_refresh = data.get("refresh_token")
        if new_refresh:
            self._refresh_token = new_refresh
            logger.info("Refresh token rotated; update TT_REFRESH in your environment.")
        logger.debug("Access token refreshed, expires_in=%s", ttl)

    def get_headers(self) -> dict[str, str]:
        self.refresh()
        if not self._access_token:
            raise AuthError("No access token")
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Version": self.api.accept_version,
            "User-Agent": self.api.user_agent,
            "Authorization": f"Bearer {self._access_token}",
        }

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        retry_on_401: bool = True,
    ) -> httpx.Response:
        """Perform an authenticated request with one 401 retry after forced refresh."""
        with self._build_client() as client:
            headers = self.get_headers()
            resp = client.request(method, path, params=params, headers=headers)
            if resp.status_code == 401 and retry_on_401:
                self.refresh(force=True)
                headers = self.get_headers()
                resp = client.request(method, path, params=params, headers=headers)
            return resp


def safe_request(
    auth: TastyAuth,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> tuple[httpx.Response | None, str | None]:
    """Returns (response, error_message). Does not raise on HTTP errors."""
    try:
        r = auth.request(method, path, params=params)
        return r, None
    except (AuthError, httpx.HTTPError) as e:
        return None, str(e)
