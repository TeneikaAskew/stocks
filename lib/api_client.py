"""
Resilient HTTP client for external API calls.

Provides retry with exponential backoff and circuit breaker patterns
for AlphaVantage, Yahoo Finance, and other external services.

Usage:
    from lib.api_client import fetch_with_retry
    resp = fetch_with_retry('https://api.example.com/data', params={'key': 'val'})
    data = resp.json()
"""

import logging
import threading
import time
from typing import Optional

import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

log = logging.getLogger(__name__)

# Retryable exceptions: network errors and server-side failures
_RETRYABLE = (
    requests.ConnectionError,
    requests.Timeout,
    requests.HTTPError,  # caught after raise_for_status for 5xx
)


class _CircuitBreaker:
    """Circuit breaker that backs off after consecutive failures.

    Every method holds `self._lock`, and the failure counter in particular
    needs it. `record_failure` was a get / increment / set, which is not
    atomic: during a vendor outage several threads read the same count and
    write back the same incremented value, so N simultaneous failures raise
    the counter by 1 instead of N. The breaker could then never reach its
    threshold and every worker would keep hammering a vendor that is already
    down — the failure mode the breaker exists to prevent, arriving only
    under the load that makes it matter.

    This was unreachable while every API handler ran on the event loop and
    was serialised by it. Threadpool dispatch is what makes it real, so it
    is fixed alongside that change rather than after it.
    """

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 60.0):
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._consecutive_failures: dict[str, int] = {}
        self._open_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def check(self, endpoint: str) -> None:
        """Raise if circuit is open for this endpoint."""
        with self._lock:
            until = self._open_until.get(endpoint, 0)
        if time.time() < until:
            remaining = until - time.time()
            raise RuntimeError(
                f"Circuit breaker open for {endpoint} "
                f"(cooling down {remaining:.0f}s after {self._threshold} consecutive failures)"
            )

    def record_success(self, endpoint: str) -> None:
        with self._lock:
            self._consecutive_failures.pop(endpoint, None)
            self._open_until.pop(endpoint, None)

    def record_failure(self, endpoint: str) -> None:
        with self._lock:
            count = self._consecutive_failures.get(endpoint, 0) + 1
            self._consecutive_failures[endpoint] = count
            opened = count >= self._threshold
            if opened:
                self._open_until[endpoint] = time.time() + self._cooldown
        if opened:
            log.warning(
                "Circuit breaker OPEN for %s after %d failures (cooldown %ds)",
                endpoint, count, self._cooldown,
            )


# Module-level singleton
_breaker = _CircuitBreaker(failure_threshold=3, cooldown_seconds=60)


def _should_retry_status(response: requests.Response) -> bool:
    """Return True if the HTTP status code warrants a retry."""
    return response.status_code in (429, 500, 502, 503, 504)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(_RETRYABLE),
    before_sleep=before_sleep_log(log, logging.WARNING),
    reraise=True,
)
def fetch_with_retry(
    url: str,
    params: Optional[dict] = None,
    timeout: int = 30,
    circuit_breaker_key: Optional[str] = None,
) -> requests.Response:
    """HTTP GET with retry, backoff, and optional circuit breaker.

    Args:
        url: The URL to fetch.
        params: Optional query parameters.
        timeout: Request timeout in seconds.
        circuit_breaker_key: Key for the circuit breaker (e.g., 'alphavantage').
            If None, circuit breaker is not used.

    Returns:
        The successful Response object.

    Raises:
        requests.HTTPError: On non-retryable HTTP errors (4xx except 429).
        RuntimeError: If circuit breaker is open.
    """
    if circuit_breaker_key:
        _breaker.check(circuit_breaker_key)

    try:
        resp = requests.get(url, params=params, timeout=timeout)

        # Retry on server errors and rate limits
        if _should_retry_status(resp):
            if circuit_breaker_key:
                _breaker.record_failure(circuit_breaker_key)
            resp.raise_for_status()  # raises HTTPError, triggering retry

        resp.raise_for_status()

        if circuit_breaker_key:
            _breaker.record_success(circuit_breaker_key)

        return resp

    except _RETRYABLE:
        if circuit_breaker_key:
            _breaker.record_failure(circuit_breaker_key)
        raise
