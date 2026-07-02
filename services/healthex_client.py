import asyncio
import base64
import json
import logging
import time
from dataclasses import dataclass

import httpx


_logger = logging.getLogger(__name__)

# Refresh this many seconds before server-reported expiry so a handed-out
# token has useful in-flight lifetime.
_TOKEN_EXPIRY_SKEW_SECONDS = 60


@dataclass(frozen=True)
class HealthExConsentState:
    """Snapshot of one externalId's PATIENT_DIRECTED_DATA_EXCHANGE consent
    within our project. Distinguishes three cases that
    `find_patient_id_by_external_id` used to collapse to `None`:

    - `patient_id is not None`: HealthEx has an OPTED_IN record for us.
    - `patient_id is None, known_by_healthex is True`: they know this
      externalId but the PATIENT_DIRECTED_DATA_EXCHANGE consent is not
      currently OPTED_IN — treat as REVOKED. This is the state Diego's
      question about "user deletes on HealthEx UI" surfaces.
    - `patient_id is None, known_by_healthex is False`: HealthEx has no
      record at all — still pending.
    """
    patient_id: str | None
    known_by_healthex: bool


@dataclass(frozen=True)
class HealthExDataStatus:
    overall_status: str
    vectorization_status: str | None
    updated_at: str | None


class HealthExError(Exception):
    """Outbound call to HealthEx failed (network, non-2xx, malformed body)."""


