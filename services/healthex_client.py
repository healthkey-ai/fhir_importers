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

    async def find_patient_id_by_external_id(self, external_id: str) -> str | None:
        """Resolve externalId → patientId via getPatientConsents.

        Returns the patientId from the first OPTED_IN
        PATIENT_DIRECTED_DATA_EXCHANGE consent record; None if the patient
        hasn't consented yet or doesn't exist on HealthEx's side yet.
        HealthEx-side eventual consistency can lag the UI by tens of seconds.
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
        # 400 "Patient not found for provided externalId" is HealthEx's signal
        # that no patient row exists yet for this externalId — treat as pending.
        if r.status_code == 400 and "Patient not found" in r.text:
            return None
        if r.status_code >= 400:
            raise HealthExError(f"GET {url} returned {r.status_code}: {r.text[:200]}")
        try:
            data = r.json()
        except ValueError as exc:
            raise HealthExError(f"GET {url} returned non-JSON body") from exc
        for entry in data.get("results", []) or []:
            cr = (entry or {}).get("consentRecord") or {}
            if (cr.get("consentType") == "PATIENT_DIRECTED_DATA_EXCHANGE"
                    and cr.get("consentStatus") == "OPTED_IN"
                    and cr.get("patientId")):
                return cr["patientId"]
        return None

    async def get_demographics(self, patient_id: str) -> dict:
        return await self._get_json(
            f"/v1/projects/{self.project_id}/patients/{patient_id}/demographics",
        )

    async def get_data_retrieval_status(self, patient_id: str) -> HealthExDataStatus:
        data = await self._get_json(
            f"/v1/projects/{self.project_id}/patients/{patient_id}/data-retrieval-status",
        )
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
    ) -> dict:
        """GET /FHIR/R4/Person/{patient_id}/$everything → Bundle dict."""
        url = f"{self._base}/FHIR/R4/Person/{patient_id}/$everything"
        params = {"_since": since} if since else None
        headers = (await self._auth_headers_json()) | {"Accept": "application/fhir+json"}
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


def _decode_jwt(token: str) -> dict:
    _, payload_b64, _ = token.split(".")
    payload_b64 += "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64))
