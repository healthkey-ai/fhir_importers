"""Per-institution HTTP retry/backoff for FHIR pulls.

Parameters come from the `fhir_institution` row (Architecture
Recommendations v1.1 § 2.3.4). The same wrapper is used by every FHIR
HTTP call so retry policy is uniform and testable.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Callable, TypeVar

import requests

from entities.fhir.institution import Institution

_logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryExhausted(Exception):
    """All `max_retry_count` attempts failed transiently."""


def with_retry(
    institution: Institution,
    callable_fn: Callable[[], requests.Response],
) -> requests.Response:
    """Invoke `callable_fn` with exponential-backoff retries per the
    institution's configured policy. Returns the first successful response
    (2xx); raises `RetryExhausted` after `max_retry_count` transient
    failures; re-raises non-transient errors immediately.
    """
    attempt = 0
    backoff = max(institution.base_backoff_seconds, 1)

    while True:
        attempt += 1
        try:
            response = callable_fn()
        except requests.RequestException as e:
            _logger.warning(
                "[%s] attempt %d/%d: network error %s",
                institution.slug,
                attempt,
                institution.max_retry_count,
                e,
            )
            if attempt >= institution.max_retry_count:
                raise RetryExhausted(
                    f"{institution.slug}: max_retry_count={institution.max_retry_count} "
                    f"exceeded; last error: {e}"
                ) from e
            _sleep(backoff, institution.jitter_factor)
            backoff = min(backoff * 2, institution.max_backoff_seconds)
            continue

        if response.ok:
            return response

        retryable = (
            response.status_code in (institution.retryable_status_codes or [])
            or response.status_code in (429, 502, 503, 504)
        )
        if not retryable:
            return response  # caller handles non-transient codes itself

        if attempt >= institution.max_retry_count:
            raise RetryExhausted(
                f"{institution.slug}: max_retry_count={institution.max_retry_count} "
                f"exceeded; last status {response.status_code}: {response.text[:300]}"
            )

        wait_seconds = backoff
        if institution.respect_retry_after:
            retry_after_header = response.headers.get("Retry-After")
            if retry_after_header:
                try:
                    wait_seconds = max(int(retry_after_header), backoff)
                except ValueError:
                    pass

        _logger.warning(
            "[%s] attempt %d/%d: status %d, sleeping %ds",
            institution.slug,
            attempt,
            institution.max_retry_count,
            response.status_code,
            wait_seconds,
        )
        _sleep(wait_seconds, institution.jitter_factor)
        backoff = min(backoff * 2, institution.max_backoff_seconds)


def _sleep(seconds: float, jitter_factor: float) -> None:
    if jitter_factor > 0:
        jitter = seconds * jitter_factor * (2 * random.random() - 1)
        seconds = max(seconds + jitter, 0.0)
    time.sleep(seconds)
