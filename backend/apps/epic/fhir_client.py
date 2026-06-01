"""Read FHIR resources from an Epic FHIR server using a patient's access token.

Phase 3: pulls the patient compartment via Patient/$everything and follows
Bundle pagination. The resulting collection Bundle is posted to ctomop's
/api/fhir/sync/ (which picks out the first-cut resource types).
"""
import logging

import httpx

logger = logging.getLogger(__name__)

# Safety bounds so a misbehaving server can't make us loop or post forever.
MAX_PAGES = 20
MAX_ENTRIES = 1000  # ctomop rejects bundles larger than this


class EpicFhirError(Exception):
    pass


def _next_link(bundle: dict) -> str | None:
    for link in bundle.get("link", []) or []:
        if link.get("relation") == "next" and link.get("url"):
            return link["url"]
    return None


class EpicFhirClient:
    def __init__(self, http: httpx.Client, access_token: str):
        self._http = http
        self._access_token = access_token

    def _get(self, url: str) -> dict:
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/fhir+json",
        }
        resp = self._http.get(url, headers=headers)
        if resp.status_code >= 400:
            logger.error("Epic FHIR GET failed: %s %s", resp.status_code, resp.text[:500])
            raise EpicFhirError(f"Epic FHIR returned {resp.status_code} for {url}")
        return resp.json()

    def fetch_patient_everything(self, fhir_base: str, patient_id: str) -> dict:
        """GET Patient/{id}/$everything, following pagination into one Bundle."""
        if not patient_id:
            raise EpicFhirError("No Epic patient id on the connection (SMART launch context missing).")

        url = f"{fhir_base.rstrip('/')}/Patient/{patient_id}/$everything"
        entries: list = []
        pages = 0
        while url and pages < MAX_PAGES and len(entries) < MAX_ENTRIES:
            page = self._get(url)
            entries.extend(page.get("entry", []) or [])
            url = _next_link(page)
            pages += 1

        if url:
            logger.warning(
                "Epic $everything truncated at %d entries / %d pages for patient %s",
                len(entries), pages, patient_id,
            )

        return {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": entries[:MAX_ENTRIES],
        }
