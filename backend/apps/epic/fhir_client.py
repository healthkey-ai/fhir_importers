"""Read FHIR resources from an Epic FHIR server using a patient's access token.

Epic does NOT implement Patient/$everything, so we fetch the patient compartment
with per-resource searches and assemble a collection Bundle for ctomop's
/api/fhir/sync/ (which picks out the first-cut resource types). Each search is
tolerant — a failure on one resource is logged and skipped so the rest still
sync.
"""
import logging
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

MAX_PAGES = 20        # pagination cap per resource search
MAX_TOTAL = 5000      # safety ceiling across the whole compartment

# Per-resource searches against the patient compartment. Epic requires a
# `category` for Observation; Condition/MedicationRequest accept `patient` alone.
_SEARCHES = [
    ("Observation", {"category": "laboratory"}),
    ("Observation", {"category": "vital-signs"}),
    ("Condition", {}),
    ("MedicationRequest", {}),
]


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
            logger.error("Epic FHIR GET failed: %s %s", resp.status_code, resp.text[:300])
            raise EpicFhirError(f"Epic FHIR returned {resp.status_code} for {url}")
        return resp.json()

    def _collect_search(self, url: str) -> list:
        """Run a search and follow pagination, returning resource entries."""
        entries: list = []
        pages = 0
        while url and pages < MAX_PAGES:
            bundle = self._get(url)
            for entry in bundle.get("entry", []) or []:
                res = (entry or {}).get("resource", {}) or {}
                # Skip search-mode OperationOutcome entries.
                if res.get("resourceType") and res.get("resourceType") != "OperationOutcome":
                    entries.append({"resource": res})
            url = _next_link(bundle)
            pages += 1
        return entries

    def fetch_patient_compartment(self, fhir_base: str, patient_id: str) -> dict:
        """Assemble the patient's resources into one collection Bundle.

        Each resource type gets its own search budget (MAX_PAGES), so a patient
        with many observations can't starve conditions/medications. The combined
        result is chunked before posting to ctomop (see tasks.run_sync).
        """
        if not patient_id:
            raise EpicFhirError("No Epic patient id on the connection (SMART launch context missing).")

        base = fhir_base.rstrip("/")
        entries: list = []

        # Patient demographics (read by id).
        try:
            patient = self._get(f"{base}/Patient/{patient_id}")
            if patient.get("resourceType") == "Patient":
                entries.append({"resource": patient})
        except EpicFhirError as exc:
            logger.warning("Patient read failed (skipped): %s", exc)

        # Per-resource searches — each independent so none starves the others.
        for resource, params in _SEARCHES:
            if len(entries) >= MAX_TOTAL:
                logger.warning("Compartment hit MAX_TOTAL=%d; remaining searches skipped", MAX_TOTAL)
                break
            query = urlencode({"patient": patient_id, **params})
            url = f"{base}/{resource}?{query}"
            try:
                entries.extend(self._collect_search(url))
            except EpicFhirError as exc:
                logger.warning("%s search failed (skipped): %s", resource, exc)

        return {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": entries[:MAX_TOTAL],
        }
