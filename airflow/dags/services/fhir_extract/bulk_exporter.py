"""FHIR Bulk Data API ($export) — initiate, poll, download.

Spec: https://hl7.org/fhir/uv/bulkdata/

Flow:
  1. Client GETs `<base>/Patient/{id}/$export` with
       Accept: application/fhir+json
       Prefer: respond-async
     and optional `_type=` / `_since=` query params.
  2. Server returns 202 Accepted with `Content-Location: <status-url>`.
  3. Client polls the status URL. While in-progress, server returns 202
     with optional `X-Progress` / `Retry-After`. When done, server returns
     200 with a JSON manifest listing `output[]` URLs (one per resource type).
  4. Client downloads each `output[].url` (NDJSON) using the same bearer
     token and stitches the resources into a single FHIR Bundle dict.

For initial implementation each operation is a separate function so the
DAG can sequence them as Airflow tasks. The poll loop is synchronous
within the polling task — fine for typical EHR durations (seconds to a
few minutes). For Epic-scale exports (>1h), switch to an Airflow
deferrable operator. TODO marker on `poll_until_complete`.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from entities.fhir.institution import Institution
from services.fhir_extract.retry_backoff import with_retry

_logger = logging.getLogger(__name__)

_DEFAULT_POLL_MIN_INTERVAL = 5      # seconds; lower bound on inter-poll sleep
_DEFAULT_POLL_MAX_INTERVAL = 120    # seconds; upper bound (ignored if Retry-After is larger)
_DEFAULT_POLL_TIMEOUT = 60 * 60     # 1 hour; abort if not complete by then


class BulkExportError(Exception):
    pass


class BulkExportTimeout(BulkExportError):
    pass


def initiate_export(
    *,
    institution: Institution,
    fhir_patient_id: str,
    access_token: str,
    since: str | None = None,
    resource_types: list[str] | None = None,
) -> str:
    """Kick off `Patient/{id}/$export` and return the status URL.

    The status URL is the value of the `Content-Location` response header
    that Bulk Data servers return on 202 Accepted. Pass it to
    `poll_until_complete`.
    """
    base = institution.fhir_base.rstrip("/")
    url = f"{base}/Patient/{fhir_patient_id}/$export"
    params: dict[str, str] = {}
    if since:
        params["_since"] = since
    if resource_types:
        params["_type"] = ",".join(resource_types)

    response = with_retry(
        institution,
        lambda: requests.get(
            url,
            params=params or None,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/fhir+json",
                "Prefer": "respond-async",
            },
            timeout=30,
        ),
    )
    if response.status_code != 202:
        raise BulkExportError(
            f"[{institution.slug}] $export expected 202, got {response.status_code}: "
            f"{response.text[:500]}"
        )

    status_url = response.headers.get("Content-Location")
    if not status_url:
        raise BulkExportError(
            f"[{institution.slug}] $export 202 response missing Content-Location header"
        )
    _logger.info("[%s] $export initiated; status_url=%s", institution.slug, status_url)
    return status_url


def poll_until_complete(
    *,
    institution: Institution,
    status_url: str,
    access_token: str,
    poll_timeout_seconds: int = _DEFAULT_POLL_TIMEOUT,
    min_interval: int = _DEFAULT_POLL_MIN_INTERVAL,
    max_interval: int = _DEFAULT_POLL_MAX_INTERVAL,
) -> dict[str, Any]:
    """Poll the bulk-export status URL until the server returns the manifest.

    TODO(performance): convert to an Airflow deferrable operator so workers
    aren't blocked across long Epic exports. Synchronous-loop is fine for
    typical sandbox runs.

    Returns the JSON manifest body. Raises:
      - BulkExportTimeout if poll_timeout_seconds elapses
      - BulkExportError on a non-2xx status
    """
    deadline = time.monotonic() + poll_timeout_seconds
    interval = min_interval
    attempt = 0

    while True:
        attempt += 1
        if time.monotonic() > deadline:
            raise BulkExportTimeout(
                f"[{institution.slug}] bulk export not complete after "
                f"{poll_timeout_seconds}s (status_url={status_url})"
            )
        response = with_retry(
            institution,
            lambda: requests.get(
                status_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
                timeout=30,
            ),
        )

        if response.status_code == 200:
            manifest = response.json()
            _logger.info(
                "[%s] bulk export complete: %d output files, %d errors",
                institution.slug,
                len(manifest.get("output") or []),
                len(manifest.get("error") or []),
            )
            return manifest

        if response.status_code == 202:
            progress = response.headers.get("X-Progress", "in-progress")
            retry_after = response.headers.get("Retry-After")
            wait = interval
            if retry_after:
                try:
                    wait = max(int(retry_after), min_interval)
                except ValueError:
                    pass
            _logger.info(
                "[%s] attempt %d: status=202 progress=%r sleeping=%ds",
                institution.slug, attempt, progress, wait,
            )
            time.sleep(wait)
            interval = min(interval * 2, max_interval)
            continue

        raise BulkExportError(
            f"[{institution.slug}] poll {status_url} returned "
            f"{response.status_code}: {response.text[:500]}"
        )


def download_manifest_as_bundle(
    *,
    institution: Institution,
    manifest: dict[str, Any],
    access_token: str,
) -> dict[str, Any]:
    """Download every NDJSON file in `manifest['output']` and stitch the
    resources into a single FHIR Bundle dict.

    The bundle shape matches what `FhirParsingService.ingest_from_bundle`
    expects, so the downstream ingest task needs no special handling for
    the bulk path.
    """
    entries: list[dict[str, Any]] = []
    output_files = manifest.get("output") or []
    _logger.info(
        "[%s] downloading %d NDJSON files from manifest",
        institution.slug, len(output_files),
    )
    for file_descriptor in output_files:
        url = file_descriptor.get("url")
        resource_type = file_descriptor.get("type")
        if not url:
            _logger.warning("[%s] manifest entry missing url: %r", institution.slug, file_descriptor)
            continue
        response = with_retry(
            institution,
            lambda u=url: requests.get(
                u,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/fhir+ndjson",
                },
                timeout=120,
                stream=True,
            ),
        )
        if not response.ok:
            raise BulkExportError(
                f"[{institution.slug}] NDJSON download failed {url} "
                f"status={response.status_code}: {response.text[:300]}"
            )
        # NDJSON: one FHIR resource per line.
        count_before = len(entries)
        for line in response.iter_lines():
            if not line:
                continue
            import json  # local import to keep top-level imports lean
            try:
                resource = json.loads(line)
            except json.JSONDecodeError as e:
                _logger.warning(
                    "[%s] malformed NDJSON line in %s: %s", institution.slug, url, e,
                )
                continue
            entries.append({"resource": resource})
        _logger.info(
            "[%s] downloaded %s: %d resources",
            institution.slug, resource_type, len(entries) - count_before,
        )

    errors = manifest.get("error") or []
    if errors:
        _logger.warning(
            "[%s] manifest reports %d server-side errors; details: %s",
            institution.slug, len(errors), errors[:3],
        )

    return {
        "resourceType": "Bundle",
        "type": "collection",
        "total": len(entries),
        "entry": entries,
    }
