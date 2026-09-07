"""Upstream Service Client — httpx calls to live services (8002/8003/8004).

Provides a single interface for fetching data from upstream services.
All calls use httpx with timeout, retry, and circuit-breaker protection.
"""
from __future__ import annotations

import logging
import os
from datetime import date

import httpx

logger = logging.getLogger("decision.upstream")

# Upstream service URLs — configurable via environment, default to localhost
# (all services run on the same host in the pilot deployment).
FEATURE_SERVICE_URL = os.getenv("FEATURE_SERVICE_URL", "http://127.0.0.1:8002")
STATE_SERVICE_URL = os.getenv("STATE_SERVICE_URL", "http://127.0.0.1:8003")
PREDICTION_SERVICE_URL = os.getenv("PREDICTION_SERVICE_URL", "http://127.0.0.1:8004")

TIMEOUT = 5.0  # seconds
MAX_RETRIES = 2


class UpstreamClient:
    """httpx-based client for all upstream service calls.

    Circuit-breaker: after 3 consecutive failures to a service,
    subsequent calls skip that service and return defaults.
    """

    def __init__(self) -> None:
        self._failure_counts: dict[str, int] = {}
        self._circuit_open: set[str] = set()
        # Single persistent client — creating an httpx.Client per call costs
        # ~0.75s (SSL context load on Windows); reuse one for connection pooling.
        self._client = httpx.Client(timeout=TIMEOUT)

    # ------------------------------------------------------------------
    # Feature Service (8002)
    # ------------------------------------------------------------------

    def fetch_features(self, customer_id: str) -> dict | None:
        """GET /features/{id}/latest — returns full feature snapshot or None."""
        url = f"{FEATURE_SERVICE_URL}/features/{customer_id}/latest"
        data = self._get(url, "features")
        return data if data else None

    # ------------------------------------------------------------------
    # State Service (8003)
    # ------------------------------------------------------------------

    def fetch_state(self, customer_id: str, as_of_date: date) -> dict | None:
        """GET /states/{id}?as_of_date= — returns state snapshot or None."""
        url = f"{STATE_SERVICE_URL}/states/{customer_id}"
        data = self._get(url, "state", params={"as_of_date": as_of_date.isoformat()})
        return data if data else None

    def fetch_state_timeline(self, customer_id: str) -> dict | None:
        """GET /states/{id}/timeline — returns state history or None."""
        url = f"{STATE_SERVICE_URL}/states/{customer_id}/timeline"
        data = self._get(url, "state")
        return data if data else None

    def fetch_portfolio(self, as_of_date: date) -> dict | None:
        """GET /states/portfolio?as_of_date= — returns aggregate state counts."""
        url = f"{STATE_SERVICE_URL}/states/portfolio"
        data = self._get(url, "state", params={"as_of_date": as_of_date.isoformat()})
        return data if data else None

    # ------------------------------------------------------------------
    # Prediction Service (8004)
    # ------------------------------------------------------------------

    def fetch_churn(self, customer_id: str, as_of_date: date) -> dict | None:
        """GET /predict/{id}/churn?as_of_date= — returns churn probability."""
        url = f"{PREDICTION_SERVICE_URL}/predict/{customer_id}/churn"
        data = self._get(url, "prediction", params={"as_of_date": as_of_date.isoformat()})
        return data if data else None

    def fetch_health(self, customer_id: str, as_of_date: date) -> dict | None:
        """GET /predict/{id}/health?as_of_date= — returns health score breakdown."""
        url = f"{PREDICTION_SERVICE_URL}/predict/{customer_id}/health"
        data = self._get(url, "prediction", params={"as_of_date": as_of_date.isoformat()})
        return data if data else None

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------

    def _get(
        self, url: str, service: str, params: dict | None = None
    ) -> dict | None:
        """GET with timeout, retry, and circuit-breaker."""
        if service in self._circuit_open:
            logger.warning("Circuit open for %s — skipping %s", service, url)
            return None

        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self._client.get(url, params=params)
                if resp.status_code == 200:
                    self._reset_failures(service)
                    return resp.json()
                elif resp.status_code == 404:
                    self._reset_failures(service)
                    return None
                else:
                    logger.warning(
                        "%s returned %d: %s", url, resp.status_code, resp.text[:200]
                    )
                    last_error = f"HTTP {resp.status_code}"
            except httpx.TimeoutException:
                logger.warning("Timeout fetching %s (attempt %d/%d)", url, attempt, MAX_RETRIES)
                last_error = "timeout"
            except httpx.ConnectError:
                logger.warning("Connection refused for %s (attempt %d/%d)", url, attempt, MAX_RETRIES)
                last_error = "connection_refused"
            except Exception as e:
                logger.warning("Error fetching %s: %s", url, e)
                last_error = str(e)

        self._record_failure(service)
        return None

    def _record_failure(self, service: str) -> None:
        self._failure_counts[service] = self._failure_counts.get(service, 0) + 1
        if self._failure_counts[service] >= 3:
            self._circuit_open.add(service)
            logger.error("Circuit OPEN for %s after 3 consecutive failures", service)

    def _reset_failures(self, service: str) -> None:
        self._failure_counts[service] = 0
        self._circuit_open.discard(service)


# Singleton
upstream = UpstreamClient()