class HealthExClient:
    """Async HTTP adapter for HealthEx — single source of protocol knowledge.

    Every URL, request body, response shape lives in this class. Delivery
    layers (FastAPI endpoints, CLI commands) call typed methods and never
    construct URLs or parse responses themselves.

    One project per client instance; pass `project_id` at construction so
    callers don't repeat it on every method call.
    """

    def __init__(
        self,
        *,
        http: httpx.AsyncClient,
        base_url: str,
        project_id: str,
        api_key: str,
        api_secret: str,
    ) -> None:
        self._http = http
        self._base = base_url.rstrip("/")
        self.project_id = project_id
        self._api_key = api_key
        self._api_secret = api_secret
        self._cached_token: str | None = None
        self._cached_until: float = 0.0
        self._refresh_lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Identity                                                           #
    # ------------------------------------------------------------------ #

    async def org_jwt(self) -> str:
        """Raw org JWT bearer token."""
        return await self._access_token()

    async def jwt_claims(self) -> dict:
        return _decode_jwt(await self._access_token())

    async def org_id(self) -> str:
        return (await self.jwt_claims())["organizationId"]

    # ------------------------------------------------------------------ #
    # Patient onboarding                                                 #
    # ------------------------------------------------------------------ #

    async def add_patient(
        self, *,
        external_id: str,
        email: str,
        first_name: str = "Test",
        last_name: str = "User",
        language: str = "en",
        contact_pref: str = "email",
        suppress_notifications: bool = True,
    ) -> dict:
        """Register a Recruitment for a single patient (addPatients batch with N=1).

        Required before minting a Unique Link — without an addPatients call
        the patient-side `link-identified-patient` step returns 404 "Recruitment
        not found" (empirically verified; contradicts the public docs).
        """
        body = {
            "patients": [{
                "externalId": external_id,
                "email": email,
                "firstName": first_name,
                "lastName": last_name,
                "languagePreference": language,
                "contactPreference": contact_pref,
            }],
            "suppressNotifications": suppress_notifications,
        }
        return await self._post_json(
            f"/v1/projects/{self.project_id}/patients", body,
        )

    async def get_unique_link(self, external_id: str | None = None) -> str:
        """Mint a Unique (or generic, if external_id is None) consent link.

        Response body is the raw URL as text/html — signature on the `xid`
        query param is server-generated and must not be forged.
        """
        url = f"{self._base}/v1/projects/{self.project_id}/link"
        body = {"externalId": external_id} if external_id else {}
        try:
            r = await self._http.post(url, json=body, headers=await self._auth_headers_json())
        except httpx.HTTPError as exc:
            raise HealthExError(f"POST {url}: {exc}") from exc
        if r.status_code not in (200, 201):
            raise HealthExError(f"POST {url} returned {r.status_code}: {r.text[:200]}")
        link = r.text.strip()
        if not link.startswith("http"):
            raise HealthExError(f"POST {url} returned unexpected body: {link[:200]!r}")
        return link

    async def get_consent_state(self, external_id: str) -> HealthExConsentState:
        """Fetch this externalId's consent snapshot via getPatientConsents.

        Docs: https://docs.healthex.io/consent-examples/find-all-studies-patient-consented-to
        See HealthExConsentState for the three cases this call distinguishes.
        """
        url = f"{self._base}/v1/patients/consents"
        headers = await self._auth_headers_json()
        headers.pop("Content-Type", None)
        try:
            r = await self._http.get(
                url,
                params={"externalId": external_id, "projectId": self.project_id},
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise HealthExError(f"GET {url}: {exc}") from exc
        # HealthEx signals "no patient row for this externalId yet" with a 400
        # whose body is a short message. Treat any 400 with a short text body as
        # pending-consent — vendor wording has changed before. Log if the
        # message doesn't contain "patient not found" so a real vendor breakage
        # (different error type behind the same status) is observable instead
        # of silently coerced to unknown.
        if r.status_code == 400 and len(r.text) < 256:
            if "patient not found" not in r.text.lower():
                _logger.warning(
                    "HealthEx getPatientConsents 400 with unfamiliar body "
                    "(treating as pending): %s",
                    r.text[:200],
                )
            return HealthExConsentState(patient_id=None, known_by_healthex=False)
        if r.status_code >= 400:
            raise HealthExError(f"GET {url} returned {r.status_code}: {r.text[:200]}")
        try:
            data = r.json()
        except ValueError as exc:
            raise HealthExError(f"GET {url} returned non-JSON body") from exc
        # Walk PATIENT_DIRECTED_DATA_EXCHANGE records. If any is OPTED_IN we
        # take its patientId; otherwise any presence of the record type means
        # HealthEx knows this externalId but they've opted out (revoked).
        known = False
        for entry in data.get("results", []) or []:
            cr = (entry or {}).get("consentRecord") or {}
            if cr.get("consentType") != "PATIENT_DIRECTED_DATA_EXCHANGE":
                continue
            known = True
            if (cr.get("consentStatus") == "OPTED_IN"
                    and cr.get("patientId")):
                return HealthExConsentState(
                    patient_id=cr["patientId"], known_by_healthex=True,
                )
        return HealthExConsentState(patient_id=None, known_by_healthex=known)

    async def get_demographics(self, patient_id: str) -> dict:
        return await self._get_json(
            f"/v1/projects/{self.project_id}/patients/{patient_id}/demographics",
        )

    async def get_data_retrieval_status(
        self, patient_id: str,
    ) -> HealthExDataStatus | None:
        """Fetch retrieval status for a consented patient.

        Returns None if HealthEx has no org-scoped status endpoint for us to
        call. The documented `/v1/patients/data-retrieval/status` endpoint
        requires a PATIENT JWT (it's for the patient-side portal to poll its
        own status), and the org-scoped variant we tried
        (`/v1/projects/{pid}/patients/{pid}/data-retrieval-status`) returns
        404 in production — no such route. Until HealthEx confirms an
        org-side endpoint, callers must treat `None` as "status unknown, keep
        current state" rather than propagating an error.
        """
        url = f"{self._base}/v1/projects/{self.project_id}/patients/{patient_id}/data-retrieval-status"
        headers = await self._auth_headers_json()
        headers.pop("Content-Type", None)
        try:
            r = await self._http.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise HealthExError(f"GET {url}: {exc}") from exc
        if r.status_code == 404:
            # Log once per call so a future doc/endpoint change is visible.
            _logger.debug(
                "HealthEx data-retrieval-status 404 (endpoint not exposed "
                "for org JWT) — treating as unknown",
            )
            return None
        if r.status_code >= 400:
            raise HealthExError(
                f"GET {url} returned {r.status_code}: {r.text[:200]}",
            )
        try:
            data = r.json()
        except ValueError as exc:
            raise HealthExError(f"GET {url} returned non-JSON body") from exc
        return HealthExDataStatus(
            overall_status=data.get("dataRetrievalStatus", "UNKNOWN"),
            vectorization_status=data.get("vectorizationStatus"),
            updated_at=data.get("updatedAt"),
        )

    # ------------------------------------------------------------------ #
    # FHIR R4 surface                                                    #
    # ------------------------------------------------------------------ #

    async def pull_everything(
        self, patient_id: str, *, since: str | None = None,
        max_pages: int = 50,
    ) -> dict:
        """GET /FHIR/R4/Person/{patient_id}/$everything → Bundle dict.

        Follows FHIR pagination via `Bundle.link[relation="next"]` per
        https://www.hl7.org/fhir/http.html#paging. All pages' entries are
        merged into a single returned Bundle; per-page timing, size, and
        entry counts are logged at INFO. `max_pages` is a safety net — we
        haven't seen HealthEx paginate in practice, but a runaway follow-
        loop would be worse than a truncated fetch.

        Heavy logging is intentional while we learn `$everything` semantics
        empirically (HealthEx docs don't specify whether a 200 body means
        retrieval is complete or can return partials mid-retrieval — the
        response is what we compare against on subsequent pulls).
        """
        start_ts = time.time()
        first_url = f"{self._base}/FHIR/R4/Person/{patient_id}/$everything"
        params: dict | None = {"_since": since} if since else None
        headers = (await self._auth_headers_json()) | {"Accept": "application/fhir+json"}

        _logger.info(
            "healthex.pull_everything.start patient=%s since=%s url=%s",
            patient_id, since or "-", first_url,
        )

        merged_entries: list = []
        page_stats: list[tuple[int, int, int]] = []  # (page_idx, entries, bytes)
        page_url: str | None = first_url
        page_params: dict | None = params
        first_bundle: dict | None = None

        for page_idx in range(max_pages):
            page_start = time.time()
            try:
                r = await self._http.get(
                    page_url, params=page_params, headers=headers,
                )
            except httpx.HTTPError as exc:
                _logger.exception(
                    "healthex.pull_everything.http_error page=%s url=%s",
                    page_idx, page_url,
                )
                raise HealthExError(f"GET {page_url}: {exc}") from exc

            elapsed_ms = int((time.time() - page_start) * 1000)
            body_bytes = len(r.content or b"")
            _logger.info(
                "healthex.pull_everything.page page=%s status=%s "
                "bytes=%s elapsed_ms=%s content_type=%s",
                page_idx, r.status_code, body_bytes, elapsed_ms,
                r.headers.get("content-type", "-"),
            )

            if r.status_code >= 400:
                _logger.warning(
                    "healthex.pull_everything.bad_status page=%s status=%s body=%s",
                    page_idx, r.status_code, r.text[:500],
                )
                raise HealthExError(
                    f"GET {page_url} returned {r.status_code}: {r.text[:200]}",
                )

            try:
                bundle = r.json()
            except ValueError as exc:
                raise HealthExError(
                    f"GET {page_url} returned non-JSON body",
                ) from exc

            entries = bundle.get("entry") or []
            page_stats.append((page_idx, len(entries), body_bytes))
            merged_entries.extend(entries)
            if first_bundle is None:
                first_bundle = bundle

            # Log resource-type breakdown for this page so we can spot
            # whether HealthEx trickles data across pages (partial retrieval
            # mid-stream) or delivers each resource type in one go.
            type_counts: dict[str, int] = {}
            for e in entries:
                rt = ((e or {}).get("resource") or {}).get("resourceType", "?")
                type_counts[rt] = type_counts.get(rt, 0) + 1
            _logger.info(
                "healthex.pull_everything.page_types page=%s counts=%s",
                page_idx, type_counts,
            )

            next_url = _next_link(bundle)
            if not next_url:
                break
            _logger.info(
                "healthex.pull_everything.follow_next page=%s next=%s",
                page_idx, next_url,
            )
            page_url = next_url
            page_params = None  # next-link URL already has params baked in.
        else:
            _logger.warning(
                "healthex.pull_everything.max_pages_reached patient=%s "
                "pages=%s — truncating; next link was still present",
                patient_id, max_pages,
            )

        total_ms = int((time.time() - start_ts) * 1000)
        _logger.info(
            "healthex.pull_everything.done patient=%s pages=%s "
            "total_entries=%s total_ms=%s",
            patient_id, len(page_stats), len(merged_entries), total_ms,
        )

        # Return a single Bundle: keep the first bundle's top-level fields
        # (id, meta, type, timestamp) and swap in the merged entry list.
        # Drop pagination `link` array since it applied to the first page only.
        result = dict(first_bundle or {"resourceType": "Bundle", "type": "searchset"})
        result["entry"] = merged_entries
        result.pop("link", None)
        # Attach a private diagnostic field so callers can surface counts
        # without re-scanning entries. Underscore-prefixed to signal it's
        # non-FHIR metadata added by us.
        result["_healthkey_pull_stats"] = {
            "pages": len(page_stats),
            "total_entries": len(merged_entries),
            "total_bytes": sum(b for _, _, b in page_stats),
            "duration_ms": total_ms,
            "since": since,
            "truncated": len(page_stats) >= max_pages,
        }
        return result

    async def get_capability_statement(self) -> dict:
        """GET /FHIR/R4/metadata → CapabilityStatement dict."""
        url = f"{self._base}/FHIR/R4/metadata"
        headers = (await self._auth_headers_json()) | {"Accept": "application/fhir+json"}
        try:
            r = await self._http.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise HealthExError(f"GET {url}: {exc}") from exc
        if r.status_code >= 400:
            raise HealthExError(f"GET {url} returned {r.status_code}: {r.text[:200]}")
        return r.json()

    # ------------------------------------------------------------------ #
    # Test patients                                                      #
    # ------------------------------------------------------------------ #

    async def create_test_patient(
        self, *,
        first_name: str = "Test",
        last_name: str = "Patient",
        date_of_birth: str = "1990-01-15",
    ) -> dict:
        """Create a synthetic test patient (auto-generated email + password).

        The password is in the response and only returned at creation; caller
        is responsible for capturing it before the response is discarded.
        """
        org = await self.org_id()
        return await self._post_json(
            f"/v1/organizations/{org}/test-patients",
            {"firstName": first_name, "lastName": last_name, "dateOfBirth": date_of_birth},
        )

    async def list_test_patients(self) -> list[dict]:
        org = await self.org_id()
        data = await self._get_json(f"/v1/organizations/{org}/test-patients")
        if not isinstance(data, list):
            raise HealthExError(f"unexpected test-patient list body: {data!r}")
        return data

    async def delete_test_patient(self, patient_id: str) -> None:
        org = await self.org_id()
        url = f"{self._base}/v1/organizations/{org}/test-patients/{patient_id}"
        try:
            r = await self._http.delete(url, headers=await self._auth_headers_json())
        except httpx.HTTPError as exc:
            raise HealthExError(f"DELETE {url}: {exc}") from exc
        if r.status_code >= 400:
            raise HealthExError(f"DELETE {url} returned {r.status_code}: {r.text[:200]}")

    # ------------------------------------------------------------------ #
    # Token cache + low-level HTTP helpers                               #
    # ------------------------------------------------------------------ #

    async def _access_token(self) -> str:
        if self._cached_token and time.time() < self._cached_until:
            return self._cached_token
        async with self._refresh_lock:
            if self._cached_token and time.time() < self._cached_until:
                return self._cached_token
            return await self._fetch_token()

    async def _fetch_token(self) -> str:
        url = f"{self._base}/v1/auth/token"
        body = {"apiKey": self._api_key, "apiSecret": self._api_secret}
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        try:
            r = await self._http.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise HealthExError(f"POST {url}: {exc}") from exc
        # HealthEx returns 201 on token mint (verified on live API).
        if r.status_code not in (200, 201):
            raise HealthExError(f"POST {url} returned {r.status_code}: {r.text[:200]}")
        try:
            data = r.json()
        except ValueError as exc:
            raise HealthExError(f"POST {url} returned non-JSON body") from exc
        token = data.get("token")
        if not token:
            raise HealthExError(f"POST {url} response missing token: {data!r}")
        # `expiration` is an absolute Unix epoch (seconds), not a relative TTL.
        expiration = data.get("expiration")
        if expiration is None:
            self._cached_until = time.time() + (23 * 3600) - _TOKEN_EXPIRY_SKEW_SECONDS
        else:
            self._cached_until = float(expiration) - _TOKEN_EXPIRY_SKEW_SECONDS
        self._cached_token = token
        _logger.info(
            "HealthEx token refreshed (valid for %ds)",
            int(self._cached_until - time.time()),
        )
        return token

    async def _auth_headers_json(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {await self._access_token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _get_json(self, path: str, *, params: dict | None = None) -> dict:
        url = f"{self._base}{path}"
        headers = await self._auth_headers_json()
        headers.pop("Content-Type", None)
        try:
            r = await self._http.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise HealthExError(f"GET {url}: {exc}") from exc
        if r.status_code >= 400:
            raise HealthExError(f"GET {url} returned {r.status_code}: {r.text[:200]}")
        try:
            return r.json()
        except ValueError as exc:
            raise HealthExError(f"GET {url} returned non-JSON body") from exc

    async def _post_json(self, path: str, body: dict) -> dict:
        url = f"{self._base}{path}"
        try:
            r = await self._http.post(url, json=body, headers=await self._auth_headers_json())
        except httpx.HTTPError as exc:
            raise HealthExError(f"POST {url}: {exc}") from exc
        if r.status_code >= 400:
            raise HealthExError(f"POST {url} returned {r.status_code}: {r.text[:200]}")
        try:
            return r.json()
        except ValueError as exc:
            raise HealthExError(f"POST {url} returned non-JSON body") from exc


def _next_link(bundle: dict) -> str | None:
    """Return the next-page URL from a FHIR Bundle's `link` array, if any.

    Per https://www.hl7.org/fhir/http.html#paging the pagination link uses
    relation `next` and carries the absolute URL to the next page (including
    any bookmark params); callers should hit it directly without re-adding
    query params.
    """
    for entry in (bundle.get("link") or []):
        if (entry or {}).get("relation") == "next" and entry.get("url"):
            return entry["url"]
    return None


def _decode_jwt(token: str) -> dict:
    _, payload_b64, _ = token.split(".")
    payload_b64 += "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64))
