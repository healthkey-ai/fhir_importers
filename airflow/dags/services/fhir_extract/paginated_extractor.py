"""Paginated FHIR Bundle fetch.

The fallback path when an institution doesn't support `$export` bulk
extraction. Calls `Patient/{fhir_patient_id}/$everything` (or an
equivalent operation), follows `link.relation = 'next'` until the chain
ends, and stitches all entries into a single Bundle.

Returns a dict in the FHIR Bundle shape that `FhirParsingService` already
consumes — so the downstream `fhir_ingest` task needs no changes.
"""
from __future__ import annotations

import logging
from typing import Any

import requests

from entities.fhir.institution import Institution
from services.fhir_extract.retry_backoff import with_retry

_logger = logging.getLogger(__name__)


def fetch_patient_everything(
    *,
    institution: Institution,
    fhir_patient_id: str,
    access_token: str,
    since: str | None = None,
) -> dict[str, Any]:
    """Pull the patient's full record via `$everything` and stitch all pages.

    Args:
        institution: source EHR config.
        fhir_patient_id: institution-scoped FHIR id (from
            `fhir_connection.fhir_patient_id`).
        access_token: plaintext bearer token (from SmartTokenRefresher).
        since: optional ISO-8601 timestamp for incremental sync — passed
            as `_since=` per FHIR spec. None → full pull.
    """
    base = institution.fhir_base.rstrip("/")
    url: str | None = f"{base}/Patient/{fhir_patient_id}/$everything"
    params: dict[str, str] | None = {"_since": since} if since else None

    accumulated_entries: list[dict[str, Any]] = []
    total: int | None = None
    bundle_type: str = "collection"
    page = 0

    while url is not None:
        page += 1
        _logger.info(
            "[%s] $everything page %d for patient=%s url=%s",
            institution.slug, page, fhir_patient_id, url,
        )
        response = with_retry(
            institution,
            lambda u=url, p=params: requests.get(
                u,
                params=p,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/fhir+json",
                },
                timeout=30,
            ),
        )
        if not response.ok:
            raise RuntimeError(
                f"[{institution.slug}] $everything failed page={page} "
                f"status={response.status_code}: {response.text[:500]}"
            )
        body = response.json()
        bundle_type = body.get("type", bundle_type)
        if total is None and "total" in body:
            total = body["total"]
        for entry in body.get("entry") or []:
            accumulated_entries.append(entry)

        # Find a `next` link, if any. After the first page, drop `params`
        # since the next-link is fully formed.
        url = _next_link(body.get("link"))
        params = None

    return {
        "resourceType": "Bundle",
        "type": bundle_type,
        "total": total if total is not None else len(accumulated_entries),
        "entry": accumulated_entries,
    }


def _next_link(links: list[dict[str, Any]] | None) -> str | None:
    for link in links or []:
        if isinstance(link, dict) and link.get("relation") == "next" and link.get("url"):
            return link["url"]
    return None
